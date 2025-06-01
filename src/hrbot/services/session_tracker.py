from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class SessionTracker:
    """Return the current session_id for a user or start a new one.

    A session is considered inactive after *idle_minutes* with no messages.
    """

    def __init__(self, idle_minutes: int = 30):
        self._current   = defaultdict(lambda: None)          # user_id → session_id
        self._last_seen = defaultdict(lambda: datetime.now(timezone.utc))
        self._idle      = timedelta(minutes=idle_minutes)


    def _expired(self, user_id: str) -> bool:
        return (
            self._current[user_id] is None
            or datetime.now(timezone.utc) - self._last_seen[user_id] >= self._idle
        )

    def new_session(self, user_id: str) -> str:
        """Force-start a brand-new session ID (used e.g. after welcome card)."""
        sid = str(uuid4())
        self._current[user_id]   = sid
        self._last_seen[user_id] = datetime.now(timezone.utc)
        return sid

    def get(self, user_id: str) -> str:
        """Return the current session-id; create one on first use."""
        if self._current[user_id] is None:       
            self._current[user_id] = str(uuid4())
        
        self._last_seen[user_id] = datetime.now(timezone.utc)
        return self._current[user_id]

        # touch last-seen timestamp
        self._last_seen[user_id] = datetime.now(timezone.utc)
        return self._current[user_id]

    def end_session(self, user_id: str) -> None:
        """Explicitly close the session (called when feedback is submitted)."""
        self._current.pop(user_id, None)
        self._last_seen.pop(user_id, None)


# singleton shared by the app
session_tracker = SessionTracker(idle_minutes=30)
