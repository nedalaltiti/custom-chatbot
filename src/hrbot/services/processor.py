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
import re

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
                              user_id: str = "anonymous",
                              system_override: Optional[str] = None
                              ) -> Result[Dict]:
        """
        Process a user message with context from chat history.
        
        Args:
            user_message: The message from the user
            chat_history: Optional list of previous message strings
            user_id: User identifier for tracking
            system_override: Optional system prompt override
            
        Returns:
            Result containing the LLM response or error
        """
        # Check if this is an HR-related query first
        hr_keywords = ['leave', 'sick', 'vacation', 'policy', 'benefit', 'insurance', 'hr', 
                       'payroll', 'employee', 'work', 'office', 'attendance', 'probation',
                       'resignation', 'discount', 'medical', 'doctor', 'workstation', 'overtime',
                       'zenhr', 'manager', 'half day', 'half-day', 'team', 'company']
        
        user_message_lower = user_message.lower()
        is_hr_query = any(keyword in user_message_lower for keyword in hr_keywords)
        
        # If it's clearly not an HR query, redirect immediately to prevent hallucination
        if not is_hr_query:
            return Success({
                "response": (
                    "I'm an HR Assistant and can only help with HR-related topics and attach the HR Support link (https://hrsupport.usclarity.com/support/home) to the response.\n\n"
                    "Is there anything else I can help you with?"
                ),
                "used_rag": False,
                "user_id": user_id,
            })
        
        # For HR queries, check if we should use RAG
        if self.rag.should_use_rag(user_message, chat_history):
            rag_result = await self.rag.query(
                user_message,
                user_id=user_id,
                chat_history=chat_history,
                system_override=system_override
            )

            if rag_result.is_success():
                payload = rag_result.unwrap()
                # Format bullet points properly
                raw_response = payload.get("response", "")
                formatted_response = self._format_bullet_points(raw_response)
                payload["response"] = formatted_response
                
                # If RAG found sources, return the result
                if payload.get("sources"):
                    return rag_result
                # If no sources found but response generated and it's not a "no info" response
                if formatted_response and "No relevant information found" not in formatted_response:
                    return rag_result
            
            # If RAG didn't find relevant documents for HR query, 
            # don't fallback to direct LLM to avoid hallucination
            logger.info("RAG didn't find relevant documents for HR query, returning knowledge base message: %s", user_message)
            return Success({
                "response": (
                    "I don't have specific information about that in my knowledge base. "
                    "For detailed information about this topic, please contact the HR department.\n\n"
                    "Open an HR support ticket ➜ https://hrsupport.usclarity.com/support/home\n\n"
                    "Is there anything else I can help you with?"
                ),
                "used_rag": True,
                "user_id": user_id,
            })
        
        # If HR query but RAG not triggered, still avoid direct LLM
        logger.info("HR query but RAG not triggered, returning knowledge base message: %s", user_message)
        return Success({
            "response": (
                "I don't have specific information about that in my knowledge base. "
                "For detailed information about this topic, please contact the HR department.\n\n"
                "Open an HR support ticket ➜ https://hrsupport.usclarity.com/support/home\n\n"
                "Is there anything else I can help you with?"
            ),
            "used_rag": True,
            "user_id": user_id,
        })
        
    def _format_bullet_points(self, text: str) -> str:
        """Format bullet points to have proper spacing, ensuring each bullet point is on its own line."""
        if not text:
            return text
        
        logger.debug(f"Original text: {repr(text)}")
        
        # Step 1: Handle bullet points that are concatenated on the same line
        # This is the main issue - bullet points appearing like "point. • Next point"
        # Replace any pattern where a bullet point follows text directly
        text = re.sub(r'(\S)\s*•\s*', r'\1\n\n• ', text)
        
        # Step 2: Ensure no bullet point starts immediately after punctuation without space
        # Handle cases like "text:•" or "text.•" 
        text = re.sub(r'([.!?:,])\s*•', r'\1\n\n•', text)
        
        # Step 3: Clean up any cases where we might have created excessive spacing
        # Replace multiple consecutive newlines with just double newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Step 4: Ensure each bullet point is properly formatted
        lines = text.split('\n')
        formatted_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            if line.startswith('•'):
                # This is a bullet point
                formatted_lines.append(line)
                
                # Check if the next non-empty line is also a bullet point
                # If so, add a blank line for spacing
                next_is_bullet = False
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:  # Found next non-empty line
                        if next_line.startswith('•'):
                            next_is_bullet = True
                        break
                
                if next_is_bullet:
                    formatted_lines.append('')  # Add blank line between bullet points
                    
            elif line:  # Non-empty, non-bullet line
                formatted_lines.append(line)
            else:  # Empty line
                # Only add if the last line wasn't empty (avoid multiple empty lines)
                if formatted_lines and formatted_lines[-1] != '':
                    formatted_lines.append('')
        
        # Step 5: Join everything back together
        result = '\n'.join(formatted_lines)
        
        # Step 6: Ensure proper spacing before the final question
        result = re.sub(r'(?<!\n)\n(Is there anything else I can help you with\?)', r'\n\n\1', result)
        
        # Step 7: Final cleanup - remove any excessive spacing
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        logger.debug(f"Formatted text: {repr(result)}")
        
        return result
        
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
        # Check if this is an HR-related query first
        hr_keywords = ['leave', 'sick', 'vacation', 'policy', 'benefit', 'insurance', 'hr', 
                       'payroll', 'employee', 'work', 'office', 'attendance', 'probation',
                       'resignation', 'discount', 'medical', 'doctor', 'workstation', 'overtime',
                       'zenhr', 'manager', 'half day', 'half-day', 'team', 'company']
        
        user_message_lower = user_message.lower()
        is_hr_query = any(keyword in user_message_lower for keyword in hr_keywords)
        
        # If it's clearly not an HR query, redirect immediately to prevent hallucination
        if not is_hr_query:
            response = (
                "I'm an HR Assistant and can only help with HR-related topics and attach the HR Support link (https://hrsupport.usclarity.com/support/home) to the response.\n\n"
                "Is there anything else I can help you with?"
            )
            yield response
            return
        
        if self.rag.should_use_rag(user_message, chat_history):
            # Try RAG first
            has_content = False
            async for chunk in self.rag.query_streaming(
                user_message,
                chat_history=chat_history,
            ):
                has_content = True
                yield chunk
            
            # If RAG yielded content, we're done
            if has_content:
                return
            
            # If RAG didn't yield content for HR query, 
            # don't fallback to direct LLM to avoid hallucination
            logger.info("RAG didn't find relevant documents for HR query in streaming, returning knowledge base message: %s", user_message)
            response = (
                "I don't have specific information about that in my knowledge base. "
                "For detailed information about this topic, please contact the HR department.\n\n"
                "Open an HR support ticket ➜ https://hrsupport.usclarity.com/support/home\n\n"
                "Is there anything else I can help you with?"
            )
            yield response
            return
        
        # If HR query but RAG not triggered, still avoid direct LLM
        response = (
            "I don't have specific information about that in my knowledge base. "
            "For detailed information about this topic, please contact the HR department.\n\n"
            "Open an HR support ticket ➜ https://hrsupport.usclarity.com/support/home\n\n"
            "Is there anything else I can help you with?"
        )
        yield response 