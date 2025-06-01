"""Database connection management for MovemintX Collector.

This module provides functionality to establish and manage database connections.
"""
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

from hrbot.config.settings import settings

logger = logging.getLogger("hrbot.config")


def get_db_connection():
    """Create and return a PostgreSQL database connection.
    
    Returns:
        A connection object to the PostgreSQL database
        
    Raises:
        psycopg2.Error: If connection fails
    """
    try:
        conn = psycopg2.connect(
            dbname=settings.db.name,
            user=settings.db.user,
            password=settings.db.password,
            host=settings.db.host,
            port=settings.db.port,
            sslmode=settings.db.sslmode,
            cursor_factory=RealDictCursor
        )
        logger.info("Database connection established successfully")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to database: {e}")
        raise