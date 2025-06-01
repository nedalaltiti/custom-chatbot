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
from hrbot.services.content_classification_service import ConversationFlow
import logging, re
from datetime import datetime

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
    await _ensure_user_message_saved(user_message, user_id, session_id, reply_to_id)
    
    # Get appropriate response message
    response_message = get_content_classification_service().get_response_message(analysis)
    if response_message:
        await adapter.send_message(service_url, conv_id, response_message)
    
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
        bot_name   = "hrbot",
        env        = "development",
        channel    = "teams",
        user_id    = user_id,
        session_id = session_id,
        role       = "user",
        text       = user_message,
        reply_to_id= reply_to_id,
    )
    
    return user_msg_id


@router.post("/", response_model=TeamsActivityResponse)
async def teams_messages(req: TeamsMessageRequest, background_tasks: BackgroundTasks):
    user_message = req.text or ""
    user_id      = req.from_.id
    user_name    = req.from_.name
    aad_object_id = req.from_.aad_object_id
    service_url  = req.service_url
    conv_id      = req.conversation.id
    
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
        state = {
            "awaiting_more_help": False,     # Waiting for yes/no to "anything else?"
            "awaiting_feedback":  False,
            "feedback_shown":     False,
            "use_streaming":      True,
            "session_id":         session_tracker.get(user_id),
            "greeting_shown":     False,     # Track if greeting card has been shown in this session   
            "last_bot_response_time": None,  # Track when bot last responded
        }
        user_states[user_id] = state          
        first_time_users.add(user_id)
    else:
        # If the previous session was ended, rebuild essentials
        if "session_id" not in state:
            state["session_id"] = session_tracker.get(user_id)
            # Clear any residual memory from previous session to prevent context pollution
            user_memories.pop(user_id, None)
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
            logger.info(f"Invoke request received: type={req.type}, name={req.name}, value={req.value}")
            
            # Handle any feedback action regardless of format
            action_data = req.value or {}
            
            # Multiple ways feedback might be submitted
            is_feedback = (
                req.name == 'message/submitAction' or
                action_data.get('actionName') == 'feedback' or
                'reaction' in action_data or
                'feedback' in str(action_data).lower()
            )
            
            if is_feedback:
                # Try different ways to extract feedback data
                reaction = None
                feedback_text = ""
                
                # Method 1: Standard actionValue format
                action_value = action_data.get('actionValue', {})
                if action_value:
                    reaction = action_value.get('reaction')
                    feedback_text = action_value.get('feedback', '')
                
                # Method 2: Direct in action_data
                if not reaction:
                    reaction = action_data.get('reaction')
                    feedback_text = action_data.get('feedback', '')
                
                # Method 3: Nested in any sub-object
                if not reaction:
                    for key, value in action_data.items():
                        if isinstance(value, dict):
                            if 'reaction' in value:
                                reaction = value['reaction']
                                feedback_text = value.get('feedback', '')
                                break
                
                # Default reaction if none found
                if not reaction:
                    reaction = 'like'  # Default to positive
                
                # Parse feedback text if it's JSON
                if isinstance(feedback_text, str) and feedback_text.startswith('{'):
                    try:
                        import json
                        feedback_data = json.loads(feedback_text)
                        feedback_text = feedback_data.get('feedbackText', '')
                    except:
                        pass
                
                # Record the feedback
                rating = 5 if str(reaction).lower() in ['like', 'positive', '👍'] else 2
                
                try:
                    await feedback_service.record_feedback(
                        user_id=user_id,
                        rating=rating,
                        comment=str(feedback_text),
                        session_id=conv_id,
                    )
                    logger.info(f"Successfully recorded feedback: user={user_id}, reaction={reaction}, rating={rating}")
                    
                    # Send acknowledgment message
                    await adapter.send_message(
                        service_url, conv_id,
                        "Thank you for your feedback! 🙏"
                    )
                    
                    # Mark that feedback was given and END session immediately
                    state["feedback_shown"] = True
                    state["awaiting_feedback"] = False
                    
                    # Cancel any pending feedback tasks
                    if user_id in feedback_service.pending_feedback:
                        task = feedback_service.pending_feedback[user_id]
                        if not task.done():
                            task.cancel()
                        del feedback_service.pending_feedback[user_id]
                    
                    # End session immediately after feedback submission
                    _clear_user_session(user_id)
                    
                except Exception as e:
                    logger.error(f"Error recording feedback: {e}")
                    # Still acknowledge to user even if DB fails
                    await adapter.send_message(
                        service_url, conv_id,
                        "Thank you for your feedback! 🙏"
                    )
            else:
                logger.info(f"Non-feedback invoke: {req.name}")
            
            # Always return successful response for ANY invoke to prevent Teams errors
            return TeamsActivityResponse(text="")
                
        except Exception as e:
            logger.error(f"Error handling invoke request: {e}")
            # Even on error, return success to prevent Teams UI errors
            return TeamsActivityResponse(text="")
    
    # Legacy invoke handling (keeping for compatibility)
    elif req.name == 'message/submitAction':
        try:
            logger.info(f"Legacy invoke handling: name={req.name}, value={req.value}")
            return TeamsActivityResponse(text="")
        except Exception as e:
            logger.error(f"Error in legacy invoke handling: {e}")
            return TeamsActivityResponse(text="")
    
    if req.value:
        action = req.value.get("action")

        if action == "submit_rating":
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

            return TeamsActivityResponse(text="")

        if action == "dismiss_feedback":
            await adapter.send_message(
                service_url, conv_id,
                "No problem! Feel free to reach out anytime you need HR assistance."
            )
            
            # Remove current feedback card and end session
            feedback_cards.pop(conv_id, None)
            _clear_user_session(user_id)
            
            return TeamsActivityResponse(text="")

        if action == "submit_feedback":
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

            # Thank-you message
            if rating >= 4:
                thank_msg = f"Thank you for the {rating}-star rating! We're glad you had a great experience."
            elif rating <= 2:
                thank_msg = "Thank you for your feedback. We're sorry it wasn't better—we'll work on improving!"
            else:
                thank_msg = "Thank you! We appreciate your feedback and are always improving."

            await adapter.send_message(service_url, conv_id, thank_msg)

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
        if user_id in first_time_users and not state.get("greeting_shown", False):
            # Show welcome card for first-time users
            card = create_welcome_card(user_name=user_name)
            await adapter.send_card(service_url, conv_id, card)
            first_time_users.remove(user_id)
            state["greeting_shown"] = True  # Mark greeting as shown for this session
            
            # If there was additional content after greeting, process it
            if user_payload:
                user_message = user_payload.strip()
                # Show typing indicator for processing the question
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            else:
                # Just greeting, record it and return
                await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                return TeamsActivityResponse(text="")
        else:
            # Returning user with greeting
            if user_payload:
                # Greeting + question - process the question
                user_message = user_payload.strip()
                # Show typing indicator for processing the question
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            elif is_only_greeting:
                # Pure greeting only (hi, hiiii, heyy, etc.) - just acknowledge without helper text
                logger.info(f"Pure greeting detected for returning user {user_id}: '{user_message}' - no helper message")
                await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                return TeamsActivityResponse(text="")
            else:
                # Not a pure greeting but detected as greeting - send helper message
                await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
                await adapter.send_message(service_url, conv_id, "I am here to assist with your inquiries. How can I help you today?")
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
            background_tasks.add_task(message_service.add_message,
                                      bot_name="hrbot", env="development", channel="teams", user_id=user_id,
                                      session_id=session_id, role="bot", text=noi_response, intent="informational",
                                      reply_to_id=user_msg_id)

            await adapter.send_message(service_url, conv_id, noi_response)

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
            await adapter.send_message(service_url, conv_id, redirect_message)
            return TeamsActivityResponse(text="")
        
    if classification_service.should_schedule_delayed_feedback(analysis):
        if not feedback_service.has_received_feedback(user_id):
            delay_minutes = classification_service.get_feedback_delay_minutes(analysis)
            feedback_service.schedule_delayed_feedback(user_id, service_url, conv_id, delay_minutes=delay_minutes)
            logger.info(f"Scheduled delayed feedback for user {user_id} in {delay_minutes} minutes")

    user_msg_id = await _ensure_user_message_saved(user_message, user_id, session_id, req.reply_to_id)
    
    # Helper function for database persistence
    async def _persist_bot_msg(reply_id: int, text: str, intent: str = "CONTINUE") -> None:
        try:
            await message_service.add_message(
                bot_name   = "hrbot",
                env        = "development",
                channel    = "teams",
                user_id    = user_id,
                session_id = session_id,
                role       = "bot",
                text       = text,
                intent     = intent,
                reply_to_id= reply_id,  
            )
        except Exception as exc:
            logger.warning("DB write (bot msg) failed: %s", exc)
    
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
                    background_tasks.add_task(_persist_bot_msg, user_msg_id, formatted_response, intent)

            # Start real-time streaming from LLM
            success = await adapter.stream_message(
                service_url, conv_id,
                text_generator=llm_stream_generator(),
                informative="I'm analyzing your request..."
            )
                
            if not success:
                logger.warning("Real-time streaming failed, falling back to traditional method")
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
                    background_tasks.add_task(_persist_bot_msg, user_msg_id, answer, intent)
                    await adapter.send_message(service_url, conv_id, answer)
                
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
                background_tasks.add_task(_persist_bot_msg, user_msg_id, answer, intent)
                await adapter.send_message(service_url, conv_id, answer)
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
            background_tasks.add_task(_persist_bot_msg, user_msg_id, answer, intent)
            
            logger.info(f"Sending regular message (length: {len(answer)})")
            await adapter.send_message(service_url, conv_id, answer)
        else:
            # Fallback message
            await adapter.send_message(
                service_url, conv_id,
                "Sorry, I hit a glitch. Please try again later."
            )
            
    return TeamsActivityResponse(text="")


def _clear_user_session(user_id: str):
    """Clear per-user memory, state, and feedback tracking."""
    
    # Clear in-memory conversation data
    mem = user_memories.pop(user_id, None)
    user_states.pop(user_id, None)
    first_time_users.discard(user_id)
    
    # Clear feedback cards tracking for this user's conversations
    feedback_cards.pop(user_id, None)
    
    # Clear feedback service session data
    feedback_service.clear_user_session(user_id)
    
    # Log session cleanup
    message_count = len(mem.messages) if mem and mem.messages else 0
    logger.info(f"Cleared session for user {user_id} (had {message_count} messages in memory)")