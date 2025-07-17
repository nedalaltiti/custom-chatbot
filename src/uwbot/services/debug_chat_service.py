"""
Debug Chat Service

This service handles debug chat functionality for testing and QA purposes,
separating the debug chat processing logic from the main router.
"""

import logging
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel
from uwbot.services.contact_service import ContactService
from uwbot.services.message_service import MessageService
from uwbot.services.session_tracker import session_tracker
from uwbot.utils.bot_name import get_bot_name
from uwbot.utils.validation_responses import format_debug_help_message

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
    
    def __init__(self, contact_service: ContactService, message_service: MessageService):
        self.contact_service = contact_service
        self.message_service = message_service
    
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
            contact_id = self.contact_service.extract_contact_id_from_message(req.text)
            
            processing_time = time.time() - start_time
            
            if contact_id:
                # Process contact validation
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
        Process contact validation for debug chat.
        
        Args:
            contact_id: The contact ID to validate
            user_id: The user ID
            session_id: The session ID
            user_msg_id: The user message ID
            
        Returns:
            The bot response text
        """
        # Check hardship validation data
        result = await self.contact_service.analyze_contact_hardship(contact_id)
        bot_response = self.contact_service.format_contact_response(result)
        
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
    
    async def test_contact_extraction(self, message: str) -> Optional[int]:
        """
        Test contact ID extraction from a message.
        
        Args:
            message: The message to test
            
        Returns:
            The extracted contact ID or None
        """
        return self.contact_service.extract_contact_id_from_message(message)
    
    async def get_debug_stats(self) -> Dict[str, Any]:
        """
        Get debug service statistics.
        
        Returns:
            Dictionary with debug service statistics
        """
        return {
            "service_name": "DebugChatService",
            "contact_service_available": self.contact_service is not None,
            "message_service_available": self.message_service is not None,
            "session_tracker_available": session_tracker is not None
        } 