#!/bin/bash
set -e

INSTANCE=${APP_INSTANCE:-jo}
APP_PORT=${PORT:-3978}

echo "[ENTRYPOINT] Starting HR Teams Bot instance: $INSTANCE on port: $APP_PORT"

# Skip database connectivity checks when using AWS Secrets Manager
# The app will handle database connection itself after loading secrets
if [ "${USE_AWS_SECRETS:-false}" = "true" ]; then
  echo "[ENTRYPOINT] Using AWS Secrets Manager - skipping database connectivity checks"
  echo "[ENTRYPOINT] App will connect to database after loading secrets from AWS"
else
  # Only do database checks for local development with direct DB env vars
  DB_HOST=${DB_HOST:-postgres}
  DB_PORT=${DB_PORT:-5432}
  
  echo "[ENTRYPOINT] Waiting for database host \"$DB_HOST\" to resolve..."
  for i in {1..30}; do
    if getent hosts "$DB_HOST" >/dev/null; then
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
    if nc -z "$DB_HOST" "$DB_PORT"; then
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

# Start the application
echo "[ENTRYPOINT] Launching application on port $APP_PORT"
exec python -m uvicorn hrbot.api.app:app --host 0.0.0.0 --port "$APP_PORT" --workers 1