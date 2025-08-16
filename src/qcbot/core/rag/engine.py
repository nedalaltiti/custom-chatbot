"""
Retrieval-Augmented Generation (RAG) core implementation.
"""

from __future__ import annotations

import logging
from typing import (Any, AsyncGenerator, Dict, List, Optional, Protocol)

from qcbot.core.rag.prompt_loader import build_prompt, get_base_system, get_flow_rules, get_template
from qcbot.infrastructure.vector_store import VectorStore
from qcbot.utils.error import ErrorCode, RAGError
from qcbot.utils.result import Error, Result, Success
from qcbot.config.settings import settings

# Import the new utility modules
from qcbot.utils.rag_search_utils import RAGSearchUtils
from qcbot.utils.rag_intent_detection import RAGIntentDetection
from qcbot.utils.rag_ranking_utils import RAGRankingUtils
from qcbot.utils.rag_prompt_utils import RAGPromptUtils

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> List[float]: ...
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...


class LLMProvider(Protocol):
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]: ...
    async def generate_response_streaming(
        self, prompt: str
    ) -> AsyncGenerator[str, None]: ...

class RetrievedChunk:
    """Represents a retrieved document chunk with metadata and relevance score."""
    
    def __init__(self, content: str, metadata: Dict[str, Any], relevance_score: float):
        self.content = content
        self.metadata = metadata
        self.relevance_score = relevance_score


class RAG:
    """
    Permissive-First RAG pipeline following best practices:
    - Send all queries to vector DB first
    - Use intent for ranking/boosting, not blocking
    - Multiple search strategies for comprehensive coverage
    - Graceful degradation for low-confidence results
    """

    def __init__(
        self,
        *,
        vector_store: Optional[VectorStore] = None,
        llm_provider: Optional[LLMProvider] = None,
        prompt_template: Optional[str] = None,
        top_k: int = 12,  # Increased for better coverage
    ) -> None:
        self.vector_store = vector_store or VectorStore()
        self.llm_provider = llm_provider
        self.default_top_k = top_k
        
        # Initialize utility modules
        self.search_utils = RAGSearchUtils(self.vector_store)
        self.intent_detection = RAGIntentDetection()
        self.ranking_utils = RAGRankingUtils()
        self.prompt_utils = RAGPromptUtils(prompt_template)
        
        # Cache for consistent results
        self._query_cache = {}
        self._cache_size = 100  # Limit cache size
        
        logger.info("RAG engine initialized with consistency optimizations (top_k=%s)", top_k)

    async def query(
        self,
        user_query: str,
        *,
        user_id: str | None = None,
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        system_override: Optional[str] = None,
    ) -> Result[Dict[str, Any]]:
        """Consistent RAG: Normalize query and use deterministic retrieval."""
        try:
            # Normalize query for consistency
            normalized_query = self.ranking_utils.normalize_query(user_query)
            logger.debug(f"Original query: '{user_query}' -> Normalized: '{normalized_query}'")
            
            # Check cache for consistent results
            cache_key = f"{normalized_query}_{top_k or self.default_top_k}"
            if cache_key in self._query_cache:
                logger.debug(f"Cache hit for query: '{normalized_query}'")
                chunks = self._query_cache[cache_key]
            else:
                k = top_k or self.default_top_k
                chunks = await self.search_utils.retrieve_with_multi_strategy(normalized_query, k)
                
                # Cache the result
                self.ranking_utils.cache_result(self._query_cache, cache_key, chunks, self._cache_size)
            
            # Apply consistent ranking based on normalized query
            ranked_chunks = self.ranking_utils.apply_intent_aware_ranking(normalized_query, chunks)
            
            context = self.prompt_utils.format_chunks_for_prompt(ranked_chunks)
            prompt = self.prompt_utils.build_prompt(
                user_query,  # Use original query for display
                context,
                chat_history,
                system_override=system_override,
            )
            
            if not self.llm_provider:
                return Error(
                    RAGError(
                        code=ErrorCode.LLM_UNAVAILABLE,
                        message="LLM provider missing",
                        user_message="The AI system is unavailable right now.",
                    )
                )

            llm_result = await self.llm_provider.generate_response(prompt)
            if llm_result.is_error():
                return llm_result  # propagate

            payload = llm_result.unwrap()
            
            # Apply formatting to ensure neat display
            if "response" in payload:
                from qcbot.services.processor import ChatProcessor
                processor = ChatProcessor()
                payload["response"] = processor._format_bullet_points(payload["response"])
            
            payload["sources"] = self.prompt_utils.extract_sources(ranked_chunks)
            payload["used_rag"] = True
            payload["confidence_level"] = self.ranking_utils.assess_confidence(ranked_chunks)
            if user_id:
                payload["user_id"] = user_id
            return Success(payload)

        except Exception as exc:  # noqa: BLE001
            logger.exception("RAG query failed: %s", exc)
            return Error(
                RAGError(
                    code=ErrorCode.QUERY_PROCESSING_ERROR,
                    message=str(exc),
                    user_message="I ran into an internal issue while answering.",
                )
            )

    async def query_streaming(
        self,
        user_query: str,
        *,
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        system_override: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming version with optimized retrieval and formatting."""
        k = top_k or self.default_top_k
        chunks = await self.search_utils.retrieve_with_multi_strategy(user_query, k)
        ranked_chunks = self.ranking_utils.apply_intent_aware_ranking(user_query, chunks)
        context = self.prompt_utils.format_chunks_for_prompt(ranked_chunks)
        prompt = self.prompt_utils.build_prompt(
                user_query,
                context,
                chat_history,
                system_override=system_override,
            )

        if not self.llm_provider:
            yield "[LLM unavailable]"
            return

        async for piece in self.llm_provider.generate_response_streaming(prompt):
            yield piece

    # Keep the public interface for backward compatibility
    def should_use_rag(self, query: str, chat_history: Optional[List[str]] = None) -> bool:
        """
        Always return True for permissive-first approach.
        Let the LLM decide what to do with the retrieved information.
        """
        return True
