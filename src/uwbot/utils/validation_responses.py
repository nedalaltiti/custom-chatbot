"""
Validation Response Formats for uwbot

This module centralizes all response formatting for validation services:
- Error responses
- Help messages
- Invalid contact ID responses

Provides consistent formatting across all validation endpoints.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ValidationResult(Enum):
    """Enum for validation result types."""
    PASS = "pass"
    NO_PASS = "no_pass"
    MIXED = "mixed"
    NO_DATA = "no_data"
    ERROR = "error"


@dataclass
class ValidationResponse:
    """Structured validation response data."""
    contact_id: int
    result: ValidationResult
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ValidationResponseFormatter:
    """Centralized formatter for all validation responses."""
    
    @staticmethod
    def format_no_data_response(contact_id: int, validation_type: str = "validation") -> str:
        """Format response when no data is available."""
        return f"Contact {contact_id} does not have {validation_type} data.\nNo {validation_type} information has been recorded for this contact."
    
    @staticmethod
    def format_error_response(contact_id: int, error_message: str, validation_type: str = "validation") -> str:
        """Format error response."""
        return f"Contact {contact_id} {validation_type} error.\n{error_message}"
    
    @staticmethod
    def format_invalid_contact_id_response(contact_id: int) -> str:
        """Format response for invalid contact ID."""
        return f"Invalid contact ID: {contact_id}. Please provide a valid contact ID between 1 and 99,999,999,999."
    
    @staticmethod
    def format_help_message() -> str:
        """Format help message for users."""
        return (
            "I'm here to help you with underwriting validation.\n"
            "Please provide a valid contact ID in the Underwriting Stage to check validation data.\n\n"
        )
    
    @staticmethod
    def format_goodbye_message() -> str:
        """Format goodbye message."""
        return "You're welcome! I'm glad I could help you with your underwriting validation check. Feel free to reach out anytime you need to validate data for other contacts. Have a great day! 👋"
    
    @staticmethod
    def format_debug_help_message() -> str:
        """Format help message for debug endpoint."""
        return (
            "I'm here to help you check underwriting validation data. "
            "Please provide a contact ID to check if validation data exists.\n\n"
        )


# Convenience functions for easy access
def format_no_data_response(contact_id: int, validation_type: str = "validation") -> str:
    """Format no data response."""
    return ValidationResponseFormatter.format_no_data_response(contact_id, validation_type)


def format_error_response(contact_id: int, error_message: str, validation_type: str = "validation") -> str:
    """Format error response."""
    return ValidationResponseFormatter.format_error_response(contact_id, error_message, validation_type)


def format_invalid_contact_id_response(contact_id: int) -> str:
    """Format invalid contact ID response."""
    return ValidationResponseFormatter.format_invalid_contact_id_response(contact_id)


def format_help_message() -> str:
    """Format help message."""
    return ValidationResponseFormatter.format_help_message()


def format_goodbye_message() -> str:
    """Format goodbye message."""
    return ValidationResponseFormatter.format_goodbye_message()


def format_debug_help_message() -> str:
    """Format debug help message."""
    return ValidationResponseFormatter.format_debug_help_message() 