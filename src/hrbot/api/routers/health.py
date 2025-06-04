from fastapi import APIRouter
import os
import platform
import sys
from hrbot.config.settings import settings
from hrbot.services.gemini_service import GeminiService
from hrbot.db.session import get_connection_pool_status, AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def health():
    """Basic health check endpoint."""
    logger.info("Health check called")
    return {"status": "ok"}

@router.get("/database")
async def database_health():
    """Database-specific health check."""
    try:
        # Test database connection
        async with AsyncSession() as session:
            result = await session.execute(text("SELECT 1 as health_check"))
            row = result.fetchone()
            
        # Get connection pool status
        pool_status = await get_connection_pool_status()
        
        return {
            "status": "healthy",
            "connection_test": "passed",
            "pool_status": pool_status,
            "engine_url": str(settings.db.url).split('@')[-1] if '@' in str(settings.db.url) else "configured"
        }
        
    except SQLAlchemyError as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "connection_test": "failed",
            "error": str(e),
            "error_type": "SQLAlchemyError"
        }
    except Exception as e:
        logger.error(f"Database health check error: {e}")
        return {
            "status": "unhealthy", 
            "connection_test": "failed",
            "error": str(e),
            "error_type": "UnknownError"
        }

@router.get("/diagnostic")
async def diagnostic():
    """Detailed diagnostic endpoint for troubleshooting."""
    # System info
    system_info = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "hostname": platform.node()
    }
    
    # Check environment variables
    env_vars = {
        "GOOGLE_APPLICATION_CREDENTIALS": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "Not set"),
        "GOOGLE_CLOUD_PROJECT": os.environ.get("GOOGLE_CLOUD_PROJECT", "Not set"),
        "TEAMS_APP_ID_CONFIGURED": bool(settings.teams.app_id),
        "GEMINI_MODEL": settings.gemini.model_name,
        "DATABASE_CONFIGURED": bool(settings.db.url)
    }
    
    # Check Gemini connection
    gemini_status = "Not tested"
    try:
        gemini = GeminiService()
        await gemini.test_connection()
        gemini_status = "Connected"
    except Exception as e:
        gemini_status = f"Error: {str(e)}"
    
    # Check database connection and pool status
    db_status = "Not tested"
    pool_info = {}
    try:
        async with AsyncSession() as session:
            await session.execute(text("SELECT 1"))
            db_status = "Connected"
            pool_info = await get_connection_pool_status()
    except Exception as e:
        db_status = f"Error: {str(e)}"
    
    return {
        "status": "ok",
        "system": system_info,
        "environment": env_vars,
        "gemini": gemini_status,
        "database": {
            "status": db_status,
            "pool": pool_info,
            "settings": {
                "host": settings.db.host,
                "port": settings.db.port,
                "database": settings.db.name,
                "pool_size": settings.db.pool_size,
                "max_overflow": settings.db.max_overflow,
                "sslmode": settings.db.sslmode
            }
        }
    }