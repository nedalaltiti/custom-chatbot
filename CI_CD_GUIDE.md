# CI/CD & Scalability Guide

This guide demonstrates how the new **configuration-driven architecture** makes the HR Bot extremely **CI/CD friendly** and **easily scalable** to new regions.

## 🎯 **Key Benefits**

✅ **Zero Code Changes**: Add new regions by just updating configuration
✅ **Standardized Deployment**: Same pipeline for all instances  
✅ **Auto-Provisioning**: Directories and configs created automatically
✅ **Pattern-Based Detection**: Flexible hostname matching
✅ **Environment Agnostic**: Works in any deployment environment

## 🏗️ **Architecture Overview**

```
instances.yaml          # Single source of truth
      ↓
AppInstanceManager      # Auto-loads and manages instances  
      ↓
Hostname Detection      # Pattern-based routing
      ↓
Auto-Provisioning      # Creates directories automatically
      ↓  
Environment Loading     # Loads appropriate .env file
```

## 📝 **Adding a New Region** 

Adding a new region requires **ZERO code changes**:

### 1. Update Configuration (instances.yaml)
```yaml
instances:
  jo:
    # ... existing config
  us:
    # ... existing config
  
  # 🆕 NEW REGION - Just add this!
  uk:
    name: "UK HR Assistant"
    supports_noi: false
    hr_support_url: "https://hrsupport.uk.usclarity.com/support/home"
    hostname_patterns:
      - "hr-chatbot-uk-*"
      - "*-uk-*"
    default: false
```

### 2. Create Environment File (.env.uk)
```bash
# UK Instance Environment
APP_ID=<uk-teams-app-id>
APP_PASSWORD=<uk-teams-app-password>
# ... rest same as other instances
```

### 3. Deploy
```bash
# Deploy to UK hostname - everything else is automatic!
kubectl apply -f uk-deployment.yaml
# HOSTNAME: hr-chatbot-uk-prod.usclaritytech.com
```

**That's it!** The system will:
- ✅ Detect "uk" from hostname automatically
- ✅ Create `data/knowledge/uk/`, `data/embeddings/uk/`, `data/prompts/uk/` 
- ✅ Load UK-specific configuration
- ✅ Use UK environment variables

## 🚀 **CI/CD Pipeline Templates**

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy HR Bot

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      instance:
        description: 'Instance to deploy (jo, us, uk, eu)'
        required: true
        default: 'jo'
        type: choice
        options:
        - jo
        - us
        - uk
        - eu

jobs:
  deploy:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        # Deploy to multiple instances in parallel
        instance: ${{ github.event.inputs.instance && [github.event.inputs.instance] || ['jo', 'us'] }}
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Environment
      run: |
        # Copy instance-specific environment
        cp env.${{ matrix.instance }}.example .env.${{ matrix.instance }}
        
        # Substitute secrets
        sed -i 's/<${{ matrix.instance }}-teams-app-id>/${{ secrets[format('{0}_APP_ID', matrix.instance)] }}/g' .env.${{ matrix.instance }}
        sed -i 's/<${{ matrix.instance }}-teams-app-password>/${{ secrets[format('{0}_APP_PASSWORD', matrix.instance)] }}/g' .env.${{ matrix.instance }}
    
    - name: Build Docker Image
      run: |
        docker build -t hrbot:${{ matrix.instance }}-${{ github.sha }} .
    
    - name: Deploy to Kubernetes
      run: |
        # Deploy using instance-specific hostname
        envsubst < k8s/deployment-template.yaml | kubectl apply -f -
      env:
        INSTANCE: ${{ matrix.instance }}
        HOSTNAME: hr-chatbot-${{ matrix.instance }}-prod.usclaritytech.com
        IMAGE_TAG: ${{ matrix.instance }}-${{ github.sha }}
```

### Kubernetes Deployment Template

```yaml
# k8s/deployment-template.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hrbot-${INSTANCE}
  labels:
    app: hrbot
    instance: ${INSTANCE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hrbot
      instance: ${INSTANCE}
  template:
    metadata:
      labels:
        app: hrbot
        instance: ${INSTANCE}
    spec:
      containers:
      - name: hrbot
        image: hrbot:${IMAGE_TAG}
        ports:
        - containerPort: 3978
        env:
        - name: HOSTNAME
          value: ${HOSTNAME}
        envFrom:
        - configMapRef:
            name: hrbot-${INSTANCE}-config
        - secretRef:
            name: hrbot-${INSTANCE}-secret

---
apiVersion: v1
kind: Service
metadata:
  name: hrbot-${INSTANCE}
spec:
  selector:
    app: hrbot
    instance: ${INSTANCE}
  ports:
  - port: 80
    targetPort: 3978

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hrbot-${INSTANCE}
spec:
  tls:
  - hosts:
    - ${HOSTNAME}
    secretName: hrbot-tls
  rules:
  - host: ${HOSTNAME}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: hrbot-${INSTANCE}
            port:
              number: 80
```

### Terraform Module (Infrastructure as Code)

```hcl
# modules/hrbot-instance/main.tf
variable "instance_id" {
  description = "Instance identifier (jo, us, uk, etc.)"
  type        = string
}

variable "hostname" {
  description = "Hostname for the instance"
  type        = string
}

variable "app_id" {
  description = "Teams App ID for this instance"
  type        = string
  sensitive   = true
}

variable "app_password" {
  description = "Teams App Password for this instance"
  type        = string
  sensitive   = true
}

# ConfigMap for instance-specific settings
resource "kubernetes_config_map" "hrbot_config" {
  metadata {
    name = "hrbot-${var.instance_id}-config"
  }

  data = {
    APP_NAME = "${title(var.instance_id)} HR Teams Bot"
    DEBUG    = "false"
    HOST     = "0.0.0.0"
    PORT     = "3978"
  }
}

# Secret for instance-specific credentials
resource "kubernetes_secret" "hrbot_secret" {
  metadata {
    name = "hrbot-${var.instance_id}-secret"
  }

  data = {
    APP_ID       = var.app_id
    APP_PASSWORD = var.app_password
  }

  type = "Opaque"
}

# Deployment
resource "kubernetes_deployment" "hrbot" {
  metadata {
    name = "hrbot-${var.instance_id}"
    labels = {
      app      = "hrbot"
      instance = var.instance_id
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app      = "hrbot"
        instance = var.instance_id
      }
    }

    template {
      metadata {
        labels = {
          app      = "hrbot"
          instance = var.instance_id
        }
      }

      spec {
        container {
          name  = "hrbot"
          image = "hrbot:latest"
          
          port {
            container_port = 3978
          }

          env {
            name  = "HOSTNAME"
            value = var.hostname
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.hrbot_config.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.hrbot_secret.metadata[0].name
            }
          }
        }
      }
    }
  }
}

# Service
resource "kubernetes_service" "hrbot" {
  metadata {
    name = "hrbot-${var.instance_id}"
  }

  spec {
    selector = {
      app      = "hrbot"
      instance = var.instance_id
    }

    port {
      port        = 80
      target_port = 3978
    }
  }
}

# Ingress
resource "kubernetes_ingress_v1" "hrbot" {
  metadata {
    name = "hrbot-${var.instance_id}"
  }

  spec {
    tls {
      hosts       = [var.hostname]
      secret_name = "hrbot-tls"
    }

    rule {
      host = var.hostname

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.hrbot.metadata[0].name
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}
```

### Using the Terraform Module

```hcl
# main.tf
module "hrbot_jo" {
  source = "./modules/hrbot-instance"
  
  instance_id  = "jo"
  hostname     = "hr-chatbot-jo-prod.usclaritytech.com"
  app_id       = var.jo_app_id
  app_password = var.jo_app_password
}

module "hrbot_us" {
  source = "./modules/hrbot-instance"
  
  instance_id  = "us"
  hostname     = "hr-chatbot-us-prod.usclaritytech.com"
  app_id       = var.us_app_id
  app_password = var.us_app_password
}

# 🆕 Adding UK instance is just this!
module "hrbot_uk" {
  source = "./modules/hrbot-instance"
  
  instance_id  = "uk"
  hostname     = "hr-chatbot-uk-prod.usclaritytech.com"
  app_id       = var.uk_app_id
  app_password = var.uk_app_password
}
```

## 🔄 **Deployment Automation Scripts**

### Bash Script for Multiple Instances

```bash
#!/bin/bash
# deploy.sh - Deploy to multiple instances

set -e

INSTANCES=("jo" "us" "uk" "eu")
ENVIRONMENT=${1:-prod}

echo "🚀 Deploying HR Bot to $ENVIRONMENT environment"

for instance in "${INSTANCES[@]}"; do
    echo "📦 Deploying $instance instance..."
    
    # Set hostname based on instance and environment
    hostname="hr-chatbot-${instance}-${ENVIRONMENT}.usclaritytech.com"
    
    # Deploy using environment substitution
    INSTANCE=$instance HOSTNAME=$hostname envsubst < k8s/deployment-template.yaml | kubectl apply -f -
    
    # Wait for rollout
    kubectl rollout status deployment/hrbot-$instance --timeout=300s
    
    echo "✅ $instance instance deployed successfully"
done

echo "🎉 All instances deployed successfully!"
```

### Python Deployment Script

```python
#!/usr/bin/env python3
# deploy.py - Advanced deployment with validation

import yaml
import subprocess
import sys
from pathlib import Path

def load_instances():
    """Load instance configuration."""
    with open('instances.yaml', 'r') as f:
        config = yaml.safe_load(f)
    return config['instances']

def deploy_instance(instance_id, instance_config, environment='prod'):
    """Deploy a single instance."""
    hostname = f"hr-chatbot-{instance_id}-{environment}.usclaritytech.com"
    
    print(f"🚀 Deploying {instance_id} to {hostname}")
    
    # Validate environment file exists
    env_file = Path(f'.env.{instance_id}')
    if not env_file.exists():
        print(f"❌ Environment file missing: {env_file}")
        return False
    
    # Deploy using kubectl with environment substitution
    env = {
        'INSTANCE': instance_id,
        'HOSTNAME': hostname,
        'IMAGE_TAG': f'{instance_id}-latest'
    }
    
    try:
        # Apply configuration
        cmd = ['envsubst'], env=env
        with open('k8s/deployment-template.yaml', 'r') as f:
            result = subprocess.run(
                ['envsubst'], 
                input=f.read(), 
                text=True, 
                capture_output=True,
                env={**subprocess.os.environ, **env}
            )
        
        # Apply to cluster
        subprocess.run(
            ['kubectl', 'apply', '-f', '-'],
            input=result.stdout,
            text=True,
            check=True
        )
        
        # Wait for deployment
        subprocess.run([
            'kubectl', 'rollout', 'status', 
            f'deployment/hrbot-{instance_id}',
            '--timeout=300s'
        ], check=True)
        
        print(f"✅ {instance_id} deployed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to deploy {instance_id}: {e}")
        return False

def main():
    environment = sys.argv[1] if len(sys.argv) > 1 else 'prod'
    instances = load_instances()
    
    success_count = 0
    total_count = len(instances)
    
    for instance_id, config in instances.items():
        if deploy_instance(instance_id, config, environment):
            success_count += 1
    
    print(f"\n🎉 Deployment complete: {success_count}/{total_count} instances successful")
    
    if success_count != total_count:
        sys.exit(1)

if __name__ == '__main__':
    main()
```

## 📊 **Monitoring & Validation**

### Health Check Script

```bash
#!/bin/bash
# health-check.sh - Validate all instances are healthy

instances=($(yq eval '.instances | keys | .[]' instances.yaml))
environment=${1:-prod}

echo "🏥 Health checking all instances in $environment..."

for instance in "${instances[@]}"; do
    hostname="hr-chatbot-${instance}-${environment}.usclaritytech.com"
    
    echo "Checking $instance at $hostname..."
    
    if curl -s -f "https://$hostname/health" > /dev/null; then
        echo "✅ $instance is healthy"
    else
        echo "❌ $instance is unhealthy"
    fi
done
```

### Configuration Validation

```python
#!/usr/bin/env python3
# validate-config.py - Validate instances.yaml

import yaml
import sys
from pathlib import Path

def validate_config():
    """Validate the instances configuration."""
    config_file = Path('instances.yaml')
    
    if not config_file.exists():
        print("❌ instances.yaml not found")
        return False
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML: {e}")
        return False
    
    instances = config.get('instances', {})
    if not instances:
        print("❌ No instances defined")
        return False
    
    # Validate each instance
    for instance_id, instance_config in instances.items():
        print(f"Validating {instance_id}...")
        
        # Required fields
        required_fields = ['name', 'hostname_patterns']
        for field in required_fields:
            if field not in instance_config:
                print(f"❌ {instance_id}: Missing required field '{field}'")
                return False
        
        # Check environment file exists
        env_file = Path(f'.env.{instance_id}')
        if not env_file.exists():
            print(f"⚠️  {instance_id}: Environment file missing: {env_file}")
    
    print("✅ Configuration is valid")
    return True

if __name__ == '__main__':
    if not validate_config():
        sys.exit(1)
```

## 🎉 **Summary: Why This is CI/CD Friendly & Scalable**

| **Feature** | **Benefit** |
|-------------|-------------|
| **Configuration-Driven** | Add new regions without code changes |
| **Pattern-Based Detection** | Flexible hostname routing |
| **Auto-Provisioning** | Directories created automatically |
| **Environment Separation** | Clean `.env.{instance}` files |
| **Template-Based Deployment** | Standardized K8s manifests |
| **Pipeline Automation** | Same CI/CD for all instances |
| **Infrastructure as Code** | Terraform modules for scaling |
| **Health Validation** | Automated testing and monitoring |

### **Adding a New Region (e.g., Canada)**

1. **Update instances.yaml** (1 minute):
   ```yaml
   ca:
     name: "Canada HR Assistant"
     supports_noi: false
     hostname_patterns: ["hr-chatbot-ca-*", "*-ca-*"]
   ```

2. **Create .env.ca** (2 minutes):
   ```bash
   cp env.us.example .env.ca
   # Edit with Canada-specific credentials
   ```

3. **Deploy** (3 minutes):
   ```bash
   ./deploy.sh ca
   # Or use CI/CD pipeline
   ```

**Total time: 6 minutes** to add a completely new region! 🚀

The system handles everything else automatically:
- Creates `data/knowledge/ca/`, `data/embeddings/ca/`, `data/prompts/ca/`
- Routes `hr-chatbot-ca-prod.usclaritytech.com` to Canada instance
- Loads Canada-specific configuration and credentials
- Uses Canada knowledge base and features 