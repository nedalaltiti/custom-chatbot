"""
Intent classification utilities for uwbot.
"""

from typing import Optional
from uwbot.utils.result import Result

__all__ = ["classify_intent"]

async def classify_intent(llm_service, message: str) -> str:
    """
    Classify the intent of a user message.
    
    Args:
        llm_service: LLM service instance
        message: User message to classify
        
    Returns:
        Intent classification string
    """
    try:
        # Simple keyword-based classification for uwbot
        message_lower = message.lower()
        
        # Check for conversation ending keywords
        ending_keywords = [
            "goodbye", "bye", "see you", "thanks", "thank you", 
            "that's all", "that is all", "done", "finished", "end",
            "stop", "quit", "exit", "no more", "no further",
            "that's it", "that is it", "all done", "complete"
        ]
        
        for keyword in ending_keywords:
            if keyword in message_lower:
                return "END"
        
        # Default to continue conversation
        return "CONTINUE"
        
    except Exception as e:
        # Default to continue on error
        return "CONTINUE"
