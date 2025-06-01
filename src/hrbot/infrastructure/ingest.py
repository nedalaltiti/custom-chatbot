# hrbot/infrastructure/ingest.py
"""
Auto-ingest helper
──────────────────
Scan `data/knowledge/`, embed any *new* files, and persist them.

• Skips files that are already present in the VectorStore
  (we compare absolute file paths stored in metadata).
• Returns the number of documents embedded during this run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hrbot.core.chunking import process_document            
from hrbot.infrastructure.vector_store import VectorStore

logger = logging.getLogger(__name__)
KNOWLEDGE_DIR = Path("data/knowledge")

async def refresh_vector_index(store: VectorStore) -> int:
    if not KNOWLEDGE_DIR.exists():
        logger.warning("Knowledge dir %s does not exist", KNOWLEDGE_DIR)
        return 0

    already_indexed = {
        doc.metadata.get("file_path") for doc in store.documents
    }

    new_files = [
        fp for fp in KNOWLEDGE_DIR.glob("*")
        if fp.is_file() and str(fp.resolve()) not in already_indexed
    ]

    if not new_files:
        return 0

    chunks = []
    for fp in new_files:
        # process_document() already extracts, chunks and fills metadata
        chunks.extend(await process_document(str(fp)))

    if chunks:
        await store.add_documents(chunks)
        logger.info("Embedded %d new docs (%d chunks)", len(new_files), len(chunks))

    return len(new_files)