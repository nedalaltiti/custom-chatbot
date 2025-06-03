# Multi-App Architecture Setup

This HR Bot uses a **multi-app architecture** where multiple app registrations exist within the same Azure AD tenant. Each app instance serves different regions or purposes while sharing the same tenant infrastructure.

## Architecture Overview

```
Single Azure AD Tenant (TENANT_ID)
├── Jordan HR Bot App (JORDAN_APP_ID)
│   ├── Knowledge Base: data/knowledge/jordan/
│   ├── Embeddings: data/embeddings/jordan/
│   ├── Prompts: data/prompts/jordan/
│   └── Features: NOI enabled
│
└── US HR Bot App (US_APP_ID)
    ├── Knowledge Base: data/knowledge/us/
    ├── Embeddings: data/embeddings/us/
    ├── Prompts: data/prompts/us/
    └── Features: NOI disabled
```

## Key Concepts

- **Single Tenant**: All app instances share the same Azure AD tenant
- **Multiple App Registrations**: Each region/instance has its own app registration
- **Shared Infrastructure**: Common codebase, database, and services
- **App-Specific Data**: Each app has its own knowledge base and embeddings
- **Feature Flags**: Different features can be enabled per app instance

## Environment Variables

### Common Variables (Same for all apps)
```bash
# Azure AD Tenant (shared)
TENANT_ID=your-tenant-id
CLIENT_ID=your-service-principal-id
CLIENT_SECRET=your-service-principal-secret

# Database (shared)
USE_AWS_SECRETS=true
AWS_DB_SECRET_NAME=chatbot-clarity-db-dev-postgres

# Gemini AI (shared)
AWS_GEMINI_SECRET_NAME=genai-gemini-vertex-prod-api
```

### App Instance Selection
```bash
# Select which app instance to run
APP_INSTANCE=jordan  # or "us"
```

### App-Specific Variables (if not using default)
```bash
# Jordan App
JORDAN_APP_ID=jordan-app-id
JORDAN_APP_PASSWORD=jordan-app-password

# US App
US_APP_ID=us-app-id
US_APP_PASSWORD=us-app-password
```

## Running Different App Instances

### Option 1: Environment Variable
```bash
# Run Jordan instance
export APP_INSTANCE=jordan
python -m uvicorn hrbot.api.app:app --port 3978

# Run US instance
export APP_INSTANCE=us
python -m uvicorn hrbot.api.app:app --port 3979
```

### Option 2: Docker Compose
```yaml
services:
  jordan-bot:
    image: hrbot:latest
    environment:
      - APP_INSTANCE=jordan
      - MICROSOFT_APP_ID=${JORDAN_APP_ID}
      - MICROSOFT_APP_PASSWORD=${JORDAN_APP_PASSWORD}
    ports:
      - "3978:3978"

  us-bot:
    image: hrbot:latest
    environment:
      - APP_INSTANCE=us
      - MICROSOFT_APP_ID=${US_APP_ID}
      - MICROSOFT_APP_PASSWORD=${US_APP_PASSWORD}
    ports:
      - "3979:3978"
```

## Adding a New App Instance

1. **Register New App in Azure AD**
   ```bash
   # Create app registration in your tenant
   az ad app create --display-name "HR Bot - Region Name"
   ```

2. **Update app_config.py**
   ```python
   AppInstance.NEW_REGION = "new_region"
   
   APP_CONFIGS[AppInstance.NEW_REGION] = AppConfig(
       name="New Region HR Assistant",
       instance=AppInstance.NEW_REGION,
       app_id=os.getenv("NEW_REGION_APP_ID"),
       app_password=os.getenv("NEW_REGION_APP_PASSWORD"),
       knowledge_base_dir=Path("data/knowledge/new_region"),
       embeddings_dir=Path("data/embeddings/new_region"),
       prompt_dir=Path("data/prompts/new_region"),
       hr_support_url="https://hrsupport.newregion.com",
       supports_noi=False,
   )
   ```

3. **Create Data Directories**
   ```bash
   mkdir -p data/knowledge/new_region
   mkdir -p data/embeddings/new_region
   mkdir -p data/prompts/new_region
   ```

4. **Upload Knowledge Base**
   ```bash
   # Copy documents to new region's knowledge base
   cp documents/*.pdf data/knowledge/new_region/
   
   # Reload knowledge base for new instance
   APP_INSTANCE=new_region python scripts/seed_knowledge.py
   ```

## Management Commands

### Reload Knowledge Base for Specific App
```python
from hrbot.core.chunking import reload_knowledge_base

# Reload Jordan knowledge base
await reload_knowledge_base(app_instance="jordan")

# Reload US knowledge base
await reload_knowledge_base(app_instance="us")
```

### Upload Document to Specific App
```python
from hrbot.core.chunking import save_uploaded_file

# Upload to Jordan instance
await save_uploaded_file(file, app_instance="jordan")
```

## Customizing Prompts for App Instances

Each app instance can have its own customized prompts to reflect regional differences, legal requirements, or company policies.

### Prompt Structure

Create a `prompt.py` file in the app's prompt directory:

```
data/prompts/
├── jordan/
│   ├── __init__.py
│   └── prompt.py
└── us/
    ├── __init__.py
    └── prompt.py
```

### Prompt File Format

Each prompt file should contain:

```python
# Required components
BASE_SYSTEM = "..."      # System prompt with instructions
FLOW_RULES = "..."       # Response formatting rules
TEMPLATE = "..."         # Final prompt template

# Required function
def build(parts: dict) -> str:
    """Build the complete prompt"""
    return TEMPLATE.format(
        system=parts.get("system", BASE_SYSTEM),
        flow_rules=FLOW_RULES,
        context=parts["context"],
        history=parts.get("history", ""),
        query=parts["query"],
    )
```

### Example Customizations

**Jordan Prompt** (data/prompts/jordan/prompt.py):
- References Jordanian labor law
- Uses 1-month notice period
- Includes NOI-related guidance

**US Prompt** (data/prompts/us/prompt.py):
- References US employment laws (at-will, FMLA, ADA)
- Uses 2-week notice period
- Uses US terminology (PTO vs annual leave)

### Fallback Behavior

If an app instance doesn't have a custom prompt file, the system will fall back to the default prompt at `src/hrbot/core/rag/prompt.py`.

### Testing Prompts

To test app-specific prompts:

```bash
# Run with Jordan prompts
APP_INSTANCE=jordan python -m uvicorn hrbot.api.app:app

# Run with US prompts
APP_INSTANCE=us python -m uvicorn hrbot.api.app:app
```

## Best Practices

1. **Consistent Naming**: Use clear, consistent names for app instances
2. **Feature Flags**: Use feature flags for region-specific functionality
3. **Knowledge Isolation**: Keep knowledge bases separate per instance
4. **Shared Resources**: Share common resources (DB, AI models) across instances
5. **Monitoring**: Use app instance tags in logs and metrics

## Troubleshooting

### Wrong App Instance Loading
```bash
# Check current app instance
echo $APP_INSTANCE

# Verify in logs
grep "app instance" logs/app.log
```

### Knowledge Base Not Found
```bash
# Check directories exist
ls -la data/knowledge/
ls -la data/embeddings/

# Verify permissions
chmod -R 755 data/
```

### App Registration Issues
```bash
# Test app credentials
az ad app show --id $JORDAN_APP_ID
az ad app show --id $US_APP_ID
``` 