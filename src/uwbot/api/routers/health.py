from fastapi import APIRouter
import os
import platform
import sys
from uwbot.config.settings import settings
from uwbot.db.session import get_connection_pool_status, AsyncSession
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
        "DATABASE_CONFIGURED": bool(settings.db.url)
    }
    
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
    
    # Check state management mode
    state_management_info = {"mode": "unknown", "database_available": None}
    try:
        from uwbot.services.hybrid_state_manager import get_hybrid_state_manager
        state_manager = get_hybrid_state_manager()
        database_available = state_manager.is_using_database()
        
        if database_available is True:
            state_management_info = {
                "mode": "database",
                "description": "Production-ready with persistent state",
                "database_available": True,
                "features": ["persistent_sessions", "horizontal_scaling", "analytics"]
            }
        elif database_available is False:
            state_management_info = {
                "mode": "in-memory", 
                "description": "Fallback mode - sessions lost on restart",
                "database_available": False,
                "features": ["single_instance_only"]
            }
        else:
            state_management_info = {
                "mode": "undetermined",
                "description": "Database check not yet performed",
                "database_available": None
            }
    except Exception as e:
        state_management_info["error"] = str(e)
    
    return {
        "status": "ok",
        "system": system_info,
        "environment": env_vars,
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
        },
        "state_management": state_management_info
    }