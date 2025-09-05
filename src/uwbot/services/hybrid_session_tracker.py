"""
Hybrid Session Tracker with Graceful Fallback

This service automatically uses database-backed or in-memory session tracking
based on database availability, providing seamless fallback functionality.
"""

import logging
from typing import Optional
from uuid import uuid4

from uwbot.services.hybrid_state_manager import get_hybrid_state_manager
from uwbot.services.session_tracker import SessionTracker

logger = logging.getLogger(__name__)


class HybridSessionTracker:
    """Session tracker that uses database with in-memory fallback."""
    
    def __init__(self, idle_minutes: int = 30):
        self.idle_minutes = idle_minutes
        self.state_manager = get_hybrid_state_manager()
        self.fallback_tracker = SessionTracker(idle_minutes)
        logger.info(f"HybridSessionTracker initialized with {idle_minutes}min idle timeout")
    
    async def get(self, user_id: str) -> str:
        """
        Return the current session-id; create one on first use.
        Uses database if available, falls back to in-memory.
        """
        try:
            # Check if we're using database mode
            if self.state_manager.is_using_database() is True:
                # Database mode - get from user state
                user_state = await self.state_manager.get_user_state(user_id)
                
                if user_state:
                    # Update activity and return existing session
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
                    
                    logger.info(f"Created new database session {session_id} for user {user_id}")
                    return user_state.session_id
            
            elif self.state_manager.is_using_database() is False:
                # In-memory mode - use fallback tracker
                session_id = self.fallback_tracker.get(user_id)
                logger.debug(f"Using in-memory session {session_id} for user {user_id}")
                return session_id
            
            else:
                # Database availability not yet determined - trigger check
                await self.state_manager._check_database_availability()
                return await self.get(user_id)  # Recursive call after check
                
        except Exception as e:
            logger.error(f"Error in hybrid session get for user {user_id}: {e}")
            # Emergency fallback to in-memory
            return self.fallback_tracker.get(user_id)
    
    async def new_session(self, user_id: str) -> str:
        """
        Force-start a brand-new session ID.
        Uses database if available, falls back to in-memory.
        """
        try:
            if self.state_manager.is_using_database() is True:
                # Database mode - clear existing state and create new
                await self.state_manager.clear_user_state(user_id)
                
                session_id = str(uuid4())
                user_state = await self.state_manager.create_user_state(
                    user_id=user_id,
                    session_id=session_id,
                    is_first_time_user=False
                )
                
                await self.state_manager.track_user_activity(
                    user_id=user_id,
                    session_id=session_id,
                    activity_type="session_forced_new"
                )
                
                logger.info(f"Force-created new database session {session_id} for user {user_id}")
                return session_id
            
            elif self.state_manager.is_using_database() is False:
                # In-memory mode - use fallback tracker
                session_id = self.fallback_tracker.new_session(user_id)
                logger.info(f"Force-created new in-memory session {session_id} for user {user_id}")
                return session_id
            
            else:
                # Database availability not yet determined
                await self.state_manager._check_database_availability()
                return await self.new_session(user_id)
                
        except Exception as e:
            logger.error(f"Error creating new hybrid session for user {user_id}: {e}")
            # Emergency fallback to in-memory
            return self.fallback_tracker.new_session(user_id)
    
    async def end_session(self, user_id: str) -> None:
        """
        Explicitly close the session.
        Uses database if available, falls back to in-memory.
        """
        try:
            if self.state_manager.is_using_database() is True:
                # Database mode - get current session for logging
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
                    logger.info(f"Ended database session {session_id} for user {user_id}")
                else:
                    logger.warning(f"Failed to end database session for user {user_id}")
            
            elif self.state_manager.is_using_database() is False:
                # In-memory mode - use fallback tracker
                self.fallback_tracker.end_session(user_id)
                logger.info(f"Ended in-memory session for user {user_id}")
            
            else:
                # Database availability not yet determined
                await self.state_manager._check_database_availability()
                await self.end_session(user_id)
                
        except Exception as e:
            logger.error(f"Error ending hybrid session for user {user_id}: {e}")
            # Emergency fallback to in-memory
            self.fallback_tracker.end_session(user_id)
    
    async def is_expired(self, user_id: str) -> bool:
        """
        Check if user's session is expired.
        Uses database if available, falls back to in-memory.
        """
        try:
            if self.state_manager.is_using_database() is True:
                # Database mode - check via state manager
                user_state = await self.state_manager.get_user_state(user_id)
                return user_state is None
            
            elif self.state_manager.is_using_database() is False:
                # In-memory mode - use fallback tracker
                return self.fallback_tracker._expired(user_id)
            
            else:
                # Database availability not yet determined
                await self.state_manager._check_database_availability()
                return await self.is_expired(user_id)
                
        except Exception as e:
            logger.error(f"Error checking session expiry for user {user_id}: {e}")
            return True  # Assume expired on error
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.
        Uses database if available, falls back to in-memory.
        """
        try:
            return await self.state_manager.cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0
    
    def get_mode(self) -> str:
        """Get current operating mode for debugging."""
        if self.state_manager.is_using_database() is True:
            return "database"
        elif self.state_manager.is_using_database() is False:
            return "in-memory"
        else:
            return "undetermined"


# Create singleton instance
hybrid_session_tracker = HybridSessionTracker(idle_minutes=30)
