from functools import lru_cache
from qcbot.services.gemini_service import GeminiService
from qcbot.services.intent_service import IntentDetectionService
from qcbot.infrastructure.vector_store import VectorStore
from qcbot.core.rag.engine import RAG
from qcbot.infrastructure.teams_adapter import TeamsAdapter
from qcbot.services.feedback_service import get_feedback_service
from qcbot.utils.card_action_handler import CardActionHandler
from qcbot.services.feedback_card_tracker import FeedbackCardTracker

"""
Dependency-provider helpers for FastAPI.

Each object is created lazily once per process and can be overridden
in tests with FastAPI's dependency-override mechanism.

Optimized for permissive-first RAG approach with comprehensive knowledge base coverage.
"""

@lru_cache
def get_llm() -> GeminiService:
    """Return a shared GeminiService instance."""
    return GeminiService()

@lru_cache
def get_intent_service() -> IntentDetectionService:
    """
    Return a shared IntentDetectionService for conversation flow control.
    """
    return IntentDetectionService(get_llm())

@lru_cache
def get_vector_store() -> VectorStore:
    """Return a shared VectorStore instance with comprehensive document coverage."""
    from qcbot.config.app_config import get_current_app_config
    app_config = get_current_app_config()
    from qcbot.infrastructure.vector_store import create_vector_store
    return create_vector_store(data_dir=app_config.embeddings_dir, collection_name="qc_documents")

@lru_cache
def get_rag() -> RAG:
    """
    Return a shared RAG pipeline instance optimized for permissive-first approach.
    """
    from qcbot.core.adapters.llm_gemini import LLMServiceAdapter
    return RAG(llm_provider=LLMServiceAdapter(get_llm()), vector_store=get_vector_store())

@lru_cache
def get_teams_adapter() -> TeamsAdapter:
    return TeamsAdapter()

@lru_cache
def get_feedback_card_tracker() -> FeedbackCardTracker:
    return FeedbackCardTracker(get_teams_adapter())

@lru_cache
def get_card_action_handler() -> CardActionHandler:
    return CardActionHandler(get_feedback_service(), get_teams_adapter())
