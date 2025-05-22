# hrbot/utils/intent.py

__all__ = ["classify_intent", "needs_hr_ticket"]

from hrbot.utils.result import Success

# If the user’s entire message is one of these “closing” words/phrases,
# immediately end the session without calling Gemini.
_CLOSE_KEYWORDS = {
    "bye", "goodbye", "thanks", "thank you", "no", "nope", "nothing",
    "that's all", "that is all", "stop", "quit", "exit"
}

async def classify_intent(llm_service, message: str) -> str:
    """
    Return "END" if the user is clearly closing the conversation,
    otherwise "CONTINUE".  First does a simple keyword check,
    then (if needed) falls back to a one‐token Gemini call.
    """
    msg = message.strip().lower()
    if msg in _CLOSE_KEYWORDS:
        return "END"

    prompt = (
        "You are an intent‐classifier.  "
        "If the user is ending the conversation respond with **ONLY** the word END.  "
        "Otherwise respond with **ONLY** the word CONTINUE.\n\n"
        f"User: {message}"
    )
    result = await llm_service.analyze_messages([prompt])
    if result.is_success():
        # first token only, defensively uppercase
        return result.unwrap()["response"].strip().split()[0].upper()
    return "CONTINUE"


_SUPPORT_KEYWORDS = {"issue", "problem", "ticket", "support", "complaint", "helpdesk"}

def needs_hr_ticket(message: str) -> bool:
    msg = message.lower()
    return any(word in msg for word in _SUPPORT_KEYWORDS)
