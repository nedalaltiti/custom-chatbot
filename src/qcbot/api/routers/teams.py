# qcbot/api/routers/teams.py

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional
import logging
from qcbot.services.feedback_service import get_feedback_service
from qcbot.services.message_service import MessageService
from qcbot.infrastructure.teams_adapter import TeamsAdapter
from qcbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from qcbot.services.processor import ChatProcessor
from qcbot.config.settings import settings
from qcbot.utils.di import get_intent_service, get_card_action_handler, get_feedback_card_tracker
from qcbot.services.session_tracker import session_tracker
from qcbot.utils.bot_name import get_bot_name
import time

# Import the new utility classes
from qcbot.utils.teams_feedback_handler import TeamsFeedbackHandler
from qcbot.utils.conversation_handler import ConversationHandler
from qcbot.utils.message_processing_service import MessageProcessingService
from qcbot.utils.session_management_service import SessionManagementService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
adapter = TeamsAdapter()
feedback_service = get_feedback_service()
chat_processor = ChatProcessor()
message_service = MessageService()

# Initialize the new service classes
teams_feedback_handler = TeamsFeedbackHandler(feedback_service)
session_management_service = SessionManagementService(feedback_service)
conversation_handler = ConversationHandler(feedback_service, adapter, message_service, session_management_service)
message_processing_service = MessageProcessingService(chat_processor, adapter, message_service)

# Debug endpoint models and implementation for QA team
class DebugChatRequest(BaseModel):
    text: str
    user_id: str = "debug-user"

class DebugChatResponse(BaseModel):
    user_message: str
    bot_response: str
    conversation_flow: str
    confidence: float
    processing_time: float
    bot_name: str

@router.post("/")
async def teams_messages(
    req: TeamsMessageRequest, 
    background_tasks: BackgroundTasks,
    feedback_card_tracker = Depends(get_feedback_card_tracker)
):
    user_message = req.text or ""
    user_id = req.from_.id
    user_name = req.from_.name
    aad_object_id = req.from_.aad_object_id
    service_url = req.service_url
    conv_id = req.conversation.id
    message_id = req.reply_to_id 

    if user_message.strip():  # Only track if user sent actual message
        feedback_service.track_user_activity(user_id)

    # Send immediate typing indicator for user feedback
    if not req.value and user_message.strip():
        try:
            await adapter.send_typing(service_url, conv_id)
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")
    
    # Get user state and session
    state = session_management_service.get_user_state(user_id)
    session_id = session_tracker.get(user_id)
    session_management_service.update_session_id(user_id, session_id)
    
    # Get job title for system override
    try:
        profile = await adapter.get_user_profile(aad_object_id)
        job_title = profile.get("jobTitle", "Unknown")
    except Exception:
        job_title = "Unknown"

    # Add job title to system context
    system_override = f"Current user job title: {job_title}"

    # Handle ALL invoke requests to prevent "Unable to reach app" errors
    if req.type == 'invoke':
        try:
            logger.info(f"🔍 INVOKE DEBUG: type={req.type}, name={req.name}")
            logger.info(f"🔍 INVOKE VALUE: {req.value}")
            logger.info(f"🔍 INVOKE REPLY_TO_ID: {req.reply_to_id}")
            logger.info(f"🔍 INVOKE ACTIVITY_ID: {req.activity_id}")
            
            # Handle any feedback action regardless of format
            action_data = req.value or {}
            
            # Check for Teams built-in feedback patterns (message-level feedback from thumbs up/down)
            is_builtin_feedback = (
                req.name in ['message/feedbackSubmit', 'feedbackLoop', 'message/feedback', 'message/executeAction'] or
                'feedbackLoop' in action_data or
                (req.name == 'message/submitAction' and action_data.get('actionName') == 'feedback' and 'actionValue' in action_data) or
                (req.name == 'message/executeAction' and 'feedback' in str(action_data).lower())
            )
            
            # Check for custom feedback patterns (our adaptive cards - session-level feedback)
            is_custom_feedback = (
                req.name == 'message/submitAction' and
                action_data.get('action') in ['submit_feedback', 'submit_rating', 'dismiss_feedback'] and
                'actionName' not in action_data  # This distinguishes our cards from Teams built-in feedback
            )
            
            is_feedback = is_builtin_feedback or is_custom_feedback
            
            logger.info(f"🔍 FEEDBACK CHECK: is_builtin={is_builtin_feedback}, is_custom={is_custom_feedback}, total={is_feedback}")
            
            if is_feedback:
                # Handle built-in Teams feedback (thumbs up/down buttons)
                if is_builtin_feedback:
                    logger.info(f"🔵 Processing BUILT-IN Teams feedback (message-level)")
                    
                    # Extract feedback data from Teams message-level feedback format
                    reaction = None
                    feedback_text = ""
                    
                    # Teams sends message-level feedback in this format:
                    # {'actionName': 'feedback', 'actionValue': {'reaction': 'dislike', 'feedback': '{"feedbackText":"bad"}'}}
                    if action_data.get('actionName') == 'feedback' and 'actionValue' in action_data:
                        action_value = action_data.get('actionValue', {})
                        reaction = action_value.get('reaction')
                        
                        # Extract feedback text from JSON string
                        feedback_json = action_value.get('feedback', '{}')
                        if isinstance(feedback_json, str):
                            try:
                                import json
                                feedback_data = json.loads(feedback_json)
                                feedback_text = feedback_data.get('feedbackText', '')
                            except:
                                feedback_text = feedback_json
                        
                    # Fallback extraction methods
                    if not reaction:
                        if 'feedbackLoop' in action_data:
                            feedback_data = action_data.get('feedbackLoop', {})
                            reaction = feedback_data.get('reaction') or feedback_data.get('type')
                            feedback_text = feedback_data.get('comment', '')
                        elif 'reaction' in action_data:
                            reaction = action_data.get('reaction')
                            feedback_text = action_data.get('comment', '')
                    
                    # Default if no specific reaction found
                    if not reaction:
                        reaction = 'like'  # Default assumption for successful invoke
                    
                    # Normalize reaction
                    standardized_feedback = str(reaction).lower()
                    if standardized_feedback in ['thumbsup', 'up', '👍', 'positive']:
                        standardized_feedback = 'like'
                    elif standardized_feedback in ['thumbsdown', 'down', '👎', 'negative']:
                        standardized_feedback = 'dislike'
                    
                    logger.info(f"🔵 Built-in feedback: reaction={reaction} -> standardized={standardized_feedback}, text='{feedback_text}'")
                    
                    # For built-in Teams feedback, try to get the message they're responding to
                    target_message_id = None
                    
                    # Method 1: Use reply_to_id if available
                    if req.reply_to_id:
                        # Try to find bot message that corresponds to this activity ID
                        target_message_id = feedback_service.get_bot_message_id_from_activity(req.reply_to_id)
                        if target_message_id:
                            logger.info(f"🔵 Found target message via reply_to_id: {req.reply_to_id} -> {target_message_id}")
                    
                    # Record the feedback if we have a target message
                    if target_message_id:
                        try:
                            result = await feedback_service.record_builtin_teams_feedback(
                                message_id=target_message_id,
                                feedback=standardized_feedback,
                                feedback_comment=str(feedback_text).strip(),
                                user_id=user_id,
                            )
                            if result:
                                logger.info(f"🔵 Recorded built-in feedback for message {target_message_id}: {standardized_feedback}")
                            else:
                                logger.warning(f"🔵 Failed to record built-in feedback for message {target_message_id} - message may not exist in database")
                        except Exception as e:
                            logger.error(f"🔴 Error recording built-in feedback: {e}")
                    else:
                        logger.info(f"🔵 Built-in feedback received but no target message found - recording as general feedback")
                        # Record as general session feedback if we can't link to specific message
                        try:
                            await feedback_service.record_feedback(
                                user_id=user_id,
                                rating=5 if standardized_feedback == 'like' else 2,  # Convert to rating
                                comment=feedback_text,
                                session_id=conv_id,
                            )
                            logger.info(f"🔵 Recorded general feedback: {standardized_feedback}")
                        except Exception as e:
                            logger.error(f"🔴 Error recording general feedback: {e}")
                    
                    # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
                    # Teams built-in feedback requires exactly {} as response
                    return {}
                
                # Handle our custom feedback cards (adaptive cards with submit actions)
                elif is_custom_feedback:
                    logger.info(f"🟢 Processing CUSTOM feedback card")
                    
                    # This is handled by the card action handlers below (submit_feedback, submit_rating, etc.)
                    # Just log it for now and let it fall through to the card handlers
                    logger.info(f"🟢 Custom feedback will be handled by card action handlers")
                    
                    # Let it fall through to card action handlers - they will return their own responses

                # NO acknowledgment message for any message-level feedback (like/dislike)
                # Both built-in and custom message-level feedback should be silent
            else:
                logger.info(f"Non-feedback invoke: {req.name}")
            
            # Always return empty JSON object for ANY non-builtin invoke to prevent Teams errors
            return {}
                
        except Exception as e:
            logger.error(f"Error handling invoke request: {e}")
            # Even on error, return empty JSON object to prevent Teams UI errors
            return {}
    
    # Handle Teams Action.Execute requests (used by built-in feedback system)
    elif req.name == 'message/executeAction':
        return await teams_feedback_handler.handle_message_execute_action(req.value, user_id, conv_id)
    
    # Handle Teams built-in feedback form submissions (composeExtensions/submitAction)
    elif req.name == 'composeExtensions/submitAction':
        return await teams_feedback_handler.handle_compose_extensions_submit_action(req.value, user_id, conv_id)
    
    # Legacy invoke handling (keeping for compatibility)
    elif req.name == 'message/submitAction':
        try:
            logger.info(f"Legacy invoke handling: name={req.name}, value={req.value}")
            return {}
        except Exception as e:
            logger.error(f"Error in legacy invoke handling: {e}")
            return {}
    
    # Handle adaptive card actions
    if req.value:
        action = req.value.get("action")

        if action == "submit_rating":
            logger.info(f"🔵 Teams router handling submit_rating action for conversation {conv_id}")
            return await get_card_action_handler().handle_submit_rating(
                req.value, conv_id, service_url, feedback_card_tracker, state
            )

        if action == "dismiss_feedback":
            return await get_card_action_handler().handle_dismiss_feedback(
                conv_id, service_url, feedback_card_tracker, user_id, state,
                session_management_service.clear_user_session
            )

        if action == "submit_feedback":
            return await get_card_action_handler().handle_submit_feedback(
                req.value, conv_id, service_url, feedback_card_tracker, user_id, state,
                session_management_service.clear_user_session
            )

        if action == "message_reply_feedback":
            return await get_card_action_handler().handle_message_reply_feedback(req.value)

        if action == "show_resources":
            logger.info(f"🔵 Teams router handling show_resources action for conversation {conv_id}")
            return await get_card_action_handler().handle_show_resources(
                conv_id, service_url
            )

        return TeamsActivityResponse(text="")

    # Handle "anything else?" responses
    if state.get("awaiting_more_help"):
        should_continue = await conversation_handler.handle_anything_else_response(
            user_message, user_id, service_url, conv_id, state, session_id, req.reply_to_id
        )
        if not should_continue:
            return TeamsActivityResponse(text="")

    # Handle greeting logic
    should_continue, processed_message = await conversation_handler.handle_greeting_logic(
        user_message, user_id, user_name, service_url, conv_id, state,
        session_management_service.first_time_users, session_management_service.feedback_cards
    )
    
    if not should_continue:
        return TeamsActivityResponse(text="")
    
    user_message = processed_message

    # Get conversation context for analysis
    memory = await session_management_service.get_or_create_memory(user_id)
    conversation_context = None
    if memory.messages:
        recent_messages = memory.messages[-4:]  # Last 4 messages for context
        conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
    
    # Analyze conversation flow using intent service
    intent_service = get_intent_service()
    flow_type = await intent_service.analyze_conversation_intent(
        user_message=user_message,
        conversation_context=conversation_context
    )
    
    # Store flow type in state for later use
    state["flow_type"] = flow_type
    logger.info(f"Conversation flow analysis: {flow_type}")

    # Mirror hrbot/uwbot: schedule delayed feedback when conversation continues
    try:
        if flow_type != "end" and not feedback_service.has_received_feedback(user_id):
            # Cancel any existing timer and schedule a new one using default delay
            feedback_service.cancel_pending_feedback(user_id)

            feedback_service.schedule_delayed_feedback(
                user_id,
                service_url,
                conv_id,
                delay_minutes=settings.feedback.feedback_timeout_minutes,
                on_card_sent=feedback_card_tracker.create_track_feedback_card_callback(),
            )
            logger.info(
                f"Scheduled delayed feedback for user {user_id} in {settings.feedback.feedback_timeout_minutes} minutes"
            )
    except Exception as e:
        logger.warning(f"Failed to schedule delayed feedback (router-level): {e}")

    # Handle resources link click
    if user_message and "show_resources" in user_message:
        logger.info(f"User clicked resources link: {user_message}")
        # Send the resources card
        try:
            from qcbot.infrastructure.cards import create_resources_card
            resources_card = create_resources_card()
            await adapter.send_card(service_url, conv_id, resources_card)
            logger.info("Successfully sent resources card")
        except Exception as e:
            logger.error(f"Failed to send resources card: {e}")
            await adapter.send_message(service_url, conv_id, "Sorry, I couldn't load the resources right now. Please try again later.")
        return TeamsActivityResponse(text="")

    # Handle conversation ending scenarios immediately
    if flow_type == "end":
        await conversation_handler.handle_conversation_ending(
            flow_type, user_id, service_url, conv_id, state, 
            user_message, session_id, req.reply_to_id, feedback_card_tracker
        )
        return TeamsActivityResponse(text="")

    # Save user message and process with AI
    user_msg_id = await conversation_handler._ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
    
    # Process message with streaming support
    success = await message_processing_service.process_message_with_streaming(
        user_message, user_id, service_url, conv_id, session_id, state, memory, system_override, user_msg_id
    )
    
    if not success:
        logger.error("Message processing failed")
        await adapter.send_message(service_url, conv_id, "Sorry, I encountered an error. Please try again.")
    
    return TeamsActivityResponse(text="")


@router.post("/debug", response_model=DebugChatResponse)
async def debug_chat(req: DebugChatRequest):
    """Debug endpoint that returns actual AI response for testing."""
    start_time = time.time()
    
    try:
        # Create a session ID for this debug conversation
        session_id = session_tracker.get(req.user_id)
        
        # Get conversation context
        memory = await session_management_service.get_or_create_memory(req.user_id)
        
        # Process debug message
        result = await message_processing_service.process_debug_message(
            req.text, req.user_id, session_id, memory
        )
        
        processing_time = time.time() - start_time
        
        return DebugChatResponse(
            user_message=result["user_message"],
            bot_response=result["bot_response"],
            conversation_flow=result["conversation_flow"],
            confidence=result["confidence"],
            processing_time=round(processing_time, 2),
            bot_name=result["bot_name"]
        )
            
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
        processing_time = time.time() - start_time
        return DebugChatResponse(
            user_message=req.text,
            bot_response=f"Error: {str(e)}",
            conversation_flow="error",
            confidence=0.0,
            processing_time=round(processing_time, 2),
            bot_name="qcbot"
        )
