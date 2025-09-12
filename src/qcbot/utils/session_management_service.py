"""
Session Management Utility for QC Bot

This utility handles session state, user memory, and session cleanup,
separating the session management logic from the main router.
"""

import logging
from typing import Dict, Any, Optional
from qcbot.services.feedback_service import MemoryEfficientFeedbackService

logger = logging.getLogger(__name__)


class ConversationBufferMemory:
    """Simple per-user chat buffer."""
    def __init__(self):
        self.messages = []

    def add_user_message(self, text: str):
        self.messages.append({"role":"user","content":text})

    def add_ai_message(self, text: str):
        self.messages.append({"role":"ai","content":text})


class SessionManagementService:
    """Service for managing user sessions, state, and memory."""
    
    def __init__(self, feedback_service: MemoryEfficientFeedbackService):
        self.feedback_service = feedback_service
        # in-memory state
        self.first_time_users = set()    # user_ids pending their first greeting
        self.user_states = {}       # user_id → {awaiting_confirmation, feedback_shown, use_streaming, last_bot_response_time}
        self.user_memories = {}       # user_id → ConversationBufferMemory
        self.feedback_cards = {}       # conv_id → AdaptiveCard activity_id
    
    async def get_or_create_memory(self, user_id: str) -> ConversationBufferMemory:
        """Get or create memory for a user."""
        if user_id not in self.user_memories:
            self.user_memories[user_id] = ConversationBufferMemory()
        return self.user_memories[user_id]
    
    def get_user_state(self, user_id: str) -> Dict[str, Any]:
        """Get or create user state."""
        state = self.user_states.get(user_id)
        if state is None:
            # First ever message from this user
            logger.info(f"Creating new session for user {user_id} - first message ever")
            state = {
                "awaiting_more_help": False,     # Waiting for yes/no to "anything else?"
                "awaiting_feedback":  False,
                "feedback_shown":     False,
                "use_streaming":      True,
                "session_id":         None,  # Will be set by caller
                "greeting_shown":     False,     # Track if greeting card has been shown in this session   
                "last_bot_response_time": None,  # Track when bot last responded
                "session_started":    True,      # Mark this as a new session start
            }
            self.user_states[user_id] = state          
            self.first_time_users.add(user_id)
            logger.info(f"Added user {user_id} to first_time_users set")
        else:
            # If the previous session was ended, rebuild essentials for new session
            if "session_id" not in state:
                logger.info(f"Rebuilding session for returning user {user_id} - session was cleared, this is a NEW session")
                # Clear any residual memory from previous session to prevent context pollution
                self.user_memories.pop(user_id, None)
                # Reset greeting shown flag for new session - this is key!
                state["greeting_shown"] = False
                state["session_started"] = True  # Mark this as a new session start
                logger.info(f"Reset greeting_shown=False for user {user_id} - new session after previous ended")
            else:
                # Continuing existing session
                state.setdefault("session_started", False)
                
            state.setdefault("awaiting_more_help", False)
            state.setdefault("awaiting_feedback", False)
            state.setdefault("feedback_shown", False)
            state.setdefault("use_streaming", True)
            state.setdefault("greeting_shown", False)
            state.setdefault("last_bot_response_time", None)
        
        return state
    
    def update_session_id(self, user_id: str, session_id: str) -> None:
        """Update the session ID for a user."""
        if user_id in self.user_states:
            self.user_states[user_id]["session_id"] = session_id
    
    def is_first_time_user(self, user_id: str) -> bool:
        """Check if user is a first-time user."""
        return user_id in self.first_time_users
    
    def remove_first_time_user(self, user_id: str) -> None:
        """Remove user from first-time users set."""
        self.first_time_users.discard(user_id)
    
    def get_feedback_card_id(self, conv_id: str) -> Optional[str]:
        """Get feedback card activity ID for a conversation."""
        return self.feedback_cards.get(conv_id)
    
    def set_feedback_card_id(self, conv_id: str, activity_id: str) -> None:
        """Set feedback card activity ID for a conversation."""
        logger.info(f"📋 Setting feedback card ID for conversation {conv_id}: {activity_id}")
        old_activity_id = self.feedback_cards.get(conv_id)
        if old_activity_id:
            logger.warning(f"⚠️ Overwriting existing feedback card ID: {old_activity_id} -> {activity_id}")
        self.feedback_cards[conv_id] = activity_id
        logger.info(f"📋 Current feedback_cards state: {self.feedback_cards}")
    
    def remove_feedback_card(self, conv_id: str) -> None:
        """Remove feedback card tracking for a conversation."""
        self.feedback_cards.pop(conv_id, None)
    
    def clear_user_session(self, user_id: str) -> None:
        """Clear per-user memory, state, and feedback tracking.
        
        This completely resets the user's session so that their next message
        will be treated as starting a new session.
        """
        
        # Clear in-memory conversation data
        mem = self.user_memories.pop(user_id, None)
        old_state = self.user_states.pop(user_id, None)  # This is the key - removes session_id 
        self.first_time_users.discard(user_id)  # They're no longer "first time" but can get greeting cards in new sessions
        
        # Clear feedback cards tracking for this user's conversations
        # Note: This would need to be enhanced to track which conversations belong to which user
        # For now, we'll clear all feedback cards (this is a limitation of the current design)
        
        # Clear feedback service session data
        self.feedback_service.clear_user_session(user_id)
        
        # Log detailed session cleanup for debugging
        message_count = len(mem.messages) if mem and mem.messages else 0
        had_greeting = old_state.get("greeting_shown", False) if old_state else False
        logger.info(f"🧹 CLEARED session for user {user_id}:")
        logger.info(f"   • {message_count} messages in memory")
        logger.info(f"   • greeting_shown was: {had_greeting}")
        logger.info(f"   • Next greeting will trigger NEW SESSION and greeting card")
        logger.info(f"   • Removed from first_time_users: {user_id in self.first_time_users}")
        
        # Ensure the user is completely removed from session tracking so next message starts fresh
        # This makes the next message go through the "state is None" or "session_id not in state" logic
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics for monitoring."""
        return {
            "active_users": len(self.user_states),
            "first_time_users": len(self.first_time_users),
            "total_memories": len(self.user_memories),
            "feedback_cards": len(self.feedback_cards)
        }
    
    def cleanup_expired_sessions(self, max_idle_minutes: int = 30) -> int:
        """Clean up expired sessions based on idle time."""
        import time
        current_time = time.time()
        expired_users = []
        
        for user_id, state in self.user_states.items():
            last_response_time = state.get("last_bot_response_time")
            if last_response_time:
                # Convert datetime to timestamp for comparison
                if hasattr(last_response_time, 'timestamp'):
                    last_timestamp = last_response_time.timestamp()
                else:
                    last_timestamp = last_response_time
                
                idle_minutes = (current_time - last_timestamp) / 60
                if idle_minutes > max_idle_minutes:
                    expired_users.append(user_id)
        
        # Clear expired sessions
        for user_id in expired_users:
            logger.info(f"Cleaning up expired session for user {user_id} (idle for >{max_idle_minutes} minutes)")
            self.clear_user_session(user_id)
        
        return len(expired_users)
