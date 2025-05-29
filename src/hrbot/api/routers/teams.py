# hrbot/api/routers/teams.py

from fastapi import APIRouter, BackgroundTasks
from hrbot.services.feedback_service import FeedbackService
from hrbot.services.message_service import MessageService
from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from hrbot.services.processor import ChatProcessor
from hrbot.utils.intent import classify_intent, needs_hr_ticket
from hrbot.infrastructure.cards import create_welcome_card, create_feedback_card
from hrbot.config.settings import settings
from hrbot.utils.streaming import adaptive_chunks, sentence_chunks
from uuid import uuid4
from hrbot.services.session_tracker import session_tracker 
from hrbot.utils.message import split_greeting

import logging, json, re, asyncio
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

router           = APIRouter()
adapter          = TeamsAdapter()
feedback_service = FeedbackService()
chat_processor   = ChatProcessor()
message_service  = MessageService()

# in-memory state
first_time_users = set()    # user_ids pending their first greeting
user_states      = {}       # user_id → {awaiting_confirmation, feedback_shown, use_streaming}
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
        first_time_users.add(user_id)
    return user_memories[user_id]


@router.post("/", response_model=TeamsActivityResponse)
async def teams_messages(req: TeamsMessageRequest, background_tasks: BackgroundTasks):
    user_message = req.text or ""
    user_id      = req.from_.id
    user_name    = req.from_.name
    aad_object_id = req.from_.aad_object_id
    service_url  = req.service_url
    conv_id      = req.conversation.id
    
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
                    
                    # Mark that feedback was given but DON'T end session
                    state["feedback_shown"] = True
                    state["awaiting_feedback"] = False
                    # Add timeout before next feedback can be shown (10 minutes)
                    state["last_feedback_time"] = datetime.utcnow().timestamp()
                    
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
        }
        user_states[user_id] = state          
        first_time_users.add(user_id)
    session_id = state["session_id"]
    
    # Get job title for system override
    try:
        profile   = await adapter.get_user_profile(aad_object_id)
        job_title = profile.get("jobTitle", "Unknown")
    except Exception:
        job_title = "Unknown"

    # Add job title to system context
    system_override = f"Current user job title: {job_title}"

    
    # ─── Handle card actions (feedback submissions, etc.) ───────────────────────
    if req.value:
        await adapter.send_typing(service_url, conv_id)
        action = req.value.get("action")

        # ── 1) User clicked a star (submit_rating) ─────────────────────────────
        if action == "submit_rating":
            raw    = req.value.get("rating")
            rating = int(raw) if str(raw).isdigit() else None

            if rating:
                # Highlight stars, keep the "Provide Feedback" button
                card = create_feedback_card(
                    selected_rating=rating,
                    interactive=True
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

        # ── 2) User dismissed the feedback prompt ────────────────────────────────
        if action == "dismiss_feedback":
            await adapter.send_message(
                service_url, conv_id,
                "No problem! Feel free to provide feedback another time."
            )
            # Mark shown and drop the card so it can't be re-shown
            state["feedback_shown"] = True
            state["awaiting_feedback"] = False 
            feedback_cards.pop(conv_id, None)
            session_tracker.end_session(user_id)
            state.pop("session_id", None)
            return TeamsActivityResponse(text="")

        # ── 3) User submitted feedback (submit_feedback) ─────────────────────────
        if action == "submit_feedback":
            raw     = req.value.get("rating")
            rating  = int(raw) if str(raw).isdigit() else 3
            comment = (req.value.get("comment") or "").strip()
            

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
            session_tracker.end_session(user_id)
            state.pop("session_id", None)

            return TeamsActivityResponse(text="")

        return TeamsActivityResponse(text="")

    # ─── Quick intent check for explicit goodbye messages (BEFORE everything else) ──────
    msg_lower = user_message.lower().strip()
    if msg_lower in ["bye", "goodbye", "exit", "quit", "stop"]:
        # Typing already sent above
        await adapter.send_message(
            service_url, conv_id,
            "Goodbye! Thank you for using our HR Assistant."
        )
        
        # Send feedback card
        act_id = await feedback_service.send_feedback_prompt(service_url, conv_id)
        if act_id:
            feedback_cards[conv_id] = act_id
            state["awaiting_feedback"] = True
            state["feedback_shown"] = True

        _clear_user_session(user_id)
        return TeamsActivityResponse(text="")

    # ─── Check if user is responding to "anything else?" question (BEFORE greeting detection) ──────
    if state.get("awaiting_more_help"):
        logger.info(f"User is responding to 'anything else?' question with: '{user_message}'")
        msg_lower = user_message.lower().strip()
        
        # Check for affirmative responses
        if any(word in msg_lower for word in ["yes", "yeah", "yep", "sure", "ok", "okay", "please", "yup"]):
            # User wants more help - reset the state and continue normally
            state["awaiting_more_help"] = False
            # Typing already sent above
            await adapter.send_message(
                service_url, conv_id,
                "Of course! What would you like to know?"
            )
            return TeamsActivityResponse(text="")
        
        # Check for negative responses  
        elif any(word in msg_lower for word in ["no", "nope", "nothing", "that's all", "that is all", "done", "finished", "bye", "goodbye", "thanks", "thank you", "cool", "awesome", "great", "perfect", "good", "got it", "understood", "alright", "all right"]):
            # User is done - send feedback
            logger.info(f"User declined more help with: '{user_message}' - ending conversation")
            state["awaiting_more_help"] = False
            # Typing already sent above
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
            # Assume they're asking a new question - reset state and process normally
            logger.info(f"User asked new question while awaiting more help: '{user_message}'")
            state["awaiting_more_help"] = False
            # Continue processing the message normally below

    # ─── Handle greeting detection (after "anything else" check) ──────────
    greet_only, user_payload = split_greeting(user_message)

    # Show greeting card for first-time users if ANY greeting is detected
    if (greet_only or user_payload) and not state.get("awaiting_more_help"):
        if user_id in first_time_users:
            # Show welcome card for first-time users
            card = create_welcome_card(user_name=user_name)
            await adapter.send_card(service_url, conv_id, card)
            first_time_users.remove(user_id)
            
            # If there was additional content after greeting, process it
            if user_payload:
                user_message = user_payload.strip()
                # Show typing indicator for processing the question
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            else:
                # Just greeting, return
                return TeamsActivityResponse(text="")
        else:
            # Returning user with greeting - just process any additional content
            if user_payload:
                user_message = user_payload.strip()
                # Show typing indicator for processing the question
                await adapter.send_typing(service_url, conv_id)
                # Continue processing the question below...
            else:
                # Just greeting from returning user - do nothing, just return
                return TeamsActivityResponse(text="")
    elif user_payload and not greet_only:
        # If greeting had additional content but not first time, use that as the actual message
        user_message = user_payload.strip()

    # ─── Record user turn in memory ────────────────────────────────────────────
    memory = await get_or_create_memory(user_id)
    memory.add_user_message(user_message)

    # Store message in database
    user_msg_id = await message_service.add_message(
        bot_name   = "hrbot",
        env        = "development",
        channel    = "teams",
        user_id    = user_id,
        session_id = session_id,
        role       = "user",
        text       = user_message,
        reply_to_id= req.reply_to_id,
    )
    
    # ─── Generate response using LLM ─────────────────────────────────────────  
    logger.info(f"[Teams] Generating response for %s", user_id)

    # Helper function for database persistence
    async def _persist_bot_msg(reply_id: int, text: str) -> None:
        try:
            await message_service.add_message(
                bot_name   = "hrbot",
                env        = "development",
                channel    = "teams",
                user_id    = user_id,
                session_id = session_id,
                role       = "bot",
                text       = text,
                intent     = "CONTINUE",
                reply_to_id= reply_id,  
            )
        except Exception as exc:
            logger.warning("DB write (bot msg) failed: %s", exc)

    # Enhanced streaming logic following Microsoft Teams requirements
    if state.get("use_streaming", True) and len(user_message.split()) > 1:
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
                    
                    # Check if response contains "anything else?" 
                    if _HAS_ANYTHING_ELSE_RE.search(formatted_response):
                        state["awaiting_more_help"] = True
                    
                    # Store in database
                    background_tasks.add_task(_persist_bot_msg, user_msg_id, formatted_response)

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
                    background_tasks.add_task(_persist_bot_msg, user_msg_id, answer)
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
                background_tasks.add_task(_persist_bot_msg, user_msg_id, answer)
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
            background_tasks.add_task(_persist_bot_msg, user_msg_id, answer)
            
            logger.info(f"Sending regular message (length: {len(answer)})")
            await adapter.send_message(service_url, conv_id, answer)
        else:
            # Fallback message
            await adapter.send_message(
                service_url, conv_id,
                "Sorry, I hit a glitch. Please try again later."
            )

    # Append ticket link if needed (for both streaming and non-streaming)
    if needs_hr_ticket(user_message):
        await adapter.send_typing(service_url, conv_id)
        await adapter.send_message(
            service_url, conv_id,
            f"\n\n---\nYou can create an HR ticket here ➜ {settings.hr_support.url}"
        )
    return TeamsActivityResponse(text="")


def _clear_user_session(user_id: str):
    """Archive conversation then clear per-user memory & state."""
    mem = user_memories.pop(user_id, None)
    user_states.pop(user_id, None)
    first_time_users.discard(user_id)

    if not mem or not mem.messages:
        return

    Path("data/conversations").mkdir(parents=True, exist_ok=True)
    ts   = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = Path(f"data/conversations/{user_id}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mem.messages, f, indent=2)
    logger.debug(f"Archived conversation for {user_id} → {path}")