"""
Background Task Service for Non-Critical Operations

This service handles operations that can be performed asynchronously without
blocking the main request/response cycle, improving user experience and system performance.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from uuid import uuid4
from contextlib import asynccontextmanager

from uwbot.services.message_service import MessageService

from uwbot.config.settings import settings
from uwbot.utils.bot_name import get_bot_name

logger = logging.getLogger(__name__)


class BackgroundTaskService:
    """Service for managing async background tasks."""
    
    def __init__(self):
        self.message_service = MessageService()

        self._running_tasks = set()
        logger.info("BackgroundTaskService initialized")
    
    def _track_task(self, task: asyncio.Task) -> None:
        """Track a background task and clean up when done."""
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
    
    def schedule_message_persistence(
        self,
        bot_name: str,
        user_id: str,
        session_id: str,
        role: str,
        text: str,
        intent: str = None,
        reply_to_id: int = None,
        channel: str = "teams"
    ) -> asyncio.Task:
        """
        Schedule message persistence as a background task.
        
        Returns:
            The background task for optional awaiting
        """
        task = asyncio.create_task(
            self._persist_message(
                bot_name=bot_name,
                user_id=user_id,
                session_id=session_id,
                role=role,
                text=text,
                intent=intent,
                reply_to_id=reply_to_id,
                channel=channel
            )
        )
        self._track_task(task)
        return task
    
    async def _persist_message(
        self,
        bot_name: str,
        user_id: str,
        session_id: str,
        role: str,
        text: str,
        intent: str = None,
        reply_to_id: int = None,
        channel: str = "teams"
    ) -> Optional[int]:
        """Internal method to persist message to database."""
        try:
            message_id = await self.message_service.add_message(
                bot_name=bot_name,
                env=settings.environment,
                channel=channel,
                user_id=user_id,
                session_id=session_id,
                role=role,
                text=text,
                intent=intent,
                reply_to_id=reply_to_id,
            )
            logger.debug(f"Background task: persisted {role} message {message_id}")
            return message_id
        except Exception as e:
            logger.warning(f"Background message persistence failed: {e}")
            return None
    
    # Feedback tracking functionality has been removed
    
    def schedule_analytics_logging(
        self,
        event_type: str,
        user_id: str,
        session_id: str,
        metadata: Dict[str, Any] = None
    ) -> asyncio.Task:
        """
        Schedule analytics/metrics logging as a background task.
        
        Args:
            event_type: Type of event (e.g., 'validation_request', 'error_occurred')
            user_id: User identifier
            session_id: Session identifier
            metadata: Additional event metadata
        """
        task = asyncio.create_task(
            self._log_analytics(
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {}
            )
        )
        self._track_task(task)
        return task
    
    async def _log_analytics(
        self,
        event_type: str,
        user_id: str,
        session_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Internal method to log analytics data."""
        try:
            # In a production system, this would send to analytics service
            # For now, we'll just log structured data
            analytics_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.environment,
                "bot_name": get_bot_name(),
                **metadata
            }
            
            # Log as structured JSON for easy parsing by log aggregation systems
            logger.info(f"ANALYTICS: {analytics_data}")
            
        except Exception as e:
            logger.warning(f"Background analytics logging failed: {e}")
    
    def schedule_cleanup_task(
        self,
        cleanup_func: Callable,
        delay_seconds: int = 60
    ) -> asyncio.Task:
        """
        Schedule a generic cleanup task.
        
        Args:
            cleanup_func: Async function to execute for cleanup
            delay_seconds: Seconds to wait before executing cleanup
        """
        task = asyncio.create_task(
            self._execute_cleanup(cleanup_func, delay_seconds)
        )
        self._track_task(task)
        return task
    
    async def _execute_cleanup(
        self,
        cleanup_func: Callable,
        delay_seconds: int
    ) -> None:
        """Internal method to execute cleanup tasks."""
        try:
            await asyncio.sleep(delay_seconds)
            if asyncio.iscoroutinefunction(cleanup_func):
                await cleanup_func()
            else:
                cleanup_func()
            logger.debug("Background cleanup task completed")
        except Exception as e:
            logger.warning(f"Background cleanup task failed: {e}")
    
    async def wait_for_all_tasks(self, timeout: int = 30) -> None:
        """
        Wait for all background tasks to complete (useful for testing/shutdown).
        
        Args:
            timeout: Maximum seconds to wait
        """
        if not self._running_tasks:
            return
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._running_tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All background tasks completed")
        except asyncio.TimeoutError:
            logger.warning(f"Background tasks did not complete within {timeout}s")
        except Exception as e:
            logger.warning(f"Error waiting for background tasks: {e}")
    
    def get_task_count(self) -> int:
        """Get the number of currently running background tasks."""
        return len(self._running_tasks)


# Singleton instance
_background_task_service = None

def get_background_task_service() -> BackgroundTaskService:
    """Get the singleton background task service instance."""
    global _background_task_service
    if _background_task_service is None:
        _background_task_service = BackgroundTaskService()
    return _background_task_service
