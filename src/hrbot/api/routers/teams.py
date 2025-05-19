from fastapi import APIRouter, BackgroundTasks, Depends
from hrbot.services.feedback_service import FeedbackService
from hrbot.infrastructure.teams_adapter import TeamsAdapter, stream_message
from hrbot.schemas.models import TeamsMessageRequest, TeamsActivityResponse
from hrbot.services.gemini_service import GeminiService
from hrbot.services.processor import ChatProcessor
from hrbot.utils.result import Success, Error
from hrbot.infrastructure.cards import create_welcome_card, create_feedback_card
import logging
import re
import asyncio
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()
adapter = TeamsAdapter()
feedback_service = FeedbackService()
llm_service = GeminiService()
chat_processor = ChatProcessor(llm_service)

# Track first-time users to send welcome card
first_time_users = set()

# Track conversation state
user_states = {}  # user_id: {"awaiting_confirmation": bool, "feedback_shown": bool, "use_streaming": bool}

# In production, use Redis or DB for memory
user_memories = {}

feedback_cards = {}  # (conv_id) -> activity_id
reaction_cards = {}

class ConversationBufferMemory:
    """ConversationBufferMemory."""

    def __init__(self):
        # Store messages internally
        self._messages = []  # list[dict]
        # For backward-compat with previous code that accessed `memory.chat_memory.*`
        self.chat_memory = self  # alias so existing code works

    def add_user_message(self, text: str):
        self._messages.append({"role": "user", "content": text})

    def add_ai_message(self, text: str):
        self._messages.append({"role": "ai", "content": text})

    @property
    def buffer_as_str(self) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in self._messages)

    # Provide messages property to mimic LangChain's internal API
    @property
    def messages(self):
        return self._messages

async def get_or_create_memory(user_id: str):
    """Get or create a conversation memory for a user."""
    if user_id not in user_memories:
        user_memories[user_id] = ConversationBufferMemory()
        # Mark as first-time user
        first_time_users.add(user_id)
        # Initialize user state
        user_states[user_id] = {
            "awaiting_confirmation": False,
            "feedback_shown": False,
            "use_streaming": True  # Enable streaming by default
        }
    return user_memories[user_id]

# Helper function to create a stream generator from a string
async def string_to_stream(text):
    """Convert a string to a streaming generator for word-by-word output."""
    words = text.split()
    for i, word in enumerate(words):
        yield word
        if i < len(words) - 1:  # If not the last word
            yield " "  # Add space between words
        await asyncio.sleep(0.05)  # Slight delay between words

# New function to simulate typing with separate messages
async def simulate_typing(adapter, service_url, conversation_id, text, delay=0.3, is_first_response=False):
    """
    Simulate typing by sending chunks of the message with delays.
    
    Args:
        adapter: The TeamsAdapter instance
        service_url: The Teams service URL
        conversation_id: The conversation ID
        text: The full text to send
        delay: Delay between chunks in seconds
        is_first_response: Whether this is the first response to a user in the conversation
    """
    # Send typing indicator once - more visibly for first responses
    await adapter.send_typing(service_url, conversation_id)
    
    # For first responses, we want to be faster but still show the typing indicator
    if is_first_response:
        await asyncio.sleep(0.2)  # Brief delay to ensure typing indicator appears
        return await adapter.send_message(service_url, conversation_id, text)
    
    # For short messages (under 50 chars), just send with a brief delay
    if len(text) < 50:
        await asyncio.sleep(0.3)  # Brief fixed delay for short messages
        return await adapter.send_message(service_url, conversation_id, text)
    
    # For longer messages, add a slightly longer delay but don't chunk
    # This simulates someone typing quickly but gives a sense of processing time
    await asyncio.sleep(min(len(text) * 0.005, 1.5))  # Max 1.5 sec delay for very long messages
    
    # Send the complete message
    return await adapter.send_message(service_url, conversation_id, text)

@router.post("/", response_model=TeamsActivityResponse)
async def teams_messages(
    req: TeamsMessageRequest,
    background_tasks: BackgroundTasks
):
    """Process incoming Teams messages using LLM with contextual memory."""
    try:
        # Extract request data
        user_message = req.text or ""
        user_id = req.from_.id
        user_name = req.from_.name  # Extract user name for personalization
        service_url = req.serviceUrl
        conversation_id = req.conversation.get("id")
        
        # If there's no user message (e.g., invoke activities from cards), handle card action or skip
        if not user_message.strip():
            # Possibly an Adaptive Card action (invoke activity)
            if req.value:
                action_type = req.value.get("action")

                # ---------------------------------------------------
                # Card action: user clicked "Later" / star / submit.
                # ---------------------------------------------------
                if action_type in {"submit_rating", "dismiss_feedback", "submit_feedback"}:
                    # Normalise rating (may be string)
                    rating_raw = req.value.get("rating")
                    rating = None
                    if isinstance(rating_raw, int):
                        rating = rating_raw
                    elif isinstance(rating_raw, str) and rating_raw.isdigit():
                        rating = int(rating_raw)

                    # Handle each action separately
                    if action_type == "submit_rating" and rating:
                        # Update card so stars stay highlighted
                        updated_card = create_feedback_card(selected_rating=rating)
                        act_id = feedback_cards.get(conversation_id)
                        if act_id:
                            await adapter.update_card(service_url, conversation_id, act_id, updated_card)
                        else:
                            act_id = await adapter.send_card(service_url, conversation_id, updated_card)
                            if act_id:
                                feedback_cards[conversation_id] = act_id
                        # No extra message; user will press Provide Feedback.
                        return TeamsActivityResponse(text="")

                    if action_type == "dismiss_feedback":
                        await adapter.send_message(service_url, conversation_id,
                                                    "No problem! Feel free to provide feedback another time.")
                        return TeamsActivityResponse(text="")

                    if action_type == "submit_feedback":
                        # Default neutral rating if not provided
                        if not rating:
                            rating = 3
                        comment = req.value.get("comment", "")

                        # Persist feedback
                        feedback_service.record_feedback(user_id, rating, comment)

                        # Thank-you message based on rating
                        if rating >= 4:
                            msg = f"Thank you for providing a {rating}-star rating! We're glad you had a good experience."
                        elif rating <= 2:
                            msg = f"Thank you for your {rating}-star feedback. We're sorry your experience wasn't better, and we'll work to improve."
                        else:
                            msg = f"Thank you for your {rating}-star feedback. We're always working to improve our services."

                        await adapter.send_message(service_url, conversation_id, msg)

                        # Try to update the card to show a submitted state (replace with simple TextBlock)
                        try:
                            submitted_card = {
                                "type": "AdaptiveCard",
                                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                "version": "1.3",
                                "body": [{
                                    "type": "TextBlock",
                                    "text": "✅ Feedback submitted – thank you!",
                                    "weight": "Bolder",
                                    "size": "Medium"
                                }]
                            }
                            act_id = feedback_cards.get(conversation_id)
                            if act_id:
                                await adapter.update_card(service_url, conversation_id, act_id, submitted_card)
                            else:
                                act_id = await adapter.send_card(service_url, conversation_id, submitted_card)
                                if act_id:
                                    feedback_cards[conversation_id] = act_id
                        except Exception as e:
                            logger.debug(f"Unable to send submitted card: {e}")

                        return TeamsActivityResponse(text="")

                if action_type and action_type.startswith("react_"):
                    # Reaction bar handling
                    react = action_type.split("_", 1)[1]
                    if react == "copy":
                        # Echo the stored text so user can copy easily
                        text = reaction_cards.get(req.replyToId, "") if hasattr(req, 'replyToId') else ""
                        if text:
                            await adapter.send_message(service_url, conversation_id, f"```{text}```")
                    elif react in {"like", "dislike"}:
                        logger.info(f"User {user_id} reacted {react} to bot message")
                        # In production store this reaction.
                    return TeamsActivityResponse(text="")

            # No card action payload → nothing to do
            logger.debug("No text and no card action payload – ignoring.")
            return TeamsActivityResponse(text="")

        # Log incoming message with more details
        logger.info(f"Received message from user {user_id}: '{user_message[:30]}...' (if longer)")
        logger.debug(f"Service URL: {service_url}, Conversation ID: {conversation_id}")

        # Send typing indicator immediately
        if service_url and conversation_id:
            await adapter.send_typing(service_url, conversation_id)
            logger.debug(f"Typing indicator sent immediately")

        # Get or create memory for user
        memory = await get_or_create_memory(user_id)
        
        # Get user state
        state = user_states.get(user_id, {
            "awaiting_confirmation": False,
            "feedback_shown": False,
            "use_streaming": True
        })
        
        # Store user message in memory
        memory.add_user_message(user_message)
        
        # Check if the message is a negative response (like "no", "nothing", etc.)
        if is_negative_response(user_message):
            logger.info(f"User {user_id} indicated conversation ending")
            if not state.get("feedback_shown"):
                logger.info(f"Showing feedback card to user {user_id}")
                state["feedback_shown"] = True
                
                # Send a farewell message
                await adapter.send_message(service_url, conversation_id, "Alright! Have a great day!")
                
                # Send the feedback card immediately
                act_id = await feedback_service.send_feedback_prompt(service_url, conversation_id)
                if act_id:
                    feedback_cards[conversation_id] = act_id

                # Conversation ended – clear memory and state
                _clear_user_session(user_id)
                
                return TeamsActivityResponse(text="Alright! Have a great day!")
        
        # Check if this is a first-time user for welcome card
        is_first_time = user_id in first_time_users
        
        # Prepare chat history (excluding the current message)
        chat_history = [m["content"] for m in memory.messages[:-1]]
        
        try:
            # First, generate the complete response for the memory
            logger.info("Generating response")
            fallback_result = await chat_processor.process_message(user_message, chat_history=chat_history)
            
            if fallback_result.is_success():
                complete_answer = fallback_result.unwrap()["response"].strip()
                
                # Check if the user message is very short (1-3 words) and not a question
                is_short_response = len(user_message.split()) <= 3 and "?" not in user_message
                
                # Check if we should append a follow-up question
                should_add_followup = False
                followup_question = ""
                
                # Important: Check if the message appears to be ending the conversation
                ending_detected = is_conversation_ending(user_message, complete_answer)
                already_has_followup = has_followup_question(complete_answer)
                
                # Only add follow-up if ALL these conditions are met:
                # 1. Conversation seems to be ending (thank you, goodbye, etc.)
                # 2. Bot's response doesn't already include a follow-up question
                # 3. User isn't already in a follow-up confirmation state
                # 4. Not a short "thanks" response from model that would make double questions
                # 5. User's message isn't a short response (1-3 words)
                # 6. LLM's response doesn't already contain a closing like "have a great day"
                # 7. User's message doesn't contain words like "nothing" or "no"
                
                has_closing = re.search(r"\bhave\s+a\s+(?:good|great|nice)\s+(?:day|evening|afternoon|night|weekend)\b", complete_answer.lower()) is not None
                
                # Don't add follow-up if the user has already indicated they don't want more help
                contains_negative = any(word in user_message.lower() for word in ["nothing", "no", "nope", "that's all", "thanks", "thank you"])
                
                if (ending_detected and 
                    not already_has_followup and 
                    not "thanks" in complete_answer.lower() and
                    not is_short_response and
                    not has_closing and
                    not contains_negative):
                    should_add_followup = True
                    followup_question = " Is there anything else I can help you with?"
                    state["awaiting_confirmation"] = True
                
                # Combine the answer with follow-up if needed
                full_response = complete_answer + followup_question if should_add_followup else complete_answer
                
                # Store the complete answer (without the added follow-up) in memory
                memory.add_ai_message(complete_answer)
                logger.debug(f"Complete answer: '{complete_answer[:30]}...' (if longer)")
                
                # If first time user, send welcome card instead
                if is_first_time and service_url and conversation_id:
                    logger.info(f"Sending welcome card to first-time user {user_id}")
                    welcome_card = create_welcome_card(user_name=user_name)  # Pass user name to personalize greeting
                    success = await adapter.send_card(service_url, conversation_id, welcome_card)
                    
                    # No longer a first-time user
                    first_time_users.discard(user_id)
                    
                    # Remove feedback card activity references for safety
                    for conv, aid in list(feedback_cards.items()):
                        if conv.startswith(user_id):
                            feedback_cards.pop(conv, None)
                    
                    if not success:
                        logger.error("Failed to send welcome card, falling back to text message")
                        await adapter.send_message(service_url, conversation_id, full_response)
                else:
                    # Regular text response for returning users
                    logger.info("Sending regular text response")
                    
                    # Use progressive 2-step streaming (Teams limitation)
                    if state.get("use_streaming", True):
                        try:
                            # Look for first sentence boundary after 40 chars but before 150 chars
                            sentence_end = -1
                            for idx, ch in enumerate(full_response[:150]):
                                if ch in ".?!" and idx >= 40:
                                    sentence_end = idx + 1
                                    break
                            if sentence_end == -1:
                                sentence_end = 120 if len(full_response) > 120 else len(full_response)

                            first_chunk = full_response[:sentence_end].lstrip()
                            remaining = full_response[sentence_end:]

                            async def remainder_chars():
                                step = 40
                                for i in range(0, len(remaining), step):
                                    yield remaining[i:i+step]
                                    await asyncio.sleep(0.05)

                            await stream_message(adapter, service_url, conversation_id, remainder_chars(), informative=first_chunk)
                            logger.info("Delivered response via two-phase streaming")
                        except Exception as e:
                            logger.warning(f"Streaming delivery failed: {str(e)}, falling back to simple message")
                            await adapter.send_message(service_url, conversation_id, full_response)
                    else:
                        await adapter.send_message(service_url, conversation_id, full_response)
                
                # Check if conversation appears to be ending
                if ending_detected and not state.get("feedback_shown"):
                    state["feedback_shown"] = True
                    # Schedule the feedback prompt (not immediately, but soon)
                    background_tasks.add_task(feedback_service.schedule_feedback, user_id, service_url, conversation_id)

                    # Clear session since user indicated end
                    _clear_user_session(user_id)
                
                # Save user state
                user_states[user_id] = state
                
                # Send the main reply
                await adapter.send_message(service_url, conversation_id, full_response)

                # Add reaction bar under the reply (one per reply)
                try:
                    r_card = create_reaction_card()
                    r_id = await adapter.send_card(service_url, conversation_id, r_card)
                    if r_id:
                        reaction_cards[r_id] = full_response  # map activity→text for copy
                except Exception as e:
                    logger.debug(f"Unable to send reaction bar: {e}")
                
                # Return the response
                return TeamsActivityResponse(text=full_response)
            else:
                # Handle error case
                error_msg = str(fallback_result.error)
                logger.error(f"Error processing message: {error_msg}")
                answer = f"Sorry, there was an error processing your request. Error: {error_msg}"
                
                # Send error message
                if service_url and conversation_id:
                    await adapter.send_message(service_url, conversation_id, answer)
                
                # Return error response
                return TeamsActivityResponse(text=answer)
                
        except Exception as processing_error:
            logger.exception(f"Error during message processing: {str(processing_error)}")
            error_message = "Sorry, I encountered an error while processing your message."
            
            if service_url and conversation_id:
                await adapter.send_message(service_url, conversation_id, error_message)
                
            return TeamsActivityResponse(text=error_message)

        # This should never be reached, but just in case
        return TeamsActivityResponse(text="I processed your message.")
    except Exception as e:
        logger.exception(f"Unhandled exception in teams_messages endpoint: {str(e)}")
        return TeamsActivityResponse(text=f"Sorry, there was an unexpected error. Please try again later.")

def is_conversation_ending(message, answer=None):
    """
    Detect if the conversation appears to be ending.
    
    Args:
        message: The user's message
        answer: The bot's answer (if provided)
        
    Returns:
        bool: True if conversation appears to be ending
    """
    # Common explicit farewell phrases
    explicit_farewell_patterns = [
        r"\b(?:bye|goodbye|farewell)\b",
        r"\b(?:that'?s\s+all|that\s+is\s+all)\b",
        r"\b(?:no\s+(?:more|further)\s+questions)\b",
        r"\b(?:that'?s\s+it|got\s+it\s+thanks)\b",
        r"\b(?:have\s+a\s+(?:good|nice|great))\b",
        r"\b(?:until\s+next\s+time|see\s+you\s+later|take\s+care)\b",
        r"^(?:nothing)(?:\.|\s*)?$"  # Add explicit "nothing" as end of conversation
    ]
    
    # Thank you patterns often indicate conversation closing
    thank_you_patterns = [
        r"\b(?:thank(s|\s+you)|thx|ty)\b"
    ]
    
    # Common negative responses to "anything else" - these are strong indicators
    # that the user wants to end the conversation
    negative_responses = [
        r"^(?:no|nope|nah)(?:\.|\s*)?$",
        r"\b(?:no|not)\s+(?:thanks|thank\s+you)\b",
        r"\b(?:nothing|that'?s\s+(?:all|it))\b",
        r"\b(?:i'?m\s+(?:good|fine|done))\b"
    ]
    
    # Special short message patterns that indicate we're already 
    # responding to a follow-up question (avoid double followups)
    short_responses = [
        r"\b(?:ok(ay)?|cool|alright|perfect|great)\b"
    ]
    
    # Check for explicit farewell
    if message:
        message_lower = message.lower()
        
        # Check for "nothing" explicitly - this is a strong indicator
        if message_lower.strip() == "nothing":
            return True
        
        # Check if this is just a short response to a previous follow-up
        # In this case, don't trigger another follow-up question
        if len(message_lower.split()) <= 3:  # 3 words or fewer
            for pattern in short_responses:
                if re.search(pattern, message_lower):
                    return False  # Don't treat short acknowledging responses as conversation endings
        
        # Check for explicit farewells
        for pattern in explicit_farewell_patterns:
            if re.search(pattern, message_lower):
                return True
                
        # Check for thank you with no follow-up question
        for pattern in thank_you_patterns:
            if re.search(pattern, message_lower) and len(message_lower.split()) <= 4:
                # Short thank you messages without additional questions
                return True
                
        # Check for negative responses (no, nope, etc.)
        for pattern in negative_responses:
            if re.search(pattern, message_lower):
                return True
                
    # If the bot's response contains indicators that it thinks the conversation is ending
    if answer:
        answer_lower = answer.lower()
        bot_farewell_markers = [
            r"\bhave\s+a\s+(?:good|great|nice)\s+(?:day|evening|afternoon|night|weekend)\b",
            r"\bfeel\s+free\s+to\s+(?:reach|come)\s+(?:out|back)\b",
            r"\bgoodbye\b",
            r"\btake\s+care\b",
            r"\balright\s*!?\s*have\s+a\b"
        ]
        
        for pattern in bot_farewell_markers:
            if re.search(pattern, answer_lower):
                return True
    
    return False

def has_followup_question(answer):
    """
    Check if the bot's answer already includes a follow-up question.
    
    Args:
        answer: The bot's response text
        
    Returns:
        bool: True if the answer already contains a follow-up question
    """
    if not answer:
        return False
        
    # Common follow-up question patterns
    followup_patterns = [
        r"\b(?:anything\s+else\s+(?:I|we)\s+can\s+(?:help|assist)\s+(?:you\s+)?with)\b",
        r"\b(?:(?:is\s+there|do\s+you\s+have)\s+(?:any|anything)\s+else)\b",
        r"\b(?:can\s+(?:I|we)\s+(?:help|assist)\s+(?:you\s+)?with\s+anything\s+else)\b",
        r"\b(?:(?:what|anything)\s+else\s+(?:can|may)\s+(?:I|we)\s+(?:help|assist)\s+(?:you\s+)?with)\b",
        r"\b(?:(?:do|would)\s+you\s+need\s+(?:help|assistance)\s+with\s+anything\s+else)\b",
        r"\b(?:(?:is|are)\s+there\s+(?:any|other)\s+(?:questions|concerns))\b",
        r"\b(?:let\s+me\s+know\s+if\s+there's\s+anything\s+else)\b"
    ]
    
    answer_lower = answer.lower()
    for pattern in followup_patterns:
        if re.search(pattern, answer_lower):
            return True
            
    # Also check for question mark near the end of the message
    last_sentences = answer_lower.split('.')[-2:]  # Get the last two sentences
    for sentence in last_sentences:
        if '?' in sentence and len(sentence) < 100:  # If it's a reasonably short question
            followup_words = ['else', 'more', 'other', 'another', 'further', 'additional']
            for word in followup_words:
                if word in sentence:
                    return True
    
    return False

def is_negative_response(message):
    """
    Detect if the message is a negative response (like "no, that's all").
    
    Args:
        message: The user's message
        
    Returns:
        bool: True if the message is a negative response
    """
    if not message:
        return False
        
    message_lower = message.lower().strip()
    
    # Quick check for common one-word responses
    if message_lower in ["no", "nope", "nah", "nothing"]:
        return True
    
    # Check for common negative responses
    negative_patterns = [
        r"^(?:no|nope|nah)(?:\.|\s*)?$",
        r"\b(?:no|not)\s+(?:thanks|thank\s+you)\b",
        r"\b(?:nothing|that'?s\s+(?:all|it))\b",
        r"\b(?:i'?m\s+(?:good|fine|done))\b"
    ]
    
    for pattern in negative_patterns:
        if re.search(pattern, message_lower):
            return True
            
    return False

# -----------------------------------------------------------
# Session helpers
# -----------------------------------------------------------

def _clear_user_session(user_id: str):
    """Persist conversation to disk then clear cached memory/state."""
    mem = user_memories.get(user_id)
    if mem and mem.messages:
        try:
            Path("data/conversations").mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            file_path = Path(f"data/conversations/{user_id}_{ts}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(mem.messages, f, indent=2, ensure_ascii=False)
            logger.debug(f"Archived conversation for {user_id} to {file_path}")
        except Exception as e:
            logger.warning(f"Failed to archive conversation for {user_id}: {e}")

    user_memories.pop(user_id, None)
    user_states.pop(user_id, None)
    first_time_users.discard(user_id)