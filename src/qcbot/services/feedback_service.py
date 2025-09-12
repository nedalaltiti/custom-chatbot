"""
Enhanced, memory-efficient feedback service with TTL cleanup, LRU eviction,
and robust scheduling to prevent memory leaks under load.
"""

import asyncio
import heapq
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from qcbot.infrastructure.teams_adapter import TeamsAdapter
from qcbot.config.settings import settings
from qcbot.infrastructure.cards import create_feedback_card
from sqlalchemy.exc import SQLAlchemyError
from qcbot.db.models import Rating, MessageReplyFeedback, MessageReply
from qcbot.db.session import get_db_session_context
from qcbot.utils.bot_name import get_bot_name
from qcbot.db.models import Message

logger = logging.getLogger(__name__)


@dataclass(order=True)
class ExpiringItem:
    """Item with expiration time for priority queue."""
    expiry_time: float
    user_id: str = field(compare=False)
    data: Any = field(compare=False, default=None)


class MemoryEfficientFeedbackService:
    """
    Production-ready feedback service with:
    - Bounded memory usage (LRU)
    - Automatic TTL-based cleanup
    - Memory pressure handling
    - Metrics and monitoring
    """

    def __init__(
        self,
        max_users: int = 10000,
        max_memory_mb: int = 100,
        activity_ttl_minutes: int = 60,
        feedback_ttl_minutes: int = 120,
    ) -> None:
        self.adapter = TeamsAdapter()

        # Configuration
        self.max_users = max_users
        self.max_memory_mb = max_memory_mb
        self.activity_ttl = timedelta(minutes=activity_ttl_minutes)
        self.feedback_ttl = timedelta(minutes=feedback_ttl_minutes)

        # Defaults
        self.default_timeout_minutes = getattr(settings.feedback, "feedback_timeout_minutes", 10)
        self.activity_check_interval = 30

        # Bounded state (LRU for activity and sent-tracking)
        self._user_activity: "OrderedDict[str, datetime]" = OrderedDict()
        self._pending_feedback: Dict[str, asyncio.Task] = {}
        self._feedback_sent: "OrderedDict[str, datetime]" = OrderedDict()

        # TTL priority queue
        self._expiry_queue: list[ExpiringItem] = []

        # Metrics
        self._metrics: Dict[str, int] = {
            "total_users_tracked": 0,
            "memory_cleanups": 0,
            "ttl_cleanups": 0,
            "tasks_cancelled": 0,
            "max_concurrent_users": 0,
        }

        # Cleanup loop (will be created when first needed)
        self._cleanup_task: Optional[asyncio.Task] = None

    # Compatibility properties
    @property
    def user_activity(self) -> Dict[str, datetime]:
        """Compatibility property for user_activity."""
        return dict(self._user_activity)

    @property
    def pending_feedback(self) -> Dict[str, asyncio.Task]:
        """Compatibility property for pending_feedback."""
        return self._pending_feedback

    @property
    def feedback_sent(self) -> set:
        """Compatibility property for feedback_sent."""
        return set(self._feedback_sent.keys())

    @property
    def activity_to_message_id(self) -> Dict[str, int]:
        """Compatibility property for activity_to_message_id."""
        return getattr(self, '_activity_to_message_id', {})

    def _ensure_cleanup_task(self):
        """Ensure cleanup task is running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            except RuntimeError:
                # No event loop running, will start later
                pass

    def track_user_activity(self, user_id: str):
        """Track user activity with LRU eviction."""
        now = datetime.now(timezone.utc)
        
        # Ensure cleanup task is running
        self._ensure_cleanup_task()
        
        # Update LRU
        if user_id in self._user_activity:
            del self._user_activity[user_id]
        self._user_activity[user_id] = now
        
        # Add to expiry queue
        self._expiry_queue.append(ExpiringItem(
            expiry_time=time.time() + self.activity_ttl.total_seconds(),
            user_id=user_id,
            data="activity"
        ))
        heapq.heapify(self._expiry_queue)
        
        # Update metrics
        self._metrics["total_users_tracked"] += 1
        self._metrics["max_concurrent_users"] = max(
            self._metrics["max_concurrent_users"], 
            len(self._user_activity)
        )
        
        # Memory pressure check
        if len(self._user_activity) > self.max_users:
            self._evict_lru_users()
        
        logger.debug(f"Tracked activity for user {user_id}")

    def track_activity_to_message_mapping(self, teams_activity_id: str, bot_message_db_id: int):
        """Track the mapping between Teams activity ID and bot message database ID."""
        if not hasattr(self, '_activity_to_message_id'):
            self._activity_to_message_id = {}
        
        if teams_activity_id and bot_message_db_id:
            self._activity_to_message_id[teams_activity_id] = bot_message_db_id
            logger.debug(f"Mapped Teams activity {teams_activity_id} to bot message DB ID {bot_message_db_id}")

    def get_bot_message_id_from_activity(self, teams_activity_id: str) -> int | None:
        """Get the bot message database ID from a Teams activity ID."""
        if not hasattr(self, '_activity_to_message_id'):
            return None
        return self._activity_to_message_id.get(teams_activity_id)

    def schedule_delayed_feedback(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int = None, on_card_sent=None):
        """Schedule delayed feedback with memory management."""
        # Cancel existing task if any
        if user_id in self._pending_feedback:
            self._pending_feedback[user_id].cancel()
            self._metrics["tasks_cancelled"] += 1

        delay = delay_minutes or self.default_timeout_minutes
        task = asyncio.create_task(
            self._send_feedback_after_inactivity(user_id, service_url, conversation_id, delay, on_card_sent)
        )
        self._pending_feedback[user_id] = task

    async def _send_feedback_after_inactivity(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int, on_card_sent=None):
        """Send feedback after inactivity period."""
        try:
            await asyncio.sleep(delay_minutes * 60)
            
            # Check if user is still inactive
            if user_id in self._user_activity:
                last_activity = self._user_activity[user_id]
                if datetime.now(timezone.utc) - last_activity >= timedelta(minutes=delay_minutes):
                    await self.send_feedback_prompt(service_url, conversation_id)
                    if on_card_sent:
                        on_card_sent(conversation_id, "feedback_card")
        except asyncio.CancelledError:
            logger.debug(f"Feedback task cancelled for user {user_id}")
        finally:
            self._pending_feedback.pop(user_id, None)

    async def send_feedback_prompt(self, service_url: str, conversation_id: str):
        """Send feedback prompt card."""
        try:
            card = create_feedback_card()
            activity_id = await self.adapter.send_card(service_url, conversation_id, card)
            if activity_id:
                logger.info(f"Sent feedback card to conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to send feedback card: {e}")

    def cancel_pending_feedback(self, user_id: str):
        """Cancel pending feedback for a user."""
        if user_id in self._pending_feedback:
            self._pending_feedback[user_id].cancel()
            del self._pending_feedback[user_id]
            self._metrics["tasks_cancelled"] += 1

    def clear_user_session(self, user_id: str):
        """Clear user session data."""
        self._user_activity.pop(user_id, None)
        self._feedback_sent.pop(user_id, None)
        self.cancel_pending_feedback(user_id)

    def has_received_feedback(self, user_id: str) -> bool:
        """Check if user has received feedback."""
        return user_id in self._feedback_sent

    def is_feedback_pending(self, user_id: str) -> bool:
        """Check if feedback is pending for user."""
        return user_id in self._pending_feedback

    async def record_feedback(self, user_id: str, rating: int, comment: str = "", **kwargs) -> Rating | None:
        """Record feedback in database."""
        try:
            async with get_db_session_context() as session:
                rating_obj = Rating(
                    bot_name=get_bot_name(),
                    env="production",
                    channel="teams",
                    user_id=user_id,
                    session_id=kwargs.get('session_id', ''),
                    rate=rating,
                    feedback_comment=comment
                )
                session.add(rating_obj)
                await session.commit()
                
                # Mark feedback as sent
                self._feedback_sent[user_id] = datetime.now(timezone.utc)
                
                return rating_obj
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return None

    async def record_message_reply_feedback(self, message_id: int, feedback: str = "", feedback_comment: str = "") -> MessageReplyFeedback | None:
        """Record message reply feedback."""
        try:
            async with get_db_session_context() as session:
                feedback_obj = MessageReplyFeedback(
                    message_id=message_id,
                    feedback=feedback,
                    feedback_comment=feedback_comment
                )
                session.add(feedback_obj)
                await session.commit()
                return feedback_obj
        except Exception as e:
            logger.error(f"Failed to record message reply feedback: {e}")
            return None

    def _evict_lru_users(self):
        """Evict least recently used users to maintain memory bounds."""
        # Remove oldest 10% of users
        evict_count = max(1, len(self._user_activity) // 10)
        for _ in range(evict_count):
            if self._user_activity:
                user_id, _ = self._user_activity.popitem(last=False)
                self._feedback_sent.pop(user_id, None)
                self.cancel_pending_feedback(user_id)
        
        self._metrics["memory_cleanups"] += 1
        logger.info(f"Evicted {evict_count} users due to memory pressure")

    async def _cleanup_loop(self):
        """Background cleanup loop for TTL-based eviction."""
        while True:
            try:
                await asyncio.sleep(self.activity_check_interval)
                await self._cleanup_expired_items()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_expired_items(self):
        """Clean up expired items from the priority queue."""
        now = time.time()
        expired_count = 0
        
        while self._expiry_queue and self._expiry_queue[0].expiry_time <= now:
            item = heapq.heappop(self._expiry_queue)
            if item.user_id in self._user_activity:
                del self._user_activity[item.user_id]
                expired_count += 1
        
        if expired_count > 0:
            self._metrics["ttl_cleanups"] += expired_count
            logger.debug(f"Cleaned up {expired_count} expired users")

    def get_metrics(self) -> Dict[str, int]:
        """Get service metrics."""
        return {
            **self._metrics,
            "active_users": len(self._user_activity),
            "pending_tasks": len(self._pending_feedback),
            "feedback_sent_count": len(self._feedback_sent),
        }

    async def close(self):
        """Cleanup resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all pending tasks
        for task in self._pending_feedback.values():
            task.cancel()
        self._pending_feedback.clear()


# Singleton instance
_feedback_service_instance = None

def get_feedback_service() -> MemoryEfficientFeedbackService:
    global _feedback_service_instance
    if _feedback_service_instance is None:
        _feedback_service_instance = MemoryEfficientFeedbackService(
            max_users=1000,  # Adjust based on expected load
            max_memory_mb=100,
            activity_ttl_minutes=60,
            feedback_ttl_minutes=120
        )
    return _feedback_service_instance

