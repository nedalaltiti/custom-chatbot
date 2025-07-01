# hrbot/api/routers/teams.py

from fastapi import APIRouter, BackgroundTasks
from hrbot.services.feedback_service import FeedbackService
from hrbot.services.message_service import MessageService
from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from hrbot.services.processor import ChatProcessor
from hrbot.infrastructure.cards import create_welcome_card, create_feedback_card
from hrbot.config.settings import settings
from hrbot.utils.di import get_intent_service, get_content_classification_service
from hrbot.services.session_tracker import session_tracker 
from hrbot.utils.message import split_greeting, is_pure_greeting
from hrbot.utils.noi import NOIAccessChecker
from hrbot.utils.bot_name import get_bot_name
from hrbot.services.content_classification_service import ConversationFlow
import logging, re
from datetime import datetime
from pydantic import BaseModel
import time

logger = logging.getLogger(__name__)

router           = APIRouter()
adapter          = TeamsAdapter()
feedback_service = FeedbackService()
chat_processor   = ChatProcessor()
message_service  = MessageService()
noi_checker      = NOIAccessChecker()  # Initialize NOI access checker

# in-memory state
first_time_users = set()    # user_ids pending their first greeting
user_states      = {}       # user_id → {awaiting_confirmation, feedback_shown, use_streaming, last_bot_response_time}
user_memories    = {}       # user_id → ConversationBufferMemory
feedback_cards   = {}       # conv_id → AdaptiveCard activity_id

# Pattern to detect if response already contains the "anything else" question
_HAS_ANYTHING_ELSE_RE = re.compile(
    r"(?:Is there anything else I can help you with\?|"
    r"Anything else I can help you with\?|"
    r"Can I help you with anything else\?)",
    re.I
)

class ConversationBufferMemory:
    """Simple per-user chat buffer."""
    def __init__(self):
        self.messages = []

    def add_user_message(self, text: str):
        self.messages.append({"role":"user","content":text})

    def add_ai_message(self, text: str):
        self.messages.append({"role":"ai","content":text})


async def get_or_create_memory(user_id: str) -> ConversationBufferMemory:
    if user_id not in user_memories:
        user_memories[user_id] = ConversationBufferMemory()
    return user_memories[user_id]


async def _handle_conversation_ending(
    analysis, user_id: str, service_url: str, conv_id: str, 
    state: dict, user_message: str, session_id: str, reply_to_id: str = None
):
    """Handle conversation ending scenarios with appropriate feedback."""
    
    # Save the user's message first
    user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, reply_to_id)
    
    # Get appropriate response message
    response_message = get_content_classification_service().get_response_message(analysis)
    if response_message:
        # Store bot message and get its database ID
        bot_msg_id = await message_service.add_message(
            bot_name=get_bot_name(),
            env="development",
            channel="teams",
            user_id=user_id,
            session_id=session_id,
            role="bot",
            text=response_message,
            intent=get_content_classification_service().get_message_intent(analysis),
            reply_to_id=user_msg_id,
        )
        
        # Send message and get Teams activity ID
        activity_id = await adapter.send_message(service_url, conv_id, response_message)
        
        # Track the mapping
        if bot_msg_id and activity_id:
            feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
            logger.debug(f"Tracked ending mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
    
    # Send feedback card if required
    if get_content_classification_service().should_send_feedback(analysis):
        logger.info(f"Sending feedback for {analysis.flow_type.value} scenario")
        
        feedback_service.cancel_pending_feedback(user_id)
        # Send appropriate feedback card based on classification
        act_id = await feedback_service.send_feedback_prompt(service_url, conv_id)
        if act_id:
            feedback_cards[conv_id] = act_id
            state["awaiting_feedback"] = True
            state["feedback_shown"] = True
    
    # Clear session for ending scenarios
    _clear_user_session(user_id)


async def _ensure_user_message_saved(user_message: str, user_id: str, session_id: str, reply_to_id: str = None) -> int:
    """
    Ensure user message is saved to both memory and database.
    Returns the message ID.
    """
    # Save to memory
    memory = await get_or_create_memory(user_id)
    memory.add_user_message(user_message)
    
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
    aad_object_id = req.from_.aad_object_id
    service_url  = req.service_url
    conv_id      = req.conversation.id
    message_id   = req.reply_to_id 

    if user_message.strip():  # Only track if user sent actual message
        feedback_service.track_user_activity(user_id)

    # Send immediate typing indicator for user feedback
    if not req.value and user_message.strip():
        try:
            await adapter.send_typing(service_url, conv_id)
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")
    
    state = user_states.get(user_id)
    if state is None:                        # first ever message from this user
        logger.info(f"Creating new session for user {user_id} - first message ever")
        state = {
            "awaiting_more_help": False,     # Waiting for yes/no to "anything else?"
            "awaiting_feedback":  False,
            "feedback_shown":     False,
            "use_streaming":      True,
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
            # Clear any residual memory from previous session to prevent context pollution
            user_memories.pop(user_id, None)
            # Reset greeting shown flag for new session - this is key!
            state["greeting_shown"] = False
            state["session_started"] = True  # Mark this as a new session start
            logger.info(f"Reset greeting_shown=False for user {user_id} - new session after previous ended")
        else:
            # Continuing existing session
            state.setdefault("session_started", False)
            
        state.setdefault("awaiting_more_help", False)
        state.setdefault("awaiting_feedback", False)
        state.setdefault("feedback_shown", False)
        state.setdefault("use_streaming", True)
        state.setdefault("greeting_shown", False)
        state.setdefault("last_bot_response_time", None)

    session_id = state["session_id"]
    
    # Get job title for system override
    try:
        profile   = await adapter.get_user_profile(aad_object_id)
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
                        await adapter.update_card(service_url, conv_id, act_id, card)
                    else:
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
                await adapter.send_message(
                    service_url, conv_id,
                    "No problem! Feel free to reach out anytime you need HR assistance."
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

    if state.get("awaiting_more_help"):
        logger.info(f"User is responding to 'anything else?' question with: '{user_message}'")
        
        # Get conversation context for better intent detection
        memory = await get_or_create_memory(user_id)
        conversation_context = None
        if memory.messages:
            # Get last few messages for context
            recent_messages = memory.messages[-4:]  # Last 4 messages for context
            conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
        
        # Use LLM-based intent detection service
        intent_service = get_intent_service()
        intent = await intent_service.analyze_conversation_intent(
            user_message=user_message,
            conversation_context=conversation_context
        )
        
        logger.info(f"Intent detection: user_message='{user_message}', detected_intent='{intent}'")
        
        if intent == "END":
            # User wants to end the conversation
            logger.info(f"User {user_id} wants to end conversation based on intent detection")
            state["awaiting_more_help"] = False
            
            # Save the user's message before ending
            await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
            
            await adapter.send_message(
                service_url, conv_id,
                "Thank you for using our HR Assistant!"
            )
            
            # Send feedback card
            act_id = await feedback_service.send_feedback_prompt(service_url, conv_id)
            if act_id:
                feedback_cards[conv_id] = act_id
                state["awaiting_feedback"] = True
                state["feedback_shown"] = True
            
            _clear_user_session(user_id)
            return TeamsActivityResponse(text="")
        else:
            # User wants to continue (CONTINUE) - process their message normally
            logger.info(f"User wants to continue conversation: '{user_message}'")
            state["awaiting_more_help"] = False
            # Continue processing the message normally below

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
            await adapter.send_card(service_url, conv_id, card)
            
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
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            else:
                # Just greeting, record it and return
                logger.info(f"Pure greeting processed for user {user_id}, ending request")
                await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                return TeamsActivityResponse(text="")
        else:
            # User has already seen greeting in this session
            logger.info(f"User {user_id} already saw greeting in this session (greeting_shown={state.get('greeting_shown')})")
            if user_payload:
                # Greeting + question - process the question
                user_message = user_payload.strip()
                logger.info(f"Processing question from repeat greeting: '{user_message}'")
                # Show typing indicator for processing the question
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            elif is_only_greeting:
                # Pure greeting in same session - give a friendly response without card
                logger.info(f"Returning user greeting again in same session: '{user_message}' - sending simple response")
                user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                
                # Store bot message and get its database ID
                bot_msg_id = await _persist_bot_msg(user_msg_id, "Hello again! How can I help you today?", "greeting")
                
                # Send message and get Teams activity ID
                activity_id = await adapter.send_message(service_url, conv_id, "Hello again! How can I help you today?")
                
                # Track the mapping
                if bot_msg_id and activity_id:
                    feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                    logger.debug(f"Tracked greeting mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                
                return TeamsActivityResponse(text="")
            else:
                # Not a pure greeting but detected as greeting - send helper message
                logger.info(f"Ambiguous greeting in same session: '{user_message}' - sending helper response")
                user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                
                # Store bot message and get its database ID
                bot_msg_id = await _persist_bot_msg(user_msg_id, "I am here to assist with your inquiries. How can I help you today?", "greeting")
                
                # Send message and get Teams activity ID
                activity_id = await adapter.send_message(service_url, conv_id, "I am here to assist with your inquiries. How can I help you today?")
                
                # Track the mapping
                if bot_msg_id and activity_id:
                    feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                    logger.debug(f"Tracked greeting mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                
                return TeamsActivityResponse(text="")
    elif user_payload and not greet_only:
        # If greeting had additional content but not first time, use that as the actual message
        user_message = user_payload.strip()

    if noi_checker.is_noi_related(user_message):
        logger.info(f"NOI-related query detected from user {user_id}: '{user_message}' (early handling)")
        try:
            noi_result = await noi_checker.check_access(user_id, job_title)
            noi_response = noi_result['response']

            # Memory & DB
            memory = await get_or_create_memory(user_id)
            memory.add_user_message(user_message)
            memory.add_ai_message(noi_response)
            user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
            
            # Store bot message and get its database ID
            bot_msg_id = await message_service.add_message(
                bot_name=get_bot_name(), env="development", channel="teams", user_id=user_id,
                session_id=session_id, role="bot", text=noi_response, intent="informational",
                reply_to_id=user_msg_id
            )

            # Send message and get Teams activity ID
            activity_id = await adapter.send_message(service_url, conv_id, noi_response)
            
            # Track the mapping
            if bot_msg_id and activity_id:
                feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                logger.debug(f"Tracked NOI mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")

            # schedule delayed feedback only
            feedback_service.cancel_pending_feedback(user_id)
            if not feedback_service.has_received_feedback(user_id):
                feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, delay_minutes=10)

            return TeamsActivityResponse(text="")
        except Exception as e:
            logger.error(f"Error processing NOI request for user {user_id}: {e}")
            # fallthrough to standard processing if error


    # Get conversation context for analysis
    memory = await get_or_create_memory(user_id)
    conversation_context = None
    if memory.messages:
        recent_messages = memory.messages[-4:]  # Last 4 messages for context
        conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
    
    # Analyze conversation flow using intelligent classification
    classification_service = get_content_classification_service()
    analysis = await classification_service.analyze_conversation_flow(
        user_message=user_message,
        conversation_context=conversation_context,
        response_type="standard"  
    )
    
    logger.info(f"Conversation flow analysis: {analysis.flow_type.value} (confidence: {analysis.confidence}, feedback_timing: {analysis.feedback_timing})")
    
    should_end = classification_service.should_end_conversation(analysis)

    # Handle conversation ending scenarios immediately
    if should_end:
        await _handle_conversation_ending(
            analysis, user_id, service_url, conv_id, state, 
            user_message, session_id, req.reply_to_id
        )
        return TeamsActivityResponse(text="")
    
    # Handle redirected scenarios (off-topic questions)
    if analysis.flow_type.value == "continue_redirected":
        # Send redirect message but continue conversation
        redirect_message = classification_service.get_response_message(analysis)
        if redirect_message:
            await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
            
            # Store bot message and get its database ID
            bot_msg_id = await _persist_bot_msg(user_msg_id, redirect_message, "off_topic")
            
            # Send message and get Teams activity ID
            activity_id = await adapter.send_message(service_url, conv_id, redirect_message)
            
            # Track the mapping
            if bot_msg_id and activity_id:
                feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                logger.debug(f"Tracked redirect mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
            
            return TeamsActivityResponse(text="")
        
    if classification_service.should_schedule_delayed_feedback(analysis):
        if not feedback_service.has_received_feedback(user_id):
            delay_minutes = classification_service.get_feedback_delay_minutes(analysis)
            # Pass a callback to update feedback_cards[conv_id] when the card is sent
            def on_card_sent(conv_id, activity_id):
                if activity_id:
                    feedback_cards[conv_id] = activity_id
            feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, delay_minutes=delay_minutes, on_card_sent=on_card_sent)
            logger.info(f"Scheduled delayed feedback for user {user_id} in {delay_minutes} minutes")

    user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
    
    # Helper function for database persistence
    async def _persist_bot_msg(reply_id: int, text: str, intent: str = "CONTINUE") -> int | None:
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
    
    logger.info(f"[Teams] Generating response for %s", user_id)

    # Enhanced streaming logic following Microsoft Teams requirements
    if state.get("use_streaming", True) and len(user_message.strip()) >= 2:
        logger.info(f"Starting real-time LLM streaming for query: {user_message[:50]}...")
        
        try:
            # Stream directly from LLM - much faster!
            async def llm_stream_generator():
                """Generator that streams directly from LLM and formats bullet points."""
                full_response = ""
                async for chunk in chat_processor.process_message_streaming(
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
                    formatted_response = chat_processor._format_bullet_points(full_response)
                    memory.add_ai_message(formatted_response)
                    
                    # Update last bot response time
                    state["last_bot_response_time"] = datetime.utcnow()
                    
                    # Check if response contains "anything else?" 
                    if _HAS_ANYTHING_ELSE_RE.search(formatted_response):
                        state["awaiting_more_help"] = True
                    
                    # Store in database with appropriate intent
                    intent = classification_service.get_message_intent(analysis)
                    bot_msg_id = await _persist_bot_msg(user_msg_id, formatted_response, intent)
                    
                    # Track the mapping - for streaming, we'll need to get the activity ID
                    # This will be handled after streaming completes
                    if bot_msg_id:
                        # Store the bot message ID temporarily to map later
                        state["last_bot_message_id"] = bot_msg_id

            # Start real-time streaming from LLM
            success, activity_id = await adapter.stream_message(
                service_url, conv_id,
                text_generator=llm_stream_generator(),
                informative="I'm analyzing your request..."
            )
            
            # Track the mapping between Teams activity ID and bot message database ID
            if success and activity_id:
                # Get the bot message ID that was stored during streaming
                bot_msg_id = state.get("last_bot_message_id")
                if bot_msg_id:
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
                # Fallback to traditional method
                result = await chat_processor.process_message(
                    user_message,
                    chat_history=[m["content"] for m in memory.messages[:-1]],
                    user_id=user_id,
                    system_override=system_override
                )
                if result.is_success():
                    answer = result.unwrap()["response"].strip()
                    memory.add_ai_message(answer)
                    state["last_bot_response_time"] = datetime.utcnow()
                    intent = classification_service.get_message_intent(analysis)
                    
                    # Check if the response already contains "anything else?" question
                    has_anything_else = _HAS_ANYTHING_ELSE_RE.search(answer)
                    if has_anything_else:
                        # Set state to await response
                        state["awaiting_more_help"] = True
                    
                    # Store bot message and get its database ID
                    bot_msg_id = await _persist_bot_msg(user_msg_id, answer, intent)
                    
                    # Send message and get Teams activity ID
                    activity_id = await adapter.send_message(service_url, conv_id, answer)
                    
                    # Track the mapping for feedback
                    if bot_msg_id and activity_id:
                        feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                        logger.debug(f"Tracked streaming fallback mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
                else:
                    # Fallback message
                    await adapter.send_message(
                        service_url, conv_id,
                        "Sorry, I hit a glitch. Please try again later."
                    )
                
        except Exception as e:
            logger.error(f"Streaming error: {e}, falling back to regular processing")
            # Fallback to traditional method
            result = await chat_processor.process_message(
                user_message,
                chat_history=[m["content"] for m in memory.messages[:-1]],
                user_id=user_id,
                system_override=system_override
            )
            if result.is_success():
                answer = result.unwrap()["response"].strip()
                memory.add_ai_message(answer)
                state["last_bot_response_time"] = datetime.utcnow()
                intent = classification_service.get_message_intent(analysis)
                
                # Check if the response already contains "anything else?" question
                has_anything_else = _HAS_ANYTHING_ELSE_RE.search(answer)
                if has_anything_else:
                    # Set state to await response
                    state["awaiting_more_help"] = True

                # Store bot message and get its database ID
                bot_msg_id = await _persist_bot_msg(user_msg_id, answer, intent)
                
                logger.info(f"Sending regular message (length: {len(answer)})")
                # Send message and get Teams activity ID
                activity_id = await adapter.send_message(service_url, conv_id, answer)
                
                # Track the mapping
                if bot_msg_id and activity_id:
                    feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                    logger.debug(f"Tracked fallback mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
            else:
                # Fallback message
                await adapter.send_message(
                    service_url, conv_id,
                    "Sorry, I hit a glitch. Please try again later."
                )
                
        return TeamsActivityResponse(text="")
    else:
        # Use traditional method for very short queries or when streaming is disabled
        logger.info(f"Using traditional processing for short query")
        
        # Show analyzing message for non-streaming responses
        if len(user_message.split()) > 1:
            try:
                await adapter.send_informative_update(
                    service_url, conv_id,
                    "I'm analyzing your request...",
                    stream_sequence=1
                )
            except Exception as e:
                logger.warning(f"Failed to send analyzing message: {e}")
        
        result = await chat_processor.process_message(
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
            intent = classification_service.get_message_intent(analysis)
            
            # Store bot message and get its database ID
            bot_msg_id = await _persist_bot_msg(user_msg_id, answer, intent)
            
            logger.info(f"Sending regular message (length: {len(answer)})")
            # Send message and get Teams activity ID
            activity_id = await adapter.send_message(service_url, conv_id, answer)
            
            # Track the mapping
            if bot_msg_id and activity_id:
                feedback_service.track_activity_to_message_mapping(activity_id, bot_msg_id)
                logger.debug(f"Tracked non-streaming mapping: Teams activity {activity_id} -> bot message DB ID {bot_msg_id}")
        else:
            # Fallback message
            await adapter.send_message(
                service_url, conv_id,
                "Sorry, I hit a glitch. Please try again later."
            )
        
    return TeamsActivityResponse(text="")


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

@router.post("/debug", response_model=DebugChatResponse)
async def debug_chat(req: DebugChatRequest):
    """Debug endpoint that returns actual AI response for testing."""
    import time
    start_time = time.time()
    
    try:
        # Create a session ID for this debug conversation
        session_id = session_tracker.get(req.user_id)
        
        # Get conversation context
        memory = await get_or_create_memory(req.user_id)
        conversation_context = None
        if memory.messages:
            recent_messages = memory.messages[-4:]
            conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
        
        # Analyze conversation flow
        classification_service = get_content_classification_service()
        analysis = await classification_service.analyze_conversation_flow(
            user_message=req.text,
            conversation_context=conversation_context,
            response_type="standard"
        )
        
        # Save user message to database
        user_msg_id = await message_service.add_message(
            bot_name="hrbot",
            env="development",
            channel="debug",  # Using 'debug' channel to distinguish from teams
            user_id=req.user_id,
            session_id=session_id,
            role="user",
            text=req.text,
            intent=None,
            reply_to_id=None,
        )
        
        # Get AI response
        result = await chat_processor.process_message(
            req.text,
            chat_history=[m["content"] for m in memory.messages],
            user_id=req.user_id
        )
        
        processing_time = time.time() - start_time
        
        if result.is_success():
            bot_response = result.unwrap()["response"].strip()
            
            # Save to memory for context
            memory.add_user_message(req.text)
            memory.add_ai_message(bot_response)
            
            # Save bot response to database
            await message_service.add_message(
                bot_name="hrbot",
                env="development", 
                channel="debug",
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent=classification_service.get_message_intent(analysis),
                reply_to_id=user_msg_id,
            )
            
            return DebugChatResponse(
                user_message=req.text,
                bot_response=bot_response,
                conversation_flow=analysis.flow_type.value,
                confidence=analysis.confidence,
                processing_time=round(processing_time, 2)
            )
        else:
            # Even on error, save to memory and database
            error_response = "Sorry, I encountered an error processing your request."
            memory.add_user_message(req.text)
            memory.add_ai_message(error_response)
            
            await message_service.add_message(
                bot_name="hrbot",
                env="development",
                channel="debug", 
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=error_response,
                intent="error",
                reply_to_id=user_msg_id,
            )
            
            return DebugChatResponse(
                user_message=req.text,
                bot_response=error_response,
                conversation_flow="error",
                confidence=0.0,
                processing_time=round(processing_time, 2)
            )
            
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
        processing_time = time.time() - start_time
        return DebugChatResponse(
            user_message=req.text,
            bot_response=f"Error: {str(e)}",
            conversation_flow="error",
            confidence=0.0,
            processing_time=round(processing_time, 2)
        )

def _clear_user_session(user_id: str):
    """Clear per-user memory, state, and feedback tracking.
    
    This completely resets the user's session so that their next message
    will be treated as starting a new session.
    """
    
    # Clear in-memory conversation data
    mem = user_memories.pop(user_id, None)
    old_state = user_states.pop(user_id, None)  # This is the key - removes session_id 
    first_time_users.discard(user_id)  # They're no longer "first time" but can get greeting cards in new sessions
    
    # Clear feedback cards tracking for this user's conversations
    feedback_cards.pop(user_id, None)
    
    # Clear feedback service session data
    feedback_service.clear_user_session(user_id)
    
    # Log detailed session cleanup for debugging
    message_count = len(mem.messages) if mem and mem.messages else 0
    had_greeting = old_state.get("greeting_shown", False) if old_state else False
    logger.info(f"🧹 CLEARED session for user {user_id}:")
    logger.info(f"   • {message_count} messages in memory")
    logger.info(f"   • greeting_shown was: {had_greeting}")
    logger.info(f"   • Next greeting will trigger NEW SESSION and greeting card")
    logger.info(f"   • Removed from first_time_users: {user_id in first_time_users}")
    
    # Ensure the user is completely removed from session tracking so next message starts fresh
    # This makes the next message go through the "state is None" or "session_id not in state" logic