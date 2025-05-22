"""
In-house NumPy/ndarray vector store (disk-backed, no FAISS).
"""

from __future__ import annotations

import asyncio
import logging
import pickle
from pathlib import Path
from typing import List, Sequence

import numpy as np

from hrbot.core.document import Document
from hrbot.infrastructure.embeddings import VertexDirectEmbeddings
from hrbot.utils.error import StorageError, ErrorCode   

logger = logging.getLogger(__name__)


class VectorStore:
    """Minimal but solid disk-backed cosine-similarity store."""

    FILE_EXT = ".npz"          # single compressed archive <collection>.npz

    def __init__(
        self,
        *,
        collection_name: str = "hr_documents",
        data_dir: str | Path = "data/embeddings",
        embeddings: VertexDirectEmbeddings | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._archive_path = self.data_dir / f"{collection_name}{self.FILE_EXT}"
        self._doclist_path = self.data_dir / f"{collection_name}_docs.pkl"

        self._embeddings = embeddings or VertexDirectEmbeddings()
        # engine.py expects this name
        self.embeddings_model = self._embeddings
        self._matrix: np.ndarray | None = None       # shape (N, dim)
        self._docs: list[Document] = []

        self._load_or_init()

    @property
    def documents(self) -> list[Document]:
        """Public accessor used by the ingest layer."""
        return self._docs

    def _load_or_init(self) -> None:
        if self._archive_path.exists() and self._doclist_path.exists():
            try:
                self._matrix = np.load(self._archive_path)["arr_0"]
                with open(self._doclist_path, "rb") as f:
                    self._docs = pickle.load(f)
                logger.info(
                    "VectorStore loaded (%d docs, dim=%d)",
                    len(self._docs),
                    self._matrix.shape[1],
                )
                return
            except Exception as exc:                                 # noqa: BLE001
                logger.warning("Corrupted vector store – rebuilding (%s)", exc)

        # fresh empty store
        dim = self._embeddings.dimension
        self._matrix = np.empty((0, dim), dtype=np.float32)
        self._docs = []
        logger.info("VectorStore initialised empty (dim=%d)", dim)

    def sync_disk(self) -> None:
        """Flush current state to disk (atomic)."""
        if self._matrix is None:      # pragma: no cover
            return

        tmp = self._archive_path.with_suffix(".tmp.npz")   # ends with .npz
        np.savez_compressed(tmp, self._matrix)             # atomic
        tmp.replace(self._archive_path)

        with open(self._doclist_path, "wb") as f:
            pickle.dump(self._docs, f)


    async def add_documents(self, docs: Sequence[Document]) -> int:
        """Embed & add *only* the docs that are not present yet.

        Returns the **number of NEW documents embedded**.
        """
        if not docs:
            return 0
        if self._matrix is None:
            raise RuntimeError("VectorStore not initialised")

        existing_hashes = {d.metadata.get("sha256") or d.sha256() for d in self._docs}
        fresh: list[Document] = []
        for d in docs:
            h = d.sha256()
            if h not in existing_hashes:
                d.metadata["sha256"] = h
                fresh.append(d)

        if not fresh:
            return 0

        texts = [d.page_content for d in fresh]
        embeds = await asyncio.to_thread(self._embeddings.embed_documents, texts)
        embeds = np.asarray(embeds, dtype=np.float32)

        # L2-normalise ⇒ cosine == dot
        embeds /= np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-9

        self._matrix = (
            np.vstack([self._matrix, embeds]) if self._matrix.size else embeds
        )
        self._docs.extend(fresh)
        self.sync_disk()
        logger.info("Added %d new docs (total =%d)", len(fresh), len(self._docs))
        return len(fresh)

    async def similarity_search(
         self,
         query: str,
         k: int = 5,
         *,
         top_k: int | None = None,      

     ) -> list[Document]:
        if self._matrix is None or not len(self._docs):
            return []

        if top_k is not None:
            k = top_k

        q = await asyncio.to_thread(self._embeddings.embed_query, query)
        q = np.asarray(q, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9

        sims = self._matrix @ q
        top_idx = np.argsort(sims)[-k:][::-1]
        return [self._docs[i] for i in top_idx]

    async def warmup(self) -> None:
        """Load data into RAM (called from FastAPI lifespan)."""
        if self._matrix is not None and self._matrix.size:
            _ = float(self._matrix[0] @ self._matrix[0])  # touch memory

    async def clear(self) -> None:
        """Danger: wipe cache from disk & memory."""
        for p in (self._archive_path, self._doclist_path):
            p.unlink(missing_ok=True)
        self._load_or_init()