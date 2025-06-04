"""
Retrieval-Augmented Generation (RAG) core implementation.
"""

from __future__ import annotations

import logging
import re
import asyncio
from dataclasses import dataclass
from typing import (Any, AsyncGenerator, Dict, List, Optional, Protocol, Set,
                    Tuple)

from hrbot.core.rag.prompt_loader import build_prompt, get_base_system, get_flow_rules, get_template
from hrbot.infrastructure.vector_store import VectorStore
from hrbot.utils.error import ErrorCode, RAGError
from hrbot.utils.result import Error, Result, Success
from hrbot.config.settings import settings

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
        self.prompt_template = prompt_template 
        self.default_top_k = top_k
        logger.info("RAG engine initialized with permissive-first approach (top_k=%s)", top_k)

    async def query(
        self,
        user_query: str,
        *,
        user_id: str | None = None,
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        system_override: Optional[str] = None,
    ) -> Result[Dict[str, Any]]:
        """Permissive-first RAG: Always retrieve, then intelligently rank and present."""
        try:
            k = top_k or self.default_top_k
            chunks = await self._retrieve_with_multi_strategy(user_query, k)
            
            # Apply intelligent ranking based on query intent
            ranked_chunks = self._apply_intent_aware_ranking(user_query, chunks)
            
            context = self._format_chunks_for_prompt(ranked_chunks)
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
            payload["sources"] = self._extract_sources(ranked_chunks)
            payload["used_rag"] = True
            payload["confidence_level"] = self._assess_confidence(ranked_chunks)
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
        """Streaming version with optimized retrieval."""
        k = top_k or self.default_top_k
        chunks = await self._retrieve_with_multi_strategy(user_query, k)
        ranked_chunks = self._apply_intent_aware_ranking(user_query, chunks)
        context = self._format_chunks_for_prompt(ranked_chunks)
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

    async def _retrieve_with_multi_strategy(self, query: str, k: int) -> List[RetrievedChunk]:
        """
        Optimized multi-strategy retrieval for comprehensive coverage with minimal latency.
        
        Strategy: Run searches in parallel for speed, then intelligently merge results.
        """
        all_chunks = []
        chunk_dedup = {}  # hash -> best_chunk to avoid duplicates
        
        # Run multiple search strategies in parallel for speed
        search_tasks = [
            self._semantic_search(query, k * 3),  # Primary search with larger pool
            self._entity_aware_search(query, k * 2),  # Entity-specific search
            self._keyword_fallback_search(query, k),  # Keyword fallback
        ]
        
        try:
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            for i, result in enumerate(search_results):
                if isinstance(result, Exception):
                    logger.warning(f"Search strategy {i} failed: {result}")
                    continue
                    
                for chunk in result:
                    chunk_id = hash(chunk.content)
                    # Keep the chunk with the highest relevance score
                    if chunk_id not in chunk_dedup or chunk.relevance_score > chunk_dedup[chunk_id].relevance_score:
                        chunk_dedup[chunk_id] = chunk
            
            all_chunks = list(chunk_dedup.values())
            
        except Exception as e:
            logger.warning(f"Multi-strategy search failed: {e}")
            # Fallback to simple search
            all_chunks = await self._semantic_search(query, k * 2)
        
        # Sort by relevance and return top results
        sorted_chunks = sorted(all_chunks, key=lambda x: x.relevance_score, reverse=True)
        return sorted_chunks[:k * 2]  # Return more chunks for better LLM context

    async def _semantic_search(self, query: str, k: int) -> List[RetrievedChunk]:
        """Primary semantic similarity search."""
        try:
            docs = await self.vector_store.similarity_search(query, top_k=k)
            chunks = []
            for idx, doc in enumerate(docs):
                # Calculate relevance based on position (first results are more relevant)
                relevance_score = 1.0 - (idx / max(len(docs), 1)) * 0.3
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=relevance_score,
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    async def _entity_aware_search(self, query: str, k: int) -> List[RetrievedChunk]:
        """Entity-aware search for specific information (names, contacts, etc.)."""
        try:
            # Quick entity extraction without heavy processing
            entities = self._extract_query_entities(query)
            if not entities:
                return []
            
            # Search with entity-enhanced query
            entity_query = f"{query} {' '.join(entities)}"
            docs = await self.vector_store.similarity_search(entity_query, top_k=k)
            
            chunks = []
            for idx, doc in enumerate(docs):
                # Boost score if content contains entities
                base_score = 0.8 - (idx / max(len(docs), 1)) * 0.2
                if self._content_contains_entities(doc.page_content, entities):
                    base_score += 0.2  # Boost for entity matches
                
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=min(base_score, 1.0),
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return []

    async def _keyword_fallback_search(self, query: str, k: int) -> List[RetrievedChunk]:
        """Keyword-based fallback search for comprehensive coverage."""
        try:
            # Extract key terms quickly
            keywords = self._extract_key_terms(query)
            if not keywords:
                return []
            
            keyword_query = " ".join(keywords)
            docs = await self.vector_store.similarity_search(keyword_query, top_k=k)
            
            chunks = []
            for idx, doc in enumerate(docs):
                relevance_score = 0.6 - (idx / max(len(docs), 1)) * 0.2
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=relevance_score,
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")
            return []

    def _extract_query_entities(self, query: str) -> List[str]:
        """Quick entity extraction for enhanced search (optimized for speed)."""
        entities = []
        query_lower = query.lower()
        
        # Common HR entities and roles
        hr_entities = [
            'doctor', 'physician', 'manager', 'director', 'supervisor', 'coordinator',
            'hr', 'admin', 'reception', 'contact', 'support', 'representative'
        ]
        
        # Question words that indicate entity queries
        if any(word in query_lower for word in ['who', 'name', 'contact', 'called']):
            for entity in hr_entities:
                if entity in query_lower:
                    entities.append(entity)
        
        return entities

    def _extract_key_terms(self, query: str) -> List[str]:
        """Extract key terms for keyword search (optimized for speed)."""
        # Simple but effective keyword extraction
        stop_words = {'the', 'is', 'are', 'was', 'were', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = re.findall(r'\b\w+\b', query.lower())
        return [word for word in words if len(word) > 2 and word not in stop_words][:5]

    def _content_contains_entities(self, content: str, entities: List[str]) -> bool:
        """Quick check if content contains relevant entities."""
        content_lower = content.lower()
        return any(entity in content_lower for entity in entities)

    def _apply_intent_aware_ranking(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        """
        Apply intent-aware ranking to boost relevant results without blocking.
        This follows the best practice of using intent for ranking, not filtering.
        """
        query_lower = query.lower()
        
        for chunk in chunks:
            content_lower = chunk.content.lower()
            
            # Boost based on query intent (additive scoring)
            if self._is_name_query(query_lower):
                if self._contains_names(content_lower):
                    chunk.relevance_score += 0.3
            
            if self._is_contact_query(query_lower):
                if self._contains_contact_info(content_lower):
                    chunk.relevance_score += 0.3
            
            if self._is_policy_query(query_lower):
                if self._contains_policy_info(content_lower):
                    chunk.relevance_score += 0.2
            
            if self._is_benefit_query(query_lower):
                if self._contains_benefit_info(content_lower):
                    chunk.relevance_score += 0.2
            
            # NEW: Boost comprehensive chunks for process questions
            if self._is_process_query(query_lower):
                if self._contains_comprehensive_process_info(content_lower):
                    chunk.relevance_score += 0.4  # Strong boost for comprehensive process info
                elif self._contains_process_steps(content_lower):
                    chunk.relevance_score += 0.2  # Medium boost for process steps
            
            # Boost structured content that often contains comprehensive info
            if chunk.metadata.get("section_type") in ["table", "list"]:
                chunk.relevance_score += 0.15
            
            # NEW: Boost chunks with multiple relevant keywords (indicates comprehensive coverage)
            if self._has_multiple_relevant_keywords(content_lower, query_lower):
                chunk.relevance_score += 0.2
        
        # Sort by boosted relevance score
        return sorted(chunks, key=lambda x: x.relevance_score, reverse=True)

    def _is_name_query(self, query: str) -> bool:
        """Check if query is asking for names."""
        return any(word in query for word in ['who', 'name', 'called', "what's the name"])

    def _is_contact_query(self, query: str) -> bool:
        """Check if query is asking for contact information."""
        return any(word in query for word in ['contact', 'phone', 'email', 'reach', 'call'])

    def _is_policy_query(self, query: str) -> bool:
        """Check if query is about policies."""
        return any(word in query for word in ['policy', 'rule', 'procedure', 'guideline'])

    def _is_benefit_query(self, query: str) -> bool:
        """Check if query is about benefits."""
        return any(word in query for word in ['benefit', 'discount', 'perk', 'insurance', 'leave'])

    def _is_process_query(self, query: str) -> bool:
        """Check if query is asking about a process or procedure."""
        process_indicators = [
            'resign', 'resignation', 'quit', 'leave work', 'how to', 'process', 
            'procedure', 'steps', 'what do i need', 'requirements', 'apply for',
            'request', 'submit', 'how can i', 'what should i'
        ]
        return any(indicator in query for indicator in process_indicators)

    def _contains_names(self, content: str) -> bool:
        """Check if content contains proper names."""
        # Look for patterns indicating names
        name_patterns = [
            r'\bdr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+',  # Capitalized words
            r'contact[\s\w]*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        return any(re.search(pattern, content) for pattern in name_patterns)

    def _contains_contact_info(self, content: str) -> bool:
        """Check if content contains contact information."""
        contact_indicators = ['phone', 'email', 'contact', 'call', 'reach', '@', 'tel:', 'ext']
        return any(indicator in content for indicator in contact_indicators)

    def _contains_policy_info(self, content: str) -> bool:
        """Check if content contains policy information."""
        policy_indicators = ['policy', 'procedure', 'rule', 'guideline', 'regulation', 'must', 'should']
        return any(indicator in content for indicator in policy_indicators)

    def _contains_benefit_info(self, content: str) -> bool:
        """Check if content contains benefit information."""
        benefit_indicators = ['benefit', 'discount', 'perk', 'insurance', 'leave', 'vacation', 'sick', 'coverage']
        return any(indicator in content for indicator in benefit_indicators)

    def _contains_comprehensive_process_info(self, content: str) -> bool:
        """Check if content contains comprehensive process information."""
        # Look for indicators of comprehensive information
        comprehensive_indicators = [
            'step', 'first', 'then', 'after', 'next', 'required', 'document',
            'notice period', 'final settlement', 'approval', 'manager', 'hr',
            'probation', 'experience certificate', 'company property'
        ]
        
        # Count how many indicators are present
        indicator_count = sum(1 for indicator in comprehensive_indicators if indicator in content)
        
        # Consider it comprehensive if it has multiple indicators
        return indicator_count >= 4

    def _contains_process_steps(self, content: str) -> bool:
        """Check if content contains process steps."""
        step_indicators = ['step', 'first', 'then', 'after', 'next', 'finally', 'must', 'need to']
        return sum(1 for indicator in step_indicators if indicator in content) >= 2

    def _has_multiple_relevant_keywords(self, content: str, query: str) -> bool:
        """Check if content has multiple keywords from the query (indicates comprehensive coverage)."""
        # Extract meaningful words from query (exclude common words)
        stop_words = {'the', 'is', 'are', 'was', 'were', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'how', 'what', 'can', 'i', 'do'}
        query_words = [word for word in query.split() if word.lower() not in stop_words and len(word) > 2]
        
        # Count how many query words appear in content
        matches = sum(1 for word in query_words if word.lower() in content)
        
        # Consider it multi-keyword if at least 2 query words are found
        return matches >= 2

    def _assess_confidence(self, chunks: List[RetrievedChunk]) -> str:
        """Assess confidence level of results for graceful degradation."""
        if not chunks:
            return "none"
        
        max_score = max(chunk.relevance_score for chunk in chunks)
        avg_score = sum(chunk.relevance_score for chunk in chunks) / len(chunks)
        
        if max_score >= 0.8 and avg_score >= 0.6:
            return "high"
        elif max_score >= 0.6 and avg_score >= 0.4:
            return "medium"
        elif max_score >= 0.4:
            return "low"
        else:
            return "very_low"

    def _build_prompt(
        self,
        query: str,
        context: str,
        history: Optional[List[str]],
        *,
        system_override: Optional[str] = None,  
    ) -> str:
        # Log context quality for monitoring
        logger.debug(f"Building prompt for query: '{query[:50]}...'")
        logger.debug(f"Context length: {len(context)} chars")
        
        if self.prompt_template:
            return self.prompt_template.format(
                context=context,
                history="\n".join(history or []),
                query=query,
            )

        # Use the prompt loader to get app-specific prompts
        return build_prompt({
            "system": system_override or get_base_system(),
            "context": context,
            "history": "\n".join(history or []),
            "query": query,
        })

    @staticmethod
    def _format_chunks_for_prompt(chunks: List[RetrievedChunk]) -> str:
        """Format chunks for LLM prompt with confidence indicators and comprehensive prioritization."""
        if not chunks:
            return "No relevant information found."
        
        # Group chunks by confidence for better presentation
        high_conf = [c for c in chunks if c.relevance_score >= 0.7]
        med_conf = [c for c in chunks if 0.4 <= c.relevance_score < 0.7]
        low_conf = [c for c in chunks if c.relevance_score < 0.4]
        
        # Prioritize high-confidence chunks and ensure we get comprehensive info
        # For process questions, we want more comprehensive chunks
        if high_conf:
            # For comprehensive responses, include more high-confidence chunks
            selected_chunks = (high_conf[:10] + med_conf[:3] + low_conf[:1])[:12]
        else:
            # Standard selection if no high-confidence chunks
            selected_chunks = (high_conf[:8] + med_conf[:4] + low_conf[:2])[:12]
        
        formatted_chunks = []
        for i, chunk in enumerate(selected_chunks):
            source = chunk.metadata.get('source', 'Unknown')
            chunk_num = chunk.metadata.get('chunk', i+1)
            
            formatted_chunks.append(f"[Document: {source}, Section: {chunk_num}]\n{chunk.content}")
        
        return "\n\n".join(formatted_chunks)

    @staticmethod
    def _extract_sources(chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
        """Extract source information from chunks."""
        seen: Set[str] = set()
        sources: List[Dict[str, Any]] = []
        for c in chunks:
            src = c.metadata.get("source")
            if src and src not in seen:
                sources.append({
                        "title": src,
                        "path": c.metadata.get("file_path", ""),
                        "type": c.metadata.get("file_type", ""),
                        "relevance": round(c.relevance_score, 2),
                })
                seen.add(src)
        return sources

    # Keep the public interface for backward compatibility
    def should_use_rag(self, query: str, chat_history: Optional[List[str]] = None) -> bool:
        """
        Always return True for permissive-first approach.
        Let the LLM decide what to do with the retrieved information.
        """
        return True
