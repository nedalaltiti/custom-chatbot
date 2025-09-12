"""
Unified document-processing & chunking layer for the RAG pipeline
─────────────────────────────────────────────────────────────────
• Advanced text extraction (PDF, DOCX, TXT, etc.)                 – non-blocking
• Configurable, sentence-aware chunking with overlap              – ChunkingConfig
• Rich metadata (hash, word/char count, page numbers, …)
• Async-safe helpers: save_uploaded_file(), reload_knowledge_base(), get_relevant_chunks()
• Standalone QC bot with dedicated knowledge base
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from qcbot.config.settings import settings
from qcbot.config.app_config import get_current_app_config
from qcbot.core.document import Document
from qcbot.infrastructure.vector_store import VectorStore
from qcbot.utils.di import get_vector_store
from qcbot.utils.text_extractors import extract_text_from_file, EXTRACTORS, ASYNC_EXTRACTORS
from qcbot.utils.chunking_utils import chunk_document, validate_chunks
from qcbot.utils.file_utils import save_uploaded_file, run_blocking

logger = logging.getLogger(__name__)


class ChunkingConfig:
    """Configuration for document chunking."""
    
    def __init__(
        self,
        chunk_size: int = 1_000,
        chunk_overlap: int = 200,
        ensure_complete_sentences: bool = True,
        max_characters_per_doc: int = 1_000_000,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.ensure_complete_sentences = ensure_complete_sentences
        self.max_characters_per_doc = max_characters_per_doc

    @classmethod
    def from_settings(cls) -> "ChunkingConfig":
        return cls(
            chunk_size=settings.performance.chunk_size,
            chunk_overlap=settings.performance.chunk_overlap,
            ensure_complete_sentences=True,  # Always ensure complete sentences for readability
        )


async def process_document(path: str, cfg: ChunkingConfig | None = None) -> List[Document]:
    """
    Process document with optimized async text extraction when possible.
    
    Uses async I/O for text files and optimized blocking for binary formats.
    """
    cfg = cfg or ChunkingConfig.from_settings()
    p = Path(path)
    if not p.exists():
        logger.warning("File not found: %s", path)
        return []

    # Skip system files and other non-document files
    system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
    if p.name in system_files or p.name.startswith('.'):
        logger.debug("Skipping system file: %s", p.name)
        return []

    ext = p.suffix.lower()
    if ext not in EXTRACTORS:
        logger.warning("Unsupported file type: %s", ext)
        return []

    # Extract text using the utility function
    try:
        text = await extract_text_from_file(str(p))
    except Exception as e:
        logger.error(f"Error extracting text from {p.name}: {e}")
        return []
        
    if not text:
        logger.warning("No text extracted from %s", p.name)
        return []

    if len(text) > cfg.max_characters_per_doc:
        text = text[: cfg.max_characters_per_doc]

    # Use faster hashing for large documents
    doc_hash = hashlib.md5(text.encode()).hexdigest()
    meta_base: Dict[str, Any] = {
        "source": p.name,
        "file_path": str(p),
        "file_type": ext,
        "processed_at": datetime.utcnow().isoformat(),
        "doc_hash": doc_hash,
        "char_count": len(text),
        "word_count": len(text.split()),
    }

    # Use the chunking utility
    chunks = chunk_document(text, meta_base, cfg.chunk_size, cfg.chunk_overlap, cfg.ensure_complete_sentences)
    
    # Validate chunks
    chunks = validate_chunks(chunks)
    
    logger.info("Processed %s (%d chars) → %d chunks", p.name, len(text), len(chunks))
    return chunks


async def get_relevant_chunks(query: str, top_k: int = 5) -> List[Document]:
    """Get relevant chunks for a query using vector search."""
    store = get_vector_store()
    return await store.similarity_search(query, top_k=top_k)


async def reload_knowledge_base_concurrent(cfg: ChunkingConfig | None = None, concurrency: int = 4) -> int:
    """
    High-performance concurrent knowledge base reloading with optimized I/O.
    
    Args:
        cfg: Chunking configuration
        concurrency: Number of concurrent file processing tasks
        
    Returns:
        Number of files processed.
    """
    # Get QC app config (standalone)
    app_config = get_current_app_config()
    
    knowledge_dir = app_config.knowledge_base_dir
    if not knowledge_dir.exists():
        logger.warning(f"Knowledge base directory does not exist: {knowledge_dir}")
        return 0

    store = get_vector_store()
    await store.delete_collection()

    # Get all supported files and sort by size (process smaller files first for better UI feedback)
    # Filter out system files and only process supported document types
    supported_extensions = ['.pdf', '.docx', '.txt', '.md', '.csv']
    system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
    
    files = [
        p for p in knowledge_dir.iterdir() 
        if p.is_file() 
        and p.suffix.lower() in supported_extensions
        and p.name not in system_files
        and not p.name.startswith('.')
    ]
    files.sort(key=lambda x: x.stat().st_size)
    
    # Use optimized semaphore for concurrency control
    sem = asyncio.Semaphore(concurrency)
    
    logger.info(f"Reloading knowledge base from {knowledge_dir} ({len(files)} files)")

    async def _optimized_worker(p: Path):
        async with sem:
            try:
                chunks = await process_document(str(p), cfg)
                if chunks:
                    await store.add_documents(chunks)
                    logger.info(f"Processed {p.name}: {len(chunks)} chunks")
                    return len(chunks)
                return 0
            except Exception as e:
                logger.error(f"Error processing {p.name}: {e}")
                return 0

    # Process all files concurrently
    tasks = [_optimized_worker(p) for p in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count successful results
    total_chunks = sum(r for r in results if isinstance(r, int))
    logger.info(f"Knowledge base reload complete: {total_chunks} total chunks")
    
    return total_chunks


# Backward compatibility - calls the optimized version
async def reload_knowledge_base(cfg: ChunkingConfig | None = None, concurrency: int = 4) -> int:
    """
    Backward compatibility wrapper for reload_knowledge_base_concurrent.
    
    This maintains API compatibility while using the optimized implementation.
    """
    return await reload_knowledge_base_concurrent(cfg, concurrency)


# Export the save_uploaded_file function from utils
__all__ = [
    'ChunkingConfig',
    'process_document', 
    'get_relevant_chunks',
    'reload_knowledge_base',
    'reload_knowledge_base_concurrent',
    'save_uploaded_file'
]
