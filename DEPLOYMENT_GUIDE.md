# HR Teams Bot Deployment Guide

This guide covers deployment of the HR Teams Bot using the unified Docker Compose configuration that supports both single instance and multi-app deployments.

## Overview

The HR Teams Bot supports two deployment modes:
- **Single Instance**: Deploy one regional instance (Jordan or US)
- **Multi-App**: Deploy both instances simultaneously with nginx proxy

## Prerequisites

### System Requirements
- Docker 20.10+ with Docker Compose v2
- 4GB+ RAM available
- 10GB+ disk space
- Network access to:
  - Microsoft Teams API endpoints
  - Google Cloud Vertex AI
  - AWS (if using AWS Secrets Manager)

### Required Files
- `.env.jo` - Jordan instance configuration
- `.env.us` - US instance configuration  
- `instances.yaml` - App instance definitions
- `docker-compose.yml` - Unified deployment configuration

## Quick Start

### 1. Environment Setup

Create environment files based on the examples:

```bash
# Copy and customize environment files
cp env.jo.example .env.jo
cp env.us.example .env.us

# Edit with your specific configuration
nano .env.jo
nano .env.us
```

### 2. Single Instance Deployment

Deploy Jordan instance only:
```bash
./scripts/deploy.sh single jo
```

Deploy US instance only:
```bash
./scripts/deploy.sh single us
```

### 3. Multi-App Deployment

Deploy both instances with nginx proxy:
```bash
./scripts/deploy.sh multi
```

## Deployment Modes

### Single Instance Mode

**Use Case**: Deploy one regional instance for specific geography

**Services Started**:
- `hrbot-jo` or `hrbot-us` (depending on selection)
- `postgres` (shared database)
- `redis` (shared cache)

**Ports**:
- Jordan: `3978` (configurable via `JO_PORT`)
- US: `3979` (configurable via `US_PORT`)

**Example**:
```bash
# Deploy Jordan instance on custom port
JO_PORT=8080 ./scripts/deploy.sh single jo

# Check status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs hrbot-jo
```

### Multi-App Mode

**Use Case**: Deploy both instances for multi-regional support

**Services Started**:
- `hrbot-jo` (Jordan instance)
- `hrbot-us` (US instance)
- `postgres` (shared database)
- `redis` (shared cache)
- `nginx` (reverse proxy)

**Ports**:
- Jordan: `3978`
- US: `3979`
- Nginx HTTP: `80`
- Nginx HTTPS: `443`

**Example**:
```bash
# Deploy all instances
./scripts/deploy.sh multi

# Check health
./scripts/deploy.sh health

# View specific service logs
./scripts/deploy.sh logs nginx
```

## Configuration

### Environment Variables

#### Global Configuration
```bash
# Docker Compose settings
COMPOSE_PROJECT_NAME=hrbot
DOCKER_BUILDKIT=1

# Port configuration
JO_PORT=3978
US_PORT=3979
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Database settings
POSTGRES_DB=hrbot
POSTGRES_USER=hrbot
POSTGRES_PASSWORD=hrbot123
POSTGRES_PORT=5432

# Redis settings
REDIS_PORT=6379
```

#### Instance-Specific (.env.jo / .env.us)
```bash
# Teams App Configuration
APP_ID=your-teams-app-id
APP_PASSWORD=your-teams-app-password
TENANT_ID=your-azure-tenant-id

# AWS Configuration (if using AWS Secrets Manager)
USE_AWS_SECRETS=true
AWS_REGION=us-west-1
AWS_DB_SECRET_NAME=chatbot-clarity-db-dev-postgres
AWS_GEMINI_SECRET_NAME=genai-gemini-vertex-prod-api

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Performance Settings
ENABLE_STREAMING=true
CACHE_EMBEDDINGS=true
SESSION_IDLE_MINUTES=30
```

### Docker Compose Profiles

The unified `docker-compose.yml` uses profiles to control which services are started:

- `default`: Jordan instance only (default profile)
- `jo`: Jordan instance with infrastructure
- `us`: US instance with infrastructure  
- `multi-app`: Both instances with nginx proxy

## Management Commands

### Deployment
```bash
# Single instance deployments
./scripts/deploy.sh single jo          # Deploy Jordan only
./scripts/deploy.sh single us          # Deploy US only

# Multi-app deployment
./scripts/deploy.sh multi              # Deploy both with proxy
```

### Monitoring
```bash
./scripts/deploy.sh status             # Service status
./scripts/deploy.sh health             # Health checks
./scripts/deploy.sh logs [service]     # View logs
```

### Maintenance
```bash
./scripts/deploy.sh restart [service]  # Restart services
./scripts/deploy.sh stop               # Stop all services
./scripts/deploy.sh build              # Rebuild images
./scripts/deploy.sh cleanup            # Full cleanup
```

### Utilities
```bash
./scripts/deploy.sh shell jo           # Open shell in container
./scripts/deploy.sh backup             # Backup data volumes
./scripts/deploy.sh restore backup.tar.gz  # Restore from backup
```

## Manual Docker Compose Commands

If you prefer direct Docker Compose commands:

### Single Instance
```bash
# Jordan instance
docker compose --profile jo up -d

# US instance  
docker compose --profile us up -d
```

### Multi-App
```bash
# All instances with proxy
docker compose --profile multi-app up -d
```

### Service Management
```bash
# View status
docker compose ps

# View logs
docker compose logs -f hrbot-jo

# Restart service
docker compose restart hrbot-us

# Stop all
docker compose down
```

## Health Checks

### Automated Health Checks

All services include health checks:
- **Application**: HTTP endpoint `/health`
- **Database**: PostgreSQL connection test
- **Redis**: Redis ping command
- **Nginx**: HTTP response check

### Manual Health Verification

```bash
# Check application health
curl http://localhost:3978/health
curl http://localhost:3979/health

# Check database
docker compose exec postgres pg_isready -U hrbot

# Check redis
docker compose exec redis redis-cli ping

# Comprehensive health check
./scripts/deploy.sh health
```

## Troubleshooting

### Common Issues

#### 1. Port Conflicts
```bash
# Check what's using the port
lsof -i :3978

# Use custom ports
JO_PORT=8080 US_PORT=8081 ./scripts/deploy.sh multi
```

#### 2. Environment File Issues
```bash
# Validate environment files exist
ls -la .env.*

# Check for required variables
grep -E "^(APP_ID|APP_PASSWORD)" .env.jo
```

#### 3. Service Health Issues
```bash
# Check service logs
./scripts/deploy.sh logs hrbot-jo

# Check container status
docker compose ps

# Restart unhealthy services
./scripts/deploy.sh restart hrbot-jo
```

#### 4. Database Connection Issues
```bash
# Check database logs
./scripts/deploy.sh logs postgres

# Test database connection
docker compose exec hrbot-jo python -c "
from hrbot.db.session import AsyncSession
import asyncio
async def test():
    async with AsyncSession() as session:
        print('Database connection successful')
asyncio.run(test())
"
```

### Log Analysis

```bash
# Application logs
./scripts/deploy.sh logs hrbot-jo | grep ERROR

# Database logs
./scripts/deploy.sh logs postgres

# All services
./scripts/deploy.sh logs

# Follow logs in real-time
docker compose logs -f
```

## Production Considerations

### Security
- Use strong passwords in environment files
- Enable SSL/TLS for nginx in production
- Restrict network access using Docker networks
- Use secrets management (AWS Secrets Manager)
- Run containers as non-root user (already configured)

### Performance
- Allocate sufficient resources (4GB+ RAM)
- Use SSD storage for better I/O performance
- Monitor resource usage with `docker stats`
- Configure log rotation to prevent disk space issues

### Backup Strategy
```bash
# Regular backups
./scripts/deploy.sh backup

# Automated backup (add to cron)
0 2 * * * /path/to/scripts/deploy.sh backup
```

### Monitoring
- Set up health check monitoring
- Monitor application logs for errors
- Track resource usage over time
- Set up alerts for service failures

## Advanced Configuration

### Custom Nginx Configuration

Edit `docker/nginx/nginx.conf` for custom proxy settings:
- SSL certificate configuration
- Rate limiting adjustments
- Custom routing rules
- Security headers

### Resource Limits

Add resource limits to `docker-compose.yml`:
```yaml
services:
  hrbot-jo:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.25'
```

### Persistent Storage

Data is persisted in Docker volumes:
- `postgres_data`: Database data
- `redis_data`: Cache data
- `hrbot_logs_jo`: Jordan instance logs
- `hrbot_logs_us`: US instance logs

## Support

For deployment issues:
1. Check the troubleshooting section above
2. Review application logs: `./scripts/deploy.sh logs`
3. Verify environment configuration
4. Check Docker and system resources
5. Consult the application documentation 