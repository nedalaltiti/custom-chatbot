#!/bin/bash
set -e

# Get configuration
INSTANCE=${APP_INSTANCE:-jo}
APP_PORT=${PORT:-3978}
USE_AWS_SECRETS=${USE_AWS_SECRETS:-true}
SKIP_DB_INIT=${SKIP_DB_INIT:-false}
SKIP_DB_WAIT=${SKIP_DB_WAIT:-false}

echo "[ENTRYPOINT] Starting HR Teams Bot instance: $INSTANCE on port: $APP_PORT"
echo "[ENTRYPOINT] USE_AWS_SECRETS: $USE_AWS_SECRETS"
echo "[ENTRYPOINT] SKIP_DB_INIT: $SKIP_DB_INIT"

# Skip ALL database connectivity checks if explicitly requested
if [ "$SKIP_DB_INIT" = "true" ] || [ "$SKIP_DB_WAIT" = "true" ]; then
  echo "[ENTRYPOINT] Skipping database connectivity checks (SKIP_DB_INIT=$SKIP_DB_INIT)"
  echo "[ENTRYPOINT] Application will handle database connections internally"
elif [ "$USE_AWS_SECRETS" = "true" ]; then
  echo "[ENTRYPOINT] Using AWS Secrets Manager - skipping local database connectivity checks"
  echo "[ENTRYPOINT] App will connect to RDS after loading secrets from AWS"
else
  # Only do database checks for local development with direct DB env vars
  DB_HOST=${DB_HOST:-postgres}
  DB_PORT=${DB_PORT:-5432}
  
  echo "[ENTRYPOINT] Local development mode - checking database connectivity"
  echo "[ENTRYPOINT] Waiting for database host \"$DB_HOST\" to resolve..."
  
  for i in {1..30}; do
    if getent hosts "$DB_HOST" >/dev/null 2>&1; then
      echo "[ENTRYPOINT] Host $DB_HOST resolved"
      break
    fi
    echo "[ENTRYPOINT] [$i/30] Host $DB_HOST not yet resolvable, retrying in 2s..."
    sleep 2
    if [ "$i" -eq 30 ]; then
      echo "[ENTRYPOINT] ERROR: Host $DB_HOST could not be resolved after 60s" >&2
      exit 1
    fi
  done

  echo "[ENTRYPOINT] Waiting for database TCP connection $DB_HOST:$DB_PORT..."
  for i in {1..30}; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
      echo "[ENTRYPOINT] Database is ready"
      break
    fi
    echo "[ENTRYPOINT] [$i/30] Database not ready yet, retrying in 2s..."
    sleep 2
    if [ "$i" -eq 30 ]; then
      echo "[ENTRYPOINT] ERROR: Database $DB_HOST:$DB_PORT not reachable after 60s" >&2
      exit 1
    fi
  done
fi

# Ensure required directories exist with proper permissions
echo "[ENTRYPOINT] Ensuring data directories exist..."
mkdir -p /app/data/{conversations,embeddings,knowledge,logs,test_storage}
mkdir -p /app/data/embeddings/{jo,us}
mkdir -p /app/data/knowledge/{jo,us}
mkdir -p /app/data/prompts/{jo,us}
mkdir -p /app/logs

# Start the application
echo "[ENTRYPOINT] Launching application on port $APP_PORT"
exec python -m uvicorn hrbot.api.app:app --host 0.0.0.0 --port "$APP_PORT" --workers 1