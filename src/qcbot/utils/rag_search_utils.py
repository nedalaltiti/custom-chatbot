"""
RAG Search Strategy Utilities for QC Bot

This module contains utilities for multi-strategy retrieval and search operations,
separating the search logic from the main RAG engine.
"""

import logging
from typing import List, Dict, Any, TYPE_CHECKING
from qcbot.infrastructure.vector_store import VectorStore

if TYPE_CHECKING:
    from qcbot.core.rag.engine import RetrievedChunk

logger = logging.getLogger(__name__)


class RAGSearchUtils:
    """Utilities for RAG search operations with multi-strategy retrieval."""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
    
    async def retrieve_with_multi_strategy(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Consistent multi-strategy retrieval with deterministic ranking."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        chunk_dedup = {}  # hash -> best_chunk to avoid duplicates
        
        # Use consistent search order for deterministic results
        search_strategies = [
            ("semantic", self._semantic_search(query, k * 2)),
            ("entity", self._entity_aware_search(query, k)),
            ("keyword", self._keyword_fallback_search(query, k // 2)),
        ]
        
        for strategy_name, search_task in search_strategies:
            try:
                result = await search_task
                for chunk in result:
                    chunk_id = hash(chunk.content)
                    if chunk_id not in chunk_dedup or chunk.relevance_score > chunk_dedup[chunk_id].relevance_score:
                        chunk_dedup[chunk_id] = chunk
            except Exception as e:
                logger.warning(f"Search strategy {strategy_name} failed: {e}")
                continue
        
        all_chunks = list(chunk_dedup.values())
        
        # Use deterministic sorting with stable tie-breaking
        sorted_chunks = sorted(
            all_chunks, 
            key=lambda x: (x.relevance_score, hash(x.content)),
            reverse=True
        )
        
        return sorted_chunks[:k]

    async def _semantic_search(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Primary semantic similarity search."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
            docs = await self.vector_store.similarity_search(query, top_k=k)
            chunks = []
            for idx, doc in enumerate(docs):
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

    async def _entity_aware_search(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Entity-aware search for specific information."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
            entities = self._extract_query_entities(query)
            if not entities:
                return []
            
            entity_query = f"{query} {' '.join(entities)}"
            docs = await self.vector_store.similarity_search(entity_query, top_k=k)
            
            chunks = []
            for idx, doc in enumerate(docs):
                base_score = 0.8 - (idx / max(len(docs), 1)) * 0.2
                if self._content_contains_entities(doc.page_content, entities):
                    base_score += 0.2
                
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=min(base_score, 1.0),
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return []

    async def _keyword_fallback_search(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Keyword-based fallback search."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
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
        """Quick entity extraction for enhanced search."""
        entities = []
        query_lower = query.lower()
        
        qc_entities = [
            'quality', 'control', 'assurance', 'inspection', 'audit', 'compliance',
            'standard', 'procedure', 'policy', 'guideline', 'process', 'workflow',
            'supervisor', 'manager', 'coordinator', 'specialist', 'technician'
        ]
        
        if any(word in query_lower for word in ['who', 'name', 'contact', 'called']):
            for entity in qc_entities:
                if entity in query_lower:
                    entities.append(entity)
        
        return entities

    def _extract_key_terms(self, query: str) -> List[str]:
        """Extract key terms for keyword search."""
        import re
        stop_words = {'the', 'is', 'are', 'was', 'were', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = re.findall(r'\b\w+\b', query.lower())
        return [word for word in words if len(word) > 2 and word not in stop_words][:5]

    def _content_contains_entities(self, content: str, entities: List[str]) -> bool:
        """Check if content contains relevant entities."""
        content_lower = content.lower()
        return any(entity in content_lower for entity in entities)
