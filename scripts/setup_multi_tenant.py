#!/usr/bin/env python3
"""
Multi-tenant setup script for HR chatbot.

This script:
1. Creates tenant-specific directory structures
2. Migrates existing data to Jordan tenant (backward compatibility)
3. Sets up US tenant structure
4. Provides guidance for deployment
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

def setup_tenant_directories():
    """Create tenant-specific directory structures."""
    
    print("🏗️  Setting up multi-tenant directory structure...")
    
    # Define tenant directories
    tenants = {
        'jordan': {
            'knowledge': 'data/knowledge/jordan',
            'embeddings': 'data/embeddings/jordan'
        },
        'us': {
            'knowledge': 'data/knowledge/us', 
            'embeddings': 'data/embeddings/us'
        }
    }
    
    # Create directories
    for tenant, paths in tenants.items():
        for dir_type, path in paths.items():
            Path(path).mkdir(parents=True, exist_ok=True)
            print(f"✅ Created {tenant} {dir_type} directory: {path}")
    
    return tenants

def migrate_existing_data():
    """Migrate existing data to Jordan tenant for backward compatibility."""
    
    print("\n📦 Migrating existing data to Jordan tenant...")
    
    # Check if old structure exists
    old_knowledge = Path("data/knowledge")
    old_embeddings = Path("data/embeddings")
    
    jordan_knowledge = Path("data/knowledge/jordan")
    jordan_embeddings = Path("data/embeddings/jordan")
    
    # Migrate knowledge files
    if old_knowledge.exists() and old_knowledge.is_dir():
        files_to_migrate = [f for f in old_knowledge.iterdir() if f.is_file()]
        if files_to_migrate:
            print(f"   Moving {len(files_to_migrate)} knowledge files to Jordan tenant...")
            for file in files_to_migrate:
                dest = jordan_knowledge / file.name
                if not dest.exists():
                    shutil.move(str(file), str(dest))
                    print(f"   ✅ Moved {file.name}")
                else:
                    print(f"   ⚠️  Skipped {file.name} (already exists)")
    
    # Migrate embeddings files
    if old_embeddings.exists() and old_embeddings.is_dir():
        files_to_migrate = [f for f in old_embeddings.iterdir() if f.is_file()]
        if files_to_migrate:
            print(f"   Moving {len(files_to_migrate)} embedding files to Jordan tenant...")
            for file in files_to_migrate:
                dest = jordan_embeddings / file.name
                if not dest.exists():
                    shutil.move(str(file), str(dest))
                    print(f"   ✅ Moved {file.name}")
                else:
                    print(f"   ⚠️  Skipped {file.name} (already exists)")

def create_tenant_config_examples():
    """Create example tenant configuration files."""
    
    print("\n📝 Creating tenant configuration examples...")
    
    # Jordan example
    jordan_config = """# Jordan Tenant Configuration
# Set TENANT_REGION=jordan in environment or create this file as 'tenant.conf'
jordan
"""
    
    # US example  
    us_config = """# US Tenant Configuration
# Set TENANT_REGION=us in environment or create this file as 'tenant.conf'
us
"""
    
    # Save examples
    Path("tenant.conf.jordan.example").write_text(jordan_config)
    Path("tenant.conf.us.example").write_text(us_config)
    
    print("   ✅ Created tenant.conf.jordan.example")
    print("   ✅ Created tenant.conf.us.example")

def create_deployment_guide():
    """Create deployment guide for multi-tenant setup."""
    
    print("\n📚 Creating deployment guide...")
    
    guide = """# Multi-Tenant HR Chatbot Deployment Guide

## Overview
The HR chatbot now supports multiple tenants (Jordan and US teams) with:
- Separate knowledge bases
- Tenant-specific features (NOI enabled for Jordan only)
- Tenant-specific HR support URLs

## Directory Structure
```
data/
├── knowledge/
│   ├── jordan/          # Jordan team knowledge base
│   │   ├── *.docx
│   │   └── *.pdf
│   └── us/              # US team knowledge base
│       ├── *.docx
│       └── *.pdf
├── embeddings/
│   ├── jordan/          # Jordan team embeddings
│   └── us/              # US team embeddings
```

## Deployment Options

### Option 1: Environment Variable (Recommended)
Set the tenant region using environment variable:

```bash
# For Jordan deployment
export TENANT_REGION=jordan

# For US deployment  
export TENANT_REGION=us
```

### Option 2: Configuration File
Create a `tenant.conf` file in the root directory:

```bash
# For Jordan
echo "jordan" > tenant.conf

# For US
echo "us" > tenant.conf
```

### Option 3: Subdomain Detection (Future)
Configure DNS to route:
- `hr-jordan.example.com` → Jordan tenant
- `hr-us.example.com` → US tenant

## Docker Deployment

### Single Tenant per Container (Recommended)
```bash
# Jordan deployment
docker run -e TENANT_REGION=jordan hr-teams-bot:latest

# US deployment
docker run -e TENANT_REGION=us hr-teams-bot:latest
```

### Multi-tenant Single Container
```bash
# Use tenant detection methods (subdomain, config file, etc.)
docker run hr-teams-bot:latest
```

## Knowledge Base Setup

### Jordan Team
1. Copy existing knowledge base files to `data/knowledge/jordan/`
2. Restart the application to rebuild embeddings

### US Team
1. Copy US-specific knowledge base files to `data/knowledge/us/`
2. Remove any NOI-related documents (feature is disabled for US)
3. Restart the application to build embeddings

## Feature Differences

| Feature | Jordan | US |
|---------|--------|-----|
| Notice of Investigation (NOI) | ✅ Enabled | ❌ Disabled |
| Resignation Process | ✅ Enabled | ✅ Enabled |
| Benefits & Policies | ✅ Enabled | ✅ Enabled |
| Medical Insurance | ✅ Enabled | ✅ Enabled |
| 401k | ❌ Not applicable | ✅ Enabled |

## Environment Variables

Required for each tenant:
```bash
# Tenant identification
TENANT_REGION=jordan  # or 'us'

# Microsoft Teams (same for both)
MICROSOFT_APP_ID=your-app-id
MICROSOFT_APP_PASSWORD=your-app-password
TENANT_ID=your-tenant-id
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret

# AWS (same for both)
AWS_REGION=us-west-1
USE_AWS_SECRETS=true

# Google Cloud (same for both)
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

## Monitoring

Each tenant will log with tenant-specific information:
```
2025-06-01 [INFO] hrbot.tenant: Detected tenant: HR Jordan Team
2025-06-01 [INFO] hrbot.vector_store: Using tenant-specific embeddings directory: data/embeddings/jordan
2025-06-01 [INFO] hrbot.chunking: Reloading knowledge base for tenant HR Jordan Team
```

## Troubleshooting

### Wrong Tenant Detected
1. Check `TENANT_REGION` environment variable
2. Verify `tenant.conf` file contents
3. Check application logs for tenant detection

### Knowledge Base Not Loading
1. Verify files exist in correct tenant directory
2. Check file permissions
3. Review application logs for processing errors

### NOI Feature Issues
- Jordan: Should work normally
- US: Should show "NOI not available" message

## Migration from Single Tenant

If migrating from single-tenant setup:
1. Run `python scripts/setup_multi_tenant.py --migrate`
2. Set `TENANT_REGION=jordan` (maintains backward compatibility)
3. Test Jordan deployment
4. Set up US tenant separately

## Best Practices

1. **Separate Deployments**: Deploy each tenant separately for better isolation
2. **Environment Variables**: Use environment variables for tenant detection
3. **Knowledge Base Management**: Keep tenant knowledge bases completely separate
4. **Monitoring**: Monitor each tenant separately
5. **Testing**: Test both tenants thoroughly before production deployment
"""
    
    Path("MULTI_TENANT_DEPLOYMENT.md").write_text(guide)
    print("   ✅ Created MULTI_TENANT_DEPLOYMENT.md")

def main():
    """Main setup function."""
    
    parser = argparse.ArgumentParser(description="Set up multi-tenant HR chatbot")
    parser.add_argument("--migrate", action="store_true", help="Migrate existing data to Jordan tenant")
    parser.add_argument("--tenant", choices=["jordan", "us"], help="Set up specific tenant only")
    
    args = parser.parse_args()
    
    print("🚀 Multi-Tenant HR Chatbot Setup")
    print("=" * 40)
    
    # Set up directories
    tenants = setup_tenant_directories()
    
    # Migrate existing data if requested
    if args.migrate:
        migrate_existing_data()
    
    # Create configuration examples
    create_tenant_config_examples()
    
    # Create deployment guide
    create_deployment_guide()
    
    print("\n🎉 Multi-tenant setup complete!")
    print("\nNext steps:")
    print("1. Copy knowledge base files to appropriate tenant directories:")
    print("   - Jordan: data/knowledge/jordan/")
    print("   - US: data/knowledge/us/")
    print("2. Set TENANT_REGION environment variable or create tenant.conf file")
    print("3. Restart the application to build tenant-specific embeddings")
    print("4. Review MULTI_TENANT_DEPLOYMENT.md for detailed deployment guide")
    
    if args.tenant:
        print(f"\n🎯 To run {args.tenant} tenant:")
        print(f"   export TENANT_REGION={args.tenant}")
        print(f"   python -m hrbot.api")

if __name__ == "__main__":
    main()