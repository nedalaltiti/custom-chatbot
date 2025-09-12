"""
Message Processing Utility for QC Bot

This utility handles message processing, streaming, and LLM interactions,
separating the message processing logic from the main router.
"""

import logging
from typing import Dict, Any, Optional, AsyncGenerator
from qcbot.services.processor import ChatProcessor
from qcbot.services.message_service import MessageService
from qcbot.infrastructure.teams_adapter import TeamsAdapter
from qcbot.utils.di import get_intent_service
from qcbot.utils.bot_name import get_bot_name
from qcbot.utils.message import split_greeting, is_pure_greeting
from qcbot.utils.resource_links import find_resource_links, format_links_response
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Pattern to detect if response already contains the "anything else" question
_HAS_ANYTHING_ELSE_RE = re.compile(
    r"(?:Is there anything else I can help you with\?|"
    r"Anything else I can help you with\?|"
    r"Can I help you with anything else\?)",
    re.I
)


class MessageProcessingService:
    """Service for processing messages, streaming, and LLM interactions."""
    
    def __init__(self, chat_processor: ChatProcessor, teams_adapter: TeamsAdapter, message_service: MessageService):
        self.chat_processor = chat_processor
        self.teams_adapter = teams_adapter
        self.message_service = message_service
    
    async def process_message_with_streaming(
        self,
        user_message: str,
        user_id: str,
        service_url: str,
        conv_id: str,
        session_id: str,
        state: dict,
        memory: Any,
        system_override: str = None,
        user_msg_id: int = None
    ) -> bool:
        """
        Process message with streaming support.
        
        Returns:
            True if processing was successful, False otherwise
        """
        logger.info(f"[Teams] Generating response for %s", user_id)

        # Quick-path: detect if user is asking for known resource links and reply immediately
        try:
            resource_matches = find_resource_links(user_message, max_items=12)
            if resource_matches:
                reply_text = format_links_response(resource_matches)

                # Save to memory and DB before sending
                memory.add_ai_message(reply_text)
                state["last_bot_response_time"] = datetime.utcnow()
                intent_service = get_intent_service()
                intent = intent_service.get_message_intent(state.get("flow_type", "CONTINUE"))
                bot_msg_id = await self._persist_bot_msg(user_msg_id, reply_text, intent, user_id, session_id)

                activity_id = await self.teams_adapter.send_message_with_resources_button(service_url, conv_id, reply_text)
                if bot_msg_id and activity_id:
                    from qcbot.services.feedback_service import get_feedback_service
                    feedback_service = get_feedback_service()
                    feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                    # NOTE: Feedback scheduling is centralized in the Teams router to avoid duplicates
                return True
        except Exception as e:
            logger.warning(f"Resource links quick-path failed: {e}")

        # Enhanced streaming logic following Microsoft Teams requirements
        if state.get("use_streaming", True) and len(user_message.strip()) >= 2:
            logger.info(f"Starting real-time LLM streaming for query: {user_message[:50]}...")
            
            try:
                # Stream directly from LLM - much faster!
                async def llm_stream_generator():
                    """Generator that streams directly from LLM and formats bullet points."""
                    full_response = ""
                    async for chunk in self.chat_processor.process_message_streaming(
                        user_message,
                        chat_history=[m["content"] for m in memory.messages[:-1]],
                        user_id=user_id
                    ):
                        full_response += chunk
                        # Format and yield chunks with proper bullet point formatting
                        yield chunk
                    
                    # Store the complete response for memory after streaming
                    if full_response.strip():
                        # Format the complete response for memory
                        formatted_response = self.chat_processor._format_bullet_points(full_response)
                        memory.add_ai_message(formatted_response)
                        
                        # Update last bot response time
                        state["last_bot_response_time"] = datetime.utcnow()
                        
                        # Check if response contains "anything else?" 
                        if _HAS_ANYTHING_ELSE_RE.search(formatted_response):
                            state["awaiting_more_help"] = True
                        
                        # Store in database with appropriate intent
                        intent_service = get_intent_service()
                        intent = intent_service.get_message_intent(state.get("flow_type", "CONTINUE"))
                        bot_msg_id = await self._persist_bot_msg(user_msg_id, formatted_response, intent, user_id, session_id)
                        
                        # NOTE: Feedback scheduling is centralized in the Teams router to avoid duplicates
                        
                        # Track the mapping - for streaming, we'll need to get the activity ID
                        # This will be handled after streaming completes
                        if bot_msg_id:
                            # Store the bot message ID temporarily to map later
                            state["last_bot_message_id"] = bot_msg_id

                # Start real-time streaming from LLM
                success, activity_id = await self.teams_adapter.stream_message(
                    service_url, conv_id,
                    text_generator=llm_stream_generator(),
                    informative="I'm analyzing your request..."
                )
                
                # Track the mapping between Teams activity ID and bot message database ID
                if success and activity_id:
                    # Get the bot message ID that was stored during streaming
                    bot_msg_id = state.get("last_bot_message_id")
                    if bot_msg_id:
                        # Import here to avoid circular imports
                        from qcbot.services.feedback_service import get_feedback_service
                        feedback_service = get_feedback_service()
                        feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                        logger.debug(f"Tracked streaming mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                        # Clean up the temporary storage
                        state.pop("last_bot_message_id", None)
                    else:
                        logger.warning(f"Streaming completed but no bot message ID found for activity {activity_id}")
                elif success:
                    logger.debug("Streaming completed successfully but no activity ID returned")
                else:
                    logger.warning("Streaming failed, falling back to traditional method")
                    return await self._fallback_to_traditional_processing(
                        user_message, user_id, service_url, conv_id, session_id, 
                        state, memory, system_override, user_msg_id
                    )
                
                return True
                
            except Exception as e:
                logger.error(f"Streaming error: {e}, falling back to regular processing")
                return await self._fallback_to_traditional_processing(
                    user_message, user_id, service_url, conv_id, session_id, 
                    state, memory, system_override, user_msg_id
                )
        else:
            # Use traditional method for very short queries or when streaming is disabled
            logger.info(f"Using traditional processing for short query")
            return await self._fallback_to_traditional_processing(
                user_message, user_id, service_url, conv_id, session_id, 
                state, memory, system_override, user_msg_id
            )
    
    async def _fallback_to_traditional_processing(
        self,
        user_message: str,
        user_id: str,
        service_url: str,
        conv_id: str,
        session_id: str,
        state: dict,
        memory: Any,
        system_override: str = None,
        user_msg_id: int = None
    ) -> bool:
        """Fallback to traditional message processing when streaming fails."""
        try:
            # Show analyzing message for non-streaming responses
            if len(user_message.split()) > 1:
                try:
                    await self.teams_adapter.send_informative_update(
                        service_url, conv_id,
                        "I'm analyzing your request...",
                        stream_sequence=1
                    )
                except Exception as e:
                    logger.warning(f"Failed to send analyzing message: {e}")
            
            result = await self.chat_processor.process_message(
                user_message,
                chat_history=[m["content"] for m in memory.messages[:-1]],
                user_id=user_id,
                system_override=system_override
            )
            
            if result.is_success():
                answer = result.unwrap()["response"].strip()
                
                # Check if the response already contains "anything else?" question
                has_anything_else = _HAS_ANYTHING_ELSE_RE.search(answer)
                if has_anything_else:
                    # Set state to await response
                    state["awaiting_more_help"] = True

                memory.add_ai_message(answer)
                state["last_bot_response_time"] = datetime.utcnow()
                intent_service = get_intent_service()
                intent = intent_service.get_message_intent(state.get("flow_type", "CONTINUE"))
                
                # Store bot message and get its database ID
                bot_msg_id = await self._persist_bot_msg(user_msg_id, answer, intent, user_id, session_id)
                
                logger.info(f"Sending regular message (length: {len(answer)})")
                # Send message with resources button and get Teams activity ID
                activity_id = await self.teams_adapter.send_message_with_resources_button(service_url, conv_id, answer)
                
                # Track the mapping
                if bot_msg_id and activity_id:
                    # Import here to avoid circular imports
                    from qcbot.services.feedback_service import get_feedback_service
                    feedback_service = get_feedback_service()
                    feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                    logger.debug(f"Tracked fallback mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                
                # NOTE: Feedback scheduling is centralized in the Teams router to avoid duplicates
                
                return True
            else:
                # Fallback message
                await self.teams_adapter.send_message(
                    service_url, conv_id,
                    "Sorry, I hit a glitch. Please try again later."
                )
                return False
                
        except Exception as e:
            logger.error(f"Error in fallback processing: {e}")
            # Fallback message
            try:
                await self.teams_adapter.send_message(
                    service_url, conv_id,
                    "Sorry, I hit a glitch. Please try again later."
                )
            except Exception as send_error:
                logger.error(f"Failed to send fallback message: {send_error}")
            return False
    
    async def _persist_bot_msg(
        self, 
        reply_id: int, 
        text: str, 
        intent: str, 
        user_id: str, 
        session_id: str
    ) -> int | None:
        """Helper function for database persistence of bot messages."""
        try:
            bot_msg_id = await self.message_service.add_message(
                bot_name=get_bot_name(),
                env="development",
                channel="teams",
                user_id=user_id,
                session_id=session_id,
                role="bot",
                text=text,
                intent=intent,
                reply_to_id=reply_id,  
            )
            return bot_msg_id
        except Exception as exc:
            logger.warning("DB write (bot msg) failed: %s", exc)
            return None
    
    async def process_debug_message(
        self,
        user_message: str,
        user_id: str,
        session_id: str,
        memory: Any
    ) -> Dict[str, Any]:
        """Process debug message and return response."""
        try:
            # Get conversation context
            conversation_context = None
            if memory.messages:
                recent_messages = memory.messages[-4:]
                conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
            
            # Analyze conversation flow
            intent_service = get_intent_service()
            flow_type = await intent_service.analyze_conversation_intent(
                user_message=user_message,
                conversation_context=conversation_context
            )
            
            # Save user message to database
            user_msg_id = await self.message_service.add_message(
                bot_name="qcbot",
                env="development",
                channel="debug",  # Using 'debug' channel to distinguish from teams
                user_id=user_id,
                session_id=session_id,
                role="user",
                text=user_message,
                intent=None,
                reply_to_id=None,
            )
            
            # Get AI response
            result = await self.chat_processor.process_message(
                user_message,
                chat_history=[m["content"] for m in memory.messages],
                user_id=user_id
            )
            
            if result.is_success():
                bot_response = result.unwrap()["response"].strip()
                
                # Save to memory for context
                memory.add_user_message(user_message)
                memory.add_ai_message(bot_response)
                
                # Save bot response to database
                await self.message_service.add_message(
                    bot_name="qcbot",
                    env="development", 
                    channel="debug",
                    user_id=user_id,
                    session_id=session_id,
                    role="bot",
                    text=bot_response,
                    intent=intent_service.get_message_intent(flow_type),
                    reply_to_id=user_msg_id,
                )
                
                return {
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "conversation_flow": flow_type,
                    "confidence": 1.0,
                    "bot_name": "qcbot"
                }
            else:
                # Even on error, save to memory and database
                error_response = "Sorry, I encountered an error processing your request."
                memory.add_user_message(user_message)
                memory.add_ai_message(error_response)
                
                await self.message_service.add_message(
                    bot_name="qcbot",
                    env="development",
                    channel="debug", 
                    user_id=user_id,
                    session_id=session_id,
                    role="bot",
                    text=error_response,
                    intent="error",
                    reply_to_id=user_msg_id,
                )
                
                return {
                    "user_message": user_message,
                    "bot_response": error_response,
                    "conversation_flow": "error",
                    "confidence": 0.0,
                    "bot_name": "qcbot"
                }
                
        except Exception as e:
            logger.error(f"Debug message processing error: {e}")
            error_response = f"Error: {str(e)}"
            return {
                "user_message": user_message,
                "bot_response": error_response,
                "conversation_flow": "error",
                "confidence": 0.0,
                "bot_name": "qcbot"
            }
