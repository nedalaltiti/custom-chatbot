#!/bin/bash

# Multi-Tenant HR Bot Deployment Script
# Usage: ./scripts/deploy_multi_tenant.sh [single|multi] [jordan|us|both]

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_TYPE="${1:-multi}"
TENANT_SELECTION="${2:-both}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if .env file exists
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_warning ".env file not found. Creating template..."
        create_env_template
    fi
    
    log_success "Prerequisites check passed"
}

# Create environment template
create_env_template() {
    cat > "$PROJECT_ROOT/.env" << 'EOF'
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=hrbot
DB_PASSWORD=change_me_secure_password
DB_NAME=hrbot

# AWS Configuration  
USE_AWS_SECRETS=true
AWS_REGION=us-west-1
AWS_DB_SECRET_NAME=chatbot-clarity-db-dev-postgres
AWS_GEMINI_SECRET_NAME=genai-gemini-vertex-prod-api

# Teams Configuration
MICROSOFT_APP_ID=your_app_id_here
MICROSOFT_APP_PASSWORD=your_app_password_here
TENANT_ID=your_tenant_id_here

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1

# Performance Settings
PERFORMANCE_ENABLE_STREAMING=true
PERFORMANCE_CACHE_EMBEDDINGS=true
PERFORMANCE_MIN_STREAMING_LENGTH=200

# Debug Settings
DEBUG=false
LOG_LEVEL=INFO
EOF
    
    log_info "Environment template created at .env - please update with your values"
}

# Setup tenant directories
setup_directories() {
    log_info "Setting up tenant directories..."
    
    cd "$PROJECT_ROOT"
    
    # Create tenant-specific directories
    mkdir -p data/knowledge/{jordan,us}
    mkdir -p data/embeddings/{jordan,us}
    mkdir -p data/prompts/{jordan,us}
    mkdir -p data/logs
    mkdir -p configs
    mkdir -p docker/nginx/ssl
    
    # Set permissions
    chmod -R 755 data/
    chmod -R 755 configs/
    
    log_success "Tenant directories created"
}

# Setup multi-tenant configuration
setup_multi_tenant_config() {
    log_info "Setting up multi-tenant configuration..."
    
    # Run the Python setup script if it exists
    if [ -f "$PROJECT_ROOT/scripts/setup_multi_tenant.py" ]; then
        cd "$PROJECT_ROOT"
        python scripts/setup_multi_tenant.py
        log_success "Multi-tenant Python setup completed"
    else
        log_warning "Multi-tenant Python setup script not found, skipping..."
    fi
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    
    cd "$PROJECT_ROOT"
    docker build -t hrbot:latest . --target runtime
    
    log_success "Docker image built successfully"
}

# Deploy single-tenant configuration
deploy_single_tenant() {
    log_info "Deploying single-tenant configuration..."
    
    cd "$PROJECT_ROOT"
    
    # Use single-tenant compose file
    if [ -f "docker-compose.single-tenant.yml" ]; then
        docker-compose -f docker-compose.single-tenant.yml down || true
        docker-compose -f docker-compose.single-tenant.yml up -d
        
        # Wait for health check
        log_info "Waiting for service to be healthy..."
        sleep 10
        
        # Check health
        if check_health "http://localhost:3978/health"; then
            log_success "Single-tenant deployment successful"
            log_info "Access the application at: http://localhost:3978"
        else
            log_error "Single-tenant deployment health check failed"
            docker-compose -f docker-compose.single-tenant.yml logs --tail=50
            exit 1
        fi
    else
        log_error "docker-compose.single-tenant.yml not found"
        exit 1
    fi
}

# Deploy multi-tenant configuration
deploy_multi_tenant() {
    log_info "Deploying multi-tenant configuration..."
    
    cd "$PROJECT_ROOT"
    
    # Use multi-tenant compose file
    if [ -f "docker-compose.multi-tenant.yml" ]; then
        docker-compose -f docker-compose.multi-tenant.yml down || true
        
        # Deploy based on tenant selection
        case $TENANT_SELECTION in
            "jordan")
                log_info "Deploying Jordan tenant only..."
                docker-compose -f docker-compose.multi-tenant.yml up -d hrbot-jordan
                JORDAN_URL="http://localhost:3978"
                ;;
            "us")
                log_info "Deploying US tenant only..."
                docker-compose -f docker-compose.multi-tenant.yml up -d hrbot-us
                US_URL="http://localhost:3979"
                ;;
            "both"|*)
                log_info "Deploying both tenants..."
                docker-compose -f docker-compose.multi-tenant.yml up -d
                JORDAN_URL="http://localhost:3978"
                US_URL="http://localhost:3979"
                ;;
        esac
        
        # Wait for services to be healthy
        log_info "Waiting for services to be healthy..."
        sleep 15
        
        # Check health for deployed services
        health_success=true
        
        if [ "$TENANT_SELECTION" = "jordan" ] || [ "$TENANT_SELECTION" = "both" ]; then
            if check_health "$JORDAN_URL/health"; then
                log_success "Jordan tenant deployment successful"
                log_info "Jordan tenant access: $JORDAN_URL"
            else
                log_error "Jordan tenant health check failed"
                health_success=false
            fi
        fi
        
        if [ "$TENANT_SELECTION" = "us" ] || [ "$TENANT_SELECTION" = "both" ]; then
            if check_health "$US_URL/health"; then
                log_success "US tenant deployment successful"
                log_info "US tenant access: $US_URL"
            else
                log_error "US tenant health check failed"
                health_success=false
            fi
        fi
        
        # Check nginx if deployed
        if docker-compose -f docker-compose.multi-tenant.yml ps | grep -q nginx; then
            log_info "Nginx load balancer is running at: http://localhost"
        fi
        
        if [ "$health_success" = false ]; then
            log_error "Some services failed health checks"
            docker-compose -f docker-compose.multi-tenant.yml logs --tail=50
            exit 1
        else
            log_success "Multi-tenant deployment successful"
        fi
    else
        log_error "docker-compose.multi-tenant.yml not found"
        exit 1
    fi
}

# Health check function
check_health() {
    local url="$1"
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            return 0
        fi
        
        log_info "Health check attempt $attempt/$max_attempts for $url"
        sleep 2
        ((attempt++))
    done
    
    return 1
}

# Show deployment status
show_status() {
    log_info "Deployment Status:"
    echo "===================="
    
    cd "$PROJECT_ROOT"
    
    if [ "$DEPLOYMENT_TYPE" = "single" ]; then
        docker-compose -f docker-compose.single-tenant.yml ps
    else
        docker-compose -f docker-compose.multi-tenant.yml ps
    fi
    
    echo ""
    log_info "Useful commands:"
    echo "  View logs: docker-compose -f docker-compose.${DEPLOYMENT_TYPE}-tenant.yml logs -f"
    echo "  Stop services: docker-compose -f docker-compose.${DEPLOYMENT_TYPE}-tenant.yml down"
    echo "  Restart services: docker-compose -f docker-compose.${DEPLOYMENT_TYPE}-tenant.yml restart"
}

# Stop deployment
stop_deployment() {
    log_info "Stopping deployment..."
    
    cd "$PROJECT_ROOT"
    
    if [ "$DEPLOYMENT_TYPE" = "single" ]; then
        docker-compose -f docker-compose.single-tenant.yml down
    else
        docker-compose -f docker-compose.multi-tenant.yml down
    fi
    
    log_success "Deployment stopped"
}

# Main deployment logic
main() {
    cd "$PROJECT_ROOT"
    
    log_info "HR Bot Multi-Tenant Deployment Script"
    log_info "Deployment Type: $DEPLOYMENT_TYPE"
    log_info "Tenant Selection: $TENANT_SELECTION"
    echo ""
    
    # Handle special commands
    case "${1:-}" in
        "stop")
            stop_deployment
            exit 0
            ;;
        "status")
            show_status
            exit 0
            ;;
        "help"|"-h"|"--help")
            show_help
            exit 0
            ;;
    esac
    
    # Normal deployment flow
    check_prerequisites
    setup_directories
    setup_multi_tenant_config
    build_image
    
    case $DEPLOYMENT_TYPE in
        "single")
            deploy_single_tenant
            ;;
        "multi")
            deploy_multi_tenant
            ;;
        *)
            log_error "Invalid deployment type: $DEPLOYMENT_TYPE"
            log_info "Valid options: single, multi"
            exit 1
            ;;
    esac
    
    echo ""
    show_status
    
    log_success "Deployment completed successfully!"
}

# Show help
show_help() {
    echo "HR Bot Multi-Tenant Deployment Script"
    echo ""
    echo "Usage: $0 [DEPLOYMENT_TYPE] [TENANT_SELECTION]"
    echo ""
    echo "DEPLOYMENT_TYPE:"
    echo "  single  - Single container with dynamic tenant detection"
    echo "  multi   - Separate containers per tenant (default)"
    echo ""
    echo "TENANT_SELECTION (for multi-tenant only):"
    echo "  jordan  - Deploy Jordan tenant only"
    echo "  us      - Deploy US tenant only"
    echo "  both    - Deploy both tenants (default)"
    echo ""
    echo "Special commands:"
    echo "  $0 stop     - Stop all services"
    echo "  $0 status   - Show deployment status"
    echo "  $0 help     - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 multi both          # Deploy both tenants in separate containers"
    echo "  $0 single              # Deploy single container with dynamic detection"
    echo "  $0 multi jordan        # Deploy Jordan tenant only"
    echo "  $0 stop                # Stop all services"
}

# Run main function
main "$@" 