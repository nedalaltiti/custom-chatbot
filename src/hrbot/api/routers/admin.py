"""
Admin router for managing the HR Teams Bot.

This module provides endpoints for:
1. Document management (upload, list, delete)
2. Knowledge base management (reload, status)
3. System diagnostics
"""

import os
import json
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import List, Dict, Any
from pathlib import Path

from hrbot.core.chunking import save_uploaded_file, reload_knowledge_base, process_document
from hrbot.core.chunking import get_vector_store
from hrbot.core.rag import RAG
from hrbot.core.rag_adapter import LLMServiceAdapter
from hrbot.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload")
async def upload_doc(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Upload a document to the knowledge base.
    
    Args:
        file: The uploaded file
        background_tasks: Optional background tasks runner
        
    Returns:
        Status information about the upload
    """
    try:
        # Save the uploaded file
        file_path = await save_uploaded_file(file)
        
        # Process the document in the background or immediately
        if background_tasks:
            background_tasks.add_task(process_and_add_document, file_path)
            return {
                "status": "processing",
                "message": f"File {file.filename} uploaded and being processed in the background",
                "file_path": file_path
            }
        else:
            # Process immediately
            chunks = await process_document(file_path)
            if not chunks:
                raise HTTPException(status_code=400, detail="Failed to extract content from document")
                
            store = get_vector_store()
            success = await store.add_documents(chunks)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to add document to vector store")
                
            return {
                "status": "complete",
                "message": f"File {file.filename} uploaded and processed",
                "chunks": len(chunks),
                "file_path": file_path
            }
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading document: {str(e)}")

async def process_and_add_document(file_path: str):
    """
    Process a document and add it to the vector store (for background tasks).
    
    Args:
        file_path: Path to the document file
    """
    try:
        chunks = await process_document(file_path)
        if chunks:
            store = get_vector_store()
            await store.add_documents(chunks)
            logger.info(f"Background processing complete for {file_path}: {len(chunks)} chunks added")
        else:
            logger.error(f"No chunks extracted from {file_path}")
    except Exception as e:
        logger.error(f"Error in background document processing: {str(e)}")

@router.get("/docs")
async def list_docs():
    """
    List all documents in the knowledge base.
    
    Returns:
        List of files in the knowledge base
    """
    try:
        knowledge_dir = Path("data/knowledge/")
        if not knowledge_dir.exists():
            return {"files": []}
            
        # List files with metadata
        files = []
        for file_path in knowledge_dir.glob("*"):
            if file_path.is_file():
                # Get file stats
                stat = file_path.stat()
                files.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size_bytes": stat.st_size,
                    "last_modified": stat.st_mtime
                })
                
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")

@router.delete("/docs/{filename}")
async def delete_doc(filename: str):
    """
    Delete a document from the knowledge base.
    
    Args:
        filename: Name of the file to delete
        
    Returns:
        Status of the deletion
    """
    try:
        file_path = Path(f"data/knowledge/{filename}")
        
        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File {filename} not found")
            
        # Delete the file
        os.remove(file_path)
        
        # Reload knowledge base to update vector store
        await reload_knowledge_base()
        
        return {
            "status": "deleted",
            "message": f"File {filename} deleted and knowledge base reloaded"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")

@router.post("/knowledge/reload")
async def reload_kb():
    """
    Reload the entire knowledge base.
    
    Returns:
        Status of the reload operation
    """
    try:
        file_count = await reload_knowledge_base()
        return {
            "status": "reloaded",
            "message": "Knowledge base reloaded",
            "files_processed": file_count
        }
    except Exception as e:
        logger.error(f"Error reloading knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reloading knowledge base: {str(e)}")

@router.get("/knowledge/status")
async def knowledge_status():
    """
    Get status information about the knowledge base.
    
    Returns:
        Status information about the knowledge base
    """
    try:
        # Get vector store
        store = get_vector_store()
        
        # Count documents in knowledge directory
        knowledge_dir = Path("data/knowledge/")
        file_count = 0
        if knowledge_dir.exists():
            file_count = sum(1 for _ in knowledge_dir.glob("*") if _.is_file())
            
        # Get document count from vector store
        doc_count = len(store.documents) if hasattr(store, 'documents') else "Unknown"
        
        # Get vector store metadata
        collection_name = getattr(store, 'collection_name', "default")
        initialized = getattr(store, 'initialized', False)
        
        return {
            "status": "ok" if initialized else "error",
            "initialized": initialized,
            "collection_name": collection_name,
            "files_in_directory": file_count,
            "documents_in_store": doc_count
        }
    except Exception as e:
        logger.error(f"Error getting knowledge base status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting knowledge base status: {str(e)}")

@router.post("/test-rag")
async def test_rag(query: dict):
    """
    Test endpoint for RAG system.
    
    Args:
        query: Dictionary with "query" field
        
    Returns:
        RAG response
    """
    try:
        # Import here to avoid circular imports
        from hrbot.core.rag import RAG
        from hrbot.core.rag_adapter import LLMServiceAdapter
        from hrbot.services.gemini_service import GeminiService

        llm_adapter = LLMServiceAdapter(GeminiService())
        rag_service = RAG(llm_provider=llm_adapter)
        
        # Process query
        query_text = query.get("query", "")
        if not query_text:
            raise HTTPException(status_code=400, detail="Query is required")
            
        logger.info(f"Testing RAG with query: {query_text}")
        
        # Call RAG service
        result = await rag_service.query(query_text, user_id="admin-test", chat_history=None)
        
        if result.is_success():
            response_data = result.unwrap()
            return {
                "status": "success",
                "used_rag": True,
                "response": response_data["response"],
                "sources": response_data.get("sources", [])
            }
        else:
            return {
                "status": "error",
                "error": str(result.error)
            }
    except Exception as e:
        logger.error(f"Error testing RAG: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error testing RAG: {str(e)}")