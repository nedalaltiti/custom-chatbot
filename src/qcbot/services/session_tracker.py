import asyncio
import threading
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Union
from uuid import uuid4
import weakref


class SessionTracker:
    """
    Production-ready session tracker with:
    - Thread safety for mixed sync/async usage
    - Memory efficiency with automatic cleanup
    - Metrics and monitoring hooks
    - Race condition prevention
    """

    def __init__(self, idle_minutes: int = 30, max_sessions: int = 10000):
        self._sessions: Dict[str, str] = {}
        self._last_seen: Dict[str, datetime] = {}
        self._idle = timedelta(minutes=idle_minutes)
        self._max_sessions = max_sessions

        # Use RLock for reentrant locking
        self._lock = threading.RLock()

        # Async locks per user for fine-grained async locking
        self._async_locks: Dict[str, asyncio.Lock] = {}

        # Metrics
        self._metrics = {
            'sessions_created': 0,
            'sessions_expired': 0,
            'sessions_ended': 0,
            'race_conditions_prevented': 0
        }

    def get(self, user_id: str) -> str:
        """Thread-safe synchronous session retrieval."""
        with self._lock:
            return self._get_or_create_session(user_id)

    async def get_async(self, user_id: str) -> str:
        """Async-safe session retrieval with per-user locking."""
        # Get or create async lock for this user (thread-safe)
        with self._lock:
            if user_id not in self._async_locks:
                self._async_locks[user_id] = asyncio.Lock()
            user_lock = self._async_locks[user_id]

        async with user_lock:
            # Use thread lock for actual data access
            with self._lock:
                return self._get_or_create_session(user_id)

    def _get_or_create_session(self, user_id: str) -> str:
        """Internal method to get or create session (must be called within lock)."""
        now = datetime.now(timezone.utc)

        # Check if we have a valid session
        if user_id in self._sessions:
            if now - self._last_seen[user_id] < self._idle:
                # Session is valid, update last seen
                self._last_seen[user_id] = now
                return self._sessions[user_id]
            else:
                # Session expired, remove it
                self._sessions.pop(user_id, None)
                self._last_seen.pop(user_id, None)
                self._async_locks.pop(user_id, None)  # Clean up async lock
                self._metrics['sessions_expired'] += 1

        # Create new session
        session_id = str(uuid4())
        self._sessions[user_id] = session_id
        self._last_seen[user_id] = now
        self._metrics['sessions_created'] += 1

        # Cleanup if we have too many sessions
        if len(self._sessions) > self._max_sessions:
            self._cleanup_expired_sessions()

        return session_id

    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions (must be called within lock)."""
        now = datetime.now(timezone.utc)
        expired_users = [
            user_id for user_id, last_seen in self._last_seen.items()
            if now - last_seen >= self._idle
        ]

        for user_id in expired_users:
            self._sessions.pop(user_id, None)
            self._last_seen.pop(user_id, None)
            self._async_locks.pop(user_id, None)  # Clean up async lock
            self._metrics['sessions_expired'] += 1
        
        # If still over limit, remove oldest sessions
        if len(self._sessions) > self._max_sessions:
            # Sort by last seen time and remove oldest
            sorted_users = sorted(
                self._last_seen.items(), 
                key=lambda x: x[1]
            )
            excess_count = len(self._sessions) - self._max_sessions
            for user_id, _ in sorted_users[:excess_count]:
                self._sessions.pop(user_id, None)
                self._last_seen.pop(user_id, None)
                self._async_locks.pop(user_id, None)  # Clean up async lock
                self._metrics['sessions_expired'] += 1

    @contextmanager
    def session_context(self, user_id: str):
        """Context manager for session lifecycle."""
        session_id = self.get(user_id)
        try:
            yield session_id
        finally:
            # Optionally update last seen on context exit
            with self._lock:
                if user_id in self._sessions:
                    self._last_seen[user_id] = datetime.now(timezone.utc)

    def get_metrics(self) -> Dict[str, int]:
        """Get session tracker metrics."""
        with self._lock:
            return {
                **self._metrics,
                'active_sessions': len(self._sessions),
                'tracked_users': len(self._last_seen)
            }

    # Backward compatibility methods
    def new_session(self, user_id: str) -> str:
        """Force-start a brand-new session ID (used e.g. after welcome card)."""
        with self._lock:
            session_id = str(uuid4())
            self._sessions[user_id] = session_id
            self._last_seen[user_id] = datetime.now(timezone.utc)
            self._metrics['sessions_created'] += 1
            return session_id

    def end_session(self, user_id: str) -> None:
        """Explicitly close the session (called when feedback is submitted)."""
        with self._lock:
            self._sessions.pop(user_id, None)
            self._last_seen.pop(user_id, None)
            self._async_locks.pop(user_id, None)  # Clean up async lock
            self._metrics['sessions_ended'] += 1

    def _expired(self, user_id: str) -> bool:
        """Check if a session is expired (backward compatibility)."""
        with self._lock:
            if user_id not in self._sessions:
                return True
            return datetime.now(timezone.utc) - self._last_seen[user_id] >= self._idle


# singleton shared by the app
session_tracker = SessionTracker(idle_minutes=30)
