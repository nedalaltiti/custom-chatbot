from fastapi import APIRouter
import os
import platform
import sys
from hrbot.config.settings import settings
from hrbot.services.gemini_service import GeminiService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def health():
    """Basic health check endpoint."""
    logger.info("Health check called")
    return {"status": "ok"}

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
        "GEMINI_MODEL": settings.gemini.model_name
    }
    
    # Check Gemini connection
    gemini_status = "Not tested"
    try:
        gemini = GeminiService()
        await gemini.test_connection()
        gemini_status = "Connected"
    except Exception as e:
        gemini_status = f"Error: {str(e)}"
    
    return {
        "status": "ok",
        "system": system_info,
        "environment": env_vars,
        "gemini": gemini_status
    }