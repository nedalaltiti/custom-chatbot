from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String,
    Text, TIMESTAMP, ForeignKey, MetaData
)
from sqlalchemy.orm import registry, relationship

metadata = MetaData(schema="ai_chatbot")
mapper   = registry(metadata=metadata)

@mapper.mapped
class Message:
    __tablename__ = "message"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    bot_name   = Column(String(128), nullable=False)
    env        = Column(String(32),  nullable=False)
    channel    = Column(String(32),  nullable=False)
    user_id    = Column(String(128), nullable=False)
    session_id = Column(String(255), nullable=False)
    role       = Column(String(16),  nullable=False)   # user | bot
    intent     = Column(String(128))
    message_text = Column(Text, nullable=False)
    timestamp    = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    replies   = relationship(
        "Message",
        secondary="ai_chatbot.message_reply",
        primaryjoin="Message.id==MessageReply.message_id",
        secondaryjoin="Message.id==MessageReply.reply_message_id",
        backref="reply_to"
    )

@mapper.mapped
class Rating:
    __tablename__ = "rating"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    bot_name   = Column(String(128), nullable=False)
    env        = Column(String(32),  nullable=False)
    channel    = Column(String(32),  nullable=False)
    user_id    = Column(String(128), nullable=False)
    session_id = Column(String(255), nullable=False)
    rate       = Column(SmallInteger)
    feedback_comment = Column(Text)
    timestamp        = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

@mapper.mapped
class MessageReply:
    __tablename__ = "message_reply"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id      = Column(BigInteger, ForeignKey("ai_chatbot.message.id", ondelete="CASCADE"), nullable=False)
    reply_message_id= Column(BigInteger, ForeignKey("ai_chatbot.message.id", ondelete="CASCADE"), nullable=False)
