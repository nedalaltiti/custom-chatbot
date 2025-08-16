# qcbot/infrastructure/ingest.py
"""
Auto-ingest helper
──────────────────
Scan app-specific knowledge directory, embed any *new* files, and persist them.

• Skips files that are already present in the VectorStore
  (we compare absolute file paths stored in metadata).
• Returns the number of documents embedded during this run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from qcbot.core.chunking import process_document
from qcbot.infrastructure.vector_store import VectorStore
from qcbot.config.app_config import get_current_app_config

logger = logging.getLogger(__name__)

async def refresh_vector_index(store: VectorStore) -> int:
    # Get app-specific knowledge directory
    app_config = get_current_app_config()
    knowledge_dir = app_config.knowledge_base_dir
    
    logger.info(f"Refreshing vector index from: {knowledge_dir}")
    
    if not knowledge_dir.exists():
        logger.warning("Knowledge dir %s does not exist", knowledge_dir)
        return 0

    # Check if store is empty (no embeddings)
    store_documents = store.documents
    is_store_empty = len(store_documents) == 0
    
    if is_store_empty:
        logger.info("Vector store is empty, processing ALL files in knowledge directory")
        # Process all supported files when store is empty
        supported_extensions = ['.pdf', '.docx', '.txt', '.md', '.csv']
        system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
        
        all_files = [
            fp for fp in knowledge_dir.glob("*")
            if fp.is_file() 
            and fp.suffix.lower() in supported_extensions
            and fp.name not in system_files
            and not fp.name.startswith('.')
        ]
        
        if not all_files:
            logger.info(f"No supported files found in {knowledge_dir}")
            return 0
            
        chunks = []
        for fp in all_files:
            try:
                file_chunks = await process_document(str(fp))
                chunks.extend(file_chunks)
                logger.info(f"Processed {fp.name}: {len(file_chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to process {fp.name}: {e}")
                continue
        
        if chunks:
            await store.add_documents(chunks)
            logger.info("Embedded %d docs (%d chunks)", 
                       len(all_files), len(chunks))
        
        return len(all_files)
    else:
        # Original logic for incremental updates
        already_indexed = {
            doc.metadata.get("file_path") for doc in store_documents
        }

        system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
        new_files = [
            fp for fp in knowledge_dir.glob("*")
            if fp.is_file() 
            and str(fp.resolve()) not in already_indexed
            and fp.name not in system_files
            and not fp.name.startswith('.')
        ]

        if not new_files:
            logger.info(f"No new files to index in {knowledge_dir}")
            return 0

        chunks = []
        for fp in new_files:
            try:
                file_chunks = await process_document(str(fp))
                chunks.extend(file_chunks)
                logger.info(f"Processed {fp.name}: {len(file_chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to process {fp.name}: {e}")
                continue

        if chunks:
            await store.add_documents(chunks)
            logger.info("Embedded %d new docs (%d chunks)", 
                       len(new_files), len(chunks))

        return len(new_files)


async def force_rebuild_embeddings(store: VectorStore) -> int:
    """
    Force a complete rebuild of embeddings from all documents in the knowledge base.
    This is useful when embeddings are deleted or corrupted.
    """
    app_config = get_current_app_config()
    knowledge_dir = app_config.knowledge_base_dir
    
    logger.info(f"Force rebuilding embeddings from: {knowledge_dir}")
    
    if not knowledge_dir.exists():
        logger.warning("Knowledge dir %s does not exist", knowledge_dir)
        return 0
    
    # Clear existing embeddings
    await store.delete_collection()
    logger.info("Cleared existing embeddings")
    
    # Process all supported files
    supported_extensions = ['.pdf', '.docx', '.txt', '.md', '.csv']
    system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
    
    all_files = [
        fp for fp in knowledge_dir.glob("*")
        if fp.is_file() 
        and fp.suffix.lower() in supported_extensions
        and fp.name not in system_files
        and not fp.name.startswith('.')
    ]
    
    if not all_files:
        logger.info(f"No supported files found in {knowledge_dir}")
        return 0
        
    chunks = []
    for fp in all_files:
        try:
            file_chunks = await process_document(str(fp))
            chunks.extend(file_chunks)
            logger.info(f"Processed {fp.name}: {len(file_chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to process {fp.name}: {e}")
            continue
    
    if chunks:
        await store.add_documents(chunks)
        logger.info("Rebuilt embeddings: %d docs (%d chunks)", 
                   len(all_files), len(chunks))
    
    return len(all_files)