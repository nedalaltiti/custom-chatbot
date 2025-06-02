# 🏢 Multi-Tenant Deployment Guide

This guide covers deploying the HR Teams Bot with multi-tenant support for Jordan and US teams.

## 📋 **Overview**

The multi-tenant system supports:
- **Jordan Team**: Full features including NOI (Notice of Investigation)
- **US Team**: Standard HR features without NOI functionality
- Tenant-specific knowledge bases and embeddings
- Isolated data storage per tenant
- Flexible deployment options

## 🚀 **Deployment Options**

### **Option 1: Separate Containers per Tenant (Recommended)**

```bash
# Deploy separate containers
docker-compose -f docker-compose.multi-tenant.yml up -d

# Access endpoints:
# Jordan Team: http://localhost:3978
# US Team: http://localhost:3979
# Load Balancer: http://localhost (if nginx enabled)
```

**Benefits:**
- Complete isolation between tenants
- Independent scaling
- Easier troubleshooting
- Different resource allocation per tenant

### **Option 2: Single Container with Dynamic Detection**

```bash
# Deploy single multi-tenant container
docker-compose -f docker-compose.single-tenant.yml up -d

# Tenant detected via:
# - X-Tenant-Region header (from nginx)
# - TENANT_REGION environment variable
# - Subdomain detection
```

**Benefits:**
- Lower resource usage
- Simpler infrastructure
- Dynamic tenant switching
- Cost-effective for smaller deployments

## 📂 **Directory Structure Setup**

```bash
# Run setup script to create tenant directories
python scripts/setup_multi_tenant.py

# Manual setup:
mkdir -p data/knowledge/{jordan,us}
mkdir -p data/embeddings/{jordan,us}
mkdir -p data/prompts/{jordan,us}
```

## 🔧 **Environment Configuration**

### **Shared Environment Variables (.env)**

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=hrbot
DB_PASSWORD=your_secure_password

# AWS Configuration
USE_AWS_SECRETS=true
AWS_REGION=us-west-1
AWS_DB_SECRET_NAME=chatbot-clarity-db-dev-postgres
AWS_GEMINI_SECRET_NAME=genai-gemini-vertex-prod-api

# Teams Configuration (shared or tenant-specific)
MICROSOFT_APP_ID=your_shared_app_id
MICROSOFT_APP_PASSWORD=your_shared_app_password
TENANT_ID=your_tenant_id

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1

# Performance Settings
PERFORMANCE_ENABLE_STREAMING=true
PERFORMANCE_CACHE_EMBEDDINGS=true
PERFORMANCE_MIN_STREAMING_LENGTH=200
```

### **Jordan-Specific Variables (.env.jordan)**

```bash
# Tenant Configuration
TENANT_REGION=jordan
APP_NAME=HR Teams Bot - Jordan

# Features
NOI_ENABLED=true

# Teams Configuration (if different)
MICROSOFT_APP_ID_JORDAN=jordan_specific_app_id
TEAMS_TENANT_ID_JORDAN=jordan_tenant_id

# Database (if using separate schemas)
DB_NAME=hrbot_jordan
```

### **US-Specific Variables (.env.us)**

```bash
# Tenant Configuration
TENANT_REGION=us
APP_NAME=HR Teams Bot - US

# Features
NOI_ENABLED=false

# HR Support
HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/us

# Teams Configuration (if different)
MICROSOFT_APP_ID_US=us_specific_app_id
TEAMS_TENANT_ID_US=us_tenant_id

# Database (if using separate schemas)
DB_NAME=hrbot_us
```

## 🐳 **Docker Deployment Commands**

### **Build and Deploy Separate Containers**

```bash
# Build the image
docker build -t hrbot:latest .

# Deploy both tenants
docker-compose -f docker-compose.multi-tenant.yml up -d

# Check status
docker-compose -f docker-compose.multi-tenant.yml ps

# View logs
docker-compose -f docker-compose.multi-tenant.yml logs -f hrbot-jordan
docker-compose -f docker-compose.multi-tenant.yml logs -f hrbot-us
```

### **Single Container Deployment**

```bash
# Build and deploy
docker-compose -f docker-compose.single-tenant.yml up -d

# Check status
docker-compose -f docker-compose.single-tenant.yml ps

# View logs with tenant filtering
docker-compose -f docker-compose.single-tenant.yml logs -f hrbot | grep jordan
```

## 🌐 **Nginx Load Balancer Setup**

### **Subdomain-Based Routing**

```nginx
# In nginx-multi-tenant.conf
map $host $tenant_region {
    default "jordan";
    ~^jordan\. "jordan";
    ~^us\. "us";
    ~^usa\. "us";
}
```

### **Path-Based Routing (Alternative)**

```nginx
location /jordan/ {
    proxy_set_header X-Tenant-Region jordan;
    proxy_pass http://hrbot_backend/;
}

location /us/ {
    proxy_set_header X-Tenant-Region us;
    proxy_pass http://hrbot_backend/;
}
```

## 📊 **Monitoring and Health Checks**

### **Health Check Endpoints**

```bash
# Jordan tenant health
curl http://localhost:3978/health

# US tenant health  
curl http://localhost:3979/health

# Multi-tenant health (with header)
curl -H "X-Tenant-Region: jordan" http://localhost:3978/health
curl -H "X-Tenant-Region: us" http://localhost:3978/health
```

### **Tenant-Specific Status**

```bash
# Check tenant detection
curl -H "X-Tenant-Region: jordan" http://localhost:3978/health/diagnostic
curl -H "X-Tenant-Region: us" http://localhost:3978/health/diagnostic
```

## 📁 **Knowledge Base Management**

### **Upload Documents per Tenant**

```bash
# Jordan documents
curl -X POST \
  -H "X-Tenant-Region: jordan" \
  -F "file=@jordan_policy.pdf" \
  http://localhost:3978/admin/upload

# US documents
curl -X POST \
  -H "X-Tenant-Region: us" \
  -F "file=@us_policy.pdf" \
  http://localhost:3978/admin/upload
```

### **Reload Knowledge Base per Tenant**

```bash
# Jordan knowledge base
curl -X POST \
  -H "X-Tenant-Region: jordan" \
  http://localhost:3978/admin/knowledge/reload

# US knowledge base
curl -X POST \
  -H "X-Tenant-Region: us" \
  http://localhost:3978/admin/knowledge/reload
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Tenant Detection Not Working**
   ```bash
   # Check environment variables
   docker exec hrbot-jordan env | grep TENANT
   
   # Check headers are being passed
   curl -v -H "X-Tenant-Region: jordan" http://localhost/health
   ```

2. **Missing Knowledge Base**
   ```bash
   # Check tenant directories exist
   docker exec hrbot-jordan ls -la /app/data/knowledge/jordan/
   
   # Run setup script
   docker exec hrbot-jordan python scripts/setup_multi_tenant.py
   ```

3. **NOI Not Working for Jordan**
   ```bash
   # Check NOI feature flag
   curl -H "X-Tenant-Region: jordan" \
        http://localhost/admin/config | jq '.features.noi_enabled'
   ```

### **Debugging Commands**

```bash
# Check tenant configuration
docker exec hrbot-jordan python -c "
from src.hrbot.config.tenant import get_current_tenant
print(get_current_tenant())
"

# Test tenant detection
docker exec hrbot-jordan python -c "
from src.hrbot.config.tenant import TenantManager
print(TenantManager.detect_tenant())
"

# Verify NOI settings
docker exec hrbot-jordan python -c "
from src.hrbot.utils.noi import NOIAccessChecker
checker = NOIAccessChecker()
print(f'NOI enabled: {checker.tenant.supports_noi}')
"
```

## 📈 **Scaling and Performance**

### **Horizontal Scaling**

```yaml
# In docker-compose.multi-tenant.yml
services:
  hrbot-jordan:
    deploy:
      replicas: 3
    
  hrbot-us:
    deploy:
      replicas: 2
```

### **Resource Allocation**

```yaml
# Different resources per tenant
hrbot-jordan:
  deploy:
    resources:
      limits:
        memory: 3G
        cpus: '1.5'

hrbot-us:
  deploy:
    resources:
      limits:
        memory: 2G
        cpus: '1.0'
```

## 🔒 **Security Considerations**

1. **Tenant Isolation**: Ensure data isolation between tenants
2. **Access Control**: Use different Teams app IDs per tenant if needed
3. **Network Segmentation**: Consider separate networks for sensitive tenants
4. **Audit Logging**: Enable tenant-specific audit logs

## 🔄 **Migration from Single-Tenant**

1. **Backup existing data**:
   ```bash
   docker exec hrbot cp -r /app/data /app/data.backup
   ```

2. **Run migration script**:
   ```bash
   python scripts/setup_multi_tenant.py --migrate-existing
   ```

3. **Update environment variables**
4. **Deploy new multi-tenant configuration**
5. **Verify tenant detection and features** 