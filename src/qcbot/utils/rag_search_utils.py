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
        """Comprehensive multi-strategy retrieval with enhanced ranking for better answers."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        chunk_dedup = {}  # hash -> best_chunk to avoid duplicates
        
        # Enhanced search strategies for comprehensive coverage
        search_strategies = [
            ("semantic_original", self._semantic_search(query, k * 3)),
            ("semantic_expanded", self._semantic_search_expanded(query, k * 2)),
            ("entity_aware", self._entity_aware_search(query, k)),
            ("keyword_fallback", self._keyword_fallback_search(query, k)),
            ("contextual", self._contextual_search(query, k)),
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
        
        # Enhanced ranking for better answer quality
        sorted_chunks = self._enhanced_ranking(query, all_chunks)
        
        return sorted_chunks[:k]

    def _enhanced_ranking(self, query: str, chunks: List["RetrievedChunk"]) -> List["RetrievedChunk"]:
        """Enhanced ranking considering multiple factors for better answer quality."""
        import re
        
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        
        def calculate_enhanced_score(chunk: "RetrievedChunk") -> float:
            content_lower = chunk.content.lower()
            content_words = set(re.findall(r'\b\w+\b', content_lower))
            
            # Base relevance score
            base_score = chunk.relevance_score
            
            # Keyword density score
            keyword_matches = len(query_words.intersection(content_words))
            keyword_density = keyword_matches / max(len(query_words), 1)
            
            # Term frequency score
            term_frequency = sum(content_lower.count(word) for word in query_words)
            tf_score = min(term_frequency / 10.0, 1.0)  # Normalize to 0-1
            
            # Content quality indicators for QC domain
            quality_indicators = ['procedure', 'process', 'standard', 'policy', 'guideline', 'protocol', 'requirement', 'specification']
            quality_score = sum(1 for indicator in quality_indicators if indicator in content_lower) / len(quality_indicators)
            
            # Length penalty for very short or very long content
            content_length = len(chunk.content)
            if content_length < 100:
                length_penalty = 0.8
            elif content_length > 2000:
                length_penalty = 0.9
            else:
                length_penalty = 1.0
            
            # Metadata boost for structured documents
            metadata_boost = 0.0
            if chunk.metadata:
                doc_type = chunk.metadata.get('file_type', '').lower()
                if doc_type in ['.docx', '.pdf']:  # Prefer structured documents
                    metadata_boost += 0.1
                
                source = chunk.metadata.get('source', '').lower()
                quality_terms = ['quality', 'procedure', 'standard', 'policy', 'guideline', 'sop']
                if any(term in source for term in quality_terms):
                    metadata_boost += 0.1
            
            # Combine scores
            enhanced_score = (
                base_score * 0.4 +
                keyword_density * 0.25 +
                tf_score * 0.15 +
                quality_score * 0.1 +
                metadata_boost * 0.1
            ) * length_penalty
            
            return enhanced_score
        
        # Calculate enhanced scores and sort
        for chunk in chunks:
            chunk.enhanced_score = calculate_enhanced_score(chunk)
        
        return sorted(
            chunks,
            key=lambda x: (x.enhanced_score, x.relevance_score, hash(x.content)),
            reverse=True
        )

    async def _semantic_search_expanded(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Semantic search with query expansion for better coverage."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
            # Create expanded query with synonyms and related terms
            expanded_query = self._expand_query_for_comprehensiveness(query)
            
            docs = await self.vector_store.similarity_search(expanded_query, top_k=k)
            if not docs:
                logger.debug(f"No documents found for expanded semantic search: '{query[:50]}...'")
                return []
                
            chunks = []
            for idx, doc in enumerate(docs):
                # Slightly lower base score for expanded queries
                relevance_score = 0.9 - (idx / max(len(docs), 1)) * 0.2
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=relevance_score,
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Expanded semantic search failed: {e}")
            return []

    def _expand_query_for_comprehensiveness(self, query: str) -> str:
        """Expand query with QC-specific terms for more comprehensive results."""
        query_lower = query.lower()
        expanded_terms = []
        
        # QC-specific terminology mapping
        qc_terms = {
            'quality': ['quality', 'qc', 'qa', 'assurance', 'control', 'standards'],
            'inspection': ['inspection', 'check', 'review', 'examine', 'audit', 'verify'],
            'process': ['process', 'procedure', 'workflow', 'method', 'protocol', 'steps'],
            'compliance': ['compliance', 'adherence', 'conformance', 'following', 'meeting'],
            'documentation': ['documentation', 'documents', 'records', 'files', 'papers'],
            'training': ['training', 'education', 'learning', 'instruction', 'development'],
            'safety': ['safety', 'security', 'protection', 'hazard', 'risk', 'precaution'],
            'equipment': ['equipment', 'tools', 'instruments', 'devices', 'machinery'],
            'testing': ['testing', 'test', 'evaluation', 'assessment', 'analysis'],
            'management': ['management', 'supervision', 'oversight', 'coordination', 'leadership']
        }
        
        # Add related terms based on query content
        for term, synonyms in qc_terms.items():
            if any(syn in query_lower for syn in synonyms):
                expanded_terms.extend(synonyms)
        
        # Add query pattern expansions
        if any(word in query_lower for word in ['how', 'what', 'when', 'where', 'why', 'who']):
            expanded_terms.extend(['procedure', 'process', 'steps', 'method', 'guideline'])
        
        if any(word in query_lower for word in ['requirement', 'standard', 'specification']):
            expanded_terms.extend(['compliance', 'adherence', 'conformance', 'criteria'])
        
        # Combine original query with expanded terms
        if expanded_terms:
            # Remove duplicates while preserving order
            seen = set()
            unique_terms = []
            for term in expanded_terms:
                if term.lower() not in seen:
                    seen.add(term.lower())
                    unique_terms.append(term)
            
            return f"{query} {' '.join(unique_terms[:10])}"  # Limit to 10 additional terms
        
        return query

    async def _contextual_search(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Contextual search considering document structure and metadata."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
            # Extract context clues from query
            context_clues = self._extract_context_clues(query)
            
            # Create contextual query
            contextual_query = f"{query} {' '.join(context_clues)}"
            docs = await self.vector_store.similarity_search(contextual_query, top_k=k)
            
            if not docs:
                logger.debug(f"No documents found for contextual search: '{query[:50]}...'")
                return []
            
            chunks = []
            for idx, doc in enumerate(docs):
                base_score = 0.8 - (idx / max(len(docs), 1)) * 0.2
                
                # Boost score based on metadata relevance
                metadata_boost = 0.0
                if doc.metadata:
                    # Check for relevant document types
                    doc_type = doc.metadata.get('file_type', '').lower()
                    if doc_type in ['.docx', '.pdf']:  # Prefer structured documents
                        metadata_boost += 0.1
                    
                    # Check for quality-related terms in source
                    source = doc.metadata.get('source', '').lower()
                    quality_terms = ['quality', 'procedure', 'standard', 'policy', 'guideline', 'sop']
                    if any(term in source for term in quality_terms):
                        metadata_boost += 0.1
                
                # Boost score based on content structure
                content_boost = 0.0
                content_lower = doc.page_content.lower()
                structure_indicators = ['step', 'procedure', 'process', 'requirement', 'standard', 'guideline']
                structure_matches = sum(1 for indicator in structure_indicators if indicator in content_lower)
                content_boost = min(structure_matches * 0.05, 0.2)
                
                relevance_score = min(base_score + metadata_boost + content_boost, 1.0)
                
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=relevance_score,
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Contextual search failed: {e}")
            return []

    def _extract_context_clues(self, query: str) -> List[str]:
        """Extract context clues from the query for better search."""
        query_lower = query.lower()
        context_clues = []
        
        # Time-related context
        if any(word in query_lower for word in ['when', 'time', 'schedule', 'deadline', 'timing']):
            context_clues.extend(['timing', 'schedule', 'deadline', 'timeframe'])
        
        # Process-related context
        if any(word in query_lower for word in ['how', 'process', 'steps', 'procedure', 'method']):
            context_clues.extend(['process', 'procedure', 'steps', 'workflow', 'methodology'])
        
        # Quality-related context
        if any(word in query_lower for word in ['quality', 'standard', 'compliance', 'requirement']):
            context_clues.extend(['quality', 'standard', 'compliance', 'requirement', 'specification'])
        
        # Document-related context
        if any(word in query_lower for word in ['document', 'form', 'template', 'record', 'file']):
            context_clues.extend(['documentation', 'form', 'template', 'record', 'file'])
        
        # Training-related context
        if any(word in query_lower for word in ['training', 'learn', 'education', 'instruction']):
            context_clues.extend(['training', 'education', 'learning', 'instruction', 'development'])
        
        # Safety-related context
        if any(word in query_lower for word in ['safety', 'hazard', 'risk', 'protection']):
            context_clues.extend(['safety', 'hazard', 'risk', 'protection', 'precaution'])
        
        return context_clues

    async def _semantic_search(self, query: str, k: int) -> List["RetrievedChunk"]:
        """Primary semantic similarity search."""
        # Import at runtime to avoid circular imports
        from qcbot.core.rag.engine import RetrievedChunk
        
        try:
            docs = await self.vector_store.similarity_search(query, top_k=k)
            if not docs:
                logger.debug(f"No documents found for semantic search: '{query[:50]}...'")
                return []
                
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
            
            if not docs:
                logger.debug(f"No documents found for entity search: '{query[:50]}...'")
                return []
            
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
            
            if not docs:
                logger.debug(f"No documents found for keyword search: '{query[:50]}...'")
                return []
            
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
