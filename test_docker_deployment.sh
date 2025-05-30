#!/bin/bash
# Test Docker deployment locally before giving to DevOps

echo "🐳 Docker Deployment Test Script"
echo "================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running!"
    echo "   Please start Docker Desktop and try again."
    exit 1
fi

echo "✅ Docker is running"

# Clean up any existing test containers
echo ""
echo "🧹 Cleaning up any existing test containers..."
docker stop hrbot-test 2>/dev/null || true
docker rm hrbot-test 2>/dev/null || true

# Build the image
echo ""
echo "🔨 Building Docker image..."
if docker build -t hr-teams-bot:test . ; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Docker build failed"
    exit 1
fi

# Create test environment file
echo ""
echo "📝 Creating test environment file..."
cat > .env.docker-test << 'EOF'
# Test environment for Docker - bypasses AWS for local testing
APP_NAME=HR Teams Bot - Docker Test
DEBUG=true
PORT=3978
HOST=0.0.0.0

# Disable AWS Secrets Manager for local testing
USE_AWS_SECRETS=false

# Disable database for testing (since we don't have local PostgreSQL)
SKIP_DB_INIT=true
DISABLE_DB_WRITES=true

# Use local Google credentials if available
GOOGLE_APPLICATION_CREDENTIALS=/app/gemini-deployment-fe9ea6bb8c92.json
GOOGLE_CLOUD_PROJECT=gemini-deployment

# Teams credentials (if available from your .env)
# MICROSOFT_APP_ID=your-app-id
# MICROSOFT_APP_PASSWORD=your-app-password
# TENANT_ID=your-tenant-id
# CLIENT_ID=your-client-id
# CLIENT_SECRET=your-client-secret

# HR Support
HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/home
HR_SUPPORT_DOMAIN=hrsupport.usclarity.com

# Performance settings
ENABLE_STREAMING=true
MIN_STREAMING_LENGTH=50
STREAMING_DELAY=1.2
CACHE_EMBEDDINGS=true
CACHE_TTL_SECONDS=3600

# Session settings
SESSION_IDLE_MINUTES=30
FEEDBACK_TIMEOUT_MINUTES=10

# Disable features that require database
USE_INTENT_CLASSIFICATION=false
EOF

# Check if we have the Google credentials file
if [ -f "gemini-deployment-fe9ea6bb8c92.json" ]; then
    echo "✅ Found Google credentials file"
    VOLUME_MOUNT="-v $(pwd)/gemini-deployment-fe9ea6bb8c92.json:/app/gemini-deployment-fe9ea6bb8c92.json:ro"
else
    echo "⚠️  Google credentials file not found - Gemini features may not work"
    VOLUME_MOUNT=""
fi

# Run the container
echo ""
echo "🚀 Starting Docker container..."
docker run -d \
    --name hrbot-test \
    --env-file .env.docker-test \
    -p 3978:3978 \
    $VOLUME_MOUNT \
    hr-teams-bot:test

# Wait for startup
echo ""
echo "⏳ Waiting for container to start..."
sleep 15

# Check if container is running
if docker ps | grep hrbot-test > /dev/null; then
    echo "✅ Container is running"
else
    echo "❌ Container failed to start"
    echo ""
    echo "📋 Container logs:"
    docker logs hrbot-test
    exit 1
fi

# Test health endpoint
echo ""
echo "🏥 Testing health endpoint..."
MAX_RETRIES=5
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:3978/health/ | grep -q "ok"; then
        echo "✅ Health check passed"
        break
    else
        RETRY=$((RETRY + 1))
        echo "⏳ Health check attempt $RETRY/$MAX_RETRIES failed, retrying..."
        sleep 5
    fi
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "❌ Health check failed after $MAX_RETRIES attempts"
    echo ""
    echo "📋 Container logs:"
    docker logs hrbot-test
    exit 1
fi

# Show diagnostic info
echo ""
echo "🔍 Diagnostic information:"
curl -s http://localhost:3978/health/diagnostic | python -m json.tool 2>/dev/null || echo "Could not retrieve diagnostics"

# Show container info
echo ""
echo "📊 Container resource usage:"
docker stats hrbot-test --no-stream

# Show recent logs
echo ""
echo "📋 Recent container logs:"
docker logs --tail 20 hrbot-test

# Instructions for cleanup and next steps
echo ""
echo "✅ Docker deployment test completed successfully!"
echo ""
echo "🧹 To clean up:"
echo "   docker stop hrbot-test"
echo "   docker rm hrbot-test"
echo "   rm .env.docker-test"
echo ""
echo "📦 To save the image for DevOps:"
echo "   docker tag hr-teams-bot:test hr-teams-bot:latest"
echo "   docker save hr-teams-bot:latest | gzip > hr-teams-bot.tar.gz"
echo ""
echo "🚀 For production deployment with AWS Secrets Manager:"
echo "   1. Copy 'production.env.template' to '.env.production'"
echo "   2. Fill in the Microsoft Teams credentials from Azure Portal"
echo "   3. Get AWS IAM credentials with Secrets Manager access"
echo "   4. Use: docker-compose --profile production up -d" 