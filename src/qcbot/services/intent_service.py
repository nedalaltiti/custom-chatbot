"""
Intent Detection Service for QC Bot.

This service determines if a user is ending the conversation or continuing it.
Simplified version without QC-specific logic.
"""

import logging
from typing import Optional
from qcbot.services.gemini_service import GeminiService
from qcbot.utils.result import Result

logger = logging.getLogger(__name__)

class IntentDetectionService:
    """Service for detecting conversation intent (continue vs end)."""
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        self.llm_service = llm_service or GeminiService()
    
    async def analyze_conversation_intent(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """
        Analyze if the user wants to continue or end the conversation.
        
        Args:
            user_message: The user's message
            conversation_context: Optional conversation history
            
        Returns:
            "continue" or "end"
        """
        try:
            # Simple keyword-based approach for QC bot
            message_lower = user_message.lower().strip()
            
            # Keywords that indicate ending the conversation
            end_keywords = [
                "goodbye", "bye", "thanks", "thank you", "that's all", 
                "that is all", "no more", "nothing else", "that's it",
                "that is it", "done", "finished", "end", "stop"
            ]
            
            # Keywords that indicate continuing
            continue_keywords = [
                "yes", "sure", "okay", "ok", "yeah", "yep", "absolutely",
                "definitely", "more", "another", "else", "what else",
                "anything else", "other", "different", "also", "and"
            ]
            
            # Check for ending keywords
            if any(keyword in message_lower for keyword in end_keywords):
                return "end"
            
            # Check for continuing keywords
            if any(keyword in message_lower for keyword in continue_keywords):
                return "continue"
            
            # Default to continue for most responses
            return "continue"
            
        except Exception as e:
            logger.error(f"Error analyzing conversation intent: {e}")
            return "continue"  # Default to continue on error
    
    def get_response_message(self, analysis) -> Optional[str]:
        """Get appropriate response message based on analysis."""
        # For QC bot, we don't need special response messages
        return None
    
    def get_message_intent(self, analysis) -> str:
        """Get message intent from analysis."""
        # For QC bot, use the analysis result directly
        return getattr(analysis, 'flow_type', 'continue')
    
    def should_send_feedback(self, analysis) -> bool:
        """Determine if feedback should be sent based on analysis."""
        # For QC bot, send feedback when conversation ends
        return getattr(analysis, 'flow_type', 'continue') == 'end' 