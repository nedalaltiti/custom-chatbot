"""
Utilities for adapting existing services to the new RAG core.

Currently provides:
• LLMServiceAdapter – wraps our concrete GeminiService (or any service exposing analyze_* methods)
  so it satisfies the LLMProvider Protocol expected by `core.rag`.
"""

import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

from hrbot.core.rag import LLMProvider
from hrbot.services.gemini_service import GeminiService
from hrbot.utils.result import Result

logger = logging.getLogger(__name__)

class LLMServiceAdapter(LLMProvider):
    """Adapter so existing GeminiService conforms to the new `LLMProvider` protocol."""

    def __init__(self, llm_service: Optional[GeminiService] = None):
        self.llm_service = llm_service or GeminiService()
        logger.debug("LLMServiceAdapter initialised")

    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        # `GeminiService.analyze_messages` expects a list of messages
        return await self.llm_service.analyze_messages([prompt])

    async def generate_response_streaming(self, prompt: str) -> AsyncGenerator[str, None]:
        async for chunk in self.llm_service.analyze_messages_streaming([prompt]):
            yield chunk 