"""
Feedback Card Tracker Service

This service manages the tracking of feedback cards across conversations,
separating the feedback card tracking logic from the main router.
"""

import logging
from typing import Dict, Any, Optional, Callable
from qcbot.infrastructure.teams_adapter import TeamsAdapter

logger = logging.getLogger(__name__)


class FeedbackCardTracker:
    """Service for tracking feedback cards across conversations."""
    
    def __init__(self, teams_adapter: TeamsAdapter):
        self.teams_adapter = teams_adapter
        self.feedback_cards: Dict[str, str] = {}  # conv_id → AdaptiveCard activity_id
    
    def track_feedback_card(self, conv_id: str, activity_id: str) -> None:
        """
        Track a feedback card for a conversation.
        
        Args:
            conv_id: The conversation ID
            activity_id: The Teams activity ID of the feedback card
        """
        self.feedback_cards[conv_id] = activity_id
        logger.info(f"📋 Tracked feedback card: conversation {conv_id} -> activity {activity_id}")
    
    def get_feedback_card_id(self, conv_id: str) -> Optional[str]:
        """
        Get the tracked feedback card ID for a conversation.
        
        Args:
            conv_id: The conversation ID
            
        Returns:
            The activity ID of the feedback card, or None if not found
        """
        return self.feedback_cards.get(conv_id)
    
    def remove_feedback_card(self, conv_id: str) -> Optional[str]:
        """
        Remove and return the tracked feedback card ID for a conversation.
        
        Args:
            conv_id: The conversation ID
            
        Returns:
            The activity ID of the removed feedback card, or None if not found
        """
        activity_id = self.feedback_cards.pop(conv_id, None)
        if activity_id:
            logger.info(f"🗑️ Removed tracked feedback card: conversation {conv_id} -> activity {activity_id}")
        return activity_id
    
    def clear_user_feedback_cards(self, user_id: str) -> None:
        """
        Clear all feedback cards for a user.
        
        Args:
            user_id: The user ID to clear feedback cards for
        """
        # Note: This is a simplified implementation
        # In a more sophisticated system, you might track user-conversation mappings
        # For now, we'll just log that we're clearing user feedback cards
        logger.info(f"🧹 Clearing feedback cards for user {user_id}")
    
    def create_track_feedback_card_callback(self) -> Callable[[str, str], None]:
        """
        Create a callback function for tracking feedback cards.
        
        This is used when passing the tracking function to other services
        that need to track feedback cards.
        
        Returns:
            A callback function that takes (conv_id, activity_id) and tracks the card
        """
        def track_feedback_card(conv_id: str, activity_id: str) -> None:
            self.track_feedback_card(conv_id, activity_id)
        
        return track_feedback_card
    
    def get_tracking_stats(self) -> Dict[str, Any]:
        """
        Get statistics about tracked feedback cards.
        
        Returns:
            Dictionary with tracking statistics
        """
        return {
            "total_tracked_cards": len(self.feedback_cards),
            "tracked_conversations": list(self.feedback_cards.keys()),
            "tracked_activities": list(self.feedback_cards.values())
        }
    
    def is_feedback_card_tracked(self, conv_id: str) -> bool:
        """
        Check if a feedback card is tracked for a conversation.
        
        Args:
            conv_id: The conversation ID
            
        Returns:
            True if a feedback card is tracked for this conversation
        """
        return conv_id in self.feedback_cards
