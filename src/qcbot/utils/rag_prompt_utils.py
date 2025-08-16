"""
RAG Prompt and Formatting Utilities for QC Bot

This module contains utilities for building prompts and formatting chunks,
separating the prompt logic from the main RAG engine.
"""

import logging
from typing import List, Dict, Any, Optional, Set, TYPE_CHECKING
from qcbot.core.rag.prompt_loader import build_prompt, get_base_system

if TYPE_CHECKING:
    from qcbot.core.rag.engine import RetrievedChunk

logger = logging.getLogger(__name__)


class RAGPromptUtils:
    """Utilities for RAG prompt building and chunk formatting."""
    
    def __init__(self, prompt_template: Optional[str] = None):
        self.prompt_template = prompt_template
    
    def build_prompt(
        self,
        query: str,
        context: str,
        history: Optional[List[str]],
        *,
        system_override: Optional[str] = None,  
    ) -> str:
        """Build prompt with context and history."""
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
    def format_chunks_for_prompt(chunks: List["RetrievedChunk"]) -> str:
        """Format chunks for LLM prompt with confidence indicators and comprehensive prioritization."""
        if not chunks:
            return "No relevant information found."
        
        # Group chunks by confidence for better presentation
        high_conf = [c for c in chunks if c.relevance_score >= 0.7]
        med_conf = [c for c in chunks if 0.4 <= c.relevance_score < 0.7]
        low_conf = [c for c in chunks if c.relevance_score < 0.4]
        
        # Use consistent chunk selection for reproducible results
        # Prioritize high-confidence chunks with deterministic ordering
        if high_conf:
            # Sort by relevance score, then by content hash for stable ordering
            high_conf_sorted = sorted(high_conf, key=lambda x: (x.relevance_score, hash(x.content)), reverse=True)
            med_conf_sorted = sorted(med_conf, key=lambda x: (x.relevance_score, hash(x.content)), reverse=True)
            low_conf_sorted = sorted(low_conf, key=lambda x: (x.relevance_score, hash(x.content)), reverse=True)
            
            selected_chunks = (high_conf_sorted[:8] + med_conf_sorted[:3] + low_conf_sorted[:1])[:10]
        else:
            # Standard selection if no high-confidence chunks
            med_conf_sorted = sorted(med_conf, key=lambda x: (x.relevance_score, hash(x.content)), reverse=True)
            low_conf_sorted = sorted(low_conf, key=lambda x: (x.relevance_score, hash(x.content)), reverse=True)
            selected_chunks = (med_conf_sorted[:6] + low_conf_sorted[:2])[:8]
        
        formatted_chunks = []
        for i, chunk in enumerate(selected_chunks):
            source = chunk.metadata.get('source', 'Unknown')
            chunk_num = chunk.metadata.get('chunk', i+1)
            
            formatted_chunks.append(f"[Document: {source}, Section: {chunk_num}]\n{chunk.content}")
        
        return "\n\n".join(formatted_chunks)

    @staticmethod
    def extract_sources(chunks: List["RetrievedChunk"]) -> List[Dict[str, Any]]:
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
