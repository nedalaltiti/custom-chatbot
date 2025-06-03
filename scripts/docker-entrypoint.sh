#!/bin/bash
set -e

INSTANCE=${APP_INSTANCE:-jo}
PORT=${PORT:-3978}
DB_HOST=${DB_HOST:-postgres}
DB_PORT=${DB_PORT:-5432}

echo "[ENTRYPOINT] Starting HR Teams Bot instance: $INSTANCE on port: $PORT"

# Wait for database DNS resolution
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

# Wait for database TCP port
echo "[ENTRYPOINT] Waiting for database TCP connection $DB_HOST:$DB_PORT ..."
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

# Start the application
echo "[ENTRYPOINT] Launching application on port $PORT"
exec python -m uvicorn hrbot.api.app:app --host 0.0.0.0 --port "$PORT" --workers 1
