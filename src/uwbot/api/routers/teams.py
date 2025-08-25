# uwbot/api/routers/teams.py

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends
from uwbot.services.feedback_service import FeedbackService
from uwbot.services.message_service import MessageService
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from uwbot.infrastructure.cards import create_feedback_card, create_welcome_card
from uwbot.utils.di import get_combined_validation_uc, get_teams_feedback_handler, get_card_action_handler, get_feedback_card_tracker   
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
feedback_service = FeedbackService()
message_service  = MessageService()
background_tasks = get_background_task_service()
state_manager    = get_hybrid_state_manager()

# Database-backed state management (replaces in-memory dictionaries)
# first_time_users and user_states are now managed by DatabaseStateManager

async def _ensure_user_message_saved(user_message: str, user_id: str, session_id: str, reply_to_id: str = None) -> int:
    """
    Ensure user message is saved to database.
    Returns the message ID.
    """
    # Save to database
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

@router.post("/")
async def teams_messages(
    req: TeamsMessageRequest, 
    background_tasks: BackgroundTasks,
    external_validation_client = Depends(get_combined_validation_uc),
    teams_feedback_handler = Depends(get_teams_feedback_handler),
    card_action_handler = Depends(get_card_action_handler),
    feedback_card_tracker = Depends(get_feedback_card_tracker)
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
        return background_tasks.schedule_message_persistence(
            bot_name=get_bot_name(),
            user_id=user_id,
            session_id=session_id,
            role="bot",
            text=text,
            intent=intent,
            reply_to_id=reply_id,
            channel="teams"
        )
    
    # Helper function for analytics logging (background)
    def _schedule_analytics(event_type: str, metadata: dict = None) -> asyncio.Task:
        """Schedule analytics logging as a background task."""
        return background_tasks.schedule_analytics_logging(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {}
        )

    # Send immediate typing indicator for user messages (but NOT for card actions)
    typing_sent = False
    
    # Comprehensive card action detection
    is_card_action = (
        req.type == 'invoke' or 
        req.name in ['message/submitAction', 'message/executeAction', 'composeExtensions/submitAction'] or
        (req.value and req.value.get('action') in ['submit_rating', 'submit_feedback', 'dismiss_feedback', 'message_reply_feedback'])
    )
    
    if not is_card_action:
        try:
            await adapter.send_typing(service_url, conv_id)
            typing_sent = True
            logger.debug(f"📝 Typing indicator sent immediately for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")
    else:
        logger.debug(f"🚫 Skipping typing indicator for card action: type={req.type}, name={req.name}")
    
    # Track user activity for feedback timeout (only for non-empty messages)
    if user_message.strip():  # Only track if user sent actual message
        feedback_service.track_user_activity(user_id)
        logger.debug(f"🔄 User activity tracked for {user_id} - feedback timeout reset")
    
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
                    return await teams_feedback_handler.handle_builtin_feedback_loop(
                        action_data, user_id, conv_id, req.reply_to_id
                    )
                
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
        return await teams_feedback_handler.handle_message_execute_action(
            req.value or {}, user_id, conv_id
        )
    
    # Handle Teams built-in feedback form submissions (composeExtensions/submitAction)
    elif req.name == 'composeExtensions/submitAction':
        return await teams_feedback_handler.handle_compose_extensions_submit_action(
            req.value or {}, user_id, conv_id
        )
    
    # Legacy invoke handling (keeping for compatibility)
    elif req.name == 'message/submitAction':
        try:
            logger.info(f"Legacy invoke handling: name={req.name}, value={req.value}")
            return {}
        except Exception as e:
            logger.error(f"Error in legacy invoke handling: {e}")
            return {}
    
    if req.value:
        action = req.value.get("action")

        if action == "submit_rating":
            return await card_action_handler.handle_submit_rating(
                req.value, conv_id, service_url, feedback_card_tracker, state
            )

        if action == "dismiss_feedback":
            return await card_action_handler.handle_dismiss_feedback(
                conv_id, service_url, feedback_card_tracker, user_id, typing_sent, _clear_user_session
            )

        if action == "submit_feedback":
            return await card_action_handler.handle_submit_feedback(
                req.value, conv_id, service_url, feedback_card_tracker, user_id, state, typing_sent, _clear_user_session
            )

        if action == "message_reply_feedback":
            return await card_action_handler.handle_message_reply_feedback(req.value)

        return TeamsActivityResponse(text="")

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
        intent = await classify_intent(user_message)
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
        
        # Track the mapping
        if bot_msg_id and activity_id:
            feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
            logger.debug(f"Tracked goodbye mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        # Send feedback card after a short delay
        try:
            await asyncio.sleep(1)  # Short delay before feedback card
            feedback_card = create_feedback_card()
            feedback_activity_id = await adapter.send_card(service_url, conv_id, feedback_card)
            
            if feedback_activity_id:
                feedback_card_tracker.track_feedback_card(conv_id, feedback_activity_id)
                logger.info(f"Sent feedback card to user {user_id} after conversation end with activity ID {feedback_activity_id}")
            else:
                logger.warning(f"Failed to send feedback card to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending feedback card after conversation end: {e}")
        
        # End the session
        await _clear_user_session(user_id, feedback_card_tracker)
        
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
        
        # Track the mapping
        if bot_msg_id and activity_id:
            feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
            logger.debug(f"Tracked {intent_type} mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
            
            # Schedule feedback card tracking as background task
            background_tasks.schedule_feedback_card_tracking(
                user_id=user_id,
                teams_activity_id=activity_id,
                bot_message_id=bot_msg_id,
                delay_minutes=10
            )
        
        # Schedule feedback after 10 minutes of inactivity
        logger.info(f"⏰ Scheduling feedback timeout for user {user_id} in conversation {conv_id} - will trigger after 10 minutes of inactivity")
        
        # Use the feedback card tracker service
        feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, on_card_sent=feedback_card_tracker.create_track_feedback_card_callback())
    
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
        
        # Track the mapping
        if bot_msg_id and activity_id:
            feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
            logger.debug(f"Tracked help mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        # Schedule feedback after 10 minutes of inactivity
        logger.info(f"⏰ Scheduling feedback timeout for user {user_id} in conversation {conv_id} - will trigger after 10 minutes of inactivity")
        
        # Use the feedback card tracker service
        feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, on_card_sent=feedback_card_tracker.create_track_feedback_card_callback())
    
    return TeamsActivityResponse(text="")