# # hrbot/services/storage_service.py
# """
# Production storage service for conversations, feedback, and analytics.
# """

# import logging
# from typing import List, Dict, Optional, Any
# from datetime import datetime, timezone, timedelta
# from sqlalchemy.orm import Session
# from sqlalchemy import func, and_, or_, desc
# from hrbot.infrastructure.database.models import (
#     User, Conversation, ConversationMessage, Feedback, SystemMetrics, db_manager
# )
# import json

# logger = logging.getLogger(__name__)

# class ProductionStorageService:
#     """Production-ready storage service with analytics capabilities."""
    
#     def __init__(self):
#         self.db_manager = db_manager
        
#     def get_session(self) -> Session:
#         """Get a database session."""
#         return next(self.db_manager.get_session())
    
#     # User Management
#     async def upsert_user(self, user_id: str, aad_object_id: str = None, 
#                          display_name: str = None, job_title: str = None, 
#                          email: str = None) -> User:
#         """Create or update user information."""
#         session = self.get_session()
#         try:
#             user = session.query(User).filter(User.user_id == user_id).first()
            
#             if user:
#                 # Update existing user
#                 user.last_seen = datetime.now(timezone.utc)
#                 if display_name:
#                     user.display_name = display_name
#                 if job_title:
#                     user.job_title = job_title
#                 if email:
#                     user.email = email
#                 if aad_object_id:
#                     user.aad_object_id = aad_object_id
#             else:
#                 # Create new user
#                 user = User(
#                     user_id=user_id,
#                     aad_object_id=aad_object_id,
#                     display_name=display_name,
#                     job_title=job_title,
#                     email=email,
#                     first_seen=datetime.now(timezone.utc),
#                     last_seen=datetime.now(timezone.utc)
#                 )
#                 session.add(user)
            
#             session.commit()
#             return user
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error upserting user {user_id}: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     # Conversation Management
#     async def start_conversation(self, user_id: str, conversation_id: str = None,
#                                user_name: str = None, job_title: str = None,
#                                service_url: str = None) -> Conversation:
#         """Start a new conversation session."""
#         session = self.get_session()
#         try:
#             # Ensure user exists
#             await self.upsert_user(user_id, display_name=user_name, job_title=job_title)
            
#             conversation = Conversation(
#                 user_id=user_id,
#                 conversation_id=conversation_id,
#                 user_name=user_name,
#                 job_title=job_title,
#                 service_url=service_url,
#                 started_at=datetime.now(timezone.utc),
#                 status="active"
#             )
            
#             session.add(conversation)
#             session.commit()
            
#             logger.info(f"Started conversation {conversation.id} for user {user_id}")
#             return conversation
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error starting conversation for user {user_id}: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     async def add_message(self, conversation_id: str, user_id: str, role: str, 
#                          content: str, intent: str = None, response_time_ms: int = None,
#                          rag_used: bool = False, sources_count: int = 0) -> ConversationMessage:
#         """Add a message to a conversation."""
#         session = self.get_session()
#         try:
#             # Get current message count for ordering
#             message_count = session.query(func.count(ConversationMessage.id)).filter(
#                 ConversationMessage.conversation_id == conversation_id
#             ).scalar() or 0
            
#             message = ConversationMessage(
#                 conversation_id=conversation_id,
#                 user_id=user_id,
#                 role=role,
#                 content=content,
#                 message_order=message_count + 1,
#                 intent=intent,
#                 response_time_ms=response_time_ms,
#                 rag_used=rag_used,
#                 sources_count=sources_count
#             )
            
#             session.add(message)
            
#             # Update conversation stats
#             conversation = session.query(Conversation).filter(
#                 Conversation.id == conversation_id
#             ).first()
#             if conversation:
#                 conversation.message_count += 1
#                 if rag_used:
#                     conversation.rag_queries += 1
            
#             session.commit()
#             return message
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error adding message to conversation {conversation_id}: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     async def end_conversation(self, conversation_id: str, status: str = "completed") -> bool:
#         """End a conversation and calculate duration."""
#         session = self.get_session()
#         try:
#             conversation = session.query(Conversation).filter(
#                 Conversation.id == conversation_id
#             ).first()
            
#             if conversation:
#                 end_time = datetime.now(timezone.utc)
#                 conversation.ended_at = end_time
#                 conversation.status = status
                
#                 # Calculate duration
#                 if conversation.started_at:
#                     duration = end_time - conversation.started_at
#                     conversation.duration_seconds = int(duration.total_seconds())
                
#                 # Update user stats
#                 user = session.query(User).filter(User.user_id == conversation.user_id).first()
#                 if user:
#                     user.total_conversations += 1
#                     user.total_messages += conversation.message_count
                
#                 session.commit()
#                 logger.info(f"Ended conversation {conversation_id} with status {status}")
#                 return True
            
#             return False
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error ending conversation {conversation_id}: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     # Feedback Management
#     async def save_feedback(self, user_id: str, rating: int, comment: str = "",
#                           conversation_id: str = None, user_name: str = None,
#                           job_title: str = None, session_duration: int = None,
#                           message_count: int = None, feedback_type: str = "session") -> Feedback:
#         """Save user feedback with detailed context."""
#         session = self.get_session()
#         try:
#             feedback = Feedback(
#                 user_id=user_id,
#                 conversation_id=conversation_id,
#                 rating=rating,
#                 comment=comment,
#                 user_name=user_name,
#                 job_title=job_title,
#                 session_duration=session_duration,
#                 message_count=message_count,
#                 feedback_type=feedback_type
#             )
            
#             session.add(feedback)
            
#             # Update conversation if provided
#             if conversation_id:
#                 conversation = session.query(Conversation).filter(
#                     Conversation.id == conversation_id
#                 ).first()
#                 if conversation:
#                     conversation.feedback_provided = True
            
#             session.commit()
#             logger.info(f"Saved feedback from user {user_id}: {rating}/5")
#             return feedback
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error saving feedback from user {user_id}: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     # Analytics and Dashboard Methods
#     async def get_dashboard_stats(self, days: int = 30) -> Dict[str, Any]:
#         """Get comprehensive dashboard statistics."""
#         session = self.get_session()
#         try:
#             end_date = datetime.now(timezone.utc)
#             start_date = end_date - timedelta(days=days)
            
#             # Basic metrics
#             total_users = session.query(func.count(User.id)).scalar() or 0
#             active_users = session.query(func.count(User.id)).filter(
#                 User.last_seen >= start_date
#             ).scalar() or 0
            
#             total_conversations = session.query(func.count(Conversation.id)).filter(
#                 Conversation.started_at >= start_date
#             ).scalar() or 0
            
#             completed_conversations = session.query(func.count(Conversation.id)).filter(
#                 and_(Conversation.started_at >= start_date, Conversation.status == "completed")
#             ).scalar() or 0
            
#             total_messages = session.query(func.count(ConversationMessage.id)).filter(
#                 ConversationMessage.created_at >= start_date
#             ).scalar() or 0
            
#             # Feedback metrics
#             feedback_stats = await self.get_feedback_stats(days)
            
#             # Conversation metrics
#             avg_duration = session.query(func.avg(Conversation.duration_seconds)).filter(
#                 and_(Conversation.started_at >= start_date, Conversation.duration_seconds.isnot(None))
#             ).scalar() or 0
            
#             avg_messages_per_conversation = session.query(func.avg(Conversation.message_count)).filter(
#                 Conversation.started_at >= start_date
#             ).scalar() or 0
            
#             # RAG usage
#             rag_queries = session.query(func.sum(Conversation.rag_queries)).filter(
#                 Conversation.started_at >= start_date
#             ).scalar() or 0
            
#             # Top job titles
#             top_job_titles = session.query(
#                 User.job_title, func.count(User.id).label('count')
#             ).filter(
#                 and_(User.job_title.isnot(None), User.last_seen >= start_date)
#             ).group_by(User.job_title).order_by(desc('count')).limit(10).all()
            
#             return {
#                 "period_days": days,
#                 "user_metrics": {
#                     "total_users": total_users,
#                     "active_users": active_users,
#                     "new_users": await self._get_new_users_count(days)
#                 },
#                 "conversation_metrics": {
#                     "total_conversations": total_conversations,
#                     "completed_conversations": completed_conversations,  
#                     "completion_rate": (completed_conversations / total_conversations * 100) if total_conversations > 0 else 0,
#                     "avg_duration_seconds": int(avg_duration),
#                     "avg_messages_per_conversation": round(avg_messages_per_conversation, 1),
#                     "total_messages": total_messages
#                 },
#                 "knowledge_metrics": {
#                     "rag_queries": rag_queries,
#                     "rag_usage_rate": (rag_queries / total_conversations * 100) if total_conversations > 0 else 0
#                 },
#                 "feedback_metrics": feedback_stats,
#                 "top_job_titles": [{"job_title": jt, "count": count} for jt, count in top_job_titles],
#                 "daily_activity": await self._get_daily_activity(days)
#             }
            
#         except Exception as e:
#             logger.error(f"Error getting dashboard stats: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     async def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
#         """Get detailed feedback statistics."""
#         session = self.get_session()
#         try:
#             end_date = datetime.now(timezone.utc)
#             start_date = end_date - timedelta(days=days)
            
#             # Basic feedback metrics
#             total_feedback = session.query(func.count(Feedback.id)).filter(
#                 Feedback.created_at >= start_date
#             ).scalar() or 0
            
#             avg_rating = session.query(func.avg(Feedback.rating)).filter(
#                 Feedback.created_at >= start_date
#             ).scalar() or 0
            
#             # Rating distribution
#             rating_distribution = {}
#             for rating in range(1, 6):
#                 count = session.query(func.count(Feedback.id)).filter(
#                     and_(Feedback.created_at >= start_date, Feedback.rating == rating)
#                 ).scalar() or 0
#                 rating_distribution[rating] = count
            
#             # Feedback by job title
#             feedback_by_job = session.query(
#                 Feedback.job_title, 
#                 func.avg(Feedback.rating).label('avg_rating'),
#                 func.count(Feedback.id).label('count')
#             ).filter(
#                 and_(Feedback.created_at >= start_date, Feedback.job_title.isnot(None))
#             ).group_by(Feedback.job_title).order_by(desc('count')).limit(10).all()
            
#             return {
#                 "total_feedback": total_feedback,
#                 "average_rating": round(avg_rating, 2),
#                 "rating_distribution": rating_distribution,
#                 "feedback_by_job_title": [
#                     {"job_title": jt, "avg_rating": round(rating, 2), "count": count} 
#                     for jt, rating, count in feedback_by_job
#                 ]
#             }
            
#         except Exception as e:
#             logger.error(f"Error getting feedback stats: {str(e)}")
#             raise
#         finally:
#             session.close()
    
#     async def _get_new_users_count(self, days: int) -> int:
#         """Get count of new users in the specified period."""
#         session = self.get_session()
#         try:
#             end_date = datetime.now(timezone.utc)
#             start_date = end_date - timedelta(days=days)
            
#             return session.query(func.count(User.id)).filter(
#                 User.first_seen >= start_date
#             ).scalar() or 0
#         finally:
#             session.close()
    
#     async def _get_daily_activity(self, days: int) -> List[Dict[str, Any]]:
#         """Get daily activity metrics."""
#         session = self.get_session()
#         try:
#             end_date = datetime.now(timezone.utc).date()
#             start_date = end_date - timedelta(days=days)
            
#             # Daily conversation counts
#             daily_conversations = session.query(
#                 func.date(Conversation.started_at).label('date'),
#                 func.count(Conversation.id).label('conversations')
#             ).filter(
#                 Conversation.started_at >= start_date
#             ).group_by(func.date(Conversation.started_at)).all()
            
#             # Daily feedback counts
#             daily_feedback = session.query(
#                 func.date(Feedback.created_at).label('date'),
#                 func.count(Feedback.id).label('feedback_count'),
#                 func.avg(Feedback.rating).label('avg_rating')
#             ).filter(
#                 Feedback.created_at >= start_date
#             ).group_by(func.date(Feedback.created_at)).all()
            
#             # Combine data
#             daily_data = {}
#             for date, conversations in daily_conversations:
#                 daily_data[str(date)] = {"conversations": conversations, "feedback_count": 0, "avg_rating": 0}
            
#             for date, feedback_count, avg_rating in daily_feedback:
#                 if str(date) in daily_data:
#                     daily_data[str(date)].update({
#                         "feedback_count": feedback_count,
#                         "avg_rating": round(avg_rating or 0, 2)
#                     })
#                 else:
#                     daily_data[str(date)] = {
#                         "conversations": 0,
#                         "feedback_count": feedback_count,
#                         "avg_rating": round(avg_rating or 0, 2)
#                     }
            
#             return [{"date": date, **data} for date, data in sorted(daily_data.items())]
            
#         finally:
#             session.close()
    
#     # Data Maintenance Methods
#     async def cleanup_old_data(self, days_to_keep: int = 365) -> Dict[str, int]:
#         """Clean up old data based on retention policy."""
#         session = self.get_session()
#         try:
#             cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
#             # Delete old conversations and related messages
#             old_conversations = session.query(Conversation).filter(
#                 Conversation.started_at < cutoff_date
#             ).all()
            
#             conversations_deleted = len(old_conversations)
#             messages_deleted = 0
            
#             for conversation in old_conversations:
#                 messages_deleted += len(conversation.messages)
#                 session.delete(conversation)  # Cascade will delete messages
            
#             # Delete old feedback (keep longer than conversations)
#             feedback_cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep * 2)
#             old_feedback = session.query(Feedback).filter(
#                 Feedback.created_at < feedback_cutoff
#             ).all()
            
#             feedback_deleted = len(old_feedback)
#             for feedback in old_feedback:
#                 session.delete(feedback)
            
#             session.commit()
            
#             logger.info(f"Cleaned up {conversations_deleted} conversations, "
#                        f"{messages_deleted} messages, {feedback_deleted} feedback records")
            
#             return {
#                 "conversations_deleted": conversations_deleted,
#                 "messages_deleted": messages_deleted,
#                 "feedback_deleted": feedback_deleted
#             }
            
#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error during data cleanup: {str(e)}")
#             raise
#         finally:
#             session.close()

# # Global storage service instance
# storage_service = ProductionStorageService()