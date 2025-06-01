"""
Database utilities for maintenance, monitoring, and management.

This module provides:
1. Connection health monitoring
2. Database maintenance operations
3. Query performance utilities
4. Connection pool management
"""

import logging
import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from hrbot.db.session import AsyncSession, engine, get_db_session_context

logger = logging.getLogger(__name__)


class DatabaseMonitor:
    """Database monitoring and health check utilities."""
    
    @staticmethod
    async def test_connection(timeout: float = 5.0) -> Dict[str, Any]:
        """
        Test database connection with timeout and proper performance tracking.
        
        Args:
            timeout: Maximum time to wait for connection test
            
        Returns:
            Dictionary with connection test results
        """
        start_time = time.time()
        try:
            # Use asyncio.wait_for for proper timeout handling
            async def connection_test():
                async with get_db_session_context() as session:
                    result = await session.execute(text("SELECT 1 as test, NOW() as timestamp"))
                    row = result.fetchone()
                    return row
            
            row = await asyncio.wait_for(connection_test(), timeout=timeout)
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "response_time_seconds": round(response_time, 3),
                "test_value": row.test if row else None,
                "server_timestamp": str(row.timestamp) if row else None,
                "connection_successful": True
            }
            
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            logger.error(f"Database connection test timed out after {timeout}s")
            return {
                "status": "unhealthy",
                "response_time_seconds": round(response_time, 3),
                "error": f"Connection timeout after {timeout} seconds",
                "error_type": "TimeoutError",
                "connection_successful": False
            }
        except SQLAlchemyError as e:
            response_time = time.time() - start_time
            logger.error(f"Database connection test failed: {e}")
            return {
                "status": "unhealthy",
                "response_time_seconds": round(response_time, 3),
                "error": str(e),
                "error_type": "SQLAlchemyError",
                "connection_successful": False
            }
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Database connection test error: {e}")
            return {
                "status": "unhealthy",
                "response_time_seconds": round(response_time, 3),
                "error": str(e),
                "error_type": "UnknownError",
                "connection_successful": False
            }
    
    @staticmethod
    async def get_database_info() -> Dict[str, Any]:
        """Get general database information with concurrent queries for speed."""
        try:
            async with get_db_session_context() as session:
                # Run multiple queries concurrently for better performance
                async def get_version():
                    result = await session.execute(text("SELECT version()"))
                    return result.scalar()
                
                async def get_database_name():
                    result = await session.execute(text("SELECT current_database()"))
                    return result.scalar()
                
                async def get_current_user():
                    result = await session.execute(text("SELECT current_user"))
                    return result.scalar()
                
                async def get_active_connections():
                    result = await session.execute(text(
                        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                    ))
                    return result.scalar()
                
                # Execute all queries concurrently
                version, database_name, current_user, active_connections = await asyncio.gather(
                    get_version(),
                    get_database_name(), 
                    get_current_user(),
                    get_active_connections(),
                    return_exceptions=True
                )
                
                return {
                    "version": version if not isinstance(version, Exception) else str(version),
                    "database_name": database_name if not isinstance(database_name, Exception) else "unknown",
                    "current_user": current_user if not isinstance(current_user, Exception) else "unknown",
                    "active_connections": active_connections if not isinstance(active_connections, Exception) else 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def get_table_stats() -> Dict[str, Any]:
        """Get statistics about application tables with concurrent queries."""
        try:
            async with get_db_session_context() as session:
                # Define all queries
                async def get_message_count():
                    result = await session.execute(text("SELECT COUNT(*) FROM ai_chatbot.message"))
                    return result.scalar()
                
                async def get_rating_count():
                    result = await session.execute(text("SELECT COUNT(*) FROM ai_chatbot.rating"))
                    return result.scalar()
                
                async def get_recent_messages():
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM ai_chatbot.message WHERE timestamp > NOW() - INTERVAL '24 hours'"
                    ))
                    return result.scalar()
                
                async def get_recent_ratings():
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM ai_chatbot.rating WHERE timestamp > NOW() - INTERVAL '24 hours'"
                    ))
                    return result.scalar()
                
                # Execute all queries concurrently for better performance
                message_count, rating_count, recent_messages, recent_ratings = await asyncio.gather(
                    get_message_count(),
                    get_rating_count(),
                    get_recent_messages(),
                    get_recent_ratings(),
                    return_exceptions=True
                )
                
                return {
                    "total_messages": message_count if not isinstance(message_count, Exception) else 0,
                    "total_ratings": rating_count if not isinstance(rating_count, Exception) else 0,
                    "messages_last_24h": recent_messages if not isinstance(recent_messages, Exception) else 0,
                    "ratings_last_24h": recent_ratings if not isinstance(recent_ratings, Exception) else 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting table stats: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


class DatabaseMaintenance:
    """Database maintenance operations."""
    
    @staticmethod
    async def cleanup_old_sessions(days_old: int = 30) -> Dict[str, Any]:
        """
        Clean up old session data efficiently.
        
        Args:
            days_old: Remove sessions older than this many days
            
        Returns:
            Dictionary with cleanup results
        """
        try:
            async with get_db_session_context() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days_old)
                
                # Run deletions concurrently for better performance
                async def delete_messages():
                    result = await session.execute(text(
                        "DELETE FROM ai_chatbot.message WHERE timestamp < :cutoff"
                    ), {"cutoff": cutoff_date})
                    return result.rowcount
                
                async def delete_ratings():
                    result = await session.execute(text(
                        "DELETE FROM ai_chatbot.rating WHERE timestamp < :cutoff"
                    ), {"cutoff": cutoff_date})
                    return result.rowcount
                
                # Execute deletions concurrently
                messages_deleted, ratings_deleted = await asyncio.gather(
                    delete_messages(),
                    delete_ratings()
                )
                
                return {
                    "status": "completed",
                    "messages_deleted": messages_deleted,
                    "ratings_deleted": ratings_deleted,
                    "cutoff_date": cutoff_date.isoformat(),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def analyze_tables() -> Dict[str, Any]:
        """Run ANALYZE on application tables concurrently."""
        try:
            async with get_db_session_context() as session:
                # Run ANALYZE commands concurrently for speed
                async def analyze_messages():
                    await session.execute(text("ANALYZE ai_chatbot.message"))
                    return "message"
                
                async def analyze_ratings():
                    await session.execute(text("ANALYZE ai_chatbot.rating"))
                    return "rating"
                
                async def analyze_replies():
                    await session.execute(text("ANALYZE ai_chatbot.message_reply"))
                    return "message_reply"
                
                # Execute all ANALYZE commands concurrently
                results = await asyncio.gather(
                    analyze_messages(),
                    analyze_ratings(), 
                    analyze_replies(),
                    return_exceptions=True
                )
                
                successful_tables = [r for r in results if not isinstance(r, Exception)]
                failed_tables = [str(r) for r in results if isinstance(r, Exception)]
                
                return {
                    "status": "completed" if not failed_tables else "partial",
                    "tables_analyzed": successful_tables,
                    "failed_tables": failed_tables,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error analyzing tables: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


class QueryPerformanceMonitor:
    """Monitor query performance and identify slow queries."""
    
    @staticmethod
    @asynccontextmanager
    async def time_query(query_name: str):
        """Context manager to time database queries with detailed logging."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            if duration > 1.0:  # Log slow queries (>1 second)
                logger.warning(f"🐌 Slow query detected: {query_name} took {duration:.3f}s")
            elif duration > 0.1:  # Log moderately slow queries
                logger.info(f"⚠️ Query {query_name} took {duration:.3f}s")
            else:
                logger.debug(f"✅ Query {query_name} completed in {duration:.3f}s")


# Concurrent convenience functions for common operations
async def is_database_healthy() -> bool:
    """Quick health check - returns True if database is responsive."""
    result = await DatabaseMonitor.test_connection(timeout=3.0)
    return result.get("connection_successful", False)

async def get_quick_stats() -> Dict[str, Any]:
    """Get a quick overview of database status with concurrent operations."""
    try:
        # Run all checks concurrently for minimal latency
        health_task = DatabaseMonitor.test_connection()
        pool_task = get_connection_pool_status()
        stats_task = DatabaseMonitor.get_table_stats()
        
        health, pool_status, table_stats = await asyncio.gather(
            health_task,
            pool_task, 
            stats_task,
            return_exceptions=True
        )
        
        return {
            "healthy": health.get("connection_successful", False) if not isinstance(health, Exception) else False,
            "response_time": health.get("response_time_seconds", 0) if not isinstance(health, Exception) else 0,
            "pool": pool_status if not isinstance(pool_status, Exception) else {"error": str(pool_status)},
            "stats": table_stats if not isinstance(table_stats, Exception) else {"error": str(table_stats)}
        }
    except Exception as e:
        logger.error(f"Error getting quick stats: {e}")
        return {
            "healthy": False,
            "error": str(e)
        }

# Import the connection pool status function for convenience
from hrbot.db.session import get_connection_pool_status

__all__ = [
    "DatabaseMonitor",
    "DatabaseMaintenance", 
    "QueryPerformanceMonitor",
    "is_database_healthy",
    "get_quick_stats",
    "get_connection_pool_status"
] 