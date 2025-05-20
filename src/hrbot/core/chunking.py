"""
Unified document-processing & chunking layer for the RAG pipeline
─────────────────────────────────────────────────────────────────
• Advanced text extraction (PDF, DOCX, TXT, etc.)                 – non-blocking
• Configurable, sentence-aware chunking with overlap              – ChunkingConfig
• Rich metadata (hash, word/char count, page numbers, …)
• Async-safe helpers: save_uploaded_file(), reload_knowledge_base(), get_relevant_chunks()
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

from hrbot.config.settings import settings
from hrbot.core.document import Document
from hrbot.infrastructure.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────
# Globals
# ───────────────────────────────────────────────────────────────
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


# ───────────────────────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────────────────────
class ChunkingConfig:
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
            chunk_size=getattr(settings, "chunk_size", 1_000),
            chunk_overlap=getattr(settings, "chunk_overlap", 200),
            ensure_complete_sentences=getattr(settings, "ensure_complete_sentences", True),
        )


# ───────────────────────────────────────────────────────────────
# Extraction helpers
# ───────────────────────────────────────────────────────────────
async def _run_blocking(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


def _extract_text_pdf(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        pages = [
            f"Page {i+1}:\n{p.extract_text()}"
            for i, p in enumerate(pdf.pages)
            if p.extract_text()
        ]
    return "\n\n".join(pages)


def _extract_text_docx(path: str) -> str:
    import zipfile
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    parts: list[str] = []

    with zipfile.ZipFile(path) as z:
        def _grab(xml_bytes: bytes):
            root = ET.fromstring(xml_bytes)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for par in root.findall(f".//{ns}p"):
                texts = "".join(t.text or "" for t in par.findall(f".//{ns}t"))
                if texts:
                    parts.append(texts)

        _grab(z.read("word/document.xml"))

        for item in z.namelist():
            if item.startswith("word/") and item.endswith(".xml") and item != "word/document.xml":
                try:
                    _grab(z.read(item))
                except Exception:
                    # skip bad part
                    pass

    cleaned = re.sub(r"\n+", "\n\n", "\n".join(parts))
    return cleaned


def _extract_text_txt(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, encoding="latin-1") as f:
            return f.read()


EXTRACTORS = {
    ".pdf": _extract_text_pdf,
    ".docx": _extract_text_docx,
    ".txt": _extract_text_txt,
    ".md": _extract_text_txt,
    ".csv": _extract_text_txt,
}

SUPPORTED_EXT = set(EXTRACTORS.keys())


# ───────────────────────────────────────────────────────────────
# Core: process_document
# ───────────────────────────────────────────────────────────────
async def process_document(path: str, cfg: ChunkingConfig | None = None) -> List[Document]:
    cfg = cfg or ChunkingConfig.from_settings()
    p = Path(path)
    if not p.exists():
        logger.warning("File not found: %s", path)
        return []

    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXT:
        logger.warning("Unsupported file type: %s", ext)
        return []

    # run blocking extraction off-thread
    text: str = await _run_blocking(EXTRACTORS[ext], str(p))
    if not text:
        logger.warning("No text extracted from %s", p.name)
        return []

    if len(text) > cfg.max_characters_per_doc:
        text = text[: cfg.max_characters_per_doc]

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

    chunks = _chunk(text, meta_base, cfg)
    logger.info("Processed %s (%d chars) → %d chunks", p.name, len(text), len(chunks))
    return chunks


def _chunk(text: str, meta: Dict[str, Any], cfg: ChunkingConfig) -> List[Document]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    cs, ov, ecs = cfg.chunk_size, cfg.chunk_overlap, cfg.ensure_complete_sentences
    chunks: list[Document] = []
    start = 0
    while start < len(text):
        end = min(start + cs, len(text))
        if ecs and end < len(text):
            nxt = text.find(".", end)
            if 0 < nxt - end < 100:
                end = nxt + 1
        payload = text[start:end]
        chunks.append(Document(page_content=payload, metadata=meta.copy()))
        start = end - ov if end - ov > start else end

    total = len(chunks)
    for i, c in enumerate(chunks, 1):
        c.metadata["chunk"] = i
        c.metadata["total_chunks"] = total
    return chunks


# ───────────────────────────────────────────────────────────────
# Semantic search helper
# ───────────────────────────────────────────────────────────────
async def get_relevant_chunks(query: str, top_k: int = 5) -> List[Document]:
    store = get_vector_store()
    return await store.similarity_search(query, top_k=top_k)


# ───────────────────────────────────────────────────────────────
# CRUD helpers for KB
# ───────────────────────────────────────────────────────────────
async def save_uploaded_file(file) -> str:
    os.makedirs("data/knowledge", exist_ok=True)
    dst = Path("data/knowledge") / file.filename
    dst.write_bytes(await file.read())
    logger.info("Saved file → %s", dst)
    return str(dst)


async def reload_knowledge_base(cfg: ChunkingConfig | None = None, concurrency: int = 4) -> int:
    """
    Re-index every file under data/knowledge/ with limited parallelism.
    Returns number of files processed.
    """
    path = Path("data/knowledge")
    if not path.exists():
        return 0

    store = get_vector_store()
    await store.delete_collection()

    sem = asyncio.Semaphore(concurrency)
    files = [p for p in path.iterdir() if p.is_file()]

    async def _worker(p: Path):
        async with sem:
            return await process_document(str(p), cfg)

    chunks: list[Document] = []
    for task in asyncio.as_completed([_worker(p) for p in files]):
        chunks.extend(await task)

    if chunks:
        await store.add_documents(chunks)
    return len(files)
