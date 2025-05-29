"""
Helpers for breaking a long LLM answer into visible, human-friendly
chunks that respect Microsoft Teams streaming requirements.

Key rules for Microsoft Teams streaming:
- Rate limit: 1 request per second maximum
- Each chunk must be meaningful and readable
- Preserve formatting in chunks
- Cumulative content approach (handled by adapter)
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncGenerator


async def sentence_chunks(
    text: str,
    *,
    min_len: int = 40,
    max_len: int = 150,
    delay: float = 1.2,  # Slightly above 1 second for Microsoft Teams rate limiting
) -> AsyncGenerator[str, None]:
    """
    Yield chunks that respect Microsoft Teams streaming requirements:
    
    1. Meaningful chunk sizes (40-150 chars)
    2. Sentence-aware chunking when possible
    3. Proper delay for rate limiting (1+ seconds)
    4. Preserve formatting (bullet points, etc.)
    
    Args:
        text: The text to chunk
        min_len: Minimum chunk length before releasing
        max_len: Maximum chunk length (force release)
        delay: Delay between chunks (Microsoft requires 1+ seconds)
    """
    if not text.strip():
        return
        
    # Preserve bullet point formatting by treating them specially
    lines = text.split('\n')
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_with_newline = line.rstrip()
        
        # If this line would make the chunk too long, yield current chunk first
        if current_length > 0 and current_length + len(line_with_newline) + 1 > max_len:
            chunk_text = '\n'.join(current_chunk)
            if chunk_text.strip():
                yield chunk_text + '\n'  # Add trailing newline to preserve formatting
                await asyncio.sleep(delay)
            current_chunk = []
            current_length = 0
        
        # Add the line to current chunk
        current_chunk.append(line_with_newline)
        current_length += len(line_with_newline) + 1  # +1 for newline
        
        # For bullet points or after question marks/periods, consider yielding
        if (current_length >= min_len and 
            (line_with_newline.strip().startswith('•') or 
             line_with_newline.strip().endswith(('?', '.', '!')) or
             line_with_newline.strip() == '')):
            
            chunk_text = '\n'.join(current_chunk)
            if chunk_text.strip():
                yield chunk_text + '\n'  # Add trailing newline to preserve formatting
                await asyncio.sleep(delay)
            current_chunk = []
            current_length = 0
    
    # Yield any remaining content
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        if chunk_text.strip():
            yield chunk_text


async def word_chunks(
    text: str,
    *,
    min_words: int = 8,
    max_words: int = 25,
    delay: float = 1.2,
) -> AsyncGenerator[str, None]:
    """
    Alternative word-based chunking for Microsoft Teams streaming.
    
    Better for flowing text without specific formatting requirements.
    Preserves line breaks and formatting.
    """
    if not text.strip():
        return
        
    # Split by lines first to preserve formatting
    lines = text.split('\n')
    current_chunk_words = []
    current_chunk_lines = []
    
    for line in lines:
        if line.strip():  # Non-empty line
            words = line.split()
            
            # If adding this line would exceed max_words, yield current chunk
            if len(current_chunk_words) + len(words) > max_words and current_chunk_words:
                yield ' '.join(current_chunk_words) + '\n'
                await asyncio.sleep(delay)
                current_chunk_words = []
                current_chunk_lines = []
            
            current_chunk_words.extend(words)
            current_chunk_lines.append(line)
            
            # Check for natural breaking points
            if (len(current_chunk_words) >= min_words and 
                (line.strip().endswith(('.', '!', '?', ':')) or 
                 line.strip().startswith('•'))):
                yield '\n'.join(current_chunk_lines) + '\n'
                await asyncio.sleep(delay)
                current_chunk_words = []
                current_chunk_lines = []
        else:  # Empty line
            current_chunk_lines.append(line)
    
    # Yield remaining words
    if current_chunk_words:
        yield '\n'.join(current_chunk_lines)


async def adaptive_chunks(
    text: str,
    *,
    delay: float = 1.2,
) -> AsyncGenerator[str, None]:
    """
    Adaptive chunking that chooses the best strategy based on text content.
    
    Uses sentence-based chunking for formatted text (bullet points, etc.)
    Uses word-based chunking for flowing text.
    Preserves formatting in all cases.
    """
    # Check if text has bullet points or structured formatting
    has_bullets = '•' in text or text.count('\n') > 3
    has_structured_content = any(line.strip().startswith('•') for line in text.split('\n'))
    
    if has_bullets or has_structured_content:
        # Use sentence chunking for formatted content
        async for chunk in sentence_chunks(text, delay=delay):
            yield chunk
    else:
        # Use word chunking for flowing text
        async for chunk in word_chunks(text, delay=delay):
            yield chunk







