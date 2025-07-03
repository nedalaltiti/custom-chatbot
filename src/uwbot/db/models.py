from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String,
    Text, TIMESTAMP, ForeignKey, MetaData
)
from sqlalchemy.orm import registry, relationship

metadata = MetaData(schema="ai_chatbot")
mapper   = registry(metadata=metadata)

# Create a separate metadata for the public schema
public_metadata = MetaData(schema="public")
public_mapper = registry(metadata=public_metadata)

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

@public_mapper.mapped
class Contact:
    __tablename__ = "contacts"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    firstname = Column(String(255), nullable=False)
    lastname = Column(String(255), nullable=True)
    acctid = Column(String(255), nullable=True)
    del_ = Column(String(1), nullable=True)  # Using del_ to avoid Python keyword conflict
    iscoapp = Column(String(1), nullable=True)
    c_type = Column(String(50), nullable=True)
    leadstatus = Column(String(50), nullable=True)

@public_mapper.mapped
class ContactUserField:
    __tablename__ = "contacts_userfields"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    contact_id = Column(BigInteger, ForeignKey("public.contacts.id"), nullable=False)
    custom_id = Column(BigInteger, nullable=False)
    f_string = Column(Text, nullable=True)
    f_text = Column(Text, nullable=True)
    f_int = Column(BigInteger, nullable=True)
    f_float = Column(BigInteger, nullable=True)  # Using BigInteger for compatibility
    f_date = Column(TIMESTAMP, nullable=True)
    f_datetime = Column(TIMESTAMP, nullable=True)
    f_bool = Column(String(1), nullable=True)