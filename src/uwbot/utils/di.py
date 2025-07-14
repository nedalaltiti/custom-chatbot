from functools import lru_cache
from typing import Optional

from uwbot.services.gemini_service import GeminiService
from uwbot.services.contact_service import ContactService
from uwbot.services.hardship_validation_service import HardshipValidationService

"""
Dependency-provider helpers for FastAPI.

Each object is created lazily once per process and can be overridden
in tests with FastAPI's dependency-override mechanism.

UWBot is focused on validation only.
"""

@lru_cache
def get_llm() -> GeminiService:
    """Return a shared GeminiService instance for validation analysis."""
    return GeminiService()


@lru_cache
def get_hardship_service() -> HardshipValidationService:
    """Return a shared HardshipValidationService instance."""
    return HardshipValidationService()


@lru_cache
def get_contact_service() -> ContactService:
    """
    Return a shared ContactService for contact database operations.
    
    This service handles:
    - Querying contact information by ID from public.contacts table
    - Searching contacts by name
    - Formatting contact responses for users
    - Extracting contact IDs from user messages
    - Validation analysis
    """
    hardship_service = get_hardship_service()
    return ContactService(hardship_service)
