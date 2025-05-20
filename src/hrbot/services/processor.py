"""
Chat processor for handling user messages with LLM integration.

This module coordinates chat processing to:
1. Process user messages with appropriate context
2. Manage conversation history and state
3. Handle both standard and streaming responses
"""

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio

from hrbot.services.gemini_service import GeminiService
from hrbot.core.adapters.llm_gemini import LLMServiceAdapter   
from hrbot.core.rag.engine import RAG
from hrbot.utils.result import Result, Success

logger = logging.getLogger(__name__)

class ChatProcessor:
    """
    Processor for handling chat messages with LLM service.
    
    Provides context-aware chat processing using:
    - LLM service for generation
    - Conversation memory for context
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """
        Initialize the chat processor.
        
        Args:
            llm_service: Service for LLM interaction (optional)
        """
        # Create or use the provided LLM service
        self.llm_service = llm_service or GeminiService()
        # Create an adapter so RAG can use the same LLM interface
        self.rag = RAG(llm_provider=LLMServiceAdapter(self.llm_service))
        
        logger.info("ChatProcessor initialised (RAG enabled)")
    
    async def process_message(self, 
                             user_message: str, 
                             chat_history: Optional[List[str]] = None,
                             user_id: str = "anonymous") -> Result[Dict]:
        """
        Process a user message with context from chat history.
        
        Args:
            user_message: The message from the user
            chat_history: Optional list of previous message strings
            user_id: User identifier for tracking
            
        Returns:
            Result containing the LLM response or error
        """
        # Always use RAG; if no knowledge found return safe response
        rag_result = await self.rag.query(
            user_message,
            user_id=user_id,
            chat_history=chat_history,
        )

        if rag_result.is_success():
            payload = rag_result.unwrap()
            # If no sources returned, respond with safe fallback
            if not payload.get("sources"):
                return Success({
                    "response": (
                        "Kindly contact the HR department for further details.\n\n"
                        "Open a support ticket ➜ https://hrsupport.usclarity.com/support/home"
                    ),
                    "used_rag": True,
                    "user_id": user_id,
                })
            return rag_result

        # If RAG errored, return generic refusal
        return Success({
            "response": (
                "Kindly contact the HR department for further details.\n\n"
                "Open a support ticket ➜ https://hrsupport.usclarity.com/support/home"
            ),
            "used_rag": True,
            "user_id": user_id,
        })
        
    async def process_message_streaming(self,
                                      user_message: str,
                                      chat_history: Optional[List[str]] = None,
                                      user_id: str = "anonymous") -> AsyncGenerator[str, None]:
        """
        Process a user message with streaming response.
        
        Args:
            user_message: The message from the user
            chat_history: Optional list of previous message strings
            user_id: User identifier for tracking
            
        Yields:
            Chunks of the response as they are generated
        """
        if self.rag.should_use_rag(user_message, chat_history):
            async for chunk in self.rag.query_streaming(
                user_message,
                chat_history=chat_history,
            ):
                yield chunk
            return
        messages = [] if not chat_history else list(chat_history)
        messages.append(user_message)
        async for chunk in self.llm_service.analyze_messages_streaming(messages):
            yield chunk 