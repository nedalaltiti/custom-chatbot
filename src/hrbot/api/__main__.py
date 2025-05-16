"""
Entry point for the HR Teams Bot application.
This module can be run directly with 'python -m hrbot.api'.
"""

import uvicorn
import logging
import os
import sys
import argparse
from dotenv import load_dotenv
from hrbot.api.app import app
from hrbot.config.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hrbot")

def check_environment():
    """Verify critical environment variables on startup."""
    # Ensure .env is loaded
    load_dotenv(override=True)
    
    # Log critical settings (without sensitive values)
    logger.info(f"Teams App ID configured: {'Yes' if settings.teams.app_id else 'No'}")
    logger.info(f"Google Cloud Project: {settings.google_cloud.project_id}")
    logger.info(f"Gemini Model: {settings.gemini.model_name}")
    logger.info(f"Server will run on port: {settings.port}")
    
    # Check Google credentials
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_path:
        if os.path.exists(creds_path):
            logger.info(f"Google credentials found at {creds_path}")
        else:
            logger.warning(f"Google credentials path set but file not found: {creds_path}")
    else:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set")

def run_server(host=None, port=None, reload=False):
    """
    Run the server with the specified settings.
    
    Args:
        host: Host to bind (overrides settings)
        port: Port to bind (overrides settings)
        reload: Enable auto-reload for development
    """
    # Check environment before starting
    check_environment()
    
    # Use provided values or fallback to settings
    host = host or settings.host
    port = port or settings.port
    
    logger.info(f"Starting HR Teams Bot on {host}:{port}")
    logger.info(f"To expose this service, use: ngrok http {port}")
    
    # Start uvicorn with provided options
    uvicorn.run(
        "hrbot.api.app:app", 
        host=host, 
        port=port,
        reload=reload
    )

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="HR Teams Bot Server")
    parser.add_argument("--host", help="Host to bind (default: from settings)")
    parser.add_argument("--port", type=int, help="Port to bind (default: from settings)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_server(host=args.host, port=args.port, reload=args.reload) 