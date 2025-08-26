from functools import lru_cache
from typing import Optional
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from uwbot.services.gemini_service import GeminiService
from uwbot.services.external_validation_client import ExternalValidationClient
from uwbot.db.session import get_db_session
from uwbot.config.settings import settings

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

# Global cache for external validation client
_external_validation_client = None
_cached_timeout = None

def get_external_validation_client() -> ExternalValidationClient:
    """Return a shared ExternalValidationClient instance with cache invalidation on timeout change."""
    global _external_validation_client, _cached_timeout
    
    current_timeout = settings.external_validation.timeout
    
    # Create new client if timeout changed or no client exists
    if _external_validation_client is None or _cached_timeout != current_timeout:
        if _external_validation_client is not None:
            # Close old client if it exists
            try:
                import asyncio
                asyncio.create_task(_external_validation_client.client.aclose())
            except Exception:
                pass  # Ignore cleanup errors
        
        _external_validation_client = ExternalValidationClient(
            api_base_url=settings.external_validation.api_base_url,
            timeout=current_timeout
        )
        _cached_timeout = current_timeout
        
    return _external_validation_client

# External validation client dependency for FastAPI
async def get_contact_validation_uc(
    session: AsyncSession = Depends(get_db_session),   # ← one session per request
) -> ExternalValidationClient:
    """Get external validation client for contact validation."""
    return get_external_validation_client()

async def get_combined_validation_uc(
    session: AsyncSession = Depends(get_db_session),   # ← one session per request
) -> ExternalValidationClient:
    """Get external validation client for combined validation."""
    return get_external_validation_client()

# Teams feedback handler
@lru_cache
def get_feedback_service():
    """Get shared feedback service singleton."""
    from uwbot.services.feedback_service import FeedbackService
    return FeedbackService()  # This will now return the singleton instance

@lru_cache
def get_teams_feedback_handler():
    """Get teams feedback handler singleton."""
    from uwbot.services.teams_feedback_handler import TeamsFeedbackHandler
    
    feedback_service = get_feedback_service()
    return TeamsFeedbackHandler(feedback_service)

# Card action handler
@lru_cache
def get_card_action_handler():
    """Get card action handler singleton."""
    from uwbot.services.card_action_handler import CardActionHandler
    from uwbot.infrastructure.teams_adapter import TeamsAdapter
    
    feedback_service = get_feedback_service()
    teams_adapter = TeamsAdapter()
    return CardActionHandler(feedback_service, teams_adapter)

# Feedback card tracker
@lru_cache
def get_feedback_card_tracker():
    """Get feedback card tracker singleton."""
    from uwbot.services.feedback_card_tracker import FeedbackCardTracker
    from uwbot.infrastructure.teams_adapter import TeamsAdapter
    
    teams_adapter = TeamsAdapter()
    return FeedbackCardTracker(teams_adapter)
