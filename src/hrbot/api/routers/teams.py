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
from hrbot.utils.streaming import sentence_chunks
from uuid import uuid4
from hrbot.services.session_tracker import session_tracker 

import logging, json, re
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
    
    state = user_states.get(user_id)
    if state is None:                        # first ever message from this user
        state = {
            "awaiting_confirmation": False,
            "feedback_shown":       False,
            "use_streaming":        True,
            "session_id":           session_tracker.get(user_id),   
        }
        user_states[user_id] = state          
        first_time_users.add(user_id)
    session_id = state["session_id"]
    try:
        profile   = await adapter.get_user_profile(aad_object_id)
        job_title = profile.get("jobTitle", "Unknown")
    except Exception:
        job_title = "Unknown"

    # 1) Build a system_override prompt fragment containing that title
    from hrbot.core.rag.prompt import BASE_SYSTEM
    system_override = BASE_SYSTEM + f"\n• Current user job title → {job_title}"

    
        # ─── Adaptive Card actions ─────────────────────────────────────────────────
    if req.value:
        await adapter.send_typing(service_url, conv_id)
        action = req.value.get("action")

        # ── 1) User clicked a star (submit_rating) ─────────────────────────────
        if action == "submit_rating":
            raw    = req.value.get("rating")
            rating = int(raw) if str(raw).isdigit() else None

            if rating:
                # Highlight stars, keep the “Provide Feedback” button
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

            return TeamsActivityResponse(text="")

        # ── 2) User dismissed the feedback prompt ────────────────────────────────
        if action == "dismiss_feedback":
            await adapter.send_message(
                service_url, conv_id,
                "No problem! Feel free to provide feedback another time."
            )
            # Mark shown and drop the card so it can’t be re-shown
            state["feedback_shown"] = True
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
                thank_msg = f"Thank you for the {rating}-star rating! We’re glad you had a great experience."
            elif rating <= 2:
                thank_msg = "Thank you for your feedback. We’re sorry it wasn’t better—we’ll work on improving!"
            else:
                thank_msg = "Thank you! We appreciate your feedback and are always improving."

            await adapter.send_message(service_url, conv_id, thank_msg)

            # Replace the card with a non-interactive “submitted” card
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
            session_tracker.end_session(user_id)
            state.pop("session_id", None)

            return TeamsActivityResponse(text="")

        return TeamsActivityResponse(text="")


    # ─── 1) Record user turn ─────────────────────────────────────────────────────
    memory = await get_or_create_memory(user_id)
    memory.add_user_message(user_message)

    session_id = state["session_id"]

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
    # ─── 2) “END” intent → ask for confirmation ─────────────────────────────────
    intent = await classify_intent(chat_processor.llm_service, user_message)
    if intent == "END" and not state["awaiting_confirmation"]:
        state["awaiting_confirmation"] = True
        await adapter.send_typing(service_url, conv_id)
        await adapter.send_message(
            service_url, conv_id,
            "Sure—are you done for today, or can I help with anything else?"
        )
        return TeamsActivityResponse(text="")

    # ─── 3) Confirmation response ───────────────────────────────────────────────
    if state["awaiting_confirmation"]:
        done = user_message.lower().strip() in {"yes","yep","no","that’s all","i’m done"}
        if done:
            await adapter.send_typing(service_url, conv_id)
            await adapter.send_message(service_url, conv_id, "Alright! Have a great day!")

            # Immediately send the feedback card and remember its activity_id
            act_id = await feedback_service.send_feedback_prompt(service_url, conv_id)
            if act_id:
                feedback_cards[conv_id] = act_id
            state["feedback_shown"] = True

            _clear_user_session(user_id)
            return TeamsActivityResponse(text="")
        state["awaiting_confirmation"] = False
    
    # ─── 4) First-time welcome card ──────────────────────────────────────────────
    try:
        profile = await adapter.get_user_profile(aad_object_id)
        job_title = profile.get("jobTitle", "")
    except Exception:
        job_title = ""

    if user_id in first_time_users:
        await adapter.send_typing(service_url, conv_id)
        card = create_welcome_card(user_name=user_name, job_title=job_title)
        await adapter.send_card(service_url, conv_id, card)
        first_time_users.remove(user_id)
        return TeamsActivityResponse(text="")

    # ─── 5) Show spinner while LLM runs ─────────────────────────────────────────  
    await adapter.send_typing(service_url, conv_id)
    logger.info(f"[Teams] Generating response for %s", user_id)

    result = await chat_processor.process_message(
        user_message,
        chat_history=[m["content"] for m in memory.messages[:-1]],
        user_id=user_id,
        system_override=system_override
    )
    
    if result.is_success():
        answer = result.unwrap()["response"].strip()
        answer = re.sub(
            r"\s*Is there anything else I can help you with\?\s*$",
            "", answer, flags=re.I
        )

        memory.add_ai_message(answer)

        async def _persist_bot_msg(reply_id: int, text: str, intnt: str) -> None:
            try:
                await message_service.add_message(
                    bot_name   = "hrbot",
                    env        = "development",
                    channel    = "teams",
                    user_id    = user_id,
                    session_id = session_id,
                    role       = "bot",
                    text       = text,
                    intent     = intnt,
                    reply_to_id= reply_id,  
                )
            except Exception as exc:
                logger.warning("DB write (bot msg) failed: %s", exc)
        
        background_tasks.add_task(_persist_bot_msg, user_msg_id, answer, intent)

        end = next(
            (i + 1 for i, ch in enumerate(answer[:150]) if ch in ".?!" and i > 40),
            None,
        ) or min(len(answer), 120)

        informative, rest = answer[:end].lstrip(), answer[end:]


        if state["use_streaming"]:
            await adapter.stream_message(
            service_url,
            conv_id,
            text_generator=sentence_chunks(rest),
            informative=informative,
        )
        else:
            await adapter.send_message(service_url, conv_id, answer)
        # append ticket link if needed
        if needs_hr_ticket(user_message) and settings.hr_support.url not in answer:
            await adapter.send_typing(service_url, conv_id)
            await adapter.send_message(
                service_url, conv_id,
                f"\n\n---\nYou can create an HR ticket here ➜ {settings.hr_support.url}"
            )
        return TeamsActivityResponse(text="")

    # ─── 6) On failure ─────────────────────────────────────────────────────────
    await adapter.send_typing(service_url, conv_id)
    await adapter.send_message(
        service_url, conv_id,
        "Sorry, I hit a glitch. Please try again later."
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