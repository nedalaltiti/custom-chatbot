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
    LLM-based intent detection service for conversation management.
    
    Uses the LLM to understand context and intent rather than keyword matching,
    providing more accurate results for conversation flow control.
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the intent detection service."""
        self.llm_service = llm_service or GeminiService()
        
    async def analyze_conversation_intent(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """
        Analyze whether the user wants to continue or end the conversation.
        
        Args:
            user_message: The user's current message
            conversation_context: Previous conversation context (optional)
            
        Returns:
            "CONTINUE" if user wants to continue, "END" if they want to end the conversation
        """
        try:
            # Create a focused prompt for intent detection
            prompt = self._build_intent_detection_prompt(user_message, conversation_context)
            
            # Get LLM analysis
            result = await self.llm_service.analyze_messages([prompt])
            
            if result.is_success():
                response = result.unwrap()["response"].strip().upper()
                
                # Extract the intent (first word should be CONTINUE or END)
                intent = response.split()[0] if response else "CONTINUE"
                
                # Validate the response
                if intent in ["CONTINUE", "END"]:
                    logger.debug(f"Intent detected for '{user_message[:30]}...': {intent}")
                    return intent
                else:
                    logger.warning(f"Unexpected intent response: {response}, defaulting to CONTINUE")
                    return "CONTINUE"
            else:
                logger.warning(f"Intent detection failed, defaulting to CONTINUE")
                return "CONTINUE"
                
        except Exception as e:
            logger.error(f"Error in intent detection: {e}, defaulting to CONTINUE")
            return "CONTINUE"
    
    def _build_intent_detection_prompt(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """Build a focused prompt for conversation intent detection."""
        
        context_section = ""
        if conversation_context:
            context_section = f"""
PREVIOUS CONVERSATION CONTEXT:
{conversation_context}

"""
        
        prompt = f"""You are an expert conversation analyst. Your job is to determine if a user wants to CONTINUE or END a conversation with an HR Assistant.

{context_section}USER'S CURRENT MESSAGE: "{user_message}"

ANALYSIS RULES:
1. Look at the COMPLETE message, not just individual words
2. Consider if the user is asking a question, requesting information, or showing interest in learning more
3. Consider acknowledgments followed by questions (like "cool, what about X?") as CONTINUE
4. **CLEAR ENDING SIGNALS** - These should ALWAYS be classified as END:
   - "nothing", "no", "nope", "that's all", "that's it"
   - "nothing else", "no thanks", "I'm good", "all set"
   - Simple negative responses without follow-up questions
   - Expressions of satisfaction without new requests

EXAMPLES:
- "cool, what about time leaves?" → CONTINUE (acknowledgment + new question)
- "nothing" → END (clear negative response)
- "no" → END (simple negative)
- "nope" → END (simple negative)
- "that's all" → END (clear completion signal)
- "nothing else" → END (clear completion signal)
- "no thanks" → END (polite refusal to continue)
- "I'm good" → END (satisfied, no more needs)
- "thanks, that helps!" → CONTINUE (appreciation but no clear ending)
- "perfect, I think that's all I need" → END (clear satisfaction + closure)
- "bye, thank you!" → END (explicit goodbye)
- "got it, anything else I should know?" → CONTINUE (asking for more info)
- "great, thanks for your help" → CONTINUE (appreciation but ambiguous)

**IMPORTANT**: Single-word negative responses (nothing, no, nope) or clear completion phrases should ALWAYS be END, regardless of context.

Respond with ONLY one word: CONTINUE or END

INTENT:"""
        
        return prompt 