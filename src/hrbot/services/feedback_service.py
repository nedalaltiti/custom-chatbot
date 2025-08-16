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

from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.config.settings import settings
from hrbot.infrastructure.cards import create_feedback_card
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.models import Rating, MessageReplyFeedback
from hrbot.db.session import get_db_session_context
from hrbot.utils.bot_name import get_bot_name

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

        # Cleanup loop
        self._cleanup_task: Optional[asyncio.Task] = asyncio.create_task(self._cleanup_loop())

    # Compatibility properties
    @property
    def pending_feedback(self) -> Dict[str, asyncio.Task]:
        return self._pending_feedback

    # API
    def track_user_activity(self, user_id: str) -> None:
        now = datetime.utcnow()
        if user_id in self._user_activity:
            self._user_activity.move_to_end(user_id)
        self._user_activity[user_id] = now

        expiry_time = time.time() + self.activity_ttl.total_seconds()
        heapq.heappush(self._expiry_queue, ExpiringItem(expiry_time, user_id, "activity"))

        if len(self._user_activity) > self.max_users:
            self._cleanup_oldest()

        self._metrics["total_users_tracked"] += 1
        logger.debug("Tracked activity for user %s", user_id)

    def schedule_delayed_feedback(
        self,
        user_id: str,
        service_url: str,
        conversation_id: str,
        delay_minutes: int | None = None,
        on_card_sent=None,
    ) -> None:
        # Cancel existing
        if user_id in self._pending_feedback:
            old = self._pending_feedback[user_id]
            if not old.done():
                old.cancel()
                self._metrics["tasks_cancelled"] += 1

        delay = delay_minutes or self.default_timeout_minutes
        self.track_user_activity(user_id)
        task = asyncio.create_task(
            self._send_feedback_after_inactivity(user_id, service_url, conversation_id, delay, on_card_sent)
        )
        self._pending_feedback[user_id] = task

        def _cleanup(_t: asyncio.Task) -> None:
            self._pending_feedback.pop(user_id, None)
            # Mark as "sent" if a card was sent during the task
            self._feedback_sent[user_id] = datetime.utcnow()
            if len(self._feedback_sent) > self.max_users // 2:
                self._feedback_sent.popitem(last=False)

        task.add_done_callback(_cleanup)
        logger.info("Scheduled feedback for user %s", user_id)

    def cancel_pending_feedback(self, user_id: str) -> None:
        if user_id in self._pending_feedback:
            task = self._pending_feedback.pop(user_id)
            if not task.done():
                task.cancel()
                self._metrics["tasks_cancelled"] += 1

    def has_received_feedback(self, user_id: str) -> bool:
        return user_id in self._feedback_sent

    def clear_user_session(self, user_id: str) -> None:
        self.cancel_pending_feedback(user_id)
        self._user_activity.pop(user_id, None)
        self._feedback_sent.pop(user_id, None)
        logger.debug("Cleared feedback session for user %s", user_id)

    async def _send_feedback_after_inactivity(
        self,
        user_id: str,
        service_url: str,
        conversation_id: str,
        delay_minutes: int,
        on_card_sent=None,
    ) -> None:
        try:
            target_inactivity = timedelta(minutes=delay_minutes)
            check_interval = min(self.activity_check_interval, delay_minutes * 60 / 4)
            logger.debug("Monitoring inactivity for user %s (%s min)", user_id, delay_minutes)

            while True:
                # Check if user has been inactive long enough
                last_activity = self.user_activity.get(user_id, datetime.utcnow())
                inactive_duration = datetime.utcnow() - last_activity
                
                if inactive_duration >= target_inactivity:
                    # User has been inactive long enough - send feedback
                    logger.info(f"User {user_id} inactive for {inactive_duration.total_seconds()/60:.1f} minutes - sending feedback")
                    
                    # Check if user already received feedback this session
                    if user_id not in self.feedback_sent:
                        activity_id = await self.send_feedback_prompt(service_url, conversation_id)
                        if activity_id:
                            self.feedback_sent.add(user_id)
                            logger.info(f"Sent delayed feedback to user {user_id} after {delay_minutes} minutes of inactivity")
                            if on_card_sent:
                                on_card_sent(conversation_id, activity_id)
                        else:
                            logger.warning(f"Failed to send feedback to user {user_id}")
                    else:
                        logger.debug(f"Skipping feedback for {user_id} - already sent this session")
                    
                last = self._user_activity.get(user_id, datetime.utcnow())
                inactive = datetime.utcnow() - last
                if inactive >= target_inactivity:
                    if user_id not in self._feedback_sent:
                        act_id = await self.send_feedback_prompt(service_url, conversation_id)
                        if act_id and callable(on_card_sent):
                            try:
                                on_card_sent(user_id, act_id)
                            except Exception:
                                pass
                        logger.info("Sent delayed feedback to %s after %s min", user_id, delay_minutes)
                    break
                await asyncio.sleep(check_interval)
        except asyncio.CancelledError:
            logger.debug("Inactivity monitor cancelled for %s", user_id)
        except Exception as exc:
            logger.error("Inactivity monitor error for %s: %s", user_id, exc)

    async def send_feedback_prompt(self, service_url: str, conversation_id: str):
        try:
            card = create_feedback_card()
            act_id = await self.adapter.send_card(service_url, conversation_id, card)
            if act_id:
                logger.info("Feedback card sent to %s", conversation_id)
            else:
                logger.warning("Failed to send feedback card to %s", conversation_id)
            return act_id
        except Exception as exc:
            logger.error("send_feedback_prompt error: %s", exc)
            return None

    async def record_feedback(
        self,
        user_id: str,
        rating: int,
        comment: str = "",
        session_id: str | None = None,
        bot_name: str | None = None,
        env: str = "development",
        channel: str = "teams",
        conversation_id: str | None = None,
        user_name: str | None = None,
        job_title: str | None = None,
        session_duration: int | None = None,
        message_count: int | None = None,
    ) -> Optional[Rating]:
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with get_db_session_context() as session:
                if bot_name is None:
                    bot_name = get_bot_name()
                row = Rating(
                    bot_name=bot_name,
                    env=env,
                    channel=channel,
                    user_id=user_id,
                    session_id=session_id or str(uuid4()),
                    rate=rating,
                    feedback_comment=comment,
                    timestamp=utc_naive,
                )
                session.add(row)
                self.clear_user_session(user_id)
                logger.info("Recorded feedback %s: %s★ '%s'", user_id, rating, (comment[:50] if comment else ""))
                return row
        except SQLAlchemyError as exc:
            logger.error("DB error saving feedback: %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error saving feedback: %s", exc)
            return None

    def is_feedback_pending(self, user_id: str) -> bool:
        t = self._pending_feedback.get(user_id)
        return bool(t and (not t.done()) and (not t.cancelled()))

    def get_user_activity_summary(self) -> dict:
        now = datetime.utcnow()
        return {
            "active_users": len(self._user_activity),
            "pending_feedback_tasks": len([t for t in self._pending_feedback.values() if not t.done()]),
            "users_with_feedback": len(self._feedback_sent),
            "recent_activity": {
                user_id: (now - activity_time).total_seconds() / 60  # minutes ago
                for user_id, activity_time in self.user_activity.items()
                if (now - activity_time).total_seconds() < 3600  # last hour only
            }
        }
    async def record_message_reply_feedback(self, message_id: int, feedback: str = "", feedback_comment: str = "") -> MessageReplyFeedback | None:
        """
        Record feedback for a specific message reply.
        
        Args:
            message_id: ID of the message reply (can be Teams activity ID or bot message DB ID)
            feedback: feedback rating (like/dislike)
            feedback_comment: Optional comment on the reply
            
        Returns:
            MessageReplyFeedback object or None if failed
        """
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with get_db_session_context() as session:
                # Check if message_id is a Teams activity ID and convert to bot message DB ID
                bot_message_db_id = self.get_bot_message_id_from_activity(str(message_id))
                if bot_message_db_id:
                    # Use the bot message database ID instead of Teams activity ID
                    actual_message_id = bot_message_db_id
                    logger.info(f"Converted Teams activity ID {message_id} to bot message DB ID {actual_message_id}")
                else:
                    # Assume it's already a bot message database ID
                    actual_message_id = message_id
                    logger.debug(f"Using message_id {message_id} as bot message DB ID (no mapping found)")
                
                row = MessageReplyFeedback(
                    message_id = actual_message_id,
                    feedback        = feedback,
                    feedback_comment= feedback_comment,
                    timestamp       = utc_naive,
                )
                session.add(row)
                # Context manager automatically commits
                
                logger.info("Recorded reply feedback for message reply %s: %s '%s'", actual_message_id, feedback, feedback_comment if feedback_comment else "")
                return row
                
        except SQLAlchemyError as exc:
            logger.error("DB error saving reply feedback: %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error saving reply feedback: %s", exc)
            return None

    def get_metrics(self) -> dict:
        return {
            **self._metrics,
            "active_users": len(self._user_activity),
            "pending_feedback": len(self._pending_feedback),
            "feedback_sent": len(self._feedback_sent),
            "expiry_queue_size": len(self._expiry_queue),
        }

    async def shutdown(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        for task in self._pending_feedback.values():
            if not task.done():
                task.cancel()
        if self._pending_feedback:
            await asyncio.gather(*self._pending_feedback.values(), return_exceptions=True)
        try:
            await self.adapter.close()
        except Exception:
            pass
        logger.info("FeedbackService shutdown complete. Metrics: %s", self.get_metrics())

    # Cleanup internals
    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(30)
                self._cleanup_expired()
                if self._check_memory_pressure():
                    self._cleanup_oldest()
                current = len(self._user_activity)
                self._metrics["max_concurrent_users"] = max(
                    self._metrics["max_concurrent_users"], current
                )
            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception as exc:
                logger.error("Cleanup loop error: %s", exc)

    def _cleanup_expired(self) -> None:
        now_ts = time.time()
        cleaned = 0
        while self._expiry_queue and self._expiry_queue[0].expiry_time <= now_ts:
            item = heapq.heappop(self._expiry_queue)
            if item.user_id in self._user_activity:
                del self._user_activity[item.user_id]
                cleaned += 1
            if item.user_id in self._feedback_sent:
                del self._feedback_sent[item.user_id]
                cleaned += 1
        expired = [uid for uid, t in self._pending_feedback.items() if t.done()]
        for uid in expired:
            del self._pending_feedback[uid]
            self._metrics["tasks_cancelled"] += 1
            cleaned += 1
        if cleaned:
            self._metrics["ttl_cleanups"] += cleaned
            logger.debug("TTL cleanup removed %s entries", cleaned)

    def _cleanup_oldest(self) -> None:
        to_remove = max(1, len(self._user_activity) // 10)
        for _ in range(to_remove):
            if not self._user_activity:
                break
            uid, _ts = self._user_activity.popitem(last=False)
            if uid in self._pending_feedback:
                t = self._pending_feedback.pop(uid)
                if not t.done():
                    t.cancel()
                    self._metrics["tasks_cancelled"] += 1
            self._feedback_sent.pop(uid, None)
        self._metrics["memory_cleanups"] += to_remove
        logger.info("Memory pressure cleanup removed %s entries", to_remove)

    def _check_memory_pressure(self) -> bool:
        total_users = len(self._user_activity) + len(self._pending_feedback)
        return total_users > self.max_users * 0.9


# Singleton accessor
_feedback_service_instance: Optional[MemoryEfficientFeedbackService] = None


def get_feedback_service() -> MemoryEfficientFeedbackService:
    global _feedback_service_instance
    if _feedback_service_instance is None:
        _feedback_service_instance = MemoryEfficientFeedbackService(
            max_users=1000,
            max_memory_mb=100,
            activity_ttl_minutes=60,
            feedback_ttl_minutes=120,
        )
    return _feedback_service_instance