# uwbot/api/routers/teams.py

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends

from uwbot.services.message_service import MessageService
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from uwbot.infrastructure.cards import create_welcome_card
from uwbot.utils.di import get_combined_validation_uc, get_builtin_feedback_service   
from uwbot.services.hybrid_session_tracker import hybrid_session_tracker
from uwbot.services.hybrid_state_manager import get_hybrid_state_manager
from uwbot.utils.bot_name import get_bot_name
from uwbot.utils.message import is_pure_greeting
from uwbot.utils.intent import classify_intent
from uwbot.config.settings import settings
from uwbot.services.background_tasks import get_background_task_service
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

router           = APIRouter()
adapter          = TeamsAdapter()
message_service  = MessageService()
background_task_service = get_background_task_service()
state_manager    = get_hybrid_state_manager()
builtin_feedback_service = get_builtin_feedback_service()

# Database-backed state management (replaces in-memory dictionaries)
# first_time_users and user_states are now managed by DatabaseStateManager

async def _ensure_user_message_saved(user_message: str, user_id: str, session_id: str, reply_to_id: str = None) -> int:
    """
    Ensure user message is saved to database.
    Returns the message ID.
    """
    # Save to database with error handling
    try:
        user_msg_id = await message_service.add_message(
            bot_name   = get_bot_name(),
            env        = settings.environment,
            channel    = "teams",
            user_id    = user_id,
            session_id = session_id,
            role       = "user",
            text       = user_message,
            reply_to_id= reply_to_id,
        )
    except Exception as e:
        logger.error(f"Failed to save user message to database: {e}")
    
    return user_msg_id

def extract_contact_id_from_message(message: str) -> Optional[int]:
    """
    Extract contact ID from user message using various patterns.
    
    Args:
        message: User message text
        
    Returns:
        Contact ID if found and valid, None otherwise
    """
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

async def _clear_user_session(user_id: str) -> None:
    """
    Clear user session.
    
    Args:
        user_id: User identifier
    """
    try:
        # End the session using hybrid session tracker
        await hybrid_session_tracker.end_session(user_id)
        
        logger.info(f"Successfully cleared session for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error clearing session for user {user_id}: {e}")

@router.post("/")
async def teams_messages(
    req: TeamsMessageRequest, 
    background_tasks: BackgroundTasks,
    external_validation_client = Depends(get_combined_validation_uc)
):
    user_message = req.text or ""
    user_id      = req.from_.id
    user_name    = req.from_.name
    service_url  = req.service_url
    conv_id      = req.conversation.id

    # Helper function for critical database persistence (synchronous)
    async def _persist_bot_msg(reply_id: int, text: str, intent: str = "validation") -> int | None:
        try:
            bot_msg_id = await message_service.add_message(
                bot_name   = get_bot_name(),
                env        = settings.environment,
                channel    = "teams",
                user_id    = user_id,
                session_id = session_id,
                role       = "bot",
                text       = text,
                intent     = intent,
                reply_to_id= reply_id,  
            )
            return bot_msg_id
        except Exception as exc:
            logger.warning("DB write (bot msg) failed: %s", exc)
            return None
    
    # Helper function for non-critical database persistence (background)
    def _schedule_bot_msg_persistence(reply_id: int, text: str, intent: str = "validation") -> asyncio.Task:
        """Schedule bot message persistence as a background task."""
        return background_task_service.schedule_message_persistence(
            bot_name=get_bot_name(),
            user_id=user_id,
            session_id=session_id,
            role="bot",
            text=text,
            intent=intent,
            reply_to_id=reply_id,
            channel="teams"
        )
    
    # Send immediate typing indicator for user messages (but NOT for card actions)
    typing_sent = False
    
    # Comprehensive card action detection
    is_card_action = (
        req.type == 'invoke' or 
        req.name in ['message/submitAction', 'message/executeAction', 'composeExtensions/submitAction']
    )
    
    if not is_card_action:
        try:
            await adapter.send_typing(service_url, conv_id)
            typing_sent = True
            logger.debug(f"📝 Typing indicator sent immediately for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")
    else:
        logger.debug(f"Skipping typing indicator for card action: type={req.type}, name={req.name}")
    
    # Get or create user state from database
    user_state = await state_manager.get_user_state(user_id)
    if user_state is None:
        # First ever message from this user - create new state
        logger.info(f"Creating new session for user {user_id} - first message ever")
        session_id = await hybrid_session_tracker.get(user_id)
        user_state = await state_manager.create_user_state(
            user_id=user_id,
            session_id=session_id,
            is_first_time_user=True
        )
        logger.info(f"Created new database state for user {user_id} with session {session_id}")
    else:
        # Existing user - update activity and get session ID
        session_id = user_state.session_id
        logger.debug(f"Retrieved existing state for user {user_id} with session {session_id}")
    
    # Track activity in database
    await state_manager.track_user_activity(
        user_id=user_id,
        session_id=session_id,
        activity_type="message",
        metadata={"message_length": len(user_message), "is_card_action": is_card_action}
    )
    
    # Convert to dictionary for backward compatibility with existing code
    state = user_state.to_dict()

    # Helper function for analytics logging (background) - defined here after session_id is available
    def _schedule_analytics(event_type: str, metadata: dict = None) -> asyncio.Task:
        """Schedule analytics logging as a background task."""
        return background_task_service.schedule_analytics_logging(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {}
        )

    # Handle ALL invoke requests to prevent "Unable to reach app" errors
    if req.type == 'invoke':
        try:
            logger.info(f"🔍 INVOKE DEBUG: type={req.type}, name={req.name}")
            
            # Handle built-in Teams feedback (like/dislike thumbs)
            action_data = req.value or {}
            
            # Check for Teams built-in feedback patterns (message-level feedback from thumbs up/down)
            is_builtin_feedback = (
                req.name in ['message/feedbackSubmit', 'feedbackLoop', 'message/feedback', 'message/executeAction'] or
                'feedbackLoop' in action_data or
                (req.name == 'message/submitAction' and action_data.get('actionName') == 'feedback' and 'actionValue' in action_data) or
                (req.name == 'message/executeAction' and 'feedback' in str(action_data).lower())
            )
            
            if is_builtin_feedback:
                logger.info(f"🔵 Processing built-in Teams feedback (thumbs up/down)")
                
                # Extract feedback data from Teams built-in feedback format
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
                
                logger.info(f"🔵 Extracted built-in feedback: reaction='{reaction}', text='{feedback_text[:50]}{'...' if len(feedback_text) > 50 else ''}'")
                
                # Store the feedback in database if we have valid reaction
                if reaction and reaction.lower() in ['like', 'dislike']:
                    try:
                        # Get session_id for this user
                        user_state = await state_manager.get_user_state(user_id)
                        if user_state:
                            feedback_session_id = user_state.session_id
                        else:
                            # Fallback to conversation ID if no user state
                            feedback_session_id = conv_id
                        
                        success = await builtin_feedback_service.record_builtin_feedback(
                            user_id=user_id,
                            session_id=feedback_session_id,
                            reaction=reaction.lower(),
                            comment=feedback_text
                        )
                        
                        if success:
                            logger.info(f"Successfully stored built-in Teams feedback: {reaction}")
                        else:
                            logger.warning(f"Failed to store built-in Teams feedback: {reaction}")
                            
                    except Exception as e:
                        logger.error(f"Error storing built-in Teams feedback: {e}")
                
                return {}  
            
            # For all other invoke requests (custom feedback cards), return empty response
            return {}
        except Exception as e:
            logger.error(f"Error handling invoke request: {e}")
            return {}

    # Check if user wants to end conversation
    intent = classify_intent(user_message)
    if intent == "END":
        logger.info(f"Goodbye intent detected for user {user_id}")
        
        # Save user message
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before response
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Send friendly goodbye message
        from uwbot.utils.validation_responses import format_goodbye_message
        goodbye_message = format_goodbye_message()
        
        # Store bot message and get its database ID
        bot_msg_id = await _persist_bot_msg(user_msg_id, goodbye_message, "goodbye")
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, goodbye_message)
        
        # End the session
        await _clear_user_session(user_id)
        
        return TeamsActivityResponse(text="")
    
    contact_id = extract_contact_id_from_message(user_message)
    
    if contact_id:
        logger.info(f"Contact query detected for ID: {contact_id}")
        
        # Schedule analytics logging for validation request (background)
        _schedule_analytics("validation_request", {
            "contact_id": contact_id,
            "message_length": len(user_message),
            "is_first_time_user": user_state.is_first_time_user
        })
        
        # Save user message first
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before processing (only if not already sent)
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Call external validation API
        try:
            logger.info(f"Calling external validation API for contact {contact_id}")
            validation_result = await external_validation_client.validate_combined(
                contact_id=contact_id,
                user_id=user_id,
                user_name=user_name
            )
            
            if validation_result.is_success():
                contact_response = validation_result.value.get('message', 'No response available')
                intent_type = "combined_validation"
                logger.info(f"External validation successful for contact {contact_id}")
                
                # Schedule analytics for successful validation (background)
                _schedule_analytics("validation_success", {
                    "contact_id": contact_id,
                    "response_length": len(contact_response)
                })
            else:
                # Handle validation error
                error_msg = validation_result.error
                if "Invalid contact ID" in error_msg:
                    from uwbot.utils.validation_responses import format_invalid_contact_id_response
                    contact_response = format_invalid_contact_id_response(contact_id)
                    intent_type = "error"
                    logger.warning(f"Invalid contact ID in Teams message: {error_msg}")
                    
                    # Schedule analytics for invalid contact ID (background)
                    _schedule_analytics("validation_error", {
                        "contact_id": contact_id,
                        "error_type": "invalid_contact_id"
                    })
                else:
                    from uwbot.utils.validation_responses import format_error_response
                    contact_response = format_error_response(contact_id, f"Error validating contact {contact_id}: {error_msg}", "validation")
                    intent_type = "error"
                
        except Exception as e:
            logger.error(f"External validation API error: {e}")
            from uwbot.utils.validation_responses import format_error_response
            contact_response = format_error_response(contact_id, f"Service temporarily unavailable. Please try again later.", "validation")
            intent_type = "error"
            
            # Schedule analytics for API error (background)
            _schedule_analytics("validation_error", {
                "contact_id": contact_id,
                "error_type": "api_error"
            })

    # Check for pure greetings using message.py utility
    is_pure_greeting_result = is_pure_greeting(user_message)
    
    # Show welcome card for pure greetings or first-time users
    should_show_greeting = False
    greeting_reason = ""
    
    if is_pure_greeting_result:
        should_show_greeting = True
        greeting_reason = "pure greeting"
    elif user_state.is_first_time_user and not state.get("greeting_shown", False):
        should_show_greeting = True
        greeting_reason = "first time user"
    
    if should_show_greeting:
        logger.info(f"Showing welcome card to user {user_id} - {greeting_reason}")
        
        # Create combined validation welcome card
        welcome_card = create_welcome_card(user_name)
        
        await adapter.send_card(service_url, conv_id, welcome_card)
        
        # Update state in database - mark greeting as shown and no longer first-time user
        await state_manager.update_user_state(
            user_id=user_id,
            greeting_shown=True,
            session_started=False,
            is_first_time_user=False
        )
        
        # Update local state for immediate use
        state["greeting_shown"] = True
        state["session_started"] = False
        
        # Save user message to database for pure greetings
        if is_pure_greeting_result:
            await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
            logger.info(f"Pure greeting processed for user {user_id}, ending request")
            return TeamsActivityResponse(text="")
        else:
            # First-time user with a question - continue processing their request
            logger.info(f"First-time user greeting shown, continuing to process their request: '{user_message}'")
            # Reset typing_sent flag so we can show typing indicator for the actual message processing
            typing_sent = False
            # Continue processing the message below

    # Handle contact queries for hardship validation
    # Only process if we have actual message content
    if not user_message.strip():
        logger.info(f"Empty message from user {user_id}, no processing needed")
        return TeamsActivityResponse(text="")
    
    # Check if user is ending the conversation using intent classification
    try:
        intent = classify_intent(user_message)
        is_ending_conversation = intent == "END"
        logger.debug(f"Intent classification for '{user_message}': {intent}")
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}, defaulting to continue")
        is_ending_conversation = False
    
    if is_ending_conversation:
        logger.info(f"User {user_id} is ending conversation with: '{user_message}'")
        
        # Save user message first
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before response
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Send friendly goodbye message
        from uwbot.utils.validation_responses import format_goodbye_message
        goodbye_message = format_goodbye_message()
        
        # Store bot message and get its database ID
        bot_msg_id = await _persist_bot_msg(user_msg_id, goodbye_message, "goodbye")
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, goodbye_message)
        
        # Log the successful response
        if bot_msg_id and activity_id:
            logger.debug(f"Sent goodbye response: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        # End the session
        await _clear_user_session(user_id)
        
        return TeamsActivityResponse(text="")
    
    contact_id = extract_contact_id_from_message(user_message)
    
    if contact_id:
        logger.info(f"Contact query detected for ID: {contact_id}")
        
        # Schedule analytics logging for validation request (background)
        _schedule_analytics("validation_request", {
            "contact_id": contact_id,
            "message_length": len(user_message),
            "is_first_time_user": user_state.is_first_time_user
        })
        
        # Save user message first
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before processing (only if not already sent)
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Call external validation API
        try:
            logger.info(f"Calling external validation API for contact {contact_id}")
            validation_result = await external_validation_client.validate_combined(
                contact_id=contact_id,
                user_id=user_id,
                user_name=user_name
            )
            
            if validation_result.is_success():
                contact_response = validation_result.value.get('message', 'No response available')
                intent_type = "combined_validation"
                logger.info(f"External validation successful for contact {contact_id}")
                
                # Schedule analytics for successful validation (background)
                _schedule_analytics("validation_success", {
                    "contact_id": contact_id,
                    "response_length": len(contact_response)
                })
            else:
                # Handle validation error
                error_msg = validation_result.error
                if "Invalid contact ID" in error_msg:
                    from uwbot.utils.validation_responses import format_invalid_contact_id_response
                    contact_response = format_invalid_contact_id_response(contact_id)
                    intent_type = "error"
                    logger.warning(f"Invalid contact ID in Teams message: {error_msg}")
                    
                    # Schedule analytics for invalid contact ID (background)
                    _schedule_analytics("validation_error", {
                        "contact_id": contact_id,
                        "error_type": "invalid_contact_id"
                    })
                else:
                    from uwbot.utils.validation_responses import format_error_response
                    contact_response = format_error_response(contact_id, f"Error validating contact {contact_id}: {error_msg}", "validation")
                    intent_type = "error"
                    logger.error(f"External validation failed for contact {contact_id}: {error_msg}")
                    
        except Exception as e:
            logger.error(f"Unexpected error calling external validation API: {e}")
            from uwbot.utils.validation_responses import format_error_response
            contact_response = format_error_response(contact_id, f"Error connecting to validation service for contact {contact_id}. Please try again.", "validation")
            intent_type = "error"
        
        # Store bot message and get its database ID
        bot_msg_id = await _persist_bot_msg(user_msg_id, contact_response, intent_type)
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, contact_response)
        
        # Log the successful response
        if bot_msg_id and activity_id:
            logger.debug(f"Sent {intent_type} response: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        return TeamsActivityResponse(text="")
    
    # If no contact ID found, provide helpful guidance
    elif user_message.strip():
        logger.info(f"No contact ID found in message: '{user_message}'")
        
        # Save user message
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before processing (only if not already sent)
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Provide helpful response for combined validation
        from uwbot.utils.validation_responses import format_help_message
        help_message = format_help_message()
        
        # Store bot message and get its database ID
        bot_msg_id = await _persist_bot_msg(user_msg_id, help_message, "help")
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, help_message)
        
        # Log the successful response 
        if bot_msg_id and activity_id:
            logger.debug(f"Sent help response: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
    
    return TeamsActivityResponse(text="")