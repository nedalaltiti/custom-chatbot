#!/bin/bash
set -e

INSTANCE=${APP_INSTANCE:-jo}
PORT=${PORT:-3978}
HOST=${HOST:-postgres}
PORT=${PORT:-5432}

# Auto-skip when running in CI *or* when DB creds come from AWS Secrets (external RDS)
if [ "${CI:-false}" = "true" ] || [ "${USE_AWS_SECRETS:-false}" = "true" ]; then
  SKIP_DB_WAIT=true
fi

echo "[ENTRYPOINT] Starting HR Teams Bot instance: $INSTANCE on port: $PORT"

# Wait for database DNS resolution
echo "[ENTRYPOINT] Waiting for database host \"$HOST\" to resolve..."
if [ "$SKIP_DB_WAIT" = "true" ]; then
  echo "[ENTRYPOINT] SKIP_DB_WAIT=true, skipping DB availability checks"
else
  for i in {1..30}; do
    if getent hosts "$HOST" >/dev/null; then
      echo "[ENTRYPOINT] Host $HOST resolved"
      break
    fi
    echo "[ENTRYPOINT] [$i/30] Host $HOST not yet resolvable, retrying in 2s..."
    sleep 2
    if [ "$i" -eq 30 ]; then
      echo "[ENTRYPOINT] ERROR: Host $HOST could not be resolved after 60s" >&2
      exit 1
    fi
  done
fi

# Wait for database TCP port
echo "[ENTRYPOINT] Waiting for database TCP connection $HOST:$PORT
 ..."
if [ "$SKIP_DB_WAIT" = "true" ]; then
  echo "[ENTRYPOINT] SKIP_DB_WAIT=true, skipping DB availability checks"
else
  for i in {1..30}; do
    if nc -z "$HOST" "$PORT
"; then
      echo "[ENTRYPOINT] Database is ready"
      break
    fi
    echo "[ENTRYPOINT] [$i/30] Database not ready yet, retrying in 2s..."
    sleep 2
    if [ "$i" -eq 30 ]; then
      echo "[ENTRYPOINT] ERROR: Database $HOST:$PORT
 not reachable after 60s" >&2
      exit 1
    fi
  done
fi

# Start the application
echo "[ENTRYPOINT] Launching application on port $PORT"
exec python -m uvicorn hrbot.api.app:app --host 0.0.0.0 --port "$PORT" --workers 1
