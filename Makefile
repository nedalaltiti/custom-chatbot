# Makefile for HR Teams Bot Docker Operations
# Usage: make <target>

.PHONY: help build up down logs clean test deploy scale backup status

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE_FILE := docker-compose.yml
APP_NAME := hrbot
BACKUP_DIR := ./backups

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

## Help target
help: ## Show this help message
	@echo "$(BLUE)HR Teams Bot Docker Commands$(NC)"
	@echo "$(YELLOW)Usage: make <target>$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## Development Commands
dev: ## Start development environment with local database
	@echo "$(BLUE)Starting development environment...$(NC)"
	docker-compose --profile development up -d
	@make status

dev-logs: ## View development logs
	@echo "$(BLUE)Following development logs...$(NC)"
	docker-compose --profile development logs -f $(APP_NAME)

dev-shell: ## Open shell in development container
	@echo "$(BLUE)Opening shell in $(APP_NAME) container...$(NC)"
	docker-compose --profile development exec $(APP_NAME) /bin/bash

dev-db: ## Connect to development database
	@echo "$(BLUE)Connecting to development database...$(NC)"
	docker-compose --profile development exec postgres psql -U chatbot_user -d az_airbyte

## Production Commands
prod: ## Start production environment with nginx
	@echo "$(BLUE)Starting production environment...$(NC)"
	docker-compose --profile production up -d
	@make status

prod-logs: ## View production logs
	@echo "$(BLUE)Following production logs...$(NC)"
	docker-compose --profile production logs -f

deploy: ## Deploy to production (build + start)
	@echo "$(BLUE)Deploying to production...$(NC)"
	@make build
	@make prod
	@echo "$(GREEN)Deployment complete!$(NC)"

## Build Commands
build: ## Build the application image
	@echo "$(BLUE)Building $(APP_NAME) image...$(NC)"
	docker-compose build $(APP_NAME)

rebuild: ## Rebuild the application image without cache
	@echo "$(BLUE)Rebuilding $(APP_NAME) image without cache...$(NC)"
	docker-compose build --no-cache $(APP_NAME)

pull: ## Pull latest images
	@echo "$(BLUE)Pulling latest images...$(NC)"
	docker-compose pull

## Service Management
up: ## Start all services (default profile)
	@echo "$(BLUE)Starting all services...$(NC)"
	docker-compose up -d
	@make status

down: ## Stop all services
	@echo "$(BLUE)Stopping all services...$(NC)"
	docker-compose down

restart: ## Restart all services
	@echo "$(BLUE)Restarting all services...$(NC)"
	docker-compose restart
	@make status

scale: ## Scale the application (usage: make scale REPLICAS=3)
	@echo "$(BLUE)Scaling $(APP_NAME) to $(REPLICAS) replicas...$(NC)"
	docker-compose up -d --scale $(APP_NAME)=$(REPLICAS)

## Monitoring Commands
status: ## Show service status
	@echo "$(BLUE)Service Status:$(NC)"
	@docker-compose ps
	@echo ""
	@echo "$(BLUE)Health Check:$(NC)"
	@curl -f http://localhost:3978/health/ 2>/dev/null && echo "$(GREEN)✅ Application healthy$(NC)" || echo "$(RED)❌ Application unhealthy$(NC)"

logs: ## View logs for all services
	@echo "$(BLUE)Following logs for all services...$(NC)"
	docker-compose logs -f

app-logs: ## View application logs only
	@echo "$(BLUE)Following $(APP_NAME) logs...$(NC)"
	docker-compose logs -f $(APP_NAME)

nginx-logs: ## View nginx logs (production)
	@echo "$(BLUE)Following nginx logs...$(NC)"
	docker-compose --profile production logs -f nginx

stats: ## Show container resource usage
	@echo "$(BLUE)Container Resource Usage:$(NC)"
	@docker stats --no-stream

## Database Commands
db-init: ## Initialize database schema
	@echo "$(BLUE)Initializing database schema...$(NC)"
	docker-compose exec $(APP_NAME) python scripts/setup_database.py

db-seed: ## Seed knowledge base
	@echo "$(BLUE)Seeding knowledge base...$(NC)"
	docker-compose exec $(APP_NAME) python scripts/seed_knowledge.py data/knowledge

db-backup: ## Backup database
	@echo "$(BLUE)Backing up database...$(NC)"
	@mkdir -p $(BACKUP_DIR)
	@docker-compose exec postgres pg_dump -U chatbot_user az_airbyte > $(BACKUP_DIR)/db-backup-$(shell date +%Y%m%d-%H%M%S).sql
	@echo "$(GREEN)Database backup created in $(BACKUP_DIR)$(NC)"

## Testing Commands
test: ## Run tests in container
	@echo "$(BLUE)Running tests...$(NC)"
	docker-compose exec $(APP_NAME) python -m pytest tests/

test-health: ## Test application health endpoints
	@echo "$(BLUE)Testing health endpoints...$(NC)"
	@curl -f http://localhost:3978/health/ && echo "$(GREEN)✅ Health endpoint OK$(NC)" || echo "$(RED)❌ Health endpoint failed$(NC)"
	@curl -f http://localhost:3978/health/database && echo "$(GREEN)✅ Database health OK$(NC)" || echo "$(RED)❌ Database health failed$(NC)"

## Maintenance Commands
clean: ## Clean up containers, networks, and volumes
	@echo "$(YELLOW)WARNING: This will remove all containers, networks, and volumes!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		echo "$(BLUE)Cleaning up...$(NC)"; \
		docker-compose down -v --remove-orphans; \
		docker system prune -f; \
		echo "$(GREEN)Cleanup complete!$(NC)"; \
	else \
		echo ""; \
		echo "$(YELLOW)Cleanup cancelled$(NC)"; \
	fi

clean-images: ## Remove application images
	@echo "$(BLUE)Removing $(APP_NAME) images...$(NC)"
	docker rmi $(shell docker images -q $(APP_NAME)) 2>/dev/null || true

backup: ## Backup application data and logs
	@echo "$(BLUE)Creating backup...$(NC)"
	@mkdir -p $(BACKUP_DIR)
	@docker run --rm -v hrbot-data:/data -v $(shell pwd)/$(BACKUP_DIR):/backup alpine tar czf /backup/hrbot-data-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@docker run --rm -v hrbot-logs:/logs -v $(shell pwd)/$(BACKUP_DIR):/backup alpine tar czf /backup/hrbot-logs-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /logs .
	@echo "$(GREEN)Backup created in $(BACKUP_DIR)$(NC)"

## Security Commands
security-scan: ## Run security scan on images
	@echo "$(BLUE)Running security scan...$(NC)"
	@which docker-scout >/dev/null 2>&1 && docker scout quickview $(APP_NAME):latest || echo "$(YELLOW)docker-scout not installed. Install with: curl -sSfL https://raw.githubusercontent.com/docker/scout-cli/main/install.sh | sh$(NC)"

ssl-cert: ## Generate self-signed SSL certificate for development
	@echo "$(BLUE)Generating SSL certificate...$(NC)"
	@mkdir -p docker/nginx/ssl
	@openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout docker/nginx/ssl/server.key \
		-out docker/nginx/ssl/server.crt \
		-subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
	@echo "$(GREEN)SSL certificate generated in docker/nginx/ssl/$(NC)"

## Configuration Commands
config: ## Validate docker-compose configuration
	@echo "$(BLUE)Validating docker-compose configuration...$(NC)"
	@docker-compose config

env-check: ## Check environment variables
	@echo "$(BLUE)Environment Variables:$(NC)"
	@echo "USE_AWS_SECRETS: $${USE_AWS_SECRETS:-not set}"
	@echo "AWS_REGION: $${AWS_REGION:-not set}"
	@echo "DEBUG: $${DEBUG:-not set}"
	@echo "PORT: $${PORT:-not set}"

## Quick Setup Commands
setup-dev: ## Quick development setup
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@make build
	@make dev
	@make db-init
	@echo "$(GREEN)Development environment ready!$(NC)"
	@echo "$(YELLOW)Access the application at: http://localhost:3978$(NC)"

setup-prod: ## Quick production setup
	@echo "$(BLUE)Setting up production environment...$(NC)"
	@make ssl-cert
	@make build
	@make prod
	@echo "$(GREEN)Production environment ready!$(NC)"
	@echo "$(YELLOW)Access the application at: https://localhost$(NC)"

## Documentation
docs: ## Open documentation
	@echo "$(BLUE)Opening documentation...$(NC)"
	@open DOCKER_README.md 2>/dev/null || xdg-open DOCKER_README.md 2>/dev/null || echo "$(YELLOW)Please open DOCKER_README.md manually$(NC)"