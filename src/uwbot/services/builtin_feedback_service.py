# uwbot/services/builtin_feedback_service.py

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError

from uwbot.db.session import get_db_session_context
from uwbot.db.models import Rating, MessageReplyFeedback
from uwbot.utils.bot_name import get_bot_name
from uwbot.config.settings import settings

logger = logging.getLogger(__name__)


class BuiltinFeedbackService:
    """
    Minimal service to handle ONLY built-in Teams like/dislike feedback.
    Does not handle custom feedback cards - only native Teams reactions.
    """

    def __init__(self):
        """Initialize the builtin feedback service."""
        # Check if database writes are disabled
        import os
        self.db_writes_enabled = not (os.environ.get("DISABLE_DB_WRITES", "").lower() in ("true", "1", "yes"))
        
        if not self.db_writes_enabled:
            logger.info("Built-in feedback storage disabled due to DISABLE_DB_WRITES")

    async def record_builtin_feedback(
        self,
        user_id: str,
        session_id: str,
        reaction: str,  # "like" or "dislike" 
        comment: str = "",
        message_id: Optional[int] = None
    ) -> bool:
        """
        Record built-in Teams feedback (like/dislike thumbs) to database.
        
        Args:
            user_id: Teams user ID
            session_id: Session identifier
            reaction: "like" or "dislike"
            comment: Optional feedback comment text
            message_id: Optional specific message ID this feedback is for
            
        Returns:
            True if successfully recorded, False otherwise
        """
        if not self.db_writes_enabled:
            logger.debug(f"Built-in feedback storage skipped (disabled): {reaction} from {user_id}")
            return False

        try:
            # Convert reaction to rating for storage
            # like = 5 stars, dislike = 1 star, neutral = 3 stars
            rating = {
                "like": 5,
                "dislike": 1,
                "neutral": 3
            }.get(reaction.lower(), 3)

            utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            
            async with get_db_session_context() as session:
                # Store as general rating feedback
                feedback_record = Rating(
                    bot_name=get_bot_name(),
                    env=settings.environment,
                    channel="teams",
                    user_id=user_id,
                    session_id=session_id,
                    rate=rating,
                    feedback_comment=comment,
                    timestamp=utc_naive,
                )
                session.add(feedback_record)
                
                logger.info(f"✅ Recorded built-in Teams feedback: {reaction} ({rating}★) from user {user_id}")
                if comment:
                    logger.info(f"   Comment: '{comment[:100]}{'...' if len(comment) > 100 else ''}'")
                
                return True
                
        except SQLAlchemyError as exc:
            logger.error(f"Database error saving built-in feedback: {exc}")
            return False
        except Exception as exc:
            logger.error(f"Unexpected error saving built-in feedback: {exc}")
            return False

    async def record_message_reply_feedback(
        self,
        message_id: int,
        feedback: str,
        feedback_comment: str = ""
    ) -> bool:
        """
        Record feedback for a specific message reply.
        
        Args:
            message_id: Database message ID
            feedback: "like" or "dislike"
            feedback_comment: Optional comment text
            
        Returns:
            True if successfully recorded, False otherwise
        """
        if not self.db_writes_enabled:
            logger.debug(f"Message reply feedback storage skipped (disabled): {feedback} for message {message_id}")
            return False

        try:
            utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            
            async with get_db_session_context() as session:
                feedback_record = MessageReplyFeedback(
                    message_id=message_id,
                    feedback=feedback,
                    feedback_comment=feedback_comment,
                    timestamp=utc_naive,
                )
                session.add(feedback_record)
                
                logger.info(f"✅ Recorded message reply feedback: {feedback} for message {message_id}")
                if feedback_comment:
                    logger.info(f"   Comment: '{feedback_comment[:100]}{'...' if len(feedback_comment) > 100 else ''}'")
                
                return True
                
        except SQLAlchemyError as exc:
            logger.error(f"Database error saving message reply feedback: {exc}")
            return False
        except Exception as exc:
            logger.error(f"Unexpected error saving message reply feedback: {exc}")
            return False


# Singleton instance
builtin_feedback_service = BuiltinFeedbackService()
