"""
RAG Intent Detection Utilities for QC Bot

This module contains utilities for detecting query intent and content analysis,
separating the intent detection logic from the main RAG engine.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


class RAGIntentDetection:
    """Utilities for RAG intent detection and content analysis."""
    
    @staticmethod
    def is_audit_query(query: str) -> bool:
        """Check if query is asking about audits or quality checks."""
        audit_indicators = [
            'audit', 'quality check', 'quality control', 'qc', 'inspection', 
            'review', 'assessment', 'evaluation', 'compliance', 'verification'
        ]
        return any(indicator in query for indicator in audit_indicators)

    @staticmethod
    def is_policy_query(query: str) -> bool:
        """Check if query is about quality policies or procedures."""
        return any(word in query for word in ['policy', 'rule', 'procedure', 'guideline', 'standard', 'protocol'])

    @staticmethod
    def is_quality_query(query: str) -> bool:
        """Check if query is about quality control processes."""
        quality_indicators = [
            'quality', 'qc', 'quality control', 'quality assurance', 'qa',
            'standards', 'specifications', 'requirements', 'criteria'
        ]
        return any(indicator in query for indicator in quality_indicators)

    @staticmethod
    def is_process_query(query: str) -> bool:
        """Check if query is asking about a quality control process or procedure."""
        process_indicators = [
            'how to', 'process', 'procedure', 'steps', 'what do i need', 
            'requirements', 'apply for', 'request', 'submit', 'how can i', 
            'what should i', 'workflow', 'method', 'approach'
        ]
        return any(indicator in query for indicator in process_indicators)

    @staticmethod
    def contains_audit_info(content: str) -> bool:
        """Check if content contains audit or quality check information."""
        audit_indicators = [
            'audit', 'quality check', 'quality control', 'qc', 'inspection', 
            'review', 'assessment', 'evaluation', 'compliance', 'verification',
            'checklist', 'criteria', 'standards', 'requirements'
        ]
        return any(indicator in content for indicator in audit_indicators)

    @staticmethod
    def contains_policy_info(content: str) -> bool:
        """Check if content contains quality policy information."""
        policy_indicators = [
            'policy', 'procedure', 'rule', 'guideline', 'regulation', 'must', 'should',
            'standard', 'protocol', 'specification', 'requirement', 'criteria'
        ]
        return any(indicator in content for indicator in policy_indicators)

    @staticmethod
    def contains_quality_info(content: str) -> bool:
        """Check if content contains quality control information."""
        quality_indicators = [
            'quality', 'qc', 'quality control', 'quality assurance', 'qa',
            'standards', 'specifications', 'requirements', 'criteria', 'metrics',
            'performance', 'efficiency', 'accuracy', 'precision'
        ]
        return any(indicator in content for indicator in quality_indicators)

    @staticmethod
    def contains_comprehensive_process_info(content: str) -> bool:
        """Check if content contains comprehensive quality control process information."""
        comprehensive_indicators = [
            'step', 'first', 'then', 'after', 'next', 'required', 'document',
            'form', 'submit', 'approval', 'review', 'complete', 'finish',
            'deadline', 'timeline', 'schedule', 'duration', 'timeframe',
            'checklist', 'criteria', 'standards', 'requirements', 'specifications',
            'quality check', 'inspection', 'verification', 'compliance',
            'supervisor', 'manager', 'qc', 'quality control'
        ]
        
        # Count how many indicators are present
        indicator_count = sum(1 for indicator in comprehensive_indicators if indicator in content)
        
        # Consider it comprehensive if it has multiple indicators
        return indicator_count >= 4

    @staticmethod
    def contains_process_steps(content: str) -> bool:
        """Check if content contains quality control process steps."""
        step_indicators = [
            'step', 'first', 'then', 'after', 'next', 'finally', 'must', 'need to',
            'check', 'verify', 'inspect', 'review', 'assess', 'evaluate',
            'quality check', 'qc step', 'inspection step'
        ]
        return sum(1 for indicator in step_indicators if indicator in content) >= 2

    @staticmethod
    def has_multiple_relevant_keywords(content: str, query: str) -> bool:
        """Check if content has multiple keywords from the query (indicates comprehensive coverage)."""
        # Extract meaningful words from query (exclude common words)
        stop_words = {'the', 'is', 'are', 'was', 'were', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'how', 'what', 'can', 'i', 'do'}
        query_words = [word for word in query.split() if word.lower() not in stop_words and len(word) > 2]
        
        # Count how many query words appear in content
        matches = sum(1 for word in query_words if word.lower() in content)
        
        # Consider it multi-keyword if at least 2 query words are found
        return matches >= 2
