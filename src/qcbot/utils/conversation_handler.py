"""
Conversation Handler Utility for QC Bot

This utility handles conversation flow, greeting logic, and session management,
separating the conversation processing logic from the main router.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from qcbot.infrastructure.teams_adapter import TeamsAdapter
from qcbot.infrastructure.cards import create_welcome_card
from qcbot.services.feedback_service import MemoryEfficientFeedbackService
from qcbot.services.message_service import MessageService
from qcbot.utils.message import split_greeting, is_pure_greeting
from qcbot.utils.bot_name import get_bot_name
from qcbot.utils.di import get_intent_service
from qcbot.utils.intent import classify_intent
from qcbot.services.gemini_service import GeminiService
from qcbot.services.session_tracker import session_tracker
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationHandler:
    """High-level conversation orchestration util."""
    
    def __init__(self, feedback_service: MemoryEfficientFeedbackService, teams_adapter: TeamsAdapter, message_service: MessageService, session_service):
        self.feedback_service = feedback_service
        self.teams_adapter = teams_adapter
        self.message_service = message_service
        self.session_service = session_service
    
    async def handle_conversation_ending(
        self,
        flow_type: str, 
        user_id: str, 
        service_url: str, 
        conv_id: str, 
        state: dict, 
        user_message: str, 
        session_id: str, 
        reply_to_id: str = None,
        feedback_card_tracker = None
    ) -> None:
        """Handle conversation ending scenarios with appropriate feedback."""
        logger.info(f"Handling conversation ending for user {user_id} with flow_type: {flow_type}")
        
        # Save the user's message before ending
        await self._ensure_user_message_saved(user_message, user_id, session_id, reply_to_id)
        
        # Get intent service for flow analysis
        from qcbot.utils.di import get_intent_service
        intent_service = get_intent_service()
        
        # Send appropriate ending message based on flow type
        if flow_type == "end":
            ending_message = "Thank you for using our QC Assistant! Feel free to reach out anytime you need assistance."
        elif flow_type == "goodbye":
            ending_message = "Goodbye! Have a great day!"
        else:
            ending_message = "Thank you for your time. Take care!"
        
        # Send ending message and track it
        try:
            activity_id = await self.teams_adapter.send_message(service_url, conv_id, ending_message)
            
            # Store bot message and track the mapping
            bot_msg_id = await self._persist_bot_msg(0, ending_message, flow_type)
            if bot_msg_id and activity_id:
                self.feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                logger.debug(f"Tracked ending mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        except Exception as e:
            logger.error(f"Error sending ending message: {e}")
        
        # Clear user session and feedback cards
        if feedback_card_tracker:
            feedback_card_tracker.clear_user_feedback_cards(user_id)
        self.feedback_service.clear_user_session(user_id)
    
    async def _ensure_user_message_saved(
        self, 
        user_message: str, 
        user_id: str, 
        session_id: str, 
        reply_to_id: str = None
    ) -> int:
        """Ensure user message is saved to database and return message ID."""
        try:
            # Check if message already exists to avoid duplicates
            # This is a simplified check - in production you might want more sophisticated deduplication
            message_id = await self.message_service.add_message(
                bot_name=get_bot_name(),
                env="development",
                channel="teams",
                user_id=user_id,
                session_id=session_id,
                role="user",
                text=user_message,
                intent=None,
                reply_to_id=reply_to_id,
            )
            return message_id
        except Exception as e:
            logger.error(f"Error saving user message: {e}")
            # Return a placeholder ID to prevent crashes
            return 0
    
    async def handle_greeting_logic(
        self,
        user_message: str,
        user_id: str,
        user_name: str,
        service_url: str,
        conv_id: str,
        state: dict,
        first_time_users: set,
        feedback_cards: dict
    ) -> Tuple[bool, str]:
        """
        Handle greeting logic and return whether to continue processing and the processed message.
        
        Returns:
            Tuple of (should_continue, processed_message)
        """
        greet_only, user_payload = split_greeting(user_message)
        is_only_greeting = is_pure_greeting(user_message)
        
        logger.debug(f"Greeting analysis for '{user_message}': greet_only={greet_only}, has_payload={bool(user_payload)}, is_pure_greeting={is_only_greeting}")

        # Show greeting card for first-time users if ANY greeting is detected
        if (greet_only or user_payload) and not state.get("awaiting_more_help"):
            # Check if we should show greeting card:
            # 1. First-time user (in first_time_users set) - always show
            # 2. OR returning user starting a new session (greeting_shown=False AND it's a greeting)
            is_first_time = user_id in first_time_users
            is_new_session_greeting = not state.get("greeting_shown", False)
            
            should_show_greeting = is_first_time or is_new_session_greeting
            
            logger.info(f"Greeting logic for user {user_id}: is_first_time={is_first_time}, is_new_session_greeting={is_new_session_greeting}, should_show_greeting={should_show_greeting}")
            
            if should_show_greeting:
                # Show welcome card ONLY once per session
                logger.info(f"Showing welcome card to user {user_id} (first_time={is_first_time}, new_session={is_new_session_greeting})")
                card = create_welcome_card(user_name=user_name)
                await self.teams_adapter.send_card(service_url, conv_id, card)
                
                # IMPORTANT: Mark greeting as shown immediately to prevent duplicates
                state["greeting_shown"] = True
                state["session_started"] = False  # Session officially started now
                
                # Remove from first_time_users if present
                first_time_users.discard(user_id)
                
                # If there was additional content after greeting, process it
                if user_payload:
                    user_message = user_payload.strip()
                    logger.info(f"Processing additional content after greeting: '{user_message}'")
                    # Show typing indicator for processing the question
                    await self.teams_adapter.send_typing(service_url, conv_id)
                    # Continue processing the question below...
                    return True, user_message
                else:
                    # Just greeting, record it and return
                    logger.info(f"Pure greeting processed for user {user_id}, ending request")
                    await self._ensure_user_message_saved(user_message, user_id, state["session_id"], None)
                    return False, ""
            else:
                # User has already seen greeting in this session
                logger.info(f"User {user_id} already saw greeting in this session (greeting_shown={state.get('greeting_shown')})")
                if user_payload:
                    # Greeting + question - process the question
                    user_message = user_payload.strip()
                    logger.info(f"Processing question from repeat greeting: '{user_message}'")
                    # Show typing indicator for processing the question
                    await self.teams_adapter.send_typing(service_url, conv_id)
                    # Continue processing the question below...
                    return True, user_message
                elif is_only_greeting:
                    # Pure greeting in same session - give a friendly response without card
                    logger.info(f"Returning user greeting again in same session: '{user_message}' - sending simple response")
                    user_msg_id = await self._ensure_user_message_saved(user_message, user_id, state["session_id"], None)
                    
                    # Store bot message and get its database ID
                    bot_msg_id = await self._persist_bot_msg(user_msg_id, "Hello again! How can I help you today?", "greeting")
                    
                    # Send message and get Teams activity ID
                    activity_id = await self.teams_adapter.send_message_with_resources_button(service_url, conv_id, "Hello again! How can I help you today?")
                    
                    # Track the mapping
                    if bot_msg_id and activity_id:
                        from qcbot.services.feedback_service import get_feedback_service
                        feedback_service = get_feedback_service()
                        feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                        logger.debug(f"Tracked greeting mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                    
                    return False, ""
                else:
                    # Not a pure greeting but detected as greeting - send helper message
                    logger.info(f"Ambiguous greeting in same session: '{user_message}' - sending helper response")
                    user_msg_id = await self._ensure_user_message_saved(user_message, user_id, state["session_id"], None)
                    
                    # Store bot message and get its database ID
                    bot_msg_id = await self._persist_bot_msg(user_msg_id, "I am here to assist with your inquiries. How can I help you today?", "greeting")
                    
                    # Send message and get Teams activity ID
                    activity_id = await self.teams_adapter.send_message_with_resources_button(service_url, conv_id, "I am here to assist with your inquiries. How can I help you today?")
                    
                    # Track the mapping
                    if bot_msg_id and activity_id:
                        from qcbot.services.feedback_service import get_feedback_service
                        feedback_service = get_feedback_service()
                        feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                        logger.debug(f"Tracked greeting mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                    
                    return False, ""
        elif user_payload and not greet_only:
            # If greeting had additional content but not first time, use that as the actual message
            user_message = user_payload.strip()
            return True, user_message
        
        return True, user_message
    
    async def _persist_bot_msg(self, reply_id: int, text: str, intent: str = "CONTINUE") -> int | None:
        """Helper function for database persistence of bot messages."""
        try:
            bot_msg_id = await self.message_service.add_message(
                bot_name=get_bot_name(),
                env="development",
                channel="teams",
                user_id="",  # This will be set by the caller
                session_id="",  # This will be set by the caller
                role="bot",
                text=text,
                intent=intent,
                reply_to_id=reply_id,  
            )
            return bot_msg_id
        except Exception as exc:
            logger.warning("DB write (bot msg) failed: %s", exc)
            return None
    
    async def handle_anything_else_response(
        self,
        user_message: str,
        user_id: str,
        service_url: str,
        conv_id: str,
        state: dict,
        session_id: str,
        reply_to_id: str = None
    ) -> bool:
        """
        Handle user response to "anything else?" question.
        
        Returns:
            True if conversation should continue, False if it should end
        """
        logger.info(f"User is responding to 'anything else?' question with: '{user_message}'")
        
        # Determine if the user is ending the conversation using classify_intent
        # which mirrors hrbot/uwbot behaviour
        intent = await classify_intent(GeminiService(), user_message)
        
        logger.info(f"Intent detection: user_message='{user_message}', detected_intent='{intent}'")
        
        if str(intent).upper() == "END":
            # User wants to end the conversation
            logger.info(f"User {user_id} wants to end conversation based on intent detection")
            state["awaiting_more_help"] = False
            
            # Save the user's message before ending
            await self._ensure_user_message_saved(user_message, user_id, session_id, reply_to_id)
            
            await self.teams_adapter.send_message(
                service_url, conv_id,
                "Thank you for using our QC Assistant!"
            )
            
            # Let the Teams router handle feedback scheduling through delayed feedback mechanism
            # This prevents duplicate feedback cards
            logger.info(f"Conversation ending - feedback will be handled by delayed feedback mechanism")
            
            return False
        else:
            # User wants to continue (CONTINUE) - process their message normally
            logger.info(f"User wants to continue conversation: '{user_message}'")
            state["awaiting_more_help"] = False
            return True
