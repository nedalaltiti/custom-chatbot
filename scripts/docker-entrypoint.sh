#!/bin/bash
set -e

INSTANCE=${APP_INSTANCE:-jo}
PORT=${PORT:-3978}

echo "[ENTRYPOINT] Starting HR Teams Bot instance: $INSTANCE on port: $PORT"

# Wait for database
echo "[ENTRYPOINT] Waiting for database..."
until nc -z postgres 5432; do
    sleep 2
done
echo "[ENTRYPOINT] Database is ready"

# Start the application
echo "[ENTRYPOINT] Starting application on port $PORT"
exec python -m uvicorn hrbot.api.app:app --host 0.0.0.0 --port $PORT --workers 1
