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
from uwbot.services.session_tracker import SessionTracker   
from uwbot.services.gemini_service import GeminiService
from uwbot.config.app_config import get_app_config

# Simple error class for invalid contact IDs
class InvalidContactIDError(ValueError):
    """Raised when a contact ID is invalid or out of range."""
    pass

from uwbot.utils.logging import setup_logging_with_pii_filter, get_logger_with_pii_filter

# Setup logging with PII filtering
setup_logging_with_pii_filter(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format_string="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    add_pii_filter=True
)
logger = get_logger_with_pii_filter("uwbot.app")

session_tracker = SessionTracker(idle_minutes=settings.session_idle_minutes)

# Store temporary credentials path for cleanup
_temp_credentials_path = None

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise expensive singletons once per process and dispose on exit."""
    global _temp_credentials_path
    
    logger.info("UWBot starting up…")

    # Validate hardship field configuration
    try:
        hardship_fields = settings.hardship_fields
        logger.info(f"Validating hardship field configuration...")
        
        # Mask configuration values without contact_id_ prefix
        hardship_id = hardship_fields.financial_hardship_id
        hardship_desc_id = hardship_fields.hardship_description_id
        
        # Apply simple masking for configuration values
        if hardship_id and len(hardship_id) >= 4:
            masked_hardship_id = f"***{hardship_id[-3:]}"
        else:
            masked_hardship_id = hardship_id
            
        if hardship_desc_id and len(hardship_desc_id) >= 4:
            masked_hardship_desc_id = f"***{hardship_desc_id[-3:]}"
        else:
            masked_hardship_desc_id = hardship_desc_id
        
        logger.info(f"  Financial hardship ID: {masked_hardship_id}")
        logger.info(f"  Hardship description ID: {masked_hardship_desc_id}")
        
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
        
        # Mask configuration values without contact_id_ prefix
        acctid = budget_fields.acctid
        c_type = budget_fields.c_type
        iscoapp = budget_fields.iscoapp
        leadstatus = budget_fields.leadstatus
        
        # Apply simple masking for configuration values
        def mask_config_value(value):
            if value and len(str(value)) >= 4:
                return f"***{str(value)[-3:]}"
            return value
        
        masked_acctid = mask_config_value(acctid)
        masked_c_type = mask_config_value(c_type)
        masked_iscoapp = mask_config_value(iscoapp)
        masked_leadstatus = mask_config_value(leadstatus)
        
        logger.info(f"  Budget acctid: {masked_acctid}")
        logger.info(f"  Budget c_type: {masked_c_type}")
        logger.info(f"  Budget iscoapp: {masked_iscoapp}")
        logger.info(f"  Budget leadstatus: {masked_leadstatus}")
        
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

    # Store temporary credentials path for cleanup
    if settings.gemini.use_aws_secrets and settings.gemini.credentials_path:
        _temp_credentials_path = settings.gemini.credentials_path
        logger.info("Using AWS Secrets Manager for Gemini credentials")

    # Initialize LLM service in background to reduce first-request latency
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
        
        # Clean up temporary credentials if using AWS Secrets Manager
        if _temp_credentials_path:
            try:
                from uwbot.utils.secret_manager import cleanup_temp_credentials
                cleanup_temp_credentials(_temp_credentials_path)
                logger.info("Cleaned up temporary AWS credentials")
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary credentials: {e}")
        
        # Clean up database connections
        try:
            from uwbot.db.session import close_database
            await close_database()
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")
        logger.info("👋  Goodbye")


async def _warmup_services():
    """Warm up LLM service in the background."""
    try:
        # Initialize Gemini
        logger.info("Warming up Gemini service...")
        gemini = GeminiService()
        await gemini.test_connection()
        
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
