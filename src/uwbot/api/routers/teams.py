# uwbot/api/routers/teams.py

import asyncio
from fastapi import APIRouter, BackgroundTasks
from uwbot.services.feedback_service import FeedbackService
from uwbot.services.message_service import MessageService
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from uwbot.infrastructure.cards import create_feedback_card
from uwbot.config.settings import settings
from uwbot.utils.di import get_contact_service
from uwbot.services.session_tracker import session_tracker 
from uwbot.utils.bot_name import get_bot_name
from uwbot.utils.message import is_pure_greeting
from uwbot.utils.intent import classify_intent
from uwbot.utils.di import get_llm
import logging
from datetime import datetime
from pydantic import BaseModel
import time

logger = logging.getLogger(__name__)

router           = APIRouter()
adapter          = TeamsAdapter()
feedback_service = FeedbackService()
message_service  = MessageService()

# in-memory state
first_time_users = set()    # user_ids pending their first greeting
user_states      = {}       # user_id → {feedback_shown, last_bot_response_time}
feedback_cards   = {}       # conv_id → AdaptiveCard activity_id

async def _ensure_user_message_saved(user_message: str, user_id: str, session_id: str, reply_to_id: str = None) -> int:
    """
    Ensure user message is saved to database.
    Returns the message ID.
    """
    # Save to database
    user_msg_id = await message_service.add_message(
        bot_name   = get_bot_name(),
        env        = "development",
        channel    = "teams",
        user_id    = user_id,
        session_id = session_id,
        role       = "user",
        text       = user_message,
        reply_to_id= reply_to_id,
    )
    
    return user_msg_id

@router.post("/")
async def teams_messages(req: TeamsMessageRequest, background_tasks: BackgroundTasks):
    user_message = req.text or ""
    user_id      = req.from_.id
    user_name    = req.from_.name
    service_url  = req.service_url
    conv_id      = req.conversation.id

    # Helper function for database persistence
    async def _persist_bot_msg(reply_id: int, text: str, intent: str = "validation") -> int | None:
        try:
            bot_msg_id = await message_service.add_message(
                bot_name   = get_bot_name(),
                env        = "development",
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

    # Send immediate typing indicator for ALL user messages (including empty ones)
    typing_sent = False
    try:
        await adapter.send_typing(service_url, conv_id)
        typing_sent = True
        logger.debug(f"📝 Typing indicator sent immediately for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to send typing indicator: {e}")
    
    # Track user activity for feedback timeout (only for non-empty messages)
    if user_message.strip():  # Only track if user sent actual message
        feedback_service.track_user_activity(user_id)
        logger.debug(f"🔄 User activity tracked for {user_id} - feedback timeout reset")
    
    state = user_states.get(user_id)
    if state is None:                        # first ever message from this user
        logger.info(f"Creating new session for user {user_id} - first message ever")
        state = {
            "awaiting_feedback":  False,
            "feedback_shown":     False,
            "session_id":         session_tracker.get(user_id),
            "greeting_shown":     False,     # Track if greeting card has been shown in this session   
            "last_bot_response_time": None,  # Track when bot last responded
            "session_started":    True,      # Mark this as a new session start
        }
        user_states[user_id] = state          
        first_time_users.add(user_id)
        logger.info(f"Added user {user_id} to first_time_users set")
    else:
        # If the previous session was ended, rebuild essentials for new session
        if "session_id" not in state:
            logger.info(f"Rebuilding session for returning user {user_id} - session was cleared, this is a NEW session")
            state["session_id"] = session_tracker.get(user_id)
            # Reset greeting shown flag for new session
            state["greeting_shown"] = False
            state["session_started"] = True  # Mark this as a new session start
            logger.info(f"Reset greeting_shown=False for user {user_id} - new session after previous ended")
        else:
            # Continuing existing session
            state.setdefault("session_started", False)
            
        state.setdefault("awaiting_feedback", False)
        state.setdefault("feedback_shown", False)
        state.setdefault("greeting_shown", False)
        state.setdefault("last_bot_response_time", None)

    session_id = state["session_id"]

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
                            await feedback_service.record_message_reply_feedback(
                                message_id=target_message_id,
                                feedback=standardized_feedback,
                                feedback_comment=str(feedback_text).strip(),
                            )
                            logger.info(f"🔵 Recorded built-in feedback for message {target_message_id}: {standardized_feedback}")
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
        try:
            logger.info(f"🔴 TEAMS ACTION.EXECUTE: message/executeAction received")
            logger.info(f"🔴 PAYLOAD: {req.value}")
            
            # This is Teams' Action.Execute from built-in feedback
            # Return empty JSON object for Action.Execute
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams Action.Execute: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
    
    # Handle Teams built-in feedback form submissions (composeExtensions/submitAction)
    elif req.name == 'composeExtensions/submitAction':
        try:
            logger.info(f"🔴 TEAMS BUILT-IN FEEDBACK: composeExtensions/submitAction received")
            logger.info(f"🔴 PAYLOAD: {req.value}")
            
            # This is Teams' built-in feedback form submission
            # The payload contains the user's feedback from the form
            
            feedback_data = req.value or {}
            
            # Extract feedback information
            # Teams sends the feedback in various possible formats
            user_feedback = ""
            feedback_category = "general"
            
            # Try to extract the feedback text from various possible fields
            for possible_field in ['feedback', 'comment', 'text', 'data', 'value']:
                if possible_field in feedback_data and feedback_data[possible_field]:
                    user_feedback = str(feedback_data[possible_field]).strip()
                    break
            
            # If no direct feedback text, check nested objects
            if not user_feedback:
                for key, value in feedback_data.items():
                    if isinstance(value, dict):
                        for nested_key in ['feedback', 'comment', 'text']:
                            if nested_key in value and value[nested_key]:
                                user_feedback = str(value[nested_key]).strip()
                                break
                        if user_feedback:
                            break
            
            logger.info(f"🔴 Extracted feedback: '{user_feedback}'")
            
            # Record the feedback in our database if we have content
            if user_feedback:
                try:
                    # Record as general session feedback since it's from Teams' form
                    await feedback_service.record_feedback(
                        user_id=user_id,
                        rating=3,  # Default neutral rating for text feedback
                        comment=user_feedback,
                        session_id=conv_id,
                    )
                    logger.info(f"🔴 Recorded Teams built-in feedback: '{user_feedback[:50]}...'")
                except Exception as e:
                    logger.error(f"🔴 Error recording Teams feedback: {e}")
            
            # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams built-in feedback: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
    
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
            try:
                raw    = req.value.get("rating")
                rating = int(raw) if str(raw).isdigit() else None

                if rating:
                    # Preserve existing comment content when updating card
                    existing_comment = req.value.get("comment", "").strip()
                    
                    # Highlight stars, keep the "Provide Feedback" button with preserved comment
                    card = create_feedback_card(
                        selected_rating=rating,
                        interactive=True,
                        existing_comment=existing_comment
                    )
                    act_id = feedback_cards.get(conv_id)
                    if act_id:
                        # Update the existing card instead of creating a new one
                        await adapter.update_card(service_url, conv_id, act_id, card)
                        logger.info(f"Updated existing feedback card for conversation {conv_id} with rating {rating}")
                    else:
                        # Only create new card if no existing card found
                        logger.warning(f"No existing feedback card found for conversation {conv_id}, creating new one")
                        new_act = await adapter.send_card(service_url, conv_id, card)
                        if new_act:
                            feedback_cards[conv_id] = new_act

                    # Remember we showed the stars
                    state["feedback_shown"] = True
                    state["awaiting_feedback"] = False 
                    
            except Exception as e:
                logger.error(f"Error processing submit_rating: {e}")

            return TeamsActivityResponse(text="")

        if action == "dismiss_feedback":
            try:
                # Send typing indicator before response (only if not already sent)
                if not typing_sent:
                    await adapter.send_typing(service_url, conv_id)
                
                await adapter.send_message(
                    service_url, conv_id,
                    "No problem! Feel free to reach out anytime you need validation assistance."
                )
                
                # Remove current feedback card and end session
                feedback_cards.pop(conv_id, None)
                _clear_user_session(user_id)
                
            except Exception as e:
                logger.error(f"Error processing dismiss_feedback: {e}")
            
            return TeamsActivityResponse(text="")

        if action == "submit_feedback":
            try:
                raw     = req.value.get("rating")
                rating  = int(raw) if str(raw).isdigit() else 3
                comment = (req.value.get("comment") or "").strip()
                
                # Also check for comment in nested structures
                if not comment:
                    comment = (req.value.get("commentValue") or "").strip()
                if not comment:
                    # Check if comment is in a nested data structure
                    for key, value in req.value.items():
                        if isinstance(value, str) and len(value.strip()) > 0 and key.lower() in ['comment', 'feedback', 'text', 'message']:
                            comment = value.strip()
                            break
                
                logger.info(f"Processing feedback submission - user: {user_id}, rating: {rating}, comment: '{comment}'")

                # Persist the feedback
                await feedback_service.record_feedback(
                    user_id   = user_id,
                    rating    = rating,
                    comment   = comment,
                    session_id= conv_id,
                )

                # Replace the card with a non-interactive "submitted" card
                submitted_card = {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.3",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "✅ Feedback submitted – thank you!",
                            "weight": "Bolder",
                            "size": "Medium"
                        }
                    ]
                }
                act_id = feedback_cards.pop(conv_id, None)
                if act_id:
                    await adapter.update_card(service_url, conv_id, act_id, submitted_card)

                state["feedback_shown"] = True
                state["awaiting_feedback"] = False 
                
                # End session immediately after feedback submission
                _clear_user_session(user_id)
                
            except Exception as e:
                logger.error(f"Error processing submit_feedback: {e}")
                # Always send a success response to prevent "Unable to reach app" errors
                try:
                    # Send typing indicator before fallback message (only if not already sent)
                    if not typing_sent:
                        await adapter.send_typing(service_url, conv_id)
                    await adapter.send_message(service_url, conv_id, "Thank you for your feedback!")
                except Exception as send_error:
                    logger.error(f"Failed to send fallback message: {send_error}")

            return TeamsActivityResponse(text="")

        if action == "message_reply_feedback":
            action_value = req.value.get("actionValue", {})
            message_id = action_value.get("messageId")
            feedback_comment = action_value.get("feedbackComment", "")
            standardized_feedback = action_value.get("feedback", "").lower()

            if message_id and standardized_feedback:
                # Record the message reply feedback
                try:
                    success = await feedback_service.record_message_reply_feedback(
                        message_id=int(message_id),
                        feedback=standardized_feedback,
                        feedback_comment=str(feedback_comment).strip(),
                        reaction=str(action_value)
                    )
                    
                    if success:
                        logger.info(f"Successfully recorded message reply feedback: message_id={message_id}, feedback={standardized_feedback}")
                        
                        # Send appropriate thank you message based on feedback
                        # NO thank you message for message-level feedback
                        # Message-level feedback should be silent and non-disruptive
                        
                    else:
                        logger.error("Failed to record message reply feedback in database")
                        # NO acknowledgment for message-level feedback, even on database failure
                        
                except Exception as e:
                    logger.error(f"Error recording message reply feedback: {e}")
                    # NO acknowledgment for message-level feedback, even on error

            return TeamsActivityResponse(text="")

        return TeamsActivityResponse(text="")

    # Check for pure greetings using message.py utility
    is_pure_greeting_result = is_pure_greeting(user_message)
    
    # Show welcome card for pure greetings or first-time users
    should_show_greeting = False
    greeting_reason = ""
    
    if is_pure_greeting_result:
        should_show_greeting = True
        greeting_reason = "pure greeting"
    elif user_id in first_time_users and not state.get("greeting_shown", False):
        should_show_greeting = True
        greeting_reason = "first time user"
    
    if should_show_greeting:
        logger.info(f"Showing welcome card to user {user_id} - {greeting_reason}")
        
        # Create hardship validation specific welcome card
        welcome_card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"Hi {user_name} 👋",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": "Accent"
                },
                {
                    "type": "TextBlock",
                    "text": "I'm your **Validation Assistant**. I can help you check if contacts have hardship validation data and analyze their financial hardship claims.",
                    "wrap": True,
                    "spacing": "Medium",
                },
            ]
        }
        
        await adapter.send_card(service_url, conv_id, welcome_card)
        
        # Mark greeting as shown and remove from first-time users
        state["greeting_shown"] = True
        state["session_started"] = False
        first_time_users.discard(user_id)
        
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
        llm_service = get_llm()
        intent = await classify_intent(llm_service, user_message)
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
        goodbye_message = "You're welcome! I'm glad I could help you with your validation check. Feel free to reach out anytime you need to validate hardship data for other contacts. Have a great day! 👋"
        
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
                feedback_cards[conv_id] = feedback_activity_id
                logger.info(f"Sent feedback card to user {user_id} after conversation end with activity ID {feedback_activity_id}")
            else:
                logger.warning(f"Failed to send feedback card to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending feedback card after conversation end: {e}")
        
        # End the session
        _clear_user_session(user_id)
        
        return TeamsActivityResponse(text="")
        
    contact_service = get_contact_service()
    contact_id = contact_service.extract_contact_id_from_message(user_message)
    
    if contact_id:
        logger.info(f"Contact query detected for ID: {contact_id}")
        
        # Save user message first
        user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
        
        # Send typing indicator before processing (only if not already sent)
        if not typing_sent:
            try:
                await adapter.send_typing(service_url, conv_id)
            except Exception as e:
                logger.warning(f"Failed to send typing indicator: {e}")
        
        # Check if the contact has hardship validation data
        contact = await contact_service.get_contact_by_id(contact_id)
        contact_response = contact_service.format_contact_response(contact)
        
        # Store bot message and get its database ID
        bot_msg_id = await _persist_bot_msg(user_msg_id, contact_response, "validation")
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, contact_response)
        
        # Track the mapping
        if bot_msg_id and activity_id:
            feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
            logger.debug(f"Tracked hardship validation mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        
        # Schedule feedback after 10 minutes of inactivity
        logger.info(f"⏰ Scheduling feedback timeout for user {user_id} in conversation {conv_id} - will trigger after 10 minutes of inactivity")
        
        # Define callback to track feedback cards in the router
        def track_feedback_card(conv_id: str, activity_id: str):
            feedback_cards[conv_id] = activity_id
            logger.info(f"📋 Tracked timeout feedback card: conversation {conv_id} -> activity {activity_id}")
        
        feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, on_card_sent=track_feedback_card)
        
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
        
        # Provide helpful response
        help_message = (
            "I'm here to help you validate hardship data.\n "
            "Please provide a contact ID to validate the hardship data.\n\n"
        )
        
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
        
        # Define callback to track feedback cards in the router
        def track_feedback_card(conv_id: str, activity_id: str):
            feedback_cards[conv_id] = activity_id
            logger.info(f"📋 Tracked timeout feedback card: conversation {conv_id} -> activity {activity_id}")
        
        feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, on_card_sent=track_feedback_card)
    
    return TeamsActivityResponse(text="")


# Debug endpoint models and implementation for QA team
class DebugChatRequest(BaseModel):
    text: str
    user_id: str = "debug-user"

class DebugChatResponse(BaseModel):
    user_message: str
    bot_response: str
    processing_time: float

@router.post("/debug", response_model=DebugChatResponse)
async def debug_chat(req: DebugChatRequest):
    """Debug endpoint that returns hardship validation check response for testing."""
    import time
    start_time = time.time()
    
    try:
        # Create a session ID for this debug conversation
        session_id = session_tracker.get(req.user_id)
        
        # Save user message to database
        user_msg_id = await message_service.add_message(
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
        
        # Check if message contains contact ID
        contact_service = get_contact_service()
        contact_id = contact_service.extract_contact_id_from_message(req.text)
        
        processing_time = time.time() - start_time
        
        if contact_id:
            # Check hardship validation data
            result = await contact_service.get_contact_by_id(contact_id)
            bot_response = contact_service.format_contact_response(result)
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=get_bot_name(),
                env="development", 
                channel="debug",
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent="validation",
                reply_to_id=user_msg_id,
            )
        else:
            # No contact ID found
            bot_response = (
                "I'm here to help you validate hardshipdata. "
                "Please provide a contact ID to validate the hardship data.\n\n"
            )
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=get_bot_name(),
                env="development",
                channel="debug", 
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent="help",
                reply_to_id=user_msg_id,
            )
        
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

def _clear_user_session(user_id: str):
    """Clear per-user memory, state, and feedback tracking.
    
    This completely resets the user's session so that their next message
    will be treated as starting a new session.
    """
    
    # Clear in-memory conversation data
    old_state = user_states.pop(user_id, None)  # This is the key - removes session_id 
    first_time_users.discard(user_id)  # They're no longer "first time" but can get greeting cards in new sessions
    
    # Clear feedback cards tracking for this user's conversations
    feedback_cards.pop(user_id, None)
    
    # Clear feedback service session data
    feedback_service.clear_user_session(user_id)
    
    # Log detailed session cleanup for debugging
    had_greeting = old_state.get("greeting_shown", False) if old_state else False
    logger.info(f"🧹 CLEARED session for user {user_id}:")
    logger.info(f"   • greeting_shown was: {had_greeting}")
    logger.info(f"   • Next greeting will trigger NEW SESSION and greeting card")
    logger.info(f"   • Removed from first_time_users: {user_id in first_time_users}")
    
    # Ensure the user is completely removed from session tracking so next message starts fresh
    # This makes the next message go through the "state is None" or "session_id not in state" logic