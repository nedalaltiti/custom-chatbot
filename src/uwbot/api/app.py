"""
FastAPI application entry-point.

All runtime wiring (middleware, routers, startup/shutdown) lives here so tests
can import `app` without side-effects.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncio
import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from uwbot.api.routers import admin, feedback, health, teams, debug
from uwbot.config.settings import settings
from uwbot.utils.error import BaseError, ErrorSeverity
from uwbot.config.app_config import get_app_config

# Simple error class for invalid contact IDs
class InvalidContactIDError(ValueError):
    """Raised when a contact ID is invalid or out of range."""
    pass

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("uwbot.app")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise expensive singletons once per process and dispose on exit."""
    
    logger.info("UWBot starting up…")

    # Validate hardship field configuration
    try:
        hardship_fields = settings.hardship_fields
        logger.info(f"Validating hardship field configuration...")
        logger.info(f"  Financial hardship ID: {hardship_fields.financial_hardship_id}")
        logger.info(f"  Hardship description ID: {hardship_fields.hardship_description_id}")
        
        if not hardship_fields.validate():
            raise ValueError("Invalid hardship field configuration detected during startup")
        
        logger.info("✅ Hardship field configuration validated successfully")
    except Exception as e:
        logger.error(f"Hardship field validation failed: {e}")
        raise

    # Validate budget field configuration
    try:
        budget_fields = settings.budget_fields
        logger.info(f"Validating budget field configuration...")
        logger.info(f"  Budget acctid: {budget_fields.acctid}")
        logger.info(f"  Budget c_type: {budget_fields.c_type}")
        logger.info(f"  Budget iscoapp: {budget_fields.iscoapp}")
        logger.info(f"  Budget leadstatus: {budget_fields.leadstatus}")
        
        if not budget_fields.validate():
            raise ValueError("Invalid budget field configuration detected during startup")
        
        logger.info("✅ Budget field configuration validated successfully")
    except Exception as e:
        logger.error(f"Budget field validation failed: {e}")
        raise

    # Initialize database connections first
    try:
        from uwbot.db.session import init_database
        await init_database()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Check if we should fail on DB errors
        if os.environ.get("SKIP_DB_INIT", "").lower() not in ("true", "1", "yes"):
            raise
        else:
            logger.warning("Continuing without database (SKIP_DB_INIT=true)")


    # Initialize service in background to reduce first-request latency
    asyncio.create_task(_warmup_services())

    # Log current app configuration
    try:
        app_config = get_app_config()
        logger.info(f"Prompts: {app_config.prompt_dir}")
        # Show Teams app configuration
        teams_settings = settings.teams
        if teams_settings.app_id:
            logger.info(f"🤖 Teams App ID: {teams_settings.app_id[:8]}...{teams_settings.app_id[-8:] if len(teams_settings.app_id) > 16 else teams_settings.app_id}")
    except Exception as e:
        logger.error(f"Error during app config logging: {e}")
        logger.info("Continuing with default configuration")

    logger.info("✅  Startup complete")
    try:
        yield
    finally:
        logger.info("👋  Shutting down...")
        
        # Clean up database connections
        try:
            from uwbot.db.session import close_database
            await close_database()
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")
        logger.info("👋  Goodbye")


async def _warmup_services():
    """Warm up services in the background."""
    try:
        logger.info("UWBot service warmup - initializing state management")
        
        # Initialize and check state management mode
        from uwbot.services.hybrid_state_manager import get_hybrid_state_manager
        state_manager = get_hybrid_state_manager()
        
        # Force database check to determine mode
        database_available = await state_manager.force_database_check()
        
        if database_available:
            logger.info("✅ State Management: DATABASE mode (production-ready)")
            logger.info("   • Persistent sessions across restarts")
            logger.info("   • Horizontal scaling support")
            logger.info("   • Full analytics tracking")
        else:
            logger.warning("⚠️ State Management: IN-MEMORY mode (fallback)")
            logger.warning("   • Sessions will be lost on restart")
            logger.warning("   • Limited to single instance")
            logger.warning("   • Create database tables to enable database mode")
        
        logger.info("Service warmup complete")
    except Exception as e:
        logger.warning(f"Service warmup failed (non-critical): {e}")


app = FastAPI(
    title=settings.app_name,
    description="UWBot Validation Bot backend",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
    redirect_slashes=False,
)

if settings.cors_origins:   # don't enable CORS unless explicitly configured
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(teams.router,  prefix="/api/messages", tags=["teams"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(admin.router,  prefix="/api/admin", tags=["admin"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])

@app.get("/")
async def root():
    """Root endpoint for health checks and basic info."""
    return {
        "service": "UWBot Validation Bot",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "teams": "/api/messages",
            "feedback": "/api/feedback",
            "admin": "/api/admin",
            "debug": "/api/debug"
        },
        "documentation": "/docs" if settings.debug else "disabled in production"
    }

@app.exception_handler(BaseError)
async def uwbot_error_handler(_: Request, exc: BaseError) -> JSONResponse:
    """Return structured JSON for domain errors; fall back to FastAPI default
    for everything else.
    """
    status_code = (
        status.HTTP_400_BAD_REQUEST
        if exc.severity in {ErrorSeverity.INFO, ErrorSeverity.WARNING}
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return JSONResponse(status_code=status_code, content=exc.to_dict())

@app.exception_handler(InvalidContactIDError)
async def invalid_contact_id_handler(_: Request, exc: InvalidContactIDError) -> JSONResponse:
    """Handle invalid contact ID errors with HTTP 422 Unprocessable Entity."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Invalid Contact ID",
            "message": str(exc),
            "type": "validation_error"
        }
    )
