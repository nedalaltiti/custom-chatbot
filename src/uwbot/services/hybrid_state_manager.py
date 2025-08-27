"""
Hybrid State Manager with Graceful Fallback

This service automatically detects if database tables exist and uses:
1. Database-backed state management (preferred)
2. In-memory state management (fallback)

This allows deployment without requiring database table creation first.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Set
from uuid import uuid4
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError

from uwbot.services.state_manager import DatabaseStateManager, UserState
from uwbot.services.session_tracker import SessionTracker
from uwbot.db.session import get_db_session_context
from uwbot.config.settings import settings

logger = logging.getLogger(__name__)


class InMemoryStateManager:
    """Fallback in-memory state manager (original approach)."""
    
    def __init__(self, session_idle_minutes: int = 30):
        self.session_idle_minutes = session_idle_minutes
        self.session_tracker = SessionTracker(session_idle_minutes)
        
        # Original in-memory storage
        self.first_time_users: Set[str] = set()
        self.user_states: Dict[str, Dict[str, Any]] = {}
        
        logger.info("InMemoryStateManager initialized (fallback mode)")
    
    async def get_user_state(self, user_id: str) -> Optional[UserState]:
        """Get user state from in-memory storage."""
        try:
            state_dict = self.user_states.get(user_id)
            if state_dict is None:
                return None
            
            return UserState(
                user_id=user_id,
                session_id=state_dict.get("session_id", str(uuid4())),
                greeting_shown=state_dict.get("greeting_shown", False),
                session_started=state_dict.get("session_started", True),
                is_first_time_user=user_id in self.first_time_users,
                last_bot_response_time=state_dict.get("last_bot_response_time"),
                metadata=state_dict.get("metadata", {})
            )
            
        except Exception as e:
            logger.error(f"Error getting in-memory user state for {user_id}: {e}")
            return None
    
    async def create_user_state(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        is_first_time_user: bool = True
    ) -> UserState:
        """Create new user state in memory."""
        if not session_id:
            session_id = self.session_tracker.get(user_id)
        
        self.user_states[user_id] = {
            "session_id": session_id,
            "greeting_shown": False,
            "session_started": True,
            "last_bot_response_time": None,
            "metadata": {}
        }
        
        if is_first_time_user:
            self.first_time_users.add(user_id)
        
        logger.info(f"Created in-memory user state for {user_id} with session {session_id}")
        
        return UserState(
            user_id=user_id,
            session_id=session_id,
            is_first_time_user=is_first_time_user
        )
    
    async def update_user_state(self, user_id: str, **updates) -> bool:
        """Update user state in memory."""
        try:
            if user_id not in self.user_states:
                # Create state if it doesn't exist
                await self.create_user_state(user_id, is_first_time_user=False)
            
            # Handle special cases
            if 'is_first_time_user' in updates:
                if updates['is_first_time_user']:
                    self.first_time_users.add(user_id)
                else:
                    self.first_time_users.discard(user_id)
                del updates['is_first_time_user']
            
            # Update the state dictionary
            self.user_states[user_id].update(updates)
            
            logger.debug(f"Updated in-memory user state for {user_id}: {updates}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating in-memory user state for {user_id}: {e}")
            return False
    
    async def clear_user_state(self, user_id: str) -> bool:
        """Clear user state from memory."""
        try:
            self.user_states.pop(user_id, None)
            self.first_time_users.discard(user_id)
            self.session_tracker.end_session(user_id)
            
            logger.info(f"Cleared in-memory user state for {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing in-memory user state for {user_id}: {e}")
            return False
    
    async def track_user_activity(
        self,
        user_id: str,
        session_id: str,
        activity_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Track user activity (no-op for in-memory, just log)."""
        logger.debug(f"Tracked {activity_type} activity for user {user_id} (in-memory mode)")
        return True
    
    async def get_first_time_users(self) -> List[str]:
        """Get list of first-time users."""
        return list(self.first_time_users)
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (basic cleanup for in-memory)."""
        # Simple cleanup - remove very old states
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.session_idle_minutes * 2)
        expired_users = []
        
        for user_id, state in self.user_states.items():
            last_activity = state.get("last_bot_response_time")
            if last_activity and last_activity < cutoff_time:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            await self.clear_user_state(user_id)
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired in-memory sessions")
        
        return len(expired_users)


class HybridStateManager:
    """Hybrid state manager that uses database with in-memory fallback."""
    
    def __init__(self, session_idle_minutes: int = 30):
        self.session_idle_minutes = session_idle_minutes
        self.db_state_manager = None
        self.memory_state_manager = InMemoryStateManager(session_idle_minutes)
        self.use_database = None  # Will be determined on first use
        self.database_check_performed = False
        
        logger.info("HybridStateManager initialized")
    
    async def _check_database_availability(self) -> bool:
        """Check if database tables exist and are accessible."""
        if self.database_check_performed:
            return self.use_database
        
        try:
            async with get_db_session_context() as session:
                # Try to check if user_session table exists
                result = await session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'ai_chatbot' 
                        AND table_name = 'user_session'
                    )
                """))
                user_session_exists = result.scalar()
                
                if user_session_exists:
                    # Try a simple query to make sure we can actually use it
                    await session.execute(text("SELECT COUNT(*) FROM ai_chatbot.user_session LIMIT 1"))
                    
                    # Initialize database state manager
                    self.db_state_manager = DatabaseStateManager(self.session_idle_minutes)
                    self.use_database = True
                    logger.info("✅ Database state management available - using database mode")
                else:
                    self.use_database = False
                    logger.info("⚠️ Database tables not found - using in-memory fallback mode")
                    
        except (SQLAlchemyError, ProgrammingError, Exception) as e:
            self.use_database = False
            logger.warning(f"⚠️ Database not available ({e}) - using in-memory fallback mode")
        
        self.database_check_performed = True
        return self.use_database
    
    async def _get_active_manager(self):
        """Get the active state manager (database or in-memory)."""
        if await self._check_database_availability():
            return self.db_state_manager
        else:
            return self.memory_state_manager
    
    async def get_user_state(self, user_id: str) -> Optional[UserState]:
        """Get user state from active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.get_user_state(user_id)
        except Exception as e:
            logger.error(f"Error in hybrid get_user_state: {e}")
            # Emergency fallback to in-memory
            return await self.memory_state_manager.get_user_state(user_id)
    
    async def create_user_state(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        is_first_time_user: bool = True
    ) -> UserState:
        """Create new user state using active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.create_user_state(user_id, session_id, is_first_time_user)
        except Exception as e:
            logger.error(f"Error in hybrid create_user_state: {e}")
            # Emergency fallback to in-memory
            return await self.memory_state_manager.create_user_state(user_id, session_id, is_first_time_user)
    
    async def update_user_state(self, user_id: str, **updates) -> bool:
        """Update user state using active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.update_user_state(user_id, **updates)
        except Exception as e:
            logger.error(f"Error in hybrid update_user_state: {e}")
            # Emergency fallback to in-memory
            return await self.memory_state_manager.update_user_state(user_id, **updates)
    
    async def clear_user_state(self, user_id: str) -> bool:
        """Clear user state using active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.clear_user_state(user_id)
        except Exception as e:
            logger.error(f"Error in hybrid clear_user_state: {e}")
            # Emergency fallback to in-memory
            return await self.memory_state_manager.clear_user_state(user_id)
    
    async def track_user_activity(
        self,
        user_id: str,
        session_id: str,
        activity_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Track user activity using active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.track_user_activity(user_id, session_id, activity_type, metadata)
        except Exception as e:
            logger.error(f"Error in hybrid track_user_activity: {e}")
            # Emergency fallback to in-memory (no-op)
            return await self.memory_state_manager.track_user_activity(user_id, session_id, activity_type, metadata)
    
    async def get_first_time_users(self) -> List[str]:
        """Get list of first-time users from active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.get_first_time_users()
        except Exception as e:
            logger.error(f"Error in hybrid get_first_time_users: {e}")
            return await self.memory_state_manager.get_first_time_users()
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions using active manager."""
        try:
            manager = await self._get_active_manager()
            return await manager.cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Error in hybrid cleanup_expired_sessions: {e}")
            return await self.memory_state_manager.cleanup_expired_sessions()
    
    def is_using_database(self) -> Optional[bool]:
        """Check if currently using database mode."""
        return self.use_database
    
    async def force_database_check(self) -> bool:
        """Force a re-check of database availability."""
        self.database_check_performed = False
        self.use_database = None
        return await self._check_database_availability()


# Singleton instance
_hybrid_state_manager = None

def get_hybrid_state_manager() -> HybridStateManager:
    """Get the singleton hybrid state manager instance."""
    global _hybrid_state_manager
    if _hybrid_state_manager is None:
        _hybrid_state_manager = HybridStateManager(
            session_idle_minutes=settings.session_idle_minutes
        )
    return _hybrid_state_manager
