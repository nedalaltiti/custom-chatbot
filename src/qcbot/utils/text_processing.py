"""
Text Processing Utilities for QC Bot

This module contains utilities for processing and analyzing text content,
including document structure identification and text enhancement.
"""

import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def identify_document_structure(text: str) -> List[Dict[str, Any]]:
    """Identify and categorize different sections of the document."""
    sections = []
    lines = text.split('\n')
    current_section = {
        "content": [],
        "type": "text",
        "priority": "normal"
    }
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Detect tables
        if '|' in line and line.count('|') >= 2:
            # Found a table - collect all table rows
            if current_section["content"]:
                sections.append(current_section)
            
            table_content = []
            while i < len(lines) and ('|' in lines[i] or lines[i].strip() == ''):
                if lines[i].strip():
                    table_content.append(lines[i])
                i += 1
            
            sections.append({
                "content": table_content,
                "type": "table", 
                "priority": "high"  # Tables often contain important structured info
            })
            
            current_section = {"content": [], "type": "text", "priority": "normal"}
            continue
        
        # Detect lists (multiple consecutive list items)
        elif re.match(r'^[•·▪▫‣⁃\-\*]\s+', line) or re.match(r'^\d+\.\s+', line):
            # Found a list - collect related list items
            if current_section["content"] and current_section["type"] != "list":
                sections.append(current_section)
            
            if current_section["type"] != "list":
                current_section = {"content": [], "type": "list", "priority": "high"}
            
            current_section["content"].append(line)
            
        # Detect section headers (PAGE markers, etc.)
        elif re.match(r'^===.*===$', line) or re.match(r'^---.*---$', line):
            if current_section["content"]:
                sections.append(current_section)
            
            sections.append({
                "content": [line],
                "type": "header",
                "priority": "low"
            })
            
            current_section = {"content": [], "type": "text", "priority": "normal"}
            
        # Regular content
        else:
            if line:  # Skip empty lines
                current_section["content"].append(line)
        
        i += 1
    
    # Add final section if it has content
    if current_section["content"]:
        sections.append(current_section)
    
    return sections


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


def clean_text(text: str) -> str:
    """Clean text while preserving structure."""
    if not text:
        return ""
    
    # Remove extra whitespace while preserving structure
    text = re.sub(r' +', ' ', text).strip()
    
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text


def detect_content_type(text: str) -> str:
    """Detect the type of content in the text."""
    if not text:
        return "empty"
    
    # Check for tables
    if '|' in text and text.count('|') >= 4:
        return "table"
    
    # Check for lists
    list_patterns = [
        r'^[•·▪▫‣⁃\-\*]\s+',
        r'^\d+\.\s+',
        r'^[a-zA-Z]\.\s+'
    ]
    
    lines = text.split('\n')
    list_lines = 0
    total_lines = len([line for line in lines if line.strip()])
    
    for line in lines:
        for pattern in list_patterns:
            if re.match(pattern, line.strip()):
                list_lines += 1
                break
    
    if total_lines > 0 and list_lines / total_lines > 0.3:
        return "list"
    
    # Check for structured content (headers, sections)
    if re.search(r'^===.*===$|^---.*---$', text, re.MULTILINE):
        return "structured"
    
    # Default to regular text
    return "text"


def extract_key_phrases(text: str) -> List[str]:
    """Extract key phrases from text for better chunking decisions."""
    if not text:
        return []
    
    # Look for common QC related terms
    key_terms = [
        r'\b(policy|procedure|guideline|standard)\b',
        r'\b(quality|control|assurance|inspection)\b',
        r'\b(employee|staff|worker|personnel)\b',
        r'\b(contact|phone|email|address)\b',
        r'\b(audit|compliance|certification|accreditation)\b',
        r'\b(process|workflow|step|instruction)\b'
    ]
    
    phrases = []
    for pattern in key_terms:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end].strip()
            if context not in phrases:
                phrases.append(context)
    
    return phrases


def calculate_text_complexity(text: str) -> Dict[str, Any]:
    """Calculate various complexity metrics for text."""
    if not text:
        return {
            "word_count": 0,
            "sentence_count": 0,
            "avg_sentence_length": 0,
            "complexity_score": 0
        }
    
    words = text.split()
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    word_count = len(words)
    sentence_count = len(sentences)
    avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
    
    # Simple complexity score based on sentence length and vocabulary
    complexity_score = min(10, avg_sentence_length / 10)
    
    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": avg_sentence_length,
        "complexity_score": complexity_score
    }
