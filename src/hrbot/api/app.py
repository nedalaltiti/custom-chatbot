"""
FastAPI application entry point.

This module defines the FastAPI application with middleware and routers.
It's imported by __main__.py to run the server, but keeps the app definition separate
to support direct import for testing and documentation.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from hrbot.api.routers import teams, admin, health, feedback
from hrbot.utils.integration import initialize_application, shutdown_application
from hrbot.config.settings import settings
import logging
import traceback
from contextlib import asynccontextmanager

# Configure application logger
logger = logging.getLogger("hrbot.api")

# Lifespan context for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up")
    await initialize_application()
    logger.info("Application startup complete")
    try:
        yield
    finally:
        logger.info("Application shutting down")
        await shutdown_application()
        logger.info("Application shutdown complete")

# Create FastAPI app with production metadata
app = FastAPI(
    title=settings.app_name,
    description="HR Teams Bot API for intelligent HR assistance",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,  # Disable docs in production
    redoc_url="/redoc" if settings.debug else None,  # Disable redoc in production
    lifespan=lifespan
)

# Add CORS middleware with appropriate settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Configure from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(teams.router, prefix="/api/messages")
app.include_router(admin.router, prefix="/admin")
app.include_router(health.router, prefix="/health")
app.include_router(feedback.router, prefix="/api/feedback")

# Add global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to log errors and return friendly responses."""
    error_id = id(exc)
    logger.error(f"Error ID {error_id} - Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    
    # Log request details for debugging
    method = request.method
    url = str(request.url)
    headers = dict(request.headers)
    
    # Remove sensitive headers if any
    if "authorization" in headers:
        headers["authorization"] = "REDACTED"
    
    logger.error(f"Request that caused error: {method} {url}")
    logger.debug(f"Headers: {headers}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "error_id": str(error_id),
            "message": "An unexpected error occurred" if not settings.debug else str(exc)
        }
    )