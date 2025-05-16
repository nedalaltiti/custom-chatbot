"""
Document processing and chunking module for RAG pipeline.

This module handles the processing of documents (PDF, text, etc.) into chunks
suitable for embedding and semantic search. It includes:
1. Document loading from various formats
2. Text extraction with proper handling of document structure 
3. Chunking strategies with configurable overlap
4. Metadata preservation for proper source attribution
"""

import os
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import pdfplumber

from hrbot.core.document import Document

from hrbot.infrastructure.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Global vector store instance for caching
_vector_store: Optional[VectorStore] = None

def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

async def process_document(file_path: str) -> List[Document]:
    """
    Process a document into chunks with metadata.
    
    Args:
        file_path: Path to the document file
        
    Returns:
        List of Document objects with text chunks and metadata
    """
    try:
        # Extract text based on file type
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return []
            
        file_extension = file_path_obj.suffix.lower()
        file_name = file_path_obj.name
        
        text = ""
        if file_extension == ".pdf":
            text = extract_text_from_pdf(file_path)
        elif file_extension == ".docx":
            text = extract_text_from_docx(file_path)
        elif file_extension in [".txt", ".md", ".csv"]:
            text = extract_text_from_text_file(file_path)
        else:
            logger.warning(f"Unsupported file type: {file_extension}")
            return []
            
        if not text:
            logger.warning(f"No text extracted from {file_path}")
            return []
            
        # Create metadata
        metadata = {
            "source": file_name,
            "file_path": str(file_path),
            "file_type": file_extension,
            "processed_at": datetime.now().isoformat()
        }
        
        # Chunk the text
        chunks = chunk_text(text, metadata)
        
        logger.info(f"Processed document {file_name} into {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        logger.error(f"Error processing document {file_path}: {str(e)}")
        return []

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text:
                    # Add page number to help with context
                    pages.append(f"Page {i+1}:\n{page_text}")
            
            return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"Error extracting text from PDF {file_path}: {str(e)}")
        return ""

def extract_text_from_docx(file_path: str) -> str:
    """
    Extract text from a DOCX file using built-in Python libraries.
    
    Args:
        file_path: Path to the DOCX file
        
    Returns:
        Extracted text as a string
    """
    try:
        # DOCX files are essentially ZIP files with XML content
        import zipfile
        import xml.etree.ElementTree as ET
        from xml.dom import minidom
        
        text_content = []
        
        # Open the docx file as a zip
        with zipfile.ZipFile(file_path) as docx_zip:
            # Check if the main document.xml exists (it should in a valid DOCX)
            if "word/document.xml" in docx_zip.namelist():
                # Extract the XML content
                xml_content = docx_zip.read("word/document.xml")
                
                # Parse the XML content
                try:
                    # Try using ElementTree first
                    root = ET.fromstring(xml_content)
                    
                    # Define the namespace (standard for DOCX files)
                    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                    
                    # Find all text elements
                    for paragraph in root.findall(f".//{namespace}p"):
                        texts = paragraph.findall(f".//{namespace}t")
                        paragraph_text = "".join(text.text for text in texts if text.text)
                        if paragraph_text:
                            text_content.append(paragraph_text)
                
                except:
                    # Fallback to minidom if ElementTree fails
                    dom = minidom.parseString(xml_content)
                    text_nodes = dom.getElementsByTagName("w:t")
                    for text_node in text_nodes:
                        if text_node.firstChild and text_node.firstChild.nodeValue:
                            text_content.append(text_node.firstChild.nodeValue)
            
            # Also try to extract from headers, footers, etc.
            for item in docx_zip.namelist():
                if item.startswith("word/") and item.endswith(".xml") and "document.xml" not in item:
                    try:
                        xml_content = docx_zip.read(item)
                        dom = minidom.parseString(xml_content)
                        text_nodes = dom.getElementsByTagName("w:t")
                        for text_node in text_nodes:
                            if text_node.firstChild and text_node.firstChild.nodeValue:
                                text_content.append(text_node.firstChild.nodeValue)
                    except:
                        # Skip any problematic files
                        continue
        
        # Join all the text with proper spacing
        if text_content:
            # Clean up text with basic spacing
            result = "\n".join(text_content)
            # Remove duplicate newlines
            result = re.sub(r'\n+', '\n\n', result)
            return result
        else:
            logger.warning(f"No text content extracted from DOCX file: {file_path}")
            return f"[No text content could be extracted from {Path(file_path).name}]"
            
    except Exception as e:
        logger.error(f"Error extracting text from DOCX {file_path}: {str(e)}")
        return f"[Error processing {Path(file_path).name}: {str(e)}]"

def extract_text_from_text_file(file_path: str) -> str:
    """
    Extract text from a plain text file.
    
    Args:
        file_path: Path to the text file
        
    Returns:
        Extracted text as a string
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with a different encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading text file with latin-1 encoding: {str(e)}")
            return ""
    except Exception as e:
        logger.error(f"Error extracting text from file {file_path}: {str(e)}")
        return ""

def chunk_text(text: str, metadata: Dict[str, Any], *, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    """
    Split text into overlapping chunks suitable for embedding.

    Args:
        text: The full text to chunk
        metadata: Metadata to attach to each chunk
        chunk_size: Maximum size of each chunk (characters)
        chunk_overlap: Overlap size between consecutive chunks

    Returns:
        List of Document objects
    """
    try:
        # Normalise whitespace
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []

        chunks: List[Document] = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = text[start:end]
            # Expand to nearest sentence boundary if possible
            if end < text_length:
                next_period = text.find('.', end)
                if 0 < next_period - end < 100:  # don't jump too far
                    end = next_period + 1
                    chunk_text = text[start:end]
            chunk_meta = metadata.copy()
            chunks.append(Document(page_content=chunk_text, metadata=chunk_meta))
            # move start forward
            start = end - chunk_overlap  # maintain overlap
            if start < 0:
                start = 0

        # Annotate chunk numbers
        total = len(chunks)
        for idx, c in enumerate(chunks, start=1):
            c.metadata["chunk"] = idx
            c.metadata["total_chunks"] = total
        return chunks

    except Exception as e:
        logger.error(f"Error chunking text: {str(e)}")
        return [Document(page_content=text, metadata=metadata)]

async def get_relevant_chunks(query: str, top_k: int = 5) -> List[Document]:
    """
    Get chunks relevant to a query using semantic search.
    
    Args:
        query: The search query
        top_k: Number of results to return
        
    Returns:
        List of Document objects with relevant text chunks
    """
    try:
        logger.info(f"[VECTOR DEBUG] Getting vector store for query: {query}")
        store = get_vector_store()
        
        logger.info(f"[VECTOR DEBUG] Vector store initialized: {store.initialized}")
        logger.info(f"[VECTOR DEBUG] Vector store has {len(store.documents)} documents")
        
        # Perform similarity search
        logger.info(f"[VECTOR DEBUG] Performing similarity search with top_k={top_k}")
        results = await store.similarity_search(query, top_k=top_k)
        
        logger.info(f"[VECTOR DEBUG] Found {len(results)} results")
        for i, doc in enumerate(results):
            source = doc.metadata.get("source", "Unknown")
            logger.info(f"[VECTOR DEBUG] Result {i+1}: Source={source}, Length={len(doc.page_content)}")
        
        return results
    except Exception as e:
        logger.error(f"[VECTOR DEBUG] Error getting relevant chunks: {str(e)}")
        return []

async def save_uploaded_file(file) -> str:
    """
    Save an uploaded file and process it into the knowledge base.
    
    Args:
        file: The uploaded file object
        
    Returns:
        File path where the document was saved
    """
    # Create knowledge directory if it doesn't exist
    os.makedirs("data/knowledge/", exist_ok=True)
    file_path = f"data/knowledge/{file.filename}"
    
    try:
        # Save the file
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        logger.info(f"Saved uploaded file to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving uploaded file: {str(e)}")
        raise

async def reload_knowledge_base() -> int:
    """
    Reload and re-chunk all documents in the knowledge base.
    
    Returns:
        Number of documents processed
    """
    try:
        knowledge_dir = Path("data/knowledge/")
        
        if not knowledge_dir.exists():
            logger.warning("Knowledge directory does not exist")
            return 0
            
        # Get vector store
        store = get_vector_store()
        
        # Clear existing collection
        await store.delete_collection()
        
        # Process each file
        file_count = 0
        total_chunks = 0
        
        for file_path in knowledge_dir.glob("*"):
            if file_path.is_file():
                chunks = await process_document(str(file_path))
                if chunks:
                    success = await store.add_documents(chunks)
                    if success:
                        file_count += 1
                        total_chunks += len(chunks)
        
        logger.info(f"Reloaded knowledge base: {file_count} files, {total_chunks} chunks")
        return file_count
    except Exception as e:
        logger.error(f"Error reloading knowledge base: {str(e)}")
        return 0