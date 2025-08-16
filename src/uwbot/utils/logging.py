"""
Logging utilities with PII (Personally Identifiable Information) filtering.

This module provides logging configuration with automatic masking of sensitive data
like contact IDs, phone numbers, and other PII in log messages.
"""

import logging
import re
from typing import Optional


class PIIFilter(logging.Filter):
    """Filter to mask PII (Personally Identifiable Information) in log messages."""
    
    def __init__(self, name: str = ""):
        super().__init__(name)
        # Patterns for contact ID masking only
        self.pii_patterns = [
            # Contact IDs - various formats
            (r'contact[_\s]+(?:id[_\s]+)?(\d{4,})', 
             lambda m: f'contact_id_***{m.group(1)[-3:]}'),
            (r'(\d{4,})\s+(?:contact|user|id)', 
             lambda m: f'contact_id_***{m.group(1)[-3:]}'),
            (r'contact[_\s]+#?(\d{4,})', 
             lambda m: f'contact_id_***{m.group(1)[-3:]}'),
            (r'user[_\s]+(\d{4,})', 
             lambda m: f'user_id_***{m.group(1)[-3:]}'),
            (r'id[_\s]+(\d{4,})', 
             lambda m: f'id_***{m.group(1)[-3:]}'),
            # Standalone contact IDs (4+ digits) - but only in log messages, not config values
            (r'\b(\d{4,})\b', 
             lambda m: f'contact_id_***{m.group(1)[-3:]}'),
        ]
    
    def filter(self, record):
        """Filter and mask PII in log records."""
        if hasattr(record, 'msg') and record.msg:
            # Convert to string if not already
            msg = str(record.msg)
            
            # Apply all PII patterns
            for pattern, replacement in self.pii_patterns:
                msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
            
            # Update the record message
            record.msg = msg
            
            # Also check args if they exist
            if hasattr(record, 'args') and record.args:
                new_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        # Apply PII masking to string arguments
                        masked_arg = arg
                        for pattern, replacement in self.pii_patterns:
                            masked_arg = re.sub(pattern, replacement, masked_arg, flags=re.IGNORECASE)
                        new_args.append(masked_arg)
                    else:
                        new_args.append(arg)
                record.args = tuple(new_args)
        
        return True


def setup_logging_with_pii_filter(
    level: int = logging.INFO,
    format_string: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    add_pii_filter: bool = True
) -> None:
    """
    Setup logging with PII filtering.
    
    Args:
        level: Logging level
        format_string: Log format string
        add_pii_filter: Whether to add PII filtering
    """
    # Configure basic logging
    logging.basicConfig(
        level=level,
        format=format_string,
        force=True  # Override any existing configuration
    )
    
    # Add PII filter to root logger
    if add_pii_filter:
        root_logger = logging.getLogger()
        pii_filter = PIIFilter()
        
        # Remove existing PII filters to avoid duplicates
        for handler in root_logger.handlers:
            for filter_obj in list(handler.filters):
                if isinstance(filter_obj, PIIFilter):
                    handler.removeFilter(filter_obj)
            handler.addFilter(pii_filter)
        
        # Also add to root logger itself
        root_logger.addFilter(pii_filter)


def get_logger_with_pii_filter(name: str) -> logging.Logger:
    """
    Get a logger with PII filtering applied.
    
    Args:
        name: Logger name
        
    Returns:
        Logger with PII filtering
    """
    logger = logging.getLogger(name)
    
    # Add PII filter if not already present
    has_pii_filter = any(
        isinstance(f, PIIFilter) for f in logger.filters
    )
    
    if not has_pii_filter:
        logger.addFilter(PIIFilter())
    
    return logger


# Convenience function for quick PII masking
def mask_pii(text: str) -> str:
    """
    Mask PII in a text string.
    
    Args:
        text: Text to mask
        
    Returns:
        Text with PII masked
    """
    if not text:
        return text
    
    filter_obj = PIIFilter()
    # Create a dummy record to use the filter
    record = logging.LogRecord(
        name="dummy",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=text,
        args=(),
        exc_info=None
    )
    
    filter_obj.filter(record)
    return record.msg 