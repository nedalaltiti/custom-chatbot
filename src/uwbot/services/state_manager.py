"""
Database-based State Management Service

This service provides persistent, scalable state management that survives:
- Application restarts
- Container restarts  
- Horizontal scaling
- Deployment updates

Replaces the problematic in-memory dictionaries with database-backed state.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from uuid import uuid4

from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from uwbot.db.models import UserSession, UserActivity
from uwbot.db.session import get_db_session_context
from uwbot.config.settings import settings
from uwbot.utils.bot_name import get_bot_name

logger = logging.getLogger(__name__)


class UserState:
    """Type-safe user state object."""
    
    def __init__(
        self,
        user_id: str,
        session_id: str,

        greeting_shown: bool = False,
        session_started: bool = True,
        is_first_time_user: bool = True,
        last_bot_response_time: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.user_id = user_id
        self.session_id = session_id

        self.greeting_shown = greeting_shown
        self.session_started = session_started
        self.is_first_time_user = is_first_time_user
        self.last_bot_response_time = last_bot_response_time
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "session_id": self.session_id,

            "greeting_shown": self.greeting_shown,
            "session_started": self.session_started,
            "last_bot_response_time": self.last_bot_response_time,
            **self.metadata
        }


class DatabaseStateManager:
    """Database-backed state management service."""
    
    def __init__(self, session_idle_minutes: int = 30):
        self.session_idle_minutes = session_idle_minutes
        self.session_idle_delta = timedelta(minutes=session_idle_minutes)
        self.bot_name = get_bot_name()
        self.env = settings.environment
        logger.info(f"DatabaseStateManager initialized for {self.bot_name} in {self.env}")
    
    async def get_user_state(self, user_id: str) -> Optional[UserState]:
        """
        Get user state from database.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserState object or None if not found
        """
        try:
            async with get_db_session_context() as session:
                stmt = select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.bot_name == self.bot_name,
                    UserSession.env == self.env
                )
                result = await session.execute(stmt)
                db_session = result.scalar_one_or_none()
                
                if not db_session:
                    return None
                
                # Check if session is expired
                if self._is_session_expired(db_session.last_activity):
                    logger.info(f"Session expired for user {user_id}, cleaning up")
                    await self._cleanup_expired_session(session, db_session)
                    return None
                
                # Parse state data
                metadata = {}
                if db_session.state_data:
                    try:
                        metadata = json.loads(db_session.state_data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON state data for user {user_id}")
                
                return UserState(
                    user_id=db_session.user_id,
                    session_id=db_session.session_id,

                    greeting_shown=db_session.greeting_shown,
                    session_started=db_session.session_started,
                    is_first_time_user=db_session.is_first_time_user,
                    last_bot_response_time=db_session.last_bot_response_time,
                    metadata=metadata
                )
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user state for {user_id}: {e}")
            return None
    
    async def create_user_state(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        is_first_time_user: bool = True
    ) -> UserState:
        """
        Create new user state in database.
        
        Args:
            user_id: User identifier
            session_id: Optional session ID (will generate if not provided)
            is_first_time_user: Whether this is a first-time user
            
        Returns:
            Created UserState object
        """
        if not session_id:
            session_id = str(uuid4())
        
        try:
            async with get_db_session_context() as session:
                db_session = UserSession(
                    user_id=user_id,
                    session_id=session_id,
                    bot_name=self.bot_name,
                    env=self.env,
                    is_first_time_user=is_first_time_user,

                    greeting_shown=False,
                    session_started=True,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    last_activity=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                
                session.add(db_session)
                await session.flush()  # Get the ID
                
                logger.info(f"Created new user state for {user_id} with session {session_id}")
                
                return UserState(
                    user_id=user_id,
                    session_id=session_id,
                    is_first_time_user=is_first_time_user
                )
                
        except IntegrityError:
            # Handle race condition - user might have been created by another request
            logger.info(f"User state already exists for {user_id}, retrieving existing")
            return await self.get_user_state(user_id) or await self.create_user_state(user_id, session_id, is_first_time_user)
        except SQLAlchemyError as e:
            logger.error(f"Database error creating user state for {user_id}: {e}")
            # Return in-memory fallback
            return UserState(user_id=user_id, session_id=session_id, is_first_time_user=is_first_time_user)
    
    async def update_user_state(self, user_id: str, **updates) -> bool:
        """
        Update user state in database.
        
        Args:
            user_id: User identifier
            **updates: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with get_db_session_context() as session:
                # Handle state data updates specially
                metadata_update = updates.pop('metadata', None)
                
                # Update last_activity timestamp
                updates['last_activity'] = datetime.now(timezone.utc).replace(tzinfo=None)
                
                stmt = update(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.bot_name == self.bot_name,
                    UserSession.env == self.env
                ).values(**updates)
                
                result = await session.execute(stmt)
                
                # Handle state data update separately if needed
                if metadata_update is not None:
                    metadata_stmt = update(UserSession).where(
                        UserSession.user_id == user_id,
                        UserSession.bot_name == self.bot_name,
                        UserSession.env == self.env
                    ).values(state_data=json.dumps(metadata_update))
                    
                    await session.execute(metadata_stmt)
                
                success = result.rowcount > 0
                if success:
                    logger.debug(f"Updated user state for {user_id}: {updates}")
                else:
                    logger.warning(f"No rows updated for user {user_id}")
                
                return success
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating user state for {user_id}: {e}")
            return False
    
    async def clear_user_state(self, user_id: str) -> bool:
        """
        Clear/delete user state from database.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with get_db_session_context() as session:
                # Delete user session
                session_stmt = delete(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.bot_name == self.bot_name,
                    UserSession.env == self.env
                )
                session_result = await session.execute(session_stmt)
                
                # Delete user activities (optional cleanup)
                activity_stmt = delete(UserActivity).where(
                    UserActivity.user_id == user_id,
                    UserActivity.bot_name == self.bot_name,
                    UserActivity.env == self.env
                )
                activity_result = await session.execute(activity_stmt)
                
                logger.info(f"Cleared user state for {user_id}: {session_result.rowcount} sessions, {activity_result.rowcount} activities")
                return session_result.rowcount > 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error clearing user state for {user_id}: {e}")
            return False
    
    async def track_user_activity(
        self,
        user_id: str,
        session_id: str,
        activity_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track user activity for analytics.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            activity_type: Type of activity (message, card_action)
            metadata: Optional activity metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with get_db_session_context() as session:
                activity = UserActivity(
                    user_id=user_id,
                    session_id=session_id,
                    bot_name=self.bot_name,
                    env=self.env,
                    activity_type=activity_type,
                    timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                    state_data=json.dumps(metadata) if metadata else None
                )
                
                session.add(activity)
                
                # Also update user session last_activity
                await self.update_user_state(user_id, last_activity=activity.timestamp)
                
                logger.debug(f"Tracked {activity_type} activity for user {user_id}")
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error tracking activity for {user_id}: {e}")
            return False
    
    async def get_first_time_users(self) -> List[str]:
        """
        Get list of first-time users.
        
        Returns:
            List of user IDs who are first-time users
        """
        try:
            async with get_db_session_context() as session:
                stmt = select(UserSession.user_id).where(
                    UserSession.is_first_time_user == True,
                    UserSession.bot_name == self.bot_name,
                    UserSession.env == self.env
                )
                result = await session.execute(stmt)
                return [row[0] for row in result.fetchall()]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting first-time users: {e}")
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions from database.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - self.session_idle_delta
            
            async with get_db_session_context() as session:
                stmt = delete(UserSession).where(
                    UserSession.last_activity < cutoff_time,
                    UserSession.bot_name == self.bot_name,
                    UserSession.env == self.env
                )
                result = await session.execute(stmt)
                
                cleaned_count = result.rowcount
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} expired sessions")
                
                return cleaned_count
                
        except SQLAlchemyError as e:
            logger.error(f"Database error cleaning up expired sessions: {e}")
            return 0
    
    def _is_session_expired(self, last_activity: datetime) -> bool:
        """Check if a session is expired based on last activity."""
        if not last_activity:
            return True
        
        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - self.session_idle_delta
        return last_activity < cutoff_time
    
    async def _cleanup_expired_session(self, session: Session, db_session: UserSession) -> None:
        """Clean up an individual expired session."""
        await session.delete(db_session)
        logger.debug(f"Cleaned up expired session for user {db_session.user_id}")


# Singleton instance
_state_manager = None

def get_state_manager() -> DatabaseStateManager:
    """Get the singleton state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = DatabaseStateManager(
            session_idle_minutes=settings.session_idle_minutes
        )
    return _state_manager
