# Multi-stage Dockerfile for HR Teams Bot
# Built with security, performance, and production best practices

# ================================
# Build Stage
# ================================
FROM python:3.11-slim as builder

# Build arguments for flexibility
ARG POETRY_VERSION=1.6.1
ARG PYTHONUNBUFFERED=1
ARG PYTHONDONTWRITEBYTECODE=1

# Set environment variables for build
ENV POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    POETRY_CACHE_DIR=/opt/poetry/.cache \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    PYTHONUNBUFFERED=${PYTHONUNBUFFERED} \
    PYTHONDONTWRITEBYTECODE=${PYTHONDONTWRITEBYTECODE}

# Install system dependencies required for building
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

# Set work directory
WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create true && \
    poetry config virtualenvs.in-project true && \
    poetry install --only=main --no-dev --no-root

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Install the application
RUN poetry install --only-root

# ================================
# Runtime Stage
# ================================
FROM python:3.11-slim as runtime

# Runtime arguments
ARG APP_USER=hrbot
ARG APP_UID=1000
ARG APP_GID=1000

# Set environment variables for runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src:$PYTHONPATH" \
    PATH="/app/.venv/bin:$PATH" \
    APP_USER=${APP_USER}

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    # Required for asyncpg (PostgreSQL)
    libpq5 \
    # Required for SSL connections
    ca-certificates \
    # Required for health checks
    curl \
    # Timezone data
    tzdata \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -g ${APP_GID} ${APP_USER} && \
    useradd -u ${APP_UID} -g ${APP_GID} -m -s /bin/bash ${APP_USER}

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/.venv /app/.venv

# Copy application code
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/src /app/src
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/scripts /app/scripts

# Create necessary directories with proper permissions
RUN mkdir -p /app/data/{conversations,embeddings,knowledge} \
    /app/logs \
    /app/tmp && \
    chown -R ${APP_USER}:${APP_USER} /app

# Switch to non-root user
USER ${APP_USER}

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3978/health/ || exit 1

# Expose port (Teams Bot standard port)
EXPOSE 3978

# Default command - can be overridden in docker-compose
CMD ["python", "-m", "uvicorn", "hrbot.api.app:app", "--host", "0.0.0.0", "--port", "3978", "--workers", "1"]

# Metadata labels following best practices
LABEL maintainer="Nedal Al-titi <nedal.altiti@live.com>" \
      description="HR Teams Bot with Gemini AI and RAG capabilities" \
      version="1.0.0" \
      org.opencontainers.image.title="HR Teams Bot" \
      org.opencontainers.image.description="Enterprise HR Assistant with AI capabilities" \
      org.opencontainers.image.vendor="US Clarity" \
      org.opencontainers.image.licenses="Proprietary" \
      org.opencontainers.image.source="https://github.com/your-org/custom-chatbot" 