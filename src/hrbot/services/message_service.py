# hrbot/services/message_service.py
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.session import get_db_session_context
from hrbot.db.models import Message, MessageReply
from hrbot.config.settings import settings

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self):
        """Initialize message service with optional database write disable."""
        # Database writes are enabled by default
        self.db_writes_enabled = True
        
        # Check for environment variable override
        import os
        if os.environ.get("DISABLE_DB_WRITES", "").lower() in ("true", "1", "yes"):
            self.db_writes_enabled = False
            logger.info("Database writes disabled via DISABLE_DB_WRITES environment variable")
            
    async def add_message(
        self,
        *,
        bot_name: str,
        env: str,
        channel: str,
        user_id: str,
        session_id: str,
        role: str,                # "user" | "bot"
        text: str,
        intent: str | None = None,
        reply_to_id: int | None = None,
    ) -> int:                           
        """
        Add a single message with optimized performance and proper validation.
        
        Returns the message ID immediately after insertion.
        """
        # Check if database writes are disabled
        if not self.db_writes_enabled:
            logger.debug(f"Database write skipped (disabled): {role} message from {user_id}")
            return 0  # Return dummy ID
            
        stamp = datetime.utcnow()

        try:
            async with get_db_session_context() as session:
                # Validate reply_to_id exists if provided - handle string/int conversion
                if reply_to_id:
                    try:
                        reply_to_id = int(reply_to_id)
                        if reply_to_id > 0:
                            from sqlalchemy import select
                            check_stmt = select(Message.id).where(Message.id == reply_to_id)
                            result = await session.execute(check_stmt)
                            if not result.scalar():
                                logger.warning(f"Invalid reply_to_id {reply_to_id} - message doesn't exist")
                                reply_to_id = None  # Don't create invalid relationship
                        else:
                            reply_to_id = None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid reply_to_id format: {reply_to_id}")
                        reply_to_id = None

                msg = Message(
                    bot_name=bot_name,
                    env=env,
                    channel=channel,
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    intent=intent,
                    message_text=text,
                    timestamp=stamp,
                )
                session.add(msg)
                
                # Flush to get the ID
                await session.flush()
                msg_id = msg.id

                # Add reply relationship only if reply_to_id is valid
                if reply_to_id and reply_to_id > 0:
                    session.add(
                        MessageReply(
                            message_id=reply_to_id,
                            reply_message_id=msg_id,
                        )
                    )

                logger.debug("Stored %s message %s", role, msg_id)
                return msg_id

        except SQLAlchemyError as exc:
            logger.error("DB error saving message: %s", exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error saving message: %s", exc)
            raise

    async def get_recent_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages for a user session efficiently.
        
        Optimized query that only fetches the essential fields.
        """
        try:
            async with get_db_session_context() as session:
                from sqlalchemy import select, desc
                
                # Optimized query - only select needed fields
                stmt = (
                    select(Message.role, Message.message_text, Message.timestamp, Message.intent)
                    .where(Message.user_id == user_id)
                    .where(Message.session_id == session_id)
                    .order_by(desc(Message.timestamp))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                messages = []
                
                for row in result:
                    messages.append({
                        "role": row.role,
                        "text": row.message_text,
                        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                        "intent": row.intent,
                    })
                
                # Return in chronological order (oldest first)
                return list(reversed(messages))

        except SQLAlchemyError as exc:
            logger.error("DB error getting recent messages: %s", exc)
            return []
        except Exception as exc:
            logger.error("Unexpected error getting recent messages: %s", exc)
            return []

# Singleton instance for dependency injection
message_service = MessageService()
