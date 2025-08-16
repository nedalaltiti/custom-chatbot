"""
RAG Ranking and Confidence Utilities for QC Bot

This module contains utilities for ranking results and assessing confidence,
separating the ranking logic from the main RAG engine.
"""

import logging
import re
from typing import List, Dict, Any, TYPE_CHECKING
from qcbot.utils.rag_intent_detection import RAGIntentDetection

if TYPE_CHECKING:
    from qcbot.core.rag.engine import RetrievedChunk

logger = logging.getLogger(__name__)


class RAGRankingUtils:
    """Utilities for RAG ranking and confidence assessment."""
    
    def __init__(self):
        self.intent_detection = RAGIntentDetection()
    
    def apply_intent_aware_ranking(self, query: str, chunks: List["RetrievedChunk"]) -> List["RetrievedChunk"]:
        """
        Apply intent-aware ranking to boost relevant results without blocking.
        This follows the best practice of using intent for ranking, not filtering.
        """
        query_lower = query.lower()
        
        for chunk in chunks:
            content_lower = chunk.content.lower()
            
            # Boost based on query intent (additive scoring)
            if self.intent_detection.is_audit_query(query_lower):
                if self.intent_detection.contains_audit_info(content_lower):
                    chunk.relevance_score += 0.4  # Strong boost for audit/quality check info
            
            if self.intent_detection.is_policy_query(query_lower):
                if self.intent_detection.contains_policy_info(content_lower):
                    chunk.relevance_score += 0.3
            
            if self.intent_detection.is_quality_query(query_lower):
                if self.intent_detection.contains_quality_info(content_lower):
                    chunk.relevance_score += 0.3
            
            # Boost comprehensive chunks for process questions
            if self.intent_detection.is_process_query(query_lower):
                if self.intent_detection.contains_comprehensive_process_info(content_lower):
                    chunk.relevance_score += 0.4  # Strong boost for comprehensive process info
                elif self.intent_detection.contains_process_steps(content_lower):
                    chunk.relevance_score += 0.2  # Medium boost for process steps
            
            # Boost structured content that often contains comprehensive info
            if chunk.metadata.get("section_type") in ["table", "list"]:
                chunk.relevance_score += 0.15
            
            # Boost chunks with multiple relevant keywords (indicates comprehensive coverage)
            if self.intent_detection.has_multiple_relevant_keywords(content_lower, query_lower):
                chunk.relevance_score += 0.2
        
        # Sort by boosted relevance score
        return sorted(chunks, key=lambda x: x.relevance_score, reverse=True)

    def assess_confidence(self, chunks: List["RetrievedChunk"]) -> str:
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

    def normalize_query(self, query: str) -> str:
        """Normalize query for consistent processing."""
        if not query:
            return ""
        
        # Convert to lowercase
        normalized = query.lower().strip()
        
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        
        # Sort words for consistent ordering (helps with similar queries)
        words = normalized.split()
        if len(words) > 3:  # Only sort if query has more than 3 words
            # Keep first 2 words in order (usually question words), sort the rest
            first_words = words[:2]
            remaining_words = sorted(words[2:])
            normalized = " ".join(first_words + remaining_words)
        
        return normalized

    def cache_result(self, cache: dict, cache_key: str, chunks: List["RetrievedChunk"], cache_size: int = 100) -> None:
        """Cache retrieval results for consistency."""
        # Limit cache size
        if len(cache) >= cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(cache))
            del cache[oldest_key]
        
        # Cache the chunks
        cache[cache_key] = chunks
        logger.debug(f"Cached result for key: {cache_key}")
