"""
Retrieval-Augmented Generation (RAG) core implementation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import (Any, AsyncGenerator, Dict, List, Optional, Protocol, Set,
                    Tuple)

from hrbot.core.rag.prompt import build as build_prompt
from hrbot.infrastructure.vector_store import VectorStore
from hrbot.utils.error import ErrorCode, RAGError
from hrbot.utils.result import Error, Result, Success

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> List[float]: ...
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...


class LLMProvider(Protocol):
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]: ...
    async def generate_response_streaming(
        self, prompt: str
    ) -> AsyncGenerator[str, None]: ...


@dataclass
class RetrievedChunk:
    content: str
    metadata: Dict[str, Any]
    relevance_score: float


class RAG:
    """A lean Retrieval‑Augmented Generation pipeline."""

    # keyword heuristics that trigger RAG even for short queries
    KNOWLEDGE_PATTERNS: Tuple[str, ...] = (
        r"\bpolicy\b",
        r"\bbenefits?\b",
        r"\btime\s+off\b",
        r"\bPTO\b",
        r"\bvacation\b",
        r"\bleaves?\b",
        r"\b401k\b",
        r"\bhealth\s+insurance\b",
        r"\bonboarding\b",
        r"\bcompensation\b",
        r"\bresign", 
        r"\bquit\b",
        r"\bleaving\b",
        r"\bnotice\b",
        r"\boff-?boarding\b",
        r"\bsick\b",
        r"\bdoctor\b",
        r"\bmedical\b",
        r"\bworkstation\b",
        r"\bpayroll\b",
        r"\bovertime\b",
        r"\bzenhr\b",
        r"\bhr\b",
        r"\binsurance\b",
        r"\bhalf.?day\b",
        r"\bleave request\b",
        r"\bmanager\b",
        r"\bemployee\b",
    )

    def __init__(
        self,
        *,
        vector_store: Optional[VectorStore] = None,
        llm_provider: Optional[LLMProvider] = None,
        prompt_template: Optional[str] = None,
        top_k: int = 3,
    ) -> None:
        self.vector_store = vector_store or VectorStore()
        self.llm_provider = llm_provider
        self.prompt_template = prompt_template 
        self.default_top_k = top_k
        logger.info("RAG engine initialised (top_k=%s)", top_k)

    async def query(
        self,
        user_query: str,
        *,
        user_id: str | None = None,
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        system_override: Optional[str] = None,
    ) -> Result[Dict[str, Any]]:
        """Retrieve → augment → generate (single‑shot)."""
        try:
            k = top_k or self.default_top_k
            chunks = await self._retrieve_documents(user_query, k)
            context = self._format_chunks_for_prompt(chunks)
            prompt = self._build_prompt(
                user_query,
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
            payload["sources"] = self._extract_sources(chunks)
            payload["used_rag"] = True
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
        """Same as :py:meth:`query` but yields the answer progressively."""
        k = top_k or self.default_top_k
        chunks = await self._retrieve_documents(user_query, k)
        context = self._format_chunks_for_prompt(chunks)
        prompt = self._build_prompt(
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


    async def _retrieve_documents(self, query: str, k: int) -> List[RetrievedChunk]:
        pool = await self.vector_store.similarity_search(query, top_k=k * 3)
        selected: List[RetrievedChunk] = []
        for idx, doc in enumerate(pool):
            selected.append(
                RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=doc.metadata.get("relevance_score", 1 - idx / max(len(pool), 1)),
                )
            )
            if len(selected) == k:
                break
        if getattr(self.vector_store, "embeddings_model", None) is None:
            for c in selected:
                c.metadata["fallback"] = True
        return selected

    def _build_prompt(
        self,
        query: str,
        context: str,
        history: Optional[List[str]],
        *,
        system_override: Optional[str] = None,  
    ) -> str:
        if self.prompt_template:
            return self.prompt_template.format(
                context=context,
                history="\n".join(history or []),
                query=query,
            )

        from hrbot.core.rag.prompt import BASE_SYSTEM, FLOW_RULES, TEMPLATE
        system = system_override or BASE_SYSTEM

        return TEMPLATE.format(
            system=system,
            flow_rules=FLOW_RULES,
            context=context,
            history="\n".join(history or []),
            query=query,
        )


    @staticmethod
    def _format_chunks_for_prompt(chunks: List[RetrievedChunk]) -> str:
        if not chunks:
            return "No relevant information found."
        return "\n\n".join(
            f"[Document: {c.metadata.get('source', 'Unknown')}, Chunk: {c.metadata.get('chunk', i+1)}]\n{c.content}"
            for i, c in enumerate(chunks)
        )

    @staticmethod
    def _extract_sources(chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
        if chunks and chunks[0].metadata.get("fallback"):
            return []
        seen: Set[str] = set()
        sources: List[Dict[str, Any]] = []
        for c in chunks:
            src = c.metadata.get("source")
            if src and src not in seen:
                sources.append(
                    {
                        "title": src,
                        "path": c.metadata.get("file_path", ""),
                        "type": c.metadata.get("file_type", ""),
                        "relevance": round(c.relevance_score, 2),
                    }
                )
                seen.add(src)
        return sources

    def should_use_rag(self, query: str, chat_history: Optional[List[str]] = None) -> bool:  # noqa: D401
        """Return *True* if RAG should run for *query*."""
        if len(query.split()) > 8:
            return True
        q = query.lower()
        if any(re.search(pat, q) for pat in self.KNOWLEDGE_PATTERNS):
            return True
        if any(token in q for token in ("?", "how", "what", "why", "when", "where")):
            return True
        return False
