"""
Chunking Utilities for QC Bot

This module contains utilities for intelligent text chunking that preserves
document structure and semantic coherence.
"""

import logging
import re
from typing import List, Dict, Any
from qcbot.core.document import Document
from qcbot.utils.text_processing import identify_document_structure

logger = logging.getLogger(__name__)


def chunk_section(section: Dict[str, Any], meta: Dict[str, Any], 
                  chunk_size: int, overlap: int, ensure_sentences: bool) -> List[Document]:
    """Chunk a section based on its type and content."""
    content_lines = section["content"]
    section_type = section["type"]
    priority = section["priority"]
    
    if not content_lines:
        return []

    section_text = '\n'.join(content_lines)
    
    # Adjust chunking strategy based on section type
    if section_type == "table":
        # Tables should generally stay together as they're structured data
        return [Document(
            page_content=section_text,
            metadata={
                **meta,
                "section_type": "table",
                "priority": priority,
                "preserve_structure": True
            }
        )]
    
    elif section_type == "list":
        # Lists should be kept together if possible, but can be split intelligently
        if len(section_text) <= chunk_size * 1.5:  # Allow slightly larger chunks for lists
            return [Document(
                page_content=section_text,
                metadata={
                    **meta,
                    "section_type": "list", 
                    "priority": priority,
                    "preserve_structure": True
                }
            )]
        else:
            # Split long lists, but try to keep related items together
            return split_list_intelligently(content_lines, meta, chunk_size, overlap)
    
    elif section_type == "header":
        # Headers are usually short and can be combined with following content
        return [Document(
            page_content=section_text,
            metadata={
                **meta,
                "section_type": "header",
                "priority": priority
            }
        )]
    
    else:  # Regular text
        return chunk_text_intelligently(section_text, meta, chunk_size, overlap, ensure_sentences)


def split_list_intelligently(list_lines: List[str], meta: Dict[str, Any], 
                            chunk_size: int, overlap: int) -> List[Document]:
    """Split long lists while keeping related items together."""
    chunks = []
    current_chunk_lines = []
    current_length = 0
    
    for line in list_lines:
        line_length = len(line)
        
        # If adding this line would exceed chunk size, create a chunk
        if current_length + line_length > chunk_size and current_chunk_lines:
            chunk_content = '\n'.join(current_chunk_lines)
            chunks.append(Document(
                page_content=chunk_content,
                metadata={
                    **meta,
                    "section_type": "list_part",
                    "priority": "high"
                }
            ))
            
            # Start new chunk with overlap
            overlap_lines = current_chunk_lines[-2:] if len(current_chunk_lines) > 2 else current_chunk_lines
            current_chunk_lines = overlap_lines + [line]
            current_length = sum(len(l) for l in current_chunk_lines)
        else:
            current_chunk_lines.append(line)
            current_length += line_length
    
    # Add final chunk
    if current_chunk_lines:
        chunk_content = '\n'.join(current_chunk_lines)
        chunks.append(Document(
            page_content=chunk_content,
            metadata={
                **meta,
                "section_type": "list_part",
                "priority": "high"
            }
        ))
    
    return chunks


def chunk_text_intelligently(text: str, meta: Dict[str, Any], 
                            chunk_size: int, overlap: int, ensure_sentences: bool) -> List[Document]:
    """Chunk regular text with intelligent boundaries."""
    if len(text) <= chunk_size:
        return [Document(
            page_content=text,
            metadata={
                **meta,
                "section_type": "text",
                "priority": "normal"
            }
        )]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Try to find a good breaking point
        if ensure_sentences and end < len(text):
            # Look for sentence boundaries
            sentence_ends = [m.end() for m in re.finditer(r'[.!?]+\s+', text[start:end + 100])]
            if sentence_ends:
                best_end = start + max(s for s in sentence_ends if s <= chunk_size)
                if best_end > start + chunk_size * 0.7:  # Don't make chunks too small
                    end = best_end
        
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Document(
                page_content=chunk_text,
                metadata={
                    **meta,
                    "section_type": "text",
                    "priority": "normal"
                }
            ))
        
        start = end - overlap if end - overlap > start else end
    
    return chunks


def chunk_document(text: str, meta: Dict[str, Any], chunk_size: int, overlap: int, 
                   ensure_sentences: bool = True) -> List[Document]:
    """
    Intelligent context-aware chunking that preserves related information.
    
    Follows AI/ML best practices:
    - Structure-aware splitting (preserves tables, lists, sections)
    - Semantic coherence (keeps related content together)
    - Adaptive overlap (more overlap for structured content)
    - Metadata enrichment (chunk type, structure info)
    """
    if not text or not text.strip():
        return []

    # Clean text while preserving structure
    text = re.sub(r' +', ' ', text).strip()
    
    # First, identify document structure
    structured_sections = identify_document_structure(text)
    
    chunks: list[Document] = []
    
    for section in structured_sections:
        section_chunks = chunk_section(
            section, 
            meta, 
            chunk_size, 
            overlap, 
            ensure_sentences
        )
        chunks.extend(section_chunks)
    
    # Add chunk metadata
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        chunk.metadata.update({
            "chunk": i,
            "total_chunks": total,
            "chunk_strategy": "context_aware"
        })
    
    return chunks


def optimize_chunk_size(text: str, target_chunks: int = 10) -> int:
    """Calculate optimal chunk size based on text length and target chunk count."""
    if not text:
        return 1000  # Default chunk size
    
    text_length = len(text)
    optimal_size = max(500, text_length // target_chunks)
    
    # Round to nearest 100 for consistency
    return round(optimal_size / 100) * 100


def calculate_overlap(chunk_size: int, text_complexity: str = "normal") -> int:
    """Calculate appropriate overlap based on chunk size and text complexity."""
    base_overlap = chunk_size // 5  # 20% base overlap
    
    # Adjust based on complexity
    complexity_multipliers = {
        "simple": 0.5,
        "normal": 1.0,
        "complex": 1.5,
        "very_complex": 2.0
    }
    
    multiplier = complexity_multipliers.get(text_complexity, 1.0)
    overlap = int(base_overlap * multiplier)
    
    # Ensure overlap is reasonable
    return min(overlap, chunk_size // 2)  # Max 50% overlap


def merge_small_chunks(chunks: List[Document], min_chunk_size: int = 200) -> List[Document]:
    """Merge very small chunks with adjacent chunks to improve coherence."""
    if not chunks:
        return chunks
    
    merged_chunks = []
    current_chunk = chunks[0]
    
    for next_chunk in chunks[1:]:
        combined_size = len(current_chunk.page_content) + len(next_chunk.page_content)
        
        if combined_size <= min_chunk_size * 2:  # Allow merging if combined size is reasonable
            # Merge the chunks
            merged_content = current_chunk.page_content + "\n\n" + next_chunk.page_content
            merged_metadata = {**current_chunk.metadata}
            merged_metadata.update({
                "merged": True,
                "original_chunks": 2
            })
            
            current_chunk = Document(
                page_content=merged_content,
                metadata=merged_metadata
            )
        else:
            # Keep current chunk and move to next
            merged_chunks.append(current_chunk)
            current_chunk = next_chunk
    
    # Add the last chunk
    merged_chunks.append(current_chunk)
    
    return merged_chunks


def validate_chunks(chunks: List[Document]) -> List[Document]:
    """Validate and clean chunks to ensure quality."""
    valid_chunks = []
    
    for chunk in chunks:
        # Skip empty chunks
        if not chunk.page_content.strip():
            continue
        
        # Skip chunks that are too short (likely incomplete)
        if len(chunk.page_content.strip()) < 50:
            continue
        
        # Clean up the content
        cleaned_content = chunk.page_content.strip()
        chunk.page_content = cleaned_content
        
        valid_chunks.append(chunk)
    
    return valid_chunks
