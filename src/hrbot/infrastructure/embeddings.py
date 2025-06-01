"""
Light-weight *lazy* wrapper around Google Vertex AI Text-Embedding models.

• Initialise only when the first embedding is requested
• Simple exponential back-off (3 tries) – good for cold starts
• Memoises model dimension so callers do not have to probe
"""

from __future__ import annotations

import asyncio
import logging
import time
import os
from typing import List, Optional

from google.cloud import aiplatform
from vertexai.preview.language_models import TextEmbeddingModel

from hrbot.config.settings import settings

logger = logging.getLogger(__name__)


class VertexDirectEmbeddings:
    """Thin async-friendly wrapper around `text-embedding-xxx` models."""

    RETRIES = 3
    BATCH_SIZE = 16            # 16×768 ≈ 49 kB :: well below 1 MiB payload limit

    def __init__(
        self,
        *,
        model_name: str = "text-embedding-005",
        project: Optional[str] = None,
        location: str = "us-central1",
    ) -> None:
        self.project = project or settings.google_cloud.project_id
        self.location = location or settings.google_cloud.location
        self.model_name = model_name

        self._model: Optional[TextEmbeddingModel] = None
        self.dimension: int = 768        # default; overwritten on first call

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        delay = 1.0
        last_err: Exception | None = None
        
        # Debug credential availability
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or self.project
        
        logger.debug(f"Embeddings init: credentials_path={creds_path}, project={project_id}, location={self.location}")
        
        if not creds_path:
            logger.warning("No GOOGLE_APPLICATION_CREDENTIALS found for embeddings - this may cause authentication issues")
        
        for attempt in range(1, self.RETRIES + 1):
            try:
                aiplatform.init(project=project_id, location=self.location)
                self._model = TextEmbeddingModel.from_pretrained(self.model_name)
                # cheap single vector to discover true dimensionality
                sample = self._model.get_embeddings(["ping"])[0].values
                self.dimension = len(sample)
                logger.info(
                    "VertexEmbeddings initialised (dim=%s) on attempt %d",
                    self.dimension,
                    attempt,
                )
                return
            except Exception as exc:                                # noqa: BLE001
                last_err = exc
                logger.warning("Embedding init failed (attempt %d): %s", attempt, exc)
                time.sleep(delay)
                delay *= 2

        # exhausted retries
        raise RuntimeError(f"Cannot initialise Vertex embeddings: {last_err}")


    def embed_query(self, text: str) -> List[float]:
        """Blocking – use `asyncio.to_thread` from the caller."""
        self._ensure_model()
        return self._model.get_embeddings([text])[0].values  # type: ignore[index]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Blocking – split in mini-batches; caller off-loads to thread."""
        if not texts:
            return []

        self._ensure_model()
        out: List[List[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            chunk = texts[i : i + self.BATCH_SIZE]
            out.extend([emb.values for emb in self._model.get_embeddings(chunk)])  # type: ignore[attr-defined]
        return out
