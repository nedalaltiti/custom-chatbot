"""
Chat processor for handling user messages with LLM integration.

This module coordinates chat processing to:
1. Process user messages with appropriate context
2. Manage conversation history and state
3. Handle both standard and streaming responses

UWBot uses direct LLM processing without RAG or knowledge base.
"""

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import re

from uwbot.services.gemini_service import GeminiService
from uwbot.core.adapters.llm_gemini import LLMServiceAdapter   
from uwbot.utils.result import Result, Success

logger = logging.getLogger(__name__)

class ChatProcessor:
    """
    Simplified processor for handling chat messages with direct LLM processing.
    
    Optimized for:
    - Low latency processing
    - Direct LLM responses without knowledge base
    - Simple conversation management
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """
        Initialize the chat processor.
        
        Args:
            llm_service: Service for LLM interaction (optional)
        """
        # Create or use the provided LLM service
        self.llm_service = llm_service or GeminiService()
        # Create LLM adapter for direct processing
        self.llm_adapter = LLMServiceAdapter(self.llm_service)
        
        logger.info("ChatProcessor initialized with direct LLM processing")
    
    async def process_message(self,
                              user_message: str,
                              chat_history: Optional[List[str]] = None,
                              user_id: str = "anonymous",
                              system_override: Optional[str] = None
                              ) -> Result[Dict]:
        """
        Process a user message using direct LLM processing.
        
        Uses LLM directly without RAG or knowledge base retrieval.
        
        Args:
            user_message: The message from the user
            chat_history: Optional list of previous message strings
            user_id: User identifier for tracking
            system_override: Optional system prompt override
            
        Returns:
            Result containing the LLM response or error
        """
        logger.debug(f"Processing message: '{user_message[:50]}...' for user {user_id}")
        
        try:
            # Commented out chat_history/context logic for previous questions
            # In process_message and process_message_streaming, do not use chat_history
            # Only use user_message (and system_override if present)
            # For example:
            messages = []
            if system_override:
                messages.append(system_override)
            messages.append(user_message)
            result = await self.llm_adapter.generate_response("\n".join(messages))
            
            if result.is_success():
                response_data = result.unwrap()
                response_text = response_data.get("response", "I'm sorry, I couldn't process your request.")
                
                return Success({
                    "response": response_text,
                    "confidence_level": "high",  # Direct LLM responses are considered high confidence
                    "sources": [],  # No sources since we're not using RAG
                    "user_id": user_id
                })
            else:
                logger.error(f"LLM processing failed: {result.error}")
                return result
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return Result(error=f"Processing error: {str(e)}")
        
    def _format_bullet_points(self, text: str) -> str:
        """
        Format bullet points to ensure proper spacing and prevent same-line issues.
        
        This method enforces strict formatting rules:
        - Every bullet point starts on a new line
        - Sub-items after colons are properly indented
        - No bullet points run together on the same line
        """
        if not text:
            return text
        
        # Step 1: Ensure bullet points never appear inline after colons
        # Pattern: "Text: • Item" should become "Text:\n• Item"
        text = re.sub(r':\s*•', ':\n\n•', text)
        
        # Step 2: Handle cases where multiple bullet points are on the same line
        # Pattern: "• Item1 • Item2" should become "• Item1\n\n• Item2"
        text = re.sub(r'(•[^•\n]+?)\s*•', r'\1\n\n•', text)
        
        # Step 3: Ensure bullet points after any non-newline character get proper spacing
        # Pattern: "text• Item" should become "text\n\n• Item"
        text = re.sub(r'([^\n])\s*•\s*', r'\1\n\n• ', text)
        
        # Step 4: Fix any bullet points that don't have proper spacing before them
        text = re.sub(r'(?<!\n\n)•', '\n\n•', text)
        
        # Step 5: Clean up excessive spacing (but preserve intentional double spacing)
        text = re.sub(r'\n{4,}', '\n\n', text)
        
        # Step 6: Ensure proper formatting between sections
        lines = text.split('\n')
        formatted_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('•'):
                # This is a bullet point
                formatted_lines.append(line)
                
                # Check if we need spacing after this bullet point
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Add spacing before next bullet point or major section
                    if next_line.startswith('•') or next_line.startswith('**') or len(next_line) > 50:
                        formatted_lines.append('')
                        
            elif line.startswith('-') and len(formatted_lines) > 0:
                # This is a sub-item, should be indented
                formatted_lines.append(f"  {line}")
                
            elif line:
                # Regular text
                formatted_lines.append(line)
                
            else:
                # Empty line - preserve single empty lines, avoid excessive spacing
                if formatted_lines and formatted_lines[-1] != '':
                    formatted_lines.append('')
            
            i += 1
        
        # Step 7: Final formatting touches
        result = '\n'.join(formatted_lines)
        
        # Ensure the closing question has proper spacing
        result = re.sub(r'(?<!\n)\n(Is there anything else I can help you with\?)', r'\n\n\1', result)
        
        # Final cleanup of excessive newlines
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        # Ensure text doesn't start with newlines
        result = result.lstrip('\n')
        
        return result
        
    async def process_message_streaming(
        self,
        user_message: str,
        chat_history: Optional[List[str]] = None,
        user_id: str = "anonymous",
        system_override: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Process a user message with streaming response using direct LLM processing.
        
        Args:
            user_message: The message from the user
            chat_history: Optional list of previous message strings
            user_id: User identifier for tracking
            system_override: Optional system prompt override
            
        Yields:
            Chunks of the response as they are generated
        """
        logger.debug(f"Processing streaming message: '{user_message[:50]}...' for user {user_id}")
        
        try:
            # Commented out chat_history/context logic for previous questions
            # In process_message and process_message_streaming, do not use chat_history
            # Only use user_message (and system_override if present)
            # For example:
            messages = []
            if system_override:
                messages.append(system_override)
            messages.append(user_message)
            result = await self.llm_adapter.generate_response("\n".join(messages))
            
            # Stream with LLM
            async for chunk in self.llm_adapter.generate_response_streaming("\n".join(messages)):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error in streaming message processing: {e}")
            yield "I'm sorry, I encountered an error processing your request." 