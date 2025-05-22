"""
FastAPI application entry-point.

All runtime wiring (middleware, routers, startup/shutdown) lives here so tests
can import `app` without side-effects.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hrbot.api.routers import admin, feedback, health, teams
from hrbot.config.settings import settings
from hrbot.utils.di import get_vector_store         
from hrbot.infrastructure.ingest import refresh_vector_index 
from hrbot.utils.error import BaseError, ErrorSeverity


logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hrbot.app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise expensive singletons once per process and dispose on exit."""
    logger.info("HR-bot starting up…")

    # Warm-up heavyweight services so the first request is brisk
    vector_store = get_vector_store()
    await vector_store.warmup()           # no-op if your store doesn’t need it

    # If no embeddings OR there are new files, build them now
    new_docs = await refresh_vector_index(vector_store)
    if new_docs:
        logger.info("Indexed %d fresh document(s) on startup", new_docs)

    logger.info("✅  Startup complete")
    try:
        yield
    finally:
        logger.info("👋  Goodbye")


app = FastAPI(
    title=settings.app_name,
    description="HR Teams-bot backend",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

if settings.cors_origins:   # don’t enable CORS unless explicitly configured
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
app.include_router(admin.router,  prefix="/admin", tags=["admin"])

@app.exception_handler(BaseError)
async def hrbot_error_handler(_: Request, exc: BaseError) -> JSONResponse:
    """Return structured JSON for domain errors; fall back to FastAPI default
    for everything else.
    """
    status_code = (
        status.HTTP_400_BAD_REQUEST
        if exc.severity in {ErrorSeverity.INFO, ErrorSeverity.WARNING}
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return JSONResponse(status_code=status_code, content=exc.to_dict())
