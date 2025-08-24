from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String,
    Text, TIMESTAMP, ForeignKey, MetaData, Boolean, Float
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

@mapper.mapped
class MessageReplyFeedback:
    __tablename__ = "message_reply_feedback"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, ForeignKey("ai_chatbot.message_reply.id", ondelete="CASCADE"), nullable=False)
    feedback        = Column(String(8), nullable=False) # like | dislike
    feedback_comment = Column(Text)
    timestamp        = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

@mapper.mapped
class UserSession:
    """Persistent user session state for scalable deployments."""
    __tablename__ = "user_session"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, unique=True, index=True)
    session_id = Column(String(255), nullable=False)
    bot_name = Column(String(128), nullable=False)
    env = Column(String(32), nullable=False)
    
    # Session state flags
    awaiting_feedback = Column(Boolean, default=False, nullable=False)
    feedback_shown = Column(Boolean, default=False, nullable=False)
    greeting_shown = Column(Boolean, default=False, nullable=False)
    session_started = Column(Boolean, default=True, nullable=False)
    is_first_time_user = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_activity = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_bot_response_time = Column(TIMESTAMP, nullable=True)
    
    # Additional state data (JSON-like data for extensibility)
    state_data = Column(Text, nullable=True)  # JSON string for additional state

@mapper.mapped 
class UserActivity:
    """Track user activity for feedback timing and analytics."""
    __tablename__ = "user_activity"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    bot_name = Column(String(128), nullable=False)
    env = Column(String(32), nullable=False)
    
    activity_type = Column(String(32), nullable=False)  # message, card_action, feedback
    timestamp = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    
    # Optional state data
    state_data = Column(Text, nullable=True)  # JSON string for activity details
