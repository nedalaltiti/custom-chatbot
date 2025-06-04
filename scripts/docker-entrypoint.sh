#!/bin/bash
set -e

# Function to detect and fix AWS credentials format
fix_aws_credentials() {
    echo "[ENTRYPOINT] Checking AWS credentials format..."
    
    # Check if AWS_SECRET_ACCESS_KEY looks like base64
    if [[ -n "$AWS_SECRET_ACCESS_KEY" ]] && [[ "$AWS_SECRET_ACCESS_KEY" =~ ^[A-Za-z0-9+/=]+$ ]] && [[ ${#AWS_SECRET_ACCESS_KEY} -eq 44 ]]; then
        echo "[ENTRYPOINT] WARNING: AWS_SECRET_ACCESS_KEY appears to be base64 encoded"
        
        # Try to decode it
        DECODED_SECRET=$(echo "$AWS_SECRET_ACCESS_KEY" | base64 -d 2>/dev/null || echo "")
        
        if [[ -n "$DECODED_SECRET" ]]; then
            echo "[ENTRYPOINT] Attempting to use decoded secret..."
            export AWS_SECRET_ACCESS_KEY="$DECODED_SECRET"
        else
            echo "[ENTRYPOINT] ERROR: Failed to decode AWS_SECRET_ACCESS_KEY"
        fi
    fi
    
    # Validate credentials format
    if [[ "$AWS_ACCESS_KEY_ID" =~ ^AKIA[A-Z0-9]{16}$ ]]; then
        echo "[ENTRYPOINT] AWS_ACCESS_KEY_ID format looks correct"
    else
        echo "[ENTRYPOINT] WARNING: AWS_ACCESS_KEY_ID format may be incorrect"
    fi
}

echo "[ENTRYPOINT] Starting HR Teams Bot instance: ${APP_INSTANCE} on port: ${PORT}"
echo "[ENTRYPOINT] USE_AWS_SECRETS: ${USE_AWS_SECRETS}"
echo "[ENTRYPOINT] SKIP_DB_INIT: ${SKIP_DB_INIT}"

# Fix AWS credentials if needed
if [[ "${USE_AWS_SECRETS}" == "true" ]]; then
    fix_aws_credentials
fi

# Load instance-specific environment file if it exists
if [[ -f ".env.${APP_INSTANCE}" ]]; then
    echo "[ENTRYPOINT] Loading environment from .env.${APP_INSTANCE}"
    set -a
    source ".env.${APP_INSTANCE}"
    set +a
fi

# AWS Secrets Manager handling
if [[ "${USE_AWS_SECRETS}" == "true" ]]; then
    echo "[ENTRYPOINT] Using AWS Secrets Manager - skipping local database connectivity checks"
    echo "[ENTRYPOINT] App will connect to RDS after loading secrets from AWS"
else
    echo "[ENTRYPOINT] Using local database configuration"
    
    # Only check connectivity if not skipping DB init
    if [[ "${SKIP_DB_INIT}" != "true" ]]; then
        echo "[ENTRYPOINT] Checking database connectivity..."
        
        max_retries=30
        retry_count=0
        
        while ! nc -z "${DB_HOST}" "${DB_PORT}"; do
            retry_count=$((retry_count + 1))
            
            if [[ $retry_count -ge $max_retries ]]; then
                echo "[ENTRYPOINT] ERROR: Database is not reachable after ${max_retries} attempts"
                exit 1
            fi
            
            echo "[ENTRYPOINT] Waiting for database... (attempt ${retry_count}/${max_retries})"
            sleep 2
        done
        
        echo "[ENTRYPOINT] ✅ Database is reachable at ${DB_HOST}:${DB_PORT}"
    fi
fi

# Ensure data directories exist
echo "[ENTRYPOINT] Ensuring data directories exist..."
mkdir -p /app/data/{conversations,embeddings,knowledge,logs,test_storage}
mkdir -p /app/data/embeddings/{jo,us}
mkdir -p /app/data/knowledge/{jo,us} 
mkdir -p /app/data/prompts/{jo,us}

# Launch the application
echo "[ENTRYPOINT] Launching application on port ${PORT}"
exec python -m uvicorn hrbot.api.app:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers 1 \
    --log-config /app/logging.yaml 2>&1 | tee -a /app/logs/app.log