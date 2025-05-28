"""
This module contains the feedback service.
"""

import asyncio
from datetime import datetime, timezone
import logging
from uuid import uuid4
from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.config.settings import settings
from hrbot.infrastructure.cards import create_feedback_card
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.models import Rating
from hrbot.db.session import AsyncSession


logger = logging.getLogger(__name__)

class FeedbackService:
    def __init__(self):
        self.adapter = TeamsAdapter()
        self.pending_feedback = {}  # user_id: asyncio.Task
        self.timeout_minutes = settings.feedback.feedback_timeout_minutes
        self.session_timeouts = {}  # user_id: last_activity_time

    async def schedule_feedback(self, user_id, service_url, conversation_id):
        """
        Schedule feedback prompt after timeout.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL
            conversation_id: Teams conversation ID
        """
        # Cancel any existing scheduled feedback
        if user_id in self.pending_feedback and not self.pending_feedback[user_id].done():
            self.pending_feedback[user_id].cancel()
            
        # Schedule feedback prompt after timeout
        task = asyncio.create_task(self._send_feedback_after_timeout(user_id, service_url, conversation_id))
        self.pending_feedback[user_id] = task
        logger.info(f"Scheduled feedback for user {user_id} in {self.timeout_minutes} minutes")

    async def _send_feedback_after_timeout(self, user_id, service_url, conversation_id):
        """
        Wait for timeout then send feedback prompt if user is still active.
        
        Args:
            user_id: User identifier
            service_url: Teams service URL
            conversation_id: Teams conversation ID
        """
        try:
            # Wait for the specified timeout
            await asyncio.sleep(self.timeout_minutes * 60)
            
            # Send the feedback prompt
            activity_id = await self.send_feedback_prompt(service_url, conversation_id)
            logger.info(f"Sent feedback prompt to user {user_id} after {self.timeout_minutes} minutes")
            return activity_id
        except asyncio.CancelledError:
            logger.debug(f"Feedback prompt for user {user_id} was cancelled")
        except Exception as e:
            logger.error(f"Error in scheduled feedback: {str(e)}")

    async def send_feedback_prompt(self, service_url, conversation_id):
        """
        Send feedback prompt with adaptive card.
        
        Args:
            service_url: Teams service URL
            conversation_id: Teams conversation ID
        """
        # Create the feedback card
        feedback_card = create_feedback_card()
        
        # Send the card
        activity_id = await self.adapter.send_card(service_url, conversation_id, feedback_card)
        return activity_id

    async def record_feedback(
        self,
        user_id: str,
        rating: int,
        comment: str = "",
        session_id: str | None = None,
        bot_name: str = "hrbot",
        env: str = "development",
        channel: str = "teams",
    ) -> Rating | None:
        """
        Record user feedback.
        
        Args:
            user_id: User identifier
            rating: Numeric rating (1-5)
            comment: Optional feedback text
            session_id: Optional session ID
            bot_name: Optional bot name
            env: Optional environment
            channel: Optional channel
        """
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with AsyncSession() as session:
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
                await session.commit()
        except SQLAlchemyError as exc:
            logger.error("DB error saving feedback: %s", exc)
            return None
        
        # Cancel any pending feedback task
        if user_id in self.pending_feedback and not self.pending_feedback[user_id].done():
             self.pending_feedback[user_id].cancel()
             del self.pending_feedback[user_id]
             
        logger.info("Recorded feedback from user %s: %s★", user_id, rating)
        return row
        
    def is_feedback_pending(self, user_id):
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