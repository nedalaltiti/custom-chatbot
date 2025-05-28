# hrbot/services/message_service.py
import logging
from datetime import datetime, timezone
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.session import AsyncSession
from hrbot.db.models  import Message, MessageReply

logger = logging.getLogger(__name__)

class MessageService:
    async def add_message(
        self,
        *,
        bot_name:   str,
        env:        str,
        channel:    str,
        user_id:    str,
        session_id: str,
        role:       str,                # "user" | "bot"
        text:       str,
        intent:     str | None = None,
        reply_to_id: int | None = None,
    ) -> int:                           # <- return PK, not the ORM object
        stamp = datetime.utcnow()       # naïve UTC; change if you switch column type

        async with AsyncSession() as session, session.begin():  # <-- 1 atomic tx
            try:
                msg = Message(
                    bot_name     = bot_name,
                    env          = env,
                    channel      = channel,
                    user_id      = user_id,
                    session_id   = session_id,
                    role         = role,
                    intent       = intent,
                    message_text = text,
                    timestamp    = stamp,
                )
                session.add(msg)
                await session.flush()   # msg.id is now available

                if reply_to_id and reply_to_id > 0:
                    session.add(
                        MessageReply(
                            message_id       = reply_to_id,
                            reply_message_id = msg.id,
                        )
                    )

                logger.debug("stored %s message %s", role, msg.id)
                return msg.id

            except SQLAlchemyError as exc:
                # session.begin() will automatically roll back on exception
                logger.error("DB error saving message: %s", exc)
                raise
