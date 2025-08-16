"""
Text Extraction Utilities for QC Bot

This module contains utilities for extracting text from various document formats
including PDF, DOCX, TXT, and other supported file types.
"""

import asyncio
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List
import aiofiles
import pdfplumber

logger = logging.getLogger(__name__)


async def _run_blocking(fn, *args):
    """Run blocking functions in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


def extract_text_pdf(path: str) -> str:
    """
    Advanced PDF extraction with table, list, and structure preservation.
    
    Follows AI/ML best practices for document processing:
    - Multi-modal extraction (text + tables + structure)
    - Content type detection and preservation
    - Fallback strategies for complex layouts
    """
    with pdfplumber.open(path) as pdf:
        extracted_content = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            page_content = []
            page_content.append(f"=== PAGE {page_num} ===")
            
            # Extract tables first (they contain structured information)
            tables = page.extract_tables()
            if tables:
                page_content.append("\n--- TABLES ---")
                for table_idx, table in enumerate(tables, 1):
                    if table and len(table) > 0:
                        page_content.append(f"\nTable {table_idx}:")
                        # Convert table to structured text
                        formatted_table = format_table_for_text(table)
                        page_content.append(formatted_table)
            
            # Extract regular text (excluding table areas to avoid duplication)
            # Get text with layout preserved
            text_content = page.extract_text(layout=True, x_tolerance=2, y_tolerance=2)
            if text_content:
                # Clean and structure the text
                structured_text = enhance_text_structure(text_content)
                if structured_text.strip():
                    page_content.append("\n--- CONTENT ---")
                    page_content.append(structured_text)
            
            # Try to extract any missed content with different settings
            fallback_text = page.extract_text(layout=False)
            if fallback_text and fallback_text not in str(page_content):
                additional_content = extract_additional_content(fallback_text, str(page_content))
                if additional_content:
                    page_content.append("\n--- ADDITIONAL ---")
                    page_content.append(additional_content)
            
            extracted_content.append("\n".join(page_content))
    
    return "\n\n".join(extracted_content)


def format_table_for_text(table: List[List[str]]) -> str:
    """Convert extracted table to well-formatted text that preserves structure."""
    if not table or len(table) == 0:
        return ""
    
    formatted_rows = []
    
    # Process header row if it exists
    if len(table) > 0 and table[0]:
        header = table[0]
        # Clean and format header
        clean_header = [str(cell or "").strip() for cell in header]
        if any(clean_header):  # Only add if header has content
            formatted_rows.append("| " + " | ".join(clean_header) + " |")
            # Add separator for markdown-style formatting
            formatted_rows.append("|" + "|".join([" --- " for _ in clean_header]) + "|")
    
    # Process data rows
    for row in table[1:] if len(table) > 1 else table:
        if row:
            clean_row = [str(cell or "").strip() for cell in row]
            if any(clean_row):  # Only add rows with content
                formatted_rows.append("| " + " | ".join(clean_row) + " |")
    
    return "\n".join(formatted_rows)


def enhance_text_structure(text: str) -> str:
    """Enhance text structure to preserve lists, headings, and formatting."""
    if not text:
        return ""
    
    lines = text.split('\n')
    enhanced_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Detect and enhance list items
        if re.match(r'^[•·▪▫‣⁃]\s*', line):
            # Already a bullet point
            enhanced_lines.append(line)
        elif re.match(r'^\d+\.\s+', line):
            # Numbered list
            enhanced_lines.append(line)
        elif re.match(r'^[a-zA-Z]\.\s+', line):
            # Lettered list
            enhanced_lines.append(line)
        elif re.match(r'^-\s+', line):
            # Dash list - convert to bullet
            enhanced_lines.append(line.replace('-', '•', 1))
        else:
            # Regular text - check if it looks like a list item
            if len(line) < 200 and ':' in line and not line.endswith('.'):
                # Might be a definition or category
                enhanced_lines.append(line)
            elif re.match(r'^[A-Z][^.!?]*[^.!?]\s*$', line) and len(line) < 100:
                # Might be a heading or category (all caps, no sentence ending)
                enhanced_lines.append(f"**{line}**")
            else:
                enhanced_lines.append(line)
    
    return '\n'.join(enhanced_lines)


def extract_additional_content(fallback_text: str, existing_content: str) -> str:
    """Extract any content missed by the primary extraction methods."""
    if not fallback_text:
        return ""
    
    # Split into sentences and check what's new
    fallback_sentences = re.split(r'[.!?]+', fallback_text)
    new_content = []
    
    for sentence in fallback_sentences:
        sentence = sentence.strip()
        if len(sentence) > 10 and sentence not in existing_content:
            # Check if it looks like meaningful content
            if re.search(r'\b(policy|procedure|benefit|discount|employee|contact|phone|email|address)\b', sentence.lower()):
                new_content.append(sentence)
    
    return '. '.join(new_content) + '.' if new_content else ""


def extract_text_docx(path: str) -> str:
    """Extract text from DOCX files."""
    parts: list[str] = []

    with zipfile.ZipFile(path) as z:
        def _grab(xml_bytes: bytes):
            root = ET.fromstring(xml_bytes)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for par in root.findall(f".//{ns}p"):
                texts = "".join(t.text or "" for t in par.findall(f".//{ns}t"))
                if texts:
                    parts.append(texts)

        _grab(z.read("word/document.xml"))

        for item in z.namelist():
            if item.startswith("word/") and item.endswith(".xml") and item != "word/document.xml":
                try:
                    _grab(z.read(item))
                except Exception:
                    # skip bad part
                    pass

    cleaned = re.sub(r"\n+", "\n\n", "\n".join(parts))
    return cleaned


async def extract_text_txt_async(path: str) -> str:
    """Async text file extraction for better concurrency."""
    try:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            return await f.read()
    except UnicodeDecodeError:
        async with aiofiles.open(path, mode='r', encoding='latin-1') as f:
            return await f.read()


def extract_text_txt(path: str) -> str:
    """Sync fallback for text extraction."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, encoding="latin-1") as f:
            return f.read()


# Extractors mapping
EXTRACTORS = {
    ".pdf": extract_text_pdf,  # PDF still needs blocking due to pdfplumber
    ".docx": extract_text_docx,
    ".txt": extract_text_txt_async,  # Now async!
    ".md": extract_text_txt_async,   # Now async!
    ".csv": extract_text_txt_async,  # Now async!
}

ASYNC_EXTRACTORS = {
    ".txt", ".md", ".csv"  # These support async extraction
}

SUPPORTED_EXT = set(EXTRACTORS.keys())  # For backward compatibility


async def extract_text_from_file(path: str) -> str:
    """
    Extract text from a file using the appropriate extractor.
    
    Args:
        path: Path to the file
        
    Returns:
        Extracted text content
    """
    import pathlib
    p = pathlib.Path(path)
    ext = p.suffix.lower()
    
    if ext not in EXTRACTORS:
        raise ValueError(f"Unsupported file type: {ext}")
    
    # Use async extraction for supported formats, blocking for others
    if ext in ASYNC_EXTRACTORS:
        text: str = await EXTRACTORS[ext](str(p))
    else:
        # Use thread executor for blocking operations (PDF, DOCX)
        text: str = await _run_blocking(EXTRACTORS[ext], str(p))
    
    return text
