"""
Database-backed Session Tracker

Replaces the in-memory session tracker with a database-backed implementation
that provides persistence and scalability across multiple application instances.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from uwbot.services.state_manager import get_state_manager, UserState

logger = logging.getLogger(__name__)


class DatabaseSessionTracker:
    """Database-backed session tracker for persistent session management."""
    
    def __init__(self, idle_minutes: int = 30):
        self.idle_minutes = idle_minutes
        self.state_manager = get_state_manager()
        logger.info(f"DatabaseSessionTracker initialized with {idle_minutes}min idle timeout")
    
    async def get(self, user_id: str) -> str:
        """
        Return the current session-id; create one on first use.
        
        Args:
            user_id: User identifier
            
        Returns:
            Current session ID for the user
        """
        try:
            # Try to get existing state
            user_state = await self.state_manager.get_user_state(user_id)
            
            if user_state:
                # Update last activity and return existing session
                await self.state_manager.track_user_activity(
                    user_id=user_id,
                    session_id=user_state.session_id,
                    activity_type="session_access"
                )
                return user_state.session_id
            else:
                # Create new session
                session_id = str(uuid4())
                user_state = await self.state_manager.create_user_state(
                    user_id=user_id,
                    session_id=session_id,
                    is_first_time_user=True
                )
                
                await self.state_manager.track_user_activity(
                    user_id=user_id,
                    session_id=session_id,
                    activity_type="session_created"
                )
                
                logger.info(f"Created new session {session_id} for user {user_id}")
                return user_state.session_id
                
        except Exception as e:
            logger.error(f"Error getting session for user {user_id}: {e}")
            # Fallback to generating a temporary session ID
            fallback_session = str(uuid4())
            logger.warning(f"Using fallback session {fallback_session} for user {user_id}")
            return fallback_session
    
    async def new_session(self, user_id: str) -> str:
        """
        Force-start a brand-new session ID (used e.g. after welcome card).
        
        Args:
            user_id: User identifier
            
        Returns:
            New session ID
        """
        try:
            # Clear existing state
            await self.state_manager.clear_user_state(user_id)
            
            # Create fresh session
            session_id = str(uuid4())
            user_state = await self.state_manager.create_user_state(
                user_id=user_id,
                session_id=session_id,
                is_first_time_user=False  # Not first time if we're forcing new session
            )
            
            await self.state_manager.track_user_activity(
                user_id=user_id,
                session_id=session_id,
                activity_type="session_forced_new"
            )
            
            logger.info(f"Force-created new session {session_id} for user {user_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Error creating new session for user {user_id}: {e}")
            # Fallback to generating a temporary session ID
            fallback_session = str(uuid4())
            logger.warning(f"Using fallback new session {fallback_session} for user {user_id}")
            return fallback_session
    
    async def end_session(self, user_id: str) -> None:
        """
        Explicitly close the session (called when session ends).
        
        Args:
            user_id: User identifier
        """
        try:
            # Get current session for logging
            user_state = await self.state_manager.get_user_state(user_id)
            session_id = user_state.session_id if user_state else "unknown"
            
            # Track session end activity
            if user_state:
                await self.state_manager.track_user_activity(
                    user_id=user_id,
                    session_id=session_id,
                    activity_type="session_ended"
                )
            
            # Clear the session
            success = await self.state_manager.clear_user_state(user_id)
            
            if success:
                logger.info(f"Ended session {session_id} for user {user_id}")
            else:
                logger.warning(f"Failed to end session for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error ending session for user {user_id}: {e}")
    
    async def is_expired(self, user_id: str) -> bool:
        """
        Check if user's session is expired.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session is expired or doesn't exist
        """
        try:
            user_state = await self.state_manager.get_user_state(user_id)
            return user_state is None  # get_user_state handles expiry check internally
            
        except Exception as e:
            logger.error(f"Error checking session expiry for user {user_id}: {e}")
            return True  # Assume expired on error
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            return await self.state_manager.cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0


# Create singleton instance
db_session_tracker = DatabaseSessionTracker(idle_minutes=30)
