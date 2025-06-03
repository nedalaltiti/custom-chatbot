#!/bin/bash

# HR Teams Bot Deployment Script
# Supports single instance and multi-app deployments using Docker Compose profiles

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

# Default environment variables
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-hrbot}"
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Logging functions
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

# Help function
show_help() {
    cat << EOF
HR Teams Bot Deployment Script

USAGE:
    $0 <command> [options]

COMMANDS:
    Single Instance Deployment:
        single <instance>     Deploy single instance (jo or us)
        
    Multi-App Deployment:
        multi                 Deploy both instances with nginx proxy
        
    Management:
        status               Show status of all services
        logs [service]       Show logs (optionally for specific service)
        restart [service]    Restart services (optionally specific service)
        stop                 Stop all services
        cleanup              Stop and remove all containers, networks, and volumes
        build                Build/rebuild images
        
    Utilities:
        health               Check health of running services
        shell <instance>     Open shell in running container
        backup               Backup data volumes
        restore <backup>     Restore from backup

EXAMPLES:
    # Deploy Jordan instance only
    $0 single jo
    
    # Deploy US instance only  
    $0 single us
    
    # Deploy both instances with nginx proxy
    $0 multi
    
    # Check status
    $0 status
    
    # View logs for specific service
    $0 logs hrbot-jo
    
    # Restart specific service
    $0 restart hrbot-us

ENVIRONMENT VARIABLES:
    COMPOSE_PROJECT_NAME    Project name for Docker Compose (default: hrbot)
    JO_PORT                 Port for Jordan instance (default: 3978)
    US_PORT                 Port for US instance (default: 3979)
    NGINX_HTTP_PORT         HTTP port for nginx (default: 80)
    NGINX_HTTPS_PORT        HTTPS port for nginx (default: 443)

EOF
}

# Validation functions
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available"
        exit 1
    fi
    
    # Check if we're in the right directory
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "docker-compose.yml not found at $COMPOSE_FILE"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Environment validation
validate_env_files() {
    local instance="$1"
    local env_file="$PROJECT_ROOT/.env.$instance"
    
    if [[ ! -f "$env_file" ]]; then
        log_error "Environment file not found: $env_file"
        log_info "Please create $env_file based on env.$instance.example"
        exit 1
    fi
    
    # Check for required variables
    local required_vars=("APP_ID" "APP_PASSWORD")
    for var in "${required_vars[@]}"; do
        if ! grep -q "^$var=" "$env_file"; then
            log_warning "$var not found in $env_file"
        fi
    done
}

# Deployment functions
deploy_single() {
    local instance="$1"
    
    if [[ "$instance" != "jo" && "$instance" != "us" ]]; then
        log_error "Invalid instance: $instance. Must be 'jo' or 'us'"
        exit 1
    fi
    
    log_info "Deploying single instance: $instance"
    
    # Validate environment
    validate_env_files "$instance"
    
    # Set environment variables for the instance
    export APP_INSTANCE="$instance"
    
    # Deploy using profile
    log_info "Starting services with profile: $instance"
    docker compose --profile "$instance" up -d --build
    
    # Wait for health check
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check health
    if check_service_health "hrbot-$instance"; then
        log_success "Single instance deployment completed successfully!"
        log_info "Instance: $instance"
        log_info "Port: $(get_instance_port "$instance")"
        log_info "Health check: http://localhost:$(get_instance_port "$instance")/health"
    else
        log_error "Deployment failed - service is not healthy"
        docker compose --profile "$instance" logs
        exit 1
    fi
}

deploy_multi() {
    log_info "Deploying multi-app configuration..."
    
    # Validate both environment files
    validate_env_files "jo"
    validate_env_files "us"
    
    # Deploy all services with multi-app profile
    log_info "Starting all services with multi-app profile"
    docker compose --profile multi-app up -d --build
    
    # Wait for services to start
    log_info "Waiting for services to be healthy..."
    sleep 15
    
    # Check health of both instances
    local jo_healthy=$(check_service_health "hrbot-jo")
    local us_healthy=$(check_service_health "hrbot-us")
    local nginx_healthy=$(check_service_health "nginx")
    
    if [[ "$jo_healthy" == "true" && "$us_healthy" == "true" && "$nginx_healthy" == "true" ]]; then
        log_success "Multi-app deployment completed successfully!"
        log_info "Jordan instance: http://localhost:${JO_PORT:-3978}"
        log_info "US instance: http://localhost:${US_PORT:-3979}"
        log_info "Nginx proxy: http://localhost:${NGINX_HTTP_PORT:-80}"
        log_info "Health checks:"
        log_info "  - Jordan: http://localhost:${JO_PORT:-3978}/health"
        log_info "  - US: http://localhost:${US_PORT:-3979}/health"
    else
        log_error "Multi-app deployment failed - some services are not healthy"
        docker compose --profile multi-app logs
        exit 1
    fi
}

# Utility functions
get_instance_port() {
    local instance="$1"
    case "$instance" in
        "jo") echo "${JO_PORT:-3978}" ;;
        "us") echo "${US_PORT:-3979}" ;;
        *) echo "3978" ;;
    esac
}

check_service_health() {
    local service="$1"
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if docker compose ps "$service" | grep -q "healthy"; then
            echo "true"
            return 0
        fi
        
        if [[ $attempt -eq $max_attempts ]]; then
            echo "false"
            return 1
        fi
        
        sleep 2
        ((attempt++))
    done
}

# Management functions
show_status() {
    log_info "Service Status:"
    docker compose ps
    
    echo
    log_info "Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
}

show_logs() {
    local service="${1:-}"
    
    if [[ -n "$service" ]]; then
        log_info "Showing logs for service: $service"
        docker compose logs -f "$service"
    else
        log_info "Showing logs for all services"
        docker compose logs -f
    fi
}

restart_services() {
    local service="${1:-}"
    
    if [[ -n "$service" ]]; then
        log_info "Restarting service: $service"
        docker compose restart "$service"
    else
        log_info "Restarting all services"
        docker compose restart
    fi
    
    log_success "Restart completed"
}

stop_services() {
    log_info "Stopping all services..."
    docker compose down
    log_success "All services stopped"
}

cleanup() {
    log_warning "This will remove all containers, networks, and volumes!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up..."
        docker compose down -v --remove-orphans
        docker system prune -f
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

build_images() {
    log_info "Building/rebuilding images..."
    docker compose build --no-cache
    log_success "Build completed"
}

check_health() {
    log_info "Checking health of running services..."
    
    local services=("hrbot-jo" "hrbot-us" "postgres" "redis" "nginx")
    local healthy_count=0
    local total_count=0
    
    for service in "${services[@]}"; do
        if docker compose ps "$service" 2>/dev/null | grep -q "Up"; then
            ((total_count++))
            if check_service_health "$service" == "true"; then
                log_success "$service: Healthy"
                ((healthy_count++))
            else
                log_error "$service: Unhealthy"
            fi
        fi
    done
    
    log_info "Health summary: $healthy_count/$total_count services healthy"
}

open_shell() {
    local instance="$1"
    local container="hrbot-$instance"
    
    if docker compose ps "$container" | grep -q "Up"; then
        log_info "Opening shell in $container..."
        docker compose exec "$container" /bin/bash
    else
        log_error "Container $container is not running"
        exit 1
    fi
}

backup_data() {
    local backup_dir="$PROJECT_ROOT/backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/hrbot_backup_$timestamp.tar.gz"
    
    mkdir -p "$backup_dir"
    
    log_info "Creating backup: $backup_file"
    
    # Backup data volumes
    docker run --rm \
        -v "${COMPOSE_PROJECT_NAME}_postgres_data:/data/postgres:ro" \
        -v "${COMPOSE_PROJECT_NAME}_redis_data:/data/redis:ro" \
        -v "${COMPOSE_PROJECT_NAME}_hrbot_logs_jo:/data/logs_jo:ro" \
        -v "${COMPOSE_PROJECT_NAME}_hrbot_logs_us:/data/logs_us:ro" \
        -v "$backup_dir:/backup" \
        alpine:latest \
        tar czf "/backup/hrbot_backup_$timestamp.tar.gz" -C /data .
    
    log_success "Backup created: $backup_file"
}

restore_data() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi
    
    log_warning "This will overwrite existing data!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restoring from backup: $backup_file"
        
        # Stop services first
        docker compose down
        
        # Restore data
        docker run --rm \
            -v "${COMPOSE_PROJECT_NAME}_postgres_data:/data/postgres" \
            -v "${COMPOSE_PROJECT_NAME}_redis_data:/data/redis" \
            -v "${COMPOSE_PROJECT_NAME}_hrbot_logs_jo:/data/logs_jo" \
            -v "${COMPOSE_PROJECT_NAME}_hrbot_logs_us:/data/logs_us" \
            -v "$(dirname "$backup_file"):/backup:ro" \
            alpine:latest \
            tar xzf "/backup/$(basename "$backup_file")" -C /data
        
        log_success "Restore completed"
    else
        log_info "Restore cancelled"
    fi
}

# Main script logic
main() {
    cd "$PROJECT_ROOT"
    
    case "${1:-}" in
        "single")
            check_prerequisites
            if [[ -z "${2:-}" ]]; then
                log_error "Instance name required for single deployment"
                show_help
                exit 1
            fi
            deploy_single "$2"
            ;;
        "multi")
            check_prerequisites
            deploy_multi
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "${2:-}"
            ;;
        "restart")
            restart_services "${2:-}"
            ;;
        "stop")
            stop_services
            ;;
        "cleanup")
            cleanup
            ;;
        "build")
            check_prerequisites
            build_images
            ;;
        "health")
            check_health
            ;;
        "shell")
            if [[ -z "${2:-}" ]]; then
                log_error "Instance name required for shell access"
                exit 1
            fi
            open_shell "$2"
            ;;
        "backup")
            backup_data
            ;;
        "restore")
            if [[ -z "${2:-}" ]]; then
                log_error "Backup file path required for restore"
                exit 1
            fi
            restore_data "$2"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "Unknown command: ${1:-}"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@" 