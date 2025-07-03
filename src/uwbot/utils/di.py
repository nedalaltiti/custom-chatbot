from functools import lru_cache
from typing import Optional

from uwbot.services.gemini_service import GeminiService
from uwbot.services.intent_service import IntentDetectionService
from uwbot.services.content_classification_service import ContentClassificationService
from uwbot.services.contact_service import ContactService
from uwbot.services.hardship_validation_service import HardshipValidationService

"""
Dependency-provider helpers for FastAPI.

Each object is created lazily once per process and can be overridden
in tests with FastAPI's dependency-override mechanism.

UWBot uses direct LLM processing without RAG or knowledge base.
"""

@lru_cache
def get_llm() -> GeminiService:
    """Return a shared GeminiService instance."""
    return GeminiService()


@lru_cache
def get_intent_service() -> IntentDetectionService:
    """
    Return a shared IntentDetectionService for conversation flow control.
    
    This service handles CONVERSATION MANAGEMENT INTENT:
    - Determines when users want to CONTINUE vs END conversations
    - Used after "Is there anything else I can help you with?" questions
    - Prevents false positives like "cool, what about X?" ending sessions
    
    Note: This is separate from RESPONSE TONE INTENT which is integrated 
    into the prompt system for determining empathetic vs neutral responses.
    """
    return IntentDetectionService(llm_service=get_llm())


@lru_cache
def get_content_classification_service() -> ContentClassificationService:
    """
    Return a shared ContentClassificationService for intelligent conversation flow analysis.
    
    This service determines:
    - When conversations should end and feedback should be collected
    - Appropriate response strategies for different content types
    - Safety interventions and policy violations
    - Smart redirection for off-topic queries
    
    Uses LLM analysis instead of hardcoded keywords for better accuracy.
    """
    return ContentClassificationService(llm_service=get_llm())


@lru_cache
def get_contact_service() -> ContactService:
    """
    Return a shared ContactService for contact database operations.
    
    This service handles:
    - Querying contact information by ID from public.contacts table
    - Searching contacts by name
    - Formatting contact responses for users
    - Extracting contact IDs from user messages
    """
    return ContactService()


@lru_cache
def get_hardship_validation_service() -> HardshipValidationService:
    return HardshipValidationService(get_llm())
