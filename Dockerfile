# Multi-stage build for optimized production image
FROM python:3.11-slim AS builder

# Build arguments
ARG POETRY_VERSION=1.6.1

# Set environment variables for build optimization
ENV POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for building (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Poetry
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

# Set work directory
WORKDIR /app

# Copy Poetry configuration
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true \
    && poetry install --only=main --no-dev --no-root \
    && rm -rf $POETRY_CACHE_DIR

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Install the application
RUN poetry install --only-root


FROM python:3.11-slim AS runtime


# Runtime arguments
ARG APP_USER=hrbot
ARG APP_UID=1000
ARG APP_GID=1000
ARG APP_INSTANCE=jo

# Set environment variables for runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PATH="/app/.venv/bin:$PATH" \
    APP_USER=${APP_USER} \
    APP_INSTANCE=${APP_INSTANCE} \
    # Performance optimizations
    PYTHONHASHSEED=random \
    # Security
    PYTHONSAFEPATH=1

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client library
    libpq5 \
    # SSL/TLS support
    ca-certificates \
    # Health check utilities
    curl \
    # Database connectivity check
    netcat-openbsd \
    # Timezone data
    tzdata \
    # Process management
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y

# Create non-root user for security
RUN groupadd -g ${APP_GID} ${APP_USER} \
    && useradd -u ${APP_UID} -g ${APP_GID} -m -s /bin/bash ${APP_USER} \
    && mkdir -p /app /app/data /app/logs /app/tmp \
    && chown -R ${APP_USER}:${APP_USER} /app

# Set work directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/.venv /app/.venv

# Copy application code
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/src /app/src
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/scripts /app/scripts

# Copy data directory structure (will be mounted in production)
COPY --chown=${APP_USER}:${APP_USER} data/ ./data/

# Copy configuration files (examples for reference)
COPY --chown=${APP_USER}:${APP_USER} instances.yaml ./
COPY --chown=${APP_USER}:${APP_USER} .env.example ./

# Copy startup script
COPY --chown=${APP_USER}:${APP_USER} scripts/docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh

# Create additional directories with proper permissions
RUN mkdir -p /app/data/{conversations,embeddings,knowledge,logs,test_storage} \
    /app/data/embeddings/{jo,us} \
    /app/data/knowledge/{jo,us} \
    /app/data/prompts/{jo,us} \
    && chmod -R 755 /app/data \
    && chown -R ${APP_USER}:${APP_USER} /app

# Switch to non-root user
USER ${APP_USER}

# Dynamic port exposure (will be overridden by Docker Compose)
EXPOSE 3978

# Use dynamic health check script
COPY --chown=${APP_USER}:${APP_USER} scripts/healthcheck.py ./healthcheck.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--", "./docker-entrypoint.sh"]

# Default will be overridden by entrypoint script
CMD ["python", "-m", "uvicorn", "hrbot.api.app:app"]

# Metadata labels
LABEL maintainer="Nedal Al-titi <nedal.altiti@live.com>" \
      description="HR Teams Bot with Gemini AI and RAG capabilities" \
      version="2.0.0" \
      org.opencontainers.image.title="HR Teams Bot" \
      org.opencontainers.image.description="Multi-region HR Assistant with AI capabilities" \
      org.opencontainers.image.vendor="US Clarity" \
      org.opencontainers.image.licenses="Proprietary"