from functools import lru_cache

from hrbot.services.gemini_service import GeminiService
from hrbot.infrastructure.vector_store import VectorStore
from hrbot.core.rag.engine import RAG 

"""
Dependency-provider helpers for FastAPI.

Each object is created lazily once per process and can be overridden
in tests with FastAPI’s dependency-override mechanism.
"""

@lru_cache
def get_llm() -> GeminiService:
    """Return a shared GeminiService instance."""
    return GeminiService()


@lru_cache
def get_vector_store() -> VectorStore:
    """Return a shared VectorStore instance."""
    return VectorStore()


@lru_cache
def get_rag() -> RAG:
    """Return a shared RAG pipeline instance wired to the shared services."""
    return RAG(
        vector_store=get_vector_store(),
        llm_provider=get_llm(),
    )
