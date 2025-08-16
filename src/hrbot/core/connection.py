"""

Async database connection helper using asyncpg.
"""
import logging
from typing import Optional, Any

import asyncpg

from hrbot.config.settings import settings

logger = logging.getLogger("hrbot.config")


async def get_db_connection() -> asyncpg.Connection:
    """Open a single asyncpg connection using settings.db.url.

    Caller is responsible to close the connection.
    """
    try:
        # settings.db.url may be SQLAlchemy style (postgresql+asyncpg://...)
        # asyncpg expects postgresql://...
        url = settings.db.url.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(url)
        logger.info("Async database connection established successfully")
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database asynchronously: {e}")
        raise
