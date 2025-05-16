"""
Enhanced document processing and chunking module for RAG pipeline.

This module offers improved handling of documents for the RAG system:
1. Advanced document loading from various formats with robust error handling
2. Intelligent text extraction with better document structure preservation
3. Multiple chunking strategies optimized for semantic retrieval
4. Rich metadata for precise source attribution and tracking
5. Seamless integration with the vector store subsystem
"""

import os
import logging
import re
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Callable, Tuple, Set
from datetime import datetime
import mimetypes

import pdfplumber

from hrbot.core.document import Document

from hrbot.infrastructure.vector_store import VectorStore
from hrbot.utils.error import DocumentError, ErrorCode, ErrorSeverity
from hrbot.utils.result import Result, Success, Error
from hrbot.config.settings import settings

logger = logging.getLogger(__name__)

# Global vector store instance for caching
_vector_store: Optional[VectorStore] = None

def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

# Supported file types and their MIME types
SUPPORTED_FORMATS = {
    # PDF files
    '.pdf': 'application/pdf',
    
    # Microsoft Office formats
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    
    # Text formats
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.json': 'application/json',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.xml': 'application/xml',
}

class ChunkingConfig:
    """Configuration parameters for document chunking."""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        use_token_based: bool = False,
        ensure_complete_sentences: bool = True,
        max_characters_per_doc: int = 1_000_000,  # Safety limit for extremely large docs
    ):
        """
        Initialize chunking configuration.
        
        Args:
            chunk_size: Target size of chunks in characters or tokens
            chunk_overlap: Overlap between chunks for context preservation
            use_token_based: Use token-based chunking instead of character-based
            ensure_complete_sentences: Try to break at sentence boundaries
            max_characters_per_doc: Maximum characters to process (for safety)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_token_based = use_token_based
        self.ensure_complete_sentences = ensure_complete_sentences
        self.max_characters_per_doc = max_characters_per_doc

    @classmethod
    def from_settings(cls) -> "ChunkingConfig":
        """Create configuration from application settings."""
        return cls(
            chunk_size=getattr(settings, "chunk_size", 1000),
            chunk_overlap=getattr(settings, "chunk_overlap", 200),
            use_token_based=getattr(settings, "use_token_chunking", False),
            ensure_complete_sentences=getattr(settings, "ensure_complete_sentences", True),
        )


async def process_document(file_path: str, config: Optional[ChunkingConfig] = None) -> List[Document]:
    """
    Process a document into chunks with metadata.
    
    Args:
        file_path: Path to the document file
        config: Optional chunking configuration
        
    Returns:
        List of Document objects with text chunks and metadata
    """
    try:
        # Use default config if not provided
        if config is None:
            config = ChunkingConfig.from_settings()
            
        # Extract text based on file type
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            raise DocumentError(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"File not found: {file_path}",
                severity=ErrorSeverity.ERROR
            )
            
        file_extension = file_path_obj.suffix.lower()
        file_name = file_path_obj.name
        
        # Check if file format is supported
        if file_extension not in SUPPORTED_FORMATS:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type not in SUPPORTED_FORMATS.values():
                raise DocumentError(
                    code=ErrorCode.UNSUPPORTED_FORMAT,
                    message=f"Unsupported file format: {file_extension}",
                    details={"file": file_path}
                )
        
        logger.info(f"Processing document: {file_path}")
        text = ""
        
        # Extract text based on file type
        try:
            if file_extension == ".pdf":
                text = extract_text_from_pdf(file_path)
            elif file_extension in [".doc", ".docx"]:
                text = extract_text_from_docx(file_path)
            elif file_extension in [".ppt", ".pptx"]:
                text = extract_text_from_ppt(file_path)
            elif file_extension in [".xls", ".xlsx"]:
                text = extract_text_from_excel(file_path)
            elif file_extension in [".txt", ".md", ".csv", ".html", ".htm", ".json", ".xml"]:
                text = extract_text_from_text_file(file_path)
            else:
                # Fallback to simple text extraction
                text = extract_text_from_text_file(file_path)
        except Exception as e:
            raise DocumentError(
                code=ErrorCode.EXTRACTION_FAILED,
                message=f"Failed to extract text from {file_path}: {str(e)}",
                details={"file": file_path, "exception": str(e)},
                cause=e
            )
            
        if not text:
            logger.warning(f"No text extracted from {file_path}")
            return []
            
        # Safety check for extremely large documents
        if len(text) > config.max_characters_per_doc:
            logger.warning(f"Document too large, truncating: {file_path} ({len(text)} chars)")
            text = text[:config.max_characters_per_doc]
            
        # Calculate document hash for tracking changes
        doc_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            
        # Create metadata
        metadata = {
            "source": file_name,
            "file_path": str(file_path),
            "file_type": file_extension,
            "processed_at": datetime.now().isoformat(),
            "doc_hash": doc_hash,
            "char_count": len(text),
            "word_count": len(text.split()),
        }
        
        # Chunk the text
        chunks = chunk_text(text, metadata, config)
        
        logger.info(f"Processed document {file_name} into {len(chunks)} chunks")
        return chunks
        
    except DocumentError:
        # Re-raise document-specific errors
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing document {file_path}: {str(e)}")
        raise DocumentError(
            code=ErrorCode.DOCUMENT_PARSE_ERROR,
            message=f"Error processing document {file_path}: {str(e)}",
            cause=e
        )

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
        raise DocumentError(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"Failed to extract text from PDF: {str(e)}",
            details={"file": file_path},
            cause=e
        )

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
        raise DocumentError(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"Failed to extract text from DOCX: {str(e)}",
            details={"file": file_path},
            cause=e
        )

def extract_text_from_ppt(file_path: str) -> str:
    """
    Extract text from a PowerPoint file.
    
    Args:
        file_path: Path to the PPT/PPTX file
        
    Returns:
        Extracted text as a string
    """
    try:
        # Try to use python-pptx if available
        logger.warning(f"PowerPoint extraction not implemented fully: {file_path}")
        return f"[PowerPoint extraction not fully implemented for {Path(file_path).name}]"
    except Exception as e:
        logger.error(f"Error extracting text from PowerPoint {file_path}: {str(e)}")
        raise DocumentError(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"Failed to extract text from PowerPoint: {str(e)}",
            details={"file": file_path},
            cause=e
        )

def extract_text_from_excel(file_path: str) -> str:
    """
    Extract text from an Excel file.
    
    Args:
        file_path: Path to the Excel file
        
    Returns:
        Extracted text as a string
    """
    try:
        # Try to use pandas if available
        logger.warning(f"Excel extraction not implemented fully: {file_path}")
        return f"[Excel extraction not fully implemented for {Path(file_path).name}]"
    except Exception as e:
        logger.error(f"Error extracting text from Excel {file_path}: {str(e)}")
        raise DocumentError(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"Failed to extract text from Excel: {str(e)}",
            details={"file": file_path},
            cause=e
        )

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
            raise DocumentError(
                code=ErrorCode.EXTRACTION_FAILED,
                message=f"Failed to read text file: {str(e)}",
                details={"file": file_path},
                cause=e
            )
    except Exception as e:
        logger.error(f"Error extracting text from file {file_path}: {str(e)}")
        raise DocumentError(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"Failed to extract text from file: {str(e)}",
            details={"file": file_path},
            cause=e
        )

def chunk_text(text: str, metadata: Dict[str, Any], config: ChunkingConfig) -> List[Document]:
    """
    Split text into chunks suitable for embedding.
    Uses a simple character-based splitter to avoid external dependencies.
    """
    try:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []

        chunk_size = config.chunk_size
        overlap = config.chunk_overlap

        chunks: List[Document] = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_txt = text[start:end]
            # Optionally extend to sentence boundary if ensure_complete_sentences
            if config.ensure_complete_sentences and end < text_length:
                next_period = text.find('.', end)
                if 0 < next_period - end < 100:
                    end = next_period + 1
                    chunk_txt = text[start:end]
            chunk_meta = metadata.copy()
            chunks.append(Document(page_content=chunk_txt, metadata=chunk_meta))
            start = end - overlap
            if start < 0:
                start = 0

        total = len(chunks)
        for idx, doc in enumerate(chunks, start=1):
            doc.metadata["chunk"] = idx
            doc.metadata["total_chunks"] = total
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
        logger.info(f"Getting relevant chunks for query: {query}")
        store = get_vector_store()
        
        # Perform similarity search
        results = await store.similarity_search(query, top_k=top_k)
        
        logger.info(f"Found {len(results)} chunks relevant to query")
        return results
    except Exception as e:
        logger.error(f"Error getting relevant chunks: {str(e)}")
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
        raise DocumentError(
            code=ErrorCode.STORAGE_UNAVAILABLE,
            message=f"Failed to save uploaded file: {str(e)}",
            details={"filename": file.filename}
        )

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
        config = ChunkingConfig.from_settings()
        
        # Create a list of file processing tasks
        tasks = []
        for file_path in knowledge_dir.glob("*"):
            if file_path.is_file():
                tasks.append(process_document(str(file_path), config))
        
        # Process files concurrently with a semaphore to limit concurrency
        sem = asyncio.Semaphore(5)  # Process up to 5 files at a time
        
        async def process_with_limit(file_path):
            async with sem:
                return await process_document(str(file_path), config)
                
        # Process all files and collect results
        all_chunks = []
        for file_path in knowledge_dir.glob("*"):
            if file_path.is_file():
                try:
                    chunks = await process_document(str(file_path), config)
                    if chunks:
                        all_chunks.extend(chunks)
                        file_count += 1
                        total_chunks += len(chunks)
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
        
        # Add all chunks to vector store
        if all_chunks:
            success = await store.add_documents(all_chunks)
            if not success:
                logger.error("Failed to add documents to vector store")
        else:
            logger.warning("No chunks extracted from any files")
        
        logger.info(f"Reloaded knowledge base: {file_count} files, {total_chunks} chunks")
        return file_count
    except Exception as e:
        logger.error(f"Error reloading knowledge base: {str(e)}")
        raise DocumentError(
            code=ErrorCode.DOCUMENT_PARSE_ERROR,
            message=f"Failed to reload knowledge base: {str(e)}",
            cause=e
        ) 