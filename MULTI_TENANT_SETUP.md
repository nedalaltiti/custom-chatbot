# 🚀 Multi-Tenant Setup Guide

## ✅ Migration Completed!

Your data has been successfully migrated to a multi-tenant structure:
- ✅ Backup created: `data_backup_[timestamp]`
- ✅ Jordan documents moved to: `data/knowledge/jordan/`
- ✅ Jordan embeddings moved to: `data/embeddings/jordan/`
- ✅ US directories created (empty, ready for content)

## 📋 Required Steps to Complete Setup

### 1. **Update Your .env File**

Add these lines to your `.env` file:

```bash
# For Jordan deployment:
TENANT_REGION=jordan
APP_NAME=HR Teams Bot - Jordan
NOI_ENABLED=true

# For US deployment (use these instead):
# TENANT_REGION=us
# APP_NAME=HR Teams Bot - US
# NOI_ENABLED=false
# HR_SUPPORT_URL=https://hrsupport.usclarity.com/support/us
```

### 2. **Add US Documents** (if needed)

Place US-specific HR documents in:
```
data/knowledge/us/
```

Example documents:
- US_Benefits_Guide.pdf
- 401k_Information.pdf
- US_Leave_Policy.pdf
- US_Employee_Handbook.pdf

### 3. **Rebuild Embeddings**

```bash
# For Jordan (already has documents):
TENANT_REGION=jordan python scripts/seed_knowledge.py data/knowledge/jordan

# For US (after adding documents):
TENANT_REGION=us python scripts/seed_knowledge.py data/knowledge/us
```

### 4. **Deploy Multi-Tenant**

**Option A: Separate containers (recommended)**
```bash
docker-compose -f docker-compose.multi-tenant.yml up -d
```
- Jordan: http://localhost:3978
- US: http://localhost:3979

**Option B: Single container with detection**
```bash
docker-compose -f docker-compose.single-tenant.yml up -d
```
- Both tenants on port 3978 (detected by header)

## 🧪 Test Your Setup

### Test Jordan tenant:
```bash
curl -H "X-Tenant-Region: jordan" http://localhost:3978/health/diagnostic | jq '.tenant'
```

### Test US tenant:
```bash
curl -H "X-Tenant-Region: us" http://localhost:3978/health/diagnostic | jq '.tenant'
```

### Test NOI (Jordan only):
```bash
# Should work for Jordan
curl -X POST http://localhost:3978/api/messages/ \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Region: jordan" \
  -d '{"text": "What is NOI?", "from": {"id": "test"}, "conversation": {"id": "test"}, "serviceUrl": "http://test"}'

# Should be disabled for US
curl -X POST http://localhost:3978/api/messages/ \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Region: us" \
  -d '{"text": "What is NOI?", "from": {"id": "test"}, "conversation": {"id": "test"}, "serviceUrl": "http://test"}'
```

## 🔍 Verify Structure

Check your new multi-tenant structure:
```bash
tree data/ -L 3
```

Should show:
```
data/
├── embeddings/
│   ├── jordan/    (contains .npz and .pkl files)
│   └── us/        (empty)
├── knowledge/
│   ├── jordan/    (contains 17 .docx files)
│   └── us/        (contains README.md and sample)
└── prompts/
    ├── jordan/    (empty)
    └── us/        (empty)
```

## 📝 Important Notes

1. **Jordan** is the default tenant when `TENANT_REGION` is not specified
2. **NOI** feature is only available for Jordan tenant
3. Each tenant has separate:
   - Knowledge base documents
   - Embeddings (vector store)
   - HR support URLs
   - Feature flags

## 🆘 Troubleshooting

If embeddings are not found:
```bash
# Check embeddings directory
ls -la data/embeddings/jordan/
ls -la data/embeddings/us/

# Rebuild if needed
TENANT_REGION=jordan python scripts/seed_knowledge.py data/knowledge/jordan
```

If tenant detection fails:
```bash
# Check environment variable
echo $TENANT_REGION

# Test with explicit header
curl -v -H "X-Tenant-Region: jordan" http://localhost:3978/health
``` 