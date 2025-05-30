# hrbot/db/session.py
import ssl
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as SQLAlchemyAsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from hrbot.config.settings import settings

logger = logging.getLogger(__name__)

def _asyncpg_ssl_arg():
    """
    Convert Postgres‐style sslmode to the `ssl` argument asyncpg expects.
    """
    mode = settings.db.sslmode.lower() 

    if mode == "disable":
        return False                               # force plain TCP
    if mode in {"allow", "prefer"}:
        return None                               # let server decide / opportunistic
    if mode in {"require", "verify-ca", "verify-full"}:
        ctx = ssl.create_default_context()
        if mode == "verify-full":
            ctx.check_hostname = True
        return ctx

    raise ValueError(f"Unsupported sslmode '{settings.db.sslmode}'")

connect_args = {"ssl": _asyncpg_ssl_arg()}

# Global engine instance with optimized settings for concurrency
engine = create_async_engine(
    settings.db.url,
    pool_pre_ping=True,           # Health checks before using connections
    echo=False,
    connect_args=connect_args,
    # All pool settings come from config to avoid conflicts
    **settings.db.engine_kwargs,
)

# Session factory optimized for performance
AsyncSession = async_sessionmaker(
    engine, 
    expire_on_commit=False,       # Avoids extra queries after commit
    class_=SQLAlchemyAsyncSession
)

# High-performance database dependency for FastAPI
async def get_db_session() -> AsyncGenerator[SQLAlchemyAsyncSession, None]:
    """
    FastAPI dependency that provides database sessions with minimal latency.
    
    Optimized for speed and simplicity.
    """
    async with AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error occurred: {e}")
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Unexpected error in database session: {e}")
            raise

# High-performance context manager for service operations
@asynccontextmanager
async def get_db_session_context() -> AsyncGenerator[SQLAlchemyAsyncSession, None]:
    """
    High-performance context manager for database sessions.
    
    Optimized for speed - minimal overhead, maximum performance.
    """
    async with AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error in service context: {e}")
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Unexpected error in service database context: {e}")
            raise

# Concurrent connection pool warming for startup performance
async def warm_connection_pool(target_connections: int = None) -> bool:
    """
    Pre-warm the connection pool with concurrent connections.
    
    This reduces latency for the first few requests by establishing
    connections in advance.
    
    Args:
        target_connections: Number of connections to warm (defaults to pool_size)
        
    Returns:
        True if warming succeeded, False otherwise
    """
    if target_connections is None:
        target_connections = min(settings.db.pool_size, 3)  # Don't overwhelm
    
    try:
        # Create multiple concurrent connections to warm the pool
        async def warm_single_connection():
            async with AsyncSession() as session:
                await session.execute(text("SELECT 1"))
                return True
        
        # Run concurrent warming tasks
        tasks = [warm_single_connection() for _ in range(target_connections)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if r is True)
        logger.info(f"Warmed {successful}/{target_connections} database connections")
        return successful > 0
        
    except Exception as e:
        logger.warning(f"Connection pool warming failed: {e}")
        return False

# Application lifecycle management with performance optimization
async def init_database():
    """Initialize database with fast connection test and optional warming."""
    try:
        # Fast connection test
        async with AsyncSession() as session:
            await session.execute(text("SELECT 1"))
            logger.info("✅ Database connection established successfully")
        
        # Optional lightweight warming (non-blocking)
        asyncio.create_task(_background_warm_pool())
            
    except Exception as e:
        logger.error(f"Failed to establish database connection: {e}")
        raise

async def _background_warm_pool():
    """Warm the pool in background without blocking startup."""
    try:
        await asyncio.sleep(0.1)  # Small delay to not interfere with startup
        warmed = await warm_connection_pool(target_connections=2)  # Reduced for speed
        if warmed:
            logger.info("🔥 Database connection pool warmed")
    except Exception as e:
        logger.debug(f"Background pool warming failed (non-critical): {e}")

async def close_database():
    """Gracefully shut down database connections."""
    try:
        # Give time for any in-flight operations to complete
        await asyncio.sleep(0.1)
        await engine.dispose()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")

# Real-time monitoring utilities
async def get_connection_pool_status():
    """Get current connection pool status for monitoring."""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid(),
        "total_available": pool.checkedin() + pool.overflow(),
        "utilization_percent": round((pool.checkedout() / (pool.size() + pool.overflow())) * 100, 1) if (pool.size() + pool.overflow()) > 0 else 0
    }

# Performance utilities
async def ensure_pool_health():
    """Ensure pool is healthy and connections are responsive."""
    try:
        async with AsyncSession() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Pool health check failed: {e}")
        return False

