"""
Intelligent intent detection service using LLM.

This service analyzes user messages to determine conversation intent without relying on
hardcoded keywords, providing more accurate and context-aware intent detection.
"""

import logging
from typing import Optional
from hrbot.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

class IntentDetectionService:
    """
    Smart intent detection service that understands conversation context
    and avoids premature session endings.
    
    Follows AI/ML best practices:
    - Context-aware classification
    - Semantic understanding over keyword matching
    - Conservative bias towards continuation
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the intent detection service."""
        self.llm_service = llm_service or GeminiService()
        
    async def analyze_conversation_intent(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """
        Analyze user intent in conversation context.
        
        Uses conservative approach - when in doubt, continue the conversation.
        Only returns END for clear, explicit conversation termination.
        
        Args:
            user_message: The user's current message
            conversation_context: Previous conversation context
            
        Returns:
            "CONTINUE" or "END"
        """
        try:
            prompt = self._build_smart_intent_prompt(user_message, conversation_context)
            
            result = await self.llm_service.analyze_messages([prompt])
            
            if result.is_success():
                response = result.unwrap()["response"].strip().upper()
                
                # Conservative parsing - default to CONTINUE if unclear
                if "END" in response and self._is_clear_ending(response):
                    logger.debug(f"Intent analysis: END detected for '{user_message[:30]}...'")
                    return "END"
                else:
                    logger.debug(f"Intent analysis: CONTINUE for '{user_message[:30]}...'")
                    return "CONTINUE"
            else:
                logger.warning(f"Intent analysis failed: {result.error}, defaulting to CONTINUE")
                return "CONTINUE"
                
        except Exception as e:
            logger.error(f"Error in intent analysis: {e}, defaulting to CONTINUE")
            return "CONTINUE"
    
    def _build_smart_intent_prompt(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """Build a sophisticated prompt for intent detection."""
        
        context_info = ""
        if conversation_context:
            context_info = f"""
Previous conversation context:
{conversation_context}

"""

        return f"""You are analyzing user intent in an HR chatbot conversation. The user was just asked "Is there anything else I can help you with?" and responded.

{context_info}User's response: "{user_message}"

CRITICAL RULES FOR CLASSIFICATION:

**CONTINUE if the user is:**
- Asking a new question (even single words like "noi", "benefits", "policy")
- Mentioning any HR topic, company process, or work-related matter
- Expressing concerns, problems, or seeking help (including sensitive topics)
- Saying anything that could be a topic, abbreviation, or request
- Being unclear or ambiguous
- Showing interest in getting information or assistance

**END ONLY if the user clearly and explicitly:**
- Says goodbye ("bye", "thanks, goodbye", "that's all, thanks")
- Confirms they're done ("no, nothing else", "I'm all set", "that's everything")
- Explicitly declines help ("no thanks", "nothing more", "I'm good")
- Simply says "no" or "nope" in response to "Is there anything else I can help you with?"

**NEVER END for:**
- Single words that could be topics/questions (noi, benefits, policy, etc.)
- Expressions of frustration, resignation, or personal struggles
- Anything that could be interpreted as seeking help or information
- Ambiguous responses (except for "no" or "nope" as a direct response)

**SPECIAL CASE:** When user responds with just "no" or "nope" to the question "Is there anything else I can help you with?", this should be classified as END because it's a clear, direct answer to the specific question.

**DEFAULT BEHAVIOR:** When in doubt, always choose CONTINUE. It's better to help someone who might not need it than to abandon someone who does.

Respond with only: CONTINUE or END

Your classification:"""

    def _is_clear_ending(self, response: str) -> bool:
        """
        Verify if the LLM response clearly indicates an ending.
        Apply additional conservative checks.
        """
        response = response.upper().strip()
        
        # Must contain END and additional confirmation language
        if "END" not in response:
            return False
            
        # Look for explicit reasoning that confirms it's a real ending
        ending_indicators = [
            "GOODBYE", "ALL SET", "NOTHING ELSE", "DONE", "FINISHED",
            "NO THANKS", "THAT'S ALL", "THANKS BYE", "EXPLICITLY",
            "NO", "NOPE", "DIRECT ANSWER", "CLEAR"
        ]
        
        return any(indicator in response for indicator in ending_indicators) 