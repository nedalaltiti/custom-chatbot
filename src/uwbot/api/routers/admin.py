"""
Admin router for managing the UWBot.

This module provides endpoints for:
1. System diagnostics
2. Basic admin operations
"""

import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/status")
async def admin_status():
    """
    Get basic admin status information.
    
    Returns:
        Status information about the system
    """
    try:
        return {
            "status": "ok",
            "service": "UWBot",
            "version": "1.0.0",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Error getting admin status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting admin status: {str(e)}")