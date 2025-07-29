"""
Debug Chat Service

This service handles debug chat functionality for testing and QA purposes,
separating the debug chat processing logic from the main router.
"""

import logging
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel
from uwbot.services.message_service import MessageService
from uwbot.services.session_tracker import session_tracker
from uwbot.utils.bot_name import get_bot_name
from uwbot.utils.validation_responses import format_debug_help_message
from uwbot.services.external_validation_client import ExternalValidationClient
from uwbot.config.settings import settings

logger = logging.getLogger(__name__)


class DebugChatRequest(BaseModel):
    """Request model for debug chat endpoint."""
    text: str
    user_id: str = "debug-user"


class DebugChatResponse(BaseModel):
    """Response model for debug chat endpoint."""
    user_message: str
    bot_response: str
    processing_time: float


class DebugChatService:
    """Service for handling debug chat functionality."""
    
    def __init__(self, message_service: MessageService):
        self.message_service = message_service
        self.external_validation_client = ExternalValidationClient(
            api_base_url=settings.external_validation.api_base_url,
            timeout=settings.external_validation.timeout
        )
    
    async def process_debug_chat(self, req: DebugChatRequest) -> DebugChatResponse:
        """
        Process a debug chat request and return the response.
        
        Args:
            req: The debug chat request
            
        Returns:
            DebugChatResponse with the processed result
        """
        start_time = time.time()
        
        try:
            # Create a session ID for this debug conversation
            session_id = session_tracker.get(req.user_id)
            
            # Save user message to database
            user_msg_id = await self._save_user_message(req, session_id)
            
            # Check if message contains contact ID
            contact_id = self._extract_contact_id_from_message(req.text)
            
            processing_time = time.time() - start_time
            
            if contact_id:
                # Process contact validation using external API
                bot_response = await self._process_contact_validation(contact_id, req.user_id, session_id, user_msg_id)
            else:
                # No contact ID found - provide help message
                bot_response = await self._process_help_message(req.user_id, session_id, user_msg_id)
            
            return DebugChatResponse(
                user_message=req.text,
                bot_response=bot_response,
                processing_time=round(processing_time, 2)
            )
                
        except Exception as e:
            logger.error(f"Debug chat error: {e}")
            processing_time = time.time() - start_time
            return DebugChatResponse(
                user_message=req.text,
                bot_response=f"Error: {str(e)}",
                processing_time=round(processing_time, 2)
            )
    
    async def _save_user_message(self, req: DebugChatRequest, session_id: str) -> int:
        """
        Save the user message to the database.
        
        Args:
            req: The debug chat request
            session_id: The session ID
            
        Returns:
            The message ID of the saved user message
        """
        return await self.message_service.add_message(
            bot_name=get_bot_name(),
            env="development",
            channel="debug",  # Using 'debug' channel to distinguish from teams
            user_id=req.user_id,
            session_id=session_id,
            role="user",
            text=req.text,
            intent=None,
            reply_to_id=None,
        )
    
    async def _process_contact_validation(
        self, 
        contact_id: int, 
        user_id: str, 
        session_id: str, 
        user_msg_id: int
    ) -> str:
        """
        Process contact validation for debug chat using external API.
        
        Args:
            contact_id: The contact ID to validate
            user_id: The user ID
            session_id: The session ID
            user_msg_id: The user message ID
            
        Returns:
            The bot response text
        """
        # Call external validation API
        validation_result = await self.external_validation_client.validate_combined(
            contact_id=contact_id,
            user_id=user_id,
            user_name="debug-user"
        )
        
        if validation_result.is_success():
            bot_response = validation_result.value.get('message', 'No response available')
        else:
            # Handle validation error
            error_msg = validation_result.error
            if "Invalid contact ID" in error_msg:
                from uwbot.utils.validation_responses import format_invalid_contact_id_response
                bot_response = format_invalid_contact_id_response(contact_id)
            else:
                from uwbot.utils.validation_responses import format_error_response
                bot_response = format_error_response(contact_id, f"Error validating contact {contact_id}: {error_msg}", "validation")
        
        # Save bot response to database
        await self.message_service.add_message(
            bot_name=get_bot_name(),
            env="development", 
            channel="debug",
            user_id=user_id,
            session_id=session_id,
            role="bot",
            text=bot_response,
            intent="validation",
            reply_to_id=user_msg_id,
        )
        
        return bot_response
    
    async def _process_help_message(
        self, 
        user_id: str, 
        session_id: str, 
        user_msg_id: int
    ) -> str:
        """
        Process help message for debug chat when no contact ID is found.
        
        Args:
            user_id: The user ID
            session_id: The session ID
            user_msg_id: The user message ID
            
        Returns:
            The bot response text
        """
        # No contact ID found - provide help message
        bot_response = format_debug_help_message()
        
        # Save bot response to database
        await self.message_service.add_message(
            bot_name=get_bot_name(),
            env="development",
            channel="debug", 
            user_id=user_id,
            session_id=session_id,
            role="bot",
            text=bot_response,
            intent="help",
            reply_to_id=user_msg_id,
        )
        
        return bot_response
    
    def _extract_contact_id_from_message(self, message: str) -> Optional[int]:
        """
        Extract contact ID from user message using various patterns.
        
        Args:
            message: The message to test
            
        Returns:
            The extracted contact ID or None
        """
        import re
        
        # Look for patterns like "ID 123", "contact 456", "user 789", etc.
        # Only capture positive numbers (no negative numbers)
        patterns = [
            r'(?:contact|user|id|person)\s+(?:#)?(\d+)',
            r'(\d+)\s+(?:contact|user|id)',
            r'find\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'get\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'look\s+up\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'search\s+for\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'(\d+)',  # Fallback: just look for any positive number
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                try:
                    contact_id = int(match.group(1))
                    # Validate the extracted contact ID
                    if 1 <= contact_id <= 99_999_999_999:
                        return contact_id
                    else:
                        logger.warning(f"Extracted invalid contact ID from message: {contact_id}")
                        return None
                except (ValueError, IndexError):
                    continue
        
        return None
    
    async def test_contact_extraction(self, message: str) -> Optional[int]:
        """
        Test contact ID extraction from a message.
        
        Args:
            message: The message to test
            
        Returns:
            The extracted contact ID or None
        """
        return self._extract_contact_id_from_message(message)
    
    async def get_debug_stats(self) -> Dict[str, Any]:
        """
        Get debug service statistics.
        
        Returns:
            Dictionary with debug service statistics
        """
        return {
            "service_name": "DebugChatService",
            "message_service_available": self.message_service is not None,
            "session_tracker_available": session_tracker is not None,
            "external_validation_client_available": self.external_validation_client is not None,
            "external_validation_api_url": settings.external_validation.api_base_url
        } 