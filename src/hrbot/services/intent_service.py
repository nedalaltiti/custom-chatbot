"""
Intelligent intent detection service using LLM.

This service analyzes user messages to determine conversation intent without relying on
hardcoded keywords, providing more accurate and context-aware intent detection.
"""

import logging
from typing import Optional
from hrbot.services.gemini_service import GeminiService
import asyncio

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
        Analyze user intent in conversation context with fallback logic.
        
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
            
            # Add timeout to prevent hanging on network issues
            try:
                result = await asyncio.wait_for(
                    self.llm_service.analyze_messages([prompt]),
                    timeout=3.0  # Short timeout for intent detection
                )
                
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
                    logger.warning(f"Intent analysis failed: {result.error}, using keyword fallback")
                    return self._get_keyword_based_intent(user_message)
                    
            except asyncio.TimeoutError:
                logger.warning(f"Intent analysis timed out, using keyword fallback")
                return self._get_keyword_based_intent(user_message)
                
        except Exception as e:
            logger.error(f"Error in intent analysis: {e}, using keyword fallback")
            return self._get_keyword_based_intent(user_message)
    
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

**NEVER END for:**
- Single words that could be topics/questions (noi, benefits, policy, etc.)
- Expressions of frustration, resignation, or personal struggles
- Anything that could be interpreted as seeking help or information
- Ambiguous responses

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
            "NO THANKS", "THAT'S ALL", "THANKS BYE", "EXPLICITLY"
        ]
        
        return any(indicator in response for indicator in ending_indicators)

    def _get_keyword_based_intent(self, user_message: str) -> str:
        """
        Fallback keyword-based intent detection when LLM is unavailable.
        
        Uses conservative approach - only returns END for very clear signals.
        """
        message_lower = user_message.lower().strip()
        
        # Very explicit ending phrases
        clear_endings = [
            "bye", "goodbye", "thanks bye", "thank you bye", 
            "that's all", "that is all", "nothing else", 
            "i'm done", "i am done", "all set", "i'm good", "im good",
            "no thanks", "no thank you", "thanks goodbye"
        ]
        
        # Check for exact matches or very clear patterns
        if message_lower in clear_endings:
            logger.debug(f"Keyword-based END detected for exact match: '{user_message}'")
            return "END"
        
        # Check for phrases that contain clear ending signals
        for ending in clear_endings:
            if ending in message_lower and len(message_lower) < 20:  # Short messages only
                logger.debug(f"Keyword-based END detected for phrase: '{user_message}'")
                return "END"
        
        # Default to CONTINUE for safety
        logger.debug(f"Keyword-based CONTINUE (default) for: '{user_message[:30]}...'")
        return "CONTINUE" 