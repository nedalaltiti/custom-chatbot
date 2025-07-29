"""
Enhanced feedback service with smart timing and user activity tracking.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from uuid import uuid4
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.config.settings import settings
from uwbot.infrastructure.cards import create_feedback_card
from sqlalchemy.exc import SQLAlchemyError
from uwbot.db.models import Rating, MessageReplyFeedback, MessageReply
from uwbot.db.session import get_db_session_context
from uwbot.utils.bot_name import get_bot_name

logger = logging.getLogger(__name__)

class FeedbackService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize if this is the first time
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.adapter = TeamsAdapter()
        self.pending_feedback = {}  # user_id: asyncio.Task - tracks scheduled feedback tasks
        self.user_activity = {}     # user_id: last_activity_time - tracks user activity
        self.feedback_sent = set()  # user_ids who already received feedback this session
        
        # Mapping from Teams activity ID to bot message database ID
        self.activity_to_message_id = {}  # teams_activity_id: bot_message_db_id
        
        # Default settings
        self.default_timeout_minutes = getattr(settings.feedback, 'feedback_timeout_minutes', 10)
        self.activity_check_interval = 30  # Check user activity every 30 seconds
        
        logger.info("FeedbackService singleton initialized")

    def track_user_activity(self, user_id: str):
        """
        Track user activity to reset feedback timers.
        Call this whenever user sends a message.
        """
        self.user_activity[user_id] = datetime.utcnow()
        logger.debug(f"Tracked activity for user {user_id}")

    def track_activity_to_message_mapping(self, teams_activity_id: str, bot_message_db_id: int):
        """
        Track the mapping between Teams activity ID and bot message database ID.
        
        Args:
            teams_activity_id: The Teams activity ID returned from send_message
            bot_message_db_id: The database ID of the bot message
        """
        if teams_activity_id and bot_message_db_id:
            self.activity_to_message_id[teams_activity_id] = bot_message_db_id
            logger.info(f"📋 Mapped Teams activity {teams_activity_id} to bot message DB ID {bot_message_db_id}")
            logger.info(f"📋 Current mappings count: {len(self.activity_to_message_id)}")
        else:
            logger.warning(f"📋 Failed to map activity - activity_id: {teams_activity_id}, bot_msg_id: {bot_message_db_id}")

    def get_bot_message_id_from_activity(self, teams_activity_id: str) -> int | None:
        """
        Get the bot message database ID from a Teams activity ID.
        
        Args:
            teams_activity_id: The Teams activity ID
            
        Returns:
            The bot message database ID, or None if not found
        """
        result = self.activity_to_message_id.get(teams_activity_id)
        logger.info(f"🔍 Looking up Teams activity {teams_activity_id} -> found: {result}")
        logger.info(f"🔍 Available mappings: {list(self.activity_to_message_id.keys())}")
        return result

    def schedule_delayed_feedback(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int = None, on_card_sent=None):
        """
        Schedule feedback prompt after period of inactivity.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL  
            conversation_id: Teams conversation ID
            delay_minutes: Minutes to wait for inactivity (default from settings)
            on_card_sent: Optional callback to call with (conversation_id, activity_id) when card is sent
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
            self._send_feedback_after_inactivity(user_id, service_url, conversation_id, delay, on_card_sent)
        )
        self.pending_feedback[user_id] = task
        logger.info(f"Scheduled delayed feedback for user {user_id} after {delay} minutes of inactivity")

    async def _send_feedback_after_inactivity(self, user_id: str, service_url: str, conversation_id: str, delay_minutes: int, on_card_sent=None):
        """
        Monitor user activity and send feedback after period of inactivity.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL
            conversation_id: Teams conversation ID 
            delay_minutes: Minutes of inactivity required
            on_card_sent: Optional callback to call with (conversation_id, activity_id) when card is sent
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
                            if on_card_sent:
                                on_card_sent(conversation_id, activity_id)
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
        
    async def record_builtin_teams_feedback(self, message_id: int, feedback: str = "", feedback_comment: str = "", user_id: str = None) -> MessageReplyFeedback | None:
        """
        Record built-in Teams feedback (like/dislike buttons) for a specific message.
        
        This method creates a message reply record first, then records the feedback
        against that message reply, since MessageReplyFeedback expects a message_reply.id.
        
        Args:
            message_id: ID of the bot message in the database
            feedback: feedback rating (like/dislike)
            feedback_comment: Optional comment on the message
            user_id: User ID for the feedback
            
        Returns:
            MessageReplyFeedback object or None if failed
        """
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with get_db_session_context() as session:
                # First, create a message reply record for this feedback
                # This is needed because MessageReplyFeedback references message_reply.id
                message_reply = MessageReply(
                    message_id=message_id,
                    reply_message_id=message_id,  # Self-reference for feedback
                )
                session.add(message_reply)
                await session.flush()  # Get the ID without committing
                
                # Now create the feedback record referencing the message reply
                feedback_record = MessageReplyFeedback(
                    message_id=message_reply.id,  # Reference the message_reply.id
                    feedback=feedback,
                    feedback_comment=feedback_comment,
                    timestamp=utc_naive,
                )
                session.add(feedback_record)
                
                # Context manager automatically commits both records
                
                logger.info(f"Recorded built-in Teams feedback for message {message_id}: {feedback} '{feedback_comment[:50] if feedback_comment else ''}'")
                return feedback_record
                
        except SQLAlchemyError as exc:
            logger.error(f"DB error saving built-in Teams feedback: {exc}")
            return None
        except Exception as exc:
            logger.error(f"Unexpected error saving built-in Teams feedback: {exc}")
            return None
        
