"""
Utilities for adapting existing services to the new RAG core.

Currently provides:
• LLMServiceAdapter – wraps our concrete GeminiService (or any service exposing analyze_* methods)
  so it satisfies the LLMProvider Protocol expected by `core.rag`.
"""

import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

from qcbot.core.rag.engine import LLMProvider
from qcbot.services.gemini_service import GeminiService
from qcbot.utils.result import Result

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
        # The prompt from RAG engine is already a complete formatted prompt
        # We need to pass it as a single message to the Gemini service
        if not prompt or not prompt.strip():
            yield "I'm having trouble processing your request right now."
            return
            
        async for chunk in self.llm_service.analyze_messages_streaming([prompt]):
            yield chunk 