"""
LLM Service Adapter for UWBot.

Provides:
• LLMServiceAdapter – wraps our concrete GeminiService for direct LLM processing
"""

import logging
from typing import Dict, List, Any, Optional, Protocol

from uwbot.services.gemini_service import GeminiService
from uwbot.utils.result import Result

logger = logging.getLogger(__name__)

class LLMProvider(Protocol):
    """Simple protocol for LLM services."""
    
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        """Generate a response from the LLM."""
        ...

class LLMServiceAdapter(LLMProvider):
    """Adapter for GeminiService to provide direct LLM processing."""

    def __init__(self, llm_service: Optional[GeminiService] = None):
        self.llm_service = llm_service or GeminiService()
        logger.debug("LLMServiceAdapter initialised")

    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        # `GeminiService.analyze_messages` expects a list of messages
        return await self.llm_service.analyze_messages([prompt]) 