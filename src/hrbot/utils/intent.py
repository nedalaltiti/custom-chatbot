# hrbot/utils/intent.py
__all__ = ["classify_intent"]
from hrbot.utils.result import Success        

async def classify_intent(llm_service, message: str) -> str:
    """
    Return "END" if the user is closing the conversation,
    otherwise "CONTINUE". Uses a single-token Gemini call.
    """
    prompt = (
        "You are an intent-classifier. "
        "If the user is ending the conversation respond with **ONLY** the word END. "
        "Otherwise respond with **ONLY** the word CONTINUE.\n\n"
        f"User: {message}"
    )

    # we just reuse the existing GeminiService
    result = await llm_service.analyze_messages([prompt])

    if result.is_success():
        # get first token; defensive lower-case & strip
        return result.unwrap()["response"].strip().split()[0].upper()

    return "CONTINUE"

SUPPORT_KEYWORDS = {"issue", "problem", "ticket", "support", "complaint", "helpdesk"}

def needs_hr_ticket(message: str) -> bool:
    msg = message.lower()
    return any(word in msg for word in SUPPORT_KEYWORDS)