# hrbot/infrastructure/ingest.py
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

from hrbot.core.chunking import process_document            
from hrbot.infrastructure.vector_store import VectorStore
from hrbot.config.app_config import get_current_app_config

logger = logging.getLogger(__name__)

async def refresh_vector_index(store: VectorStore) -> int:
    # Get app-specific knowledge directory
    app_config = get_current_app_config()
    knowledge_dir = app_config.knowledge_base_dir
    
    logger.info(f"Refreshing vector index from: {knowledge_dir}")
    
    if not knowledge_dir.exists():
        logger.warning("Knowledge dir %s does not exist", knowledge_dir)
        return 0

    already_indexed = {
        doc.metadata.get("file_path") for doc in store.documents
    }

    new_files = [
        fp for fp in knowledge_dir.glob("*")
        if fp.is_file() and str(fp.resolve()) not in already_indexed
    ]

    if not new_files:
        logger.info(f"No new files to index in {knowledge_dir}")
        return 0

    chunks = []
    for fp in new_files:
        # process_document() already extracts, chunks and fills metadata
        chunks.extend(await process_document(str(fp)))

    if chunks:
        await store.add_documents(chunks)
        logger.info("Embedded %d new docs (%d chunks) for app instance: %s", 
                   len(new_files), len(chunks), app_config.instance_id)

    return len(new_files)