"""
Enhanced feedback service with smart timing and user activity tracking.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from uuid import uuid4
from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.config.settings import settings
from hrbot.infrastructure.cards import create_feedback_card
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.models import Rating
from hrbot.db.session import get_db_session_context
from hrbot.utils.bot_name import get_bot_name

logger = logging.getLogger(__name__)

class FeedbackService:
    def __init__(self):
        self.adapter = TeamsAdapter()
        self.pending_feedback = {}  # user_id: asyncio.Task - tracks scheduled feedback tasks
        self.user_activity = {}     # user_id: last_activity_time - tracks user activity
        self.feedback_sent = set()  # user_ids who already received feedback this session
        
        # Default settings
        self.default_timeout_minutes = getattr(settings.feedback, 'feedback_timeout_minutes', 10)
        self.activity_check_interval = 30  # Check user activity every 30 seconds

    def track_user_activity(self, user_id: str):
        """
        Track user activity to reset feedback timers.
        Call this whenever user sends a message.
        """
        self.user_activity[user_id] = datetime.utcnow()
        logger.debug(f"Tracked activity for user {user_id}")

    def schedule_delayed_feedback(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int = None):
        """
        Schedule feedback prompt after period of inactivity.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL  
            conversation_id: Teams conversation ID
            delay_minutes: Minutes to wait for inactivity (default from settings)
        """
        # Don't schedule if user already got feedback this session
        if user_id in self.feedback_sent:
            logger.debug(f"Skipping feedback scheduling for {user_id} - already sent this session")
            return

        # Cancel any existing scheduled feedback
        if user_id in self.pending_feedback and not self.pending_feedback[user_id].done():
            self.pending_feedback[user_id].cancel()
            logger.debug(f"Cancelled existing feedback task for user {user_id}")
            
        # Use provided delay or default
        delay = delay_minutes or self.default_timeout_minutes
        
        # Track initial activity and schedule feedback
        self.track_user_activity(user_id)
        task = asyncio.create_task(
            self._send_feedback_after_inactivity(user_id, service_url, conversation_id, delay)
        )
        self.pending_feedback[user_id] = task
        logger.info(f"Scheduled delayed feedback for user {user_id} after {delay} minutes of inactivity")

    async def _send_feedback_after_inactivity(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int):
        """
        Monitor user activity and send feedback after period of inactivity.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL
            conversation_id: Teams conversation ID 
            delay_minutes: Minutes of inactivity required
        """
        try:
            target_inactivity = timedelta(minutes=delay_minutes)
            check_interval = min(self.activity_check_interval, delay_minutes * 60 / 4)  # Check 4 times during delay period
            
            logger.debug(f"Starting inactivity monitoring for user {user_id} (target: {delay_minutes} min)")
            
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
                        else:
                            logger.warning(f"Failed to send feedback to user {user_id}")
                    else:
                        logger.debug(f"Skipping feedback for {user_id} - already sent this session")
                    
                    break
                else:
                    # User still not inactive long enough - continue monitoring
                    remaining = target_inactivity - inactive_duration
                    logger.debug(f"User {user_id} needs {remaining.total_seconds()/60:.1f} more minutes of inactivity")
                    
                    # Sleep until next check
                    await asyncio.sleep(check_interval)
                    
        except asyncio.CancelledError:
            logger.debug(f"Feedback monitoring for user {user_id} was cancelled (user became active)")
        except Exception as e:
            logger.error(f"Error in delayed feedback monitoring for user {user_id}: {str(e)}")

    async def schedule_feedback(self, user_id: str, service_url: str, conversation_id: str):
        """
        Legacy method - schedule feedback with default timeout.
        Kept for backward compatibility.
        """
        self.schedule_delayed_feedback(user_id, service_url, conversation_id)

    async def send_feedback_prompt(self, service_url: str, conversation_id: str):
        """
        Send feedback prompt with adaptive card.
        
        Args:
            service_url: Teams service URL
            conversation_id: Teams conversation ID
            
        Returns:
            Activity ID of the sent card, or None if failed
        """
        try:
            # Create the feedback card
            feedback_card = create_feedback_card()
            
            # Send the card
            activity_id = await self.adapter.send_card(service_url, conversation_id, feedback_card)
            
            if activity_id:
                logger.info(f"Successfully sent feedback card to conversation {conversation_id}")
            else:
                logger.warning(f"Failed to send feedback card to conversation {conversation_id}")
                
            return activity_id
            
        except Exception as e:
            logger.error(f"Error sending feedback prompt: {str(e)}")
            return None

    def cancel_pending_feedback(self, user_id: str):
        """
        Cancel any pending feedback task for a user.
        
        Args:
            user_id: User identifier
        """
        if user_id in self.pending_feedback:
            task = self.pending_feedback[user_id]
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled pending feedback task for user {user_id}")
            del self.pending_feedback[user_id]

    def clear_user_session(self, user_id: str):
        """
        Clear all user session data including activity tracking and feedback status.
        Call this when user session ends or when feedback is submitted.
        
        Args:
            user_id: User identifier
        """
        # Cancel pending feedback
        self.cancel_pending_feedback(user_id)
        
        # Clear activity tracking
        self.user_activity.pop(user_id, None)
        
        # Clear feedback sent status
        self.feedback_sent.discard(user_id)
        
        logger.debug(f"Cleared session data for user {user_id}")

    async def record_feedback(
        self,
        user_id: str,
        rating: int,
        comment: str = "",
        session_id: str | None = None,
        bot_name: str = None,
        env: str = "development",
        channel: str = "teams",
        conversation_id: str | None = None,
        user_name: str | None = None,
        job_title: str | None = None,
        session_duration: int | None = None,
        message_count: int | None = None,
    ) -> Rating | None:
        """
        Record user feedback with enhanced context.
        
        Args:
            user_id: User identifier
            rating: Numeric rating (1-5)
            comment: Optional feedback text
            session_id: Optional session ID
            bot_name: Optional bot name
            env: Optional environment
            channel: Optional channel
            conversation_id: Optional conversation ID
            user_name: Optional user name
            job_title: Optional job title
            session_duration: Optional session duration in seconds
            message_count: Optional number of messages in session
        """
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with get_db_session_context() as session:
                # Use app-aware bot name if not provided
                if bot_name is None:
                    bot_name = get_bot_name()
                    
                row = Rating(
                    bot_name        = bot_name,
                    env             = env,
                    channel         = channel,
                    user_id         = user_id,
                    session_id      = session_id or str(uuid4()),
                    rate            = rating,
                    feedback_comment= comment,
                    timestamp       = utc_naive,
                )
                session.add(row)
                # Context manager automatically commits
                
                # Clear all session data for this user since feedback was submitted
                self.clear_user_session(user_id)
                     
                logger.info("Recorded feedback from user %s: %s★ '%s'", user_id, rating, comment[:50] if comment else "")
                return row
                
        except SQLAlchemyError as exc:
            logger.error("DB error saving feedback: %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error saving feedback: %s", exc)
            return None
        
    def is_feedback_pending(self, user_id: str) -> bool:
        """
        Check if feedback is pending for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            bool: True if feedback is scheduled and not yet sent
        """
        return (user_id in self.pending_feedback and 
                not self.pending_feedback[user_id].done() and 
                not self.pending_feedback[user_id].cancelled())

    def has_received_feedback(self, user_id: str) -> bool:
        """
        Check if user has already received feedback this session.
        
        Args:
            user_id: User identifier
            
        Returns:
            bool: True if user already received feedback
        """
        return user_id in self.feedback_sent

    def get_user_activity_summary(self) -> dict:
        """
        Get summary of user activity for debugging/monitoring.
        
        Returns:
            dict: Summary of active users and pending feedback
        """
        now = datetime.utcnow()
        return {
            "active_users": len(self.user_activity),
            "pending_feedback_tasks": len([t for t in self.pending_feedback.values() if not t.done()]),
            "users_with_feedback": len(self.feedback_sent),
            "recent_activity": {
                user_id: (now - activity_time).total_seconds() / 60  # minutes ago
                for user_id, activity_time in self.user_activity.items()
                if (now - activity_time).total_seconds() < 3600  # last hour only
            }
        }