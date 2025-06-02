#!/usr/bin/env python3
"""
Migration script to convert single-tenant data structure to multi-tenant.

This script will:
1. Create tenant-specific directories for Jordan and US
2. Move existing data to Jordan tenant (as default)
3. Create empty US tenant directories
4. Provide instructions for next steps
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_backup():
    """Create a backup of the existing data directory."""
    data_dir = Path("data")
    if not data_dir.exists():
        logger.error("Data directory not found!")
        return False
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"data_backup_{timestamp}")
    
    logger.info(f"Creating backup at {backup_dir}...")
    shutil.copytree(data_dir, backup_dir)
    logger.info("✅ Backup created successfully")
    return True

def create_tenant_structure():
    """Create the multi-tenant directory structure."""
    logger.info("Creating multi-tenant directory structure...")
    
    # Define tenant directories
    tenants = ["jordan", "us"]
    subdirs = ["knowledge", "embeddings", "prompts"]
    
    for tenant in tenants:
        for subdir in subdirs:
            tenant_path = Path(f"data/{subdir}/{tenant}")
            tenant_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created: {tenant_path}")
    
    # Create other necessary directories
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    Path("configs").mkdir(parents=True, exist_ok=True)
    logger.info("✅ Multi-tenant directory structure created")

def migrate_existing_data():
    """Migrate existing data to Jordan tenant."""
    logger.info("Migrating existing data to Jordan tenant...")
    
    # Move knowledge documents
    knowledge_src = Path("data/knowledge")
    knowledge_dst = Path("data/knowledge/jordan")
    
    if knowledge_src.exists():
        # Move all files from knowledge root to jordan subdirectory
        for file_path in knowledge_src.glob("*"):
            if file_path.is_file():
                dst_path = knowledge_dst / file_path.name
                logger.info(f"Moving {file_path.name} to Jordan knowledge base...")
                shutil.move(str(file_path), str(dst_path))
    
    # Move embeddings
    embeddings_src = Path("data/embeddings")
    embeddings_dst = Path("data/embeddings/jordan")
    
    if embeddings_src.exists():
        # Move all files from embeddings root to jordan subdirectory
        for file_path in embeddings_src.glob("*"):
            if file_path.is_file():
                dst_path = embeddings_dst / file_path.name
                logger.info(f"Moving {file_path.name} to Jordan embeddings...")
                shutil.move(str(file_path), str(dst_path))
    
    logger.info("✅ Data migration completed")

def create_us_sample_data():
    """Create sample US tenant data."""
    logger.info("Creating sample US tenant configuration...")
    
    # Create a README for US knowledge base
    us_readme = Path("data/knowledge/us/README.md")
    us_readme.write_text("""# US HR Knowledge Base

This directory should contain US-specific HR documents such as:
- US Benefits Guide
- 401(k) Information
- US Leave Policies
- US Employee Handbook
- Healthcare Plans
- US Labor Law Compliance

Note: NOI (Notice of Investigation) is not available for US team.
""")
    
    # Create a sample document
    us_sample = Path("data/knowledge/us/US_Welcome.txt")
    us_sample.write_text("""Welcome to US HR Knowledge Base

This is a placeholder document for the US HR team.
Please add your US-specific HR documents to this directory.

Key differences from Jordan tenant:
- No NOI (Notice of Investigation) functionality
- US-specific benefits and policies
- Different HR support URL
""")
    
    logger.info("✅ US tenant sample data created")

def update_env_files():
    """Create tenant-specific environment variable examples."""
    logger.info("Creating environment configuration examples...")
    
    # Check if .env exists
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning(".env file not found - creating template...")
        env_content = """# Multi-Tenant Configuration

# Default tenant (when not specified)
DEFAULT_TENANT_REGION=jordan

# Tenant detection method
TENANT_DETECTION_METHOD=auto

# Jordan-specific settings (when running Jordan instance)
# TENANT_REGION=jordan
# NOI_ENABLED=true

# US-specific settings (when running US instance)  
# TENANT_REGION=us
# NOI_ENABLED=false
# HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/us

# Shared settings
DB_HOST=localhost
DB_PORT=5432
DB_USER=hrbot
DB_PASSWORD=your_password

# Teams Configuration
MICROSOFT_APP_ID=your_app_id
MICROSOFT_APP_PASSWORD=your_app_password
TENANT_ID=your_tenant_id

# Google Cloud
GOOGLE_CLOUD_PROJECT=your_project
GOOGLE_CLOUD_LOCATION=us-central1

# AWS (if using)
USE_AWS_SECRETS=false
AWS_REGION=us-west-1
"""
        env_path.write_text(env_content)
        logger.info("Created .env template")
    
    # Create example env files for each tenant
    jordan_env = Path(".env.jordan.example")
    jordan_env.write_text("""# Jordan Tenant Environment Variables
TENANT_REGION=jordan
APP_NAME=HR Teams Bot - Jordan
NOI_ENABLED=true
HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/home
""")
    
    us_env = Path(".env.us.example")
    us_env.write_text("""# US Tenant Environment Variables
TENANT_REGION=us
APP_NAME=HR Teams Bot - US
NOI_ENABLED=false
HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/us
""")
    
    logger.info("✅ Environment configuration examples created")

def main():
    """Run the migration process."""
    logger.info("🚀 Starting multi-tenant migration...")
    logger.info("=" * 60)
    
    # Step 1: Create backup
    if not create_backup():
        logger.error("Failed to create backup. Aborting migration.")
        return
    
    # Step 2: Create tenant structure
    create_tenant_structure()
    
    # Step 3: Migrate existing data
    migrate_existing_data()
    
    # Step 4: Create US sample data
    create_us_sample_data()
    
    # Step 5: Update environment files
    update_env_files()
    
    logger.info("=" * 60)
    logger.info("✅ Migration completed successfully!")
    logger.info("")
    logger.info("📋 Next steps:")
    logger.info("1. Review the migrated data in data/knowledge/jordan/")
    logger.info("2. Add US-specific documents to data/knowledge/us/")
    logger.info("3. Update your .env file with TENANT_REGION=jordan (for Jordan deployment)")
    logger.info("4. For US deployment, use TENANT_REGION=us")
    logger.info("5. Rebuild embeddings for each tenant:")
    logger.info("   - TENANT_REGION=jordan python scripts/seed_knowledge.py data/knowledge/jordan")
    logger.info("   - TENANT_REGION=us python scripts/seed_knowledge.py data/knowledge/us")
    logger.info("")
    logger.info("🔄 To deploy both tenants:")
    logger.info("   docker-compose -f docker-compose.multi-tenant.yml up -d")
    logger.info("")
    logger.info("🔙 Backup created at: data_backup_<timestamp>")

if __name__ == "__main__":
    main() 