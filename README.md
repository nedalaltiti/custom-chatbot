# HR Teams Bot

A sophisticated multi-regional HR assistant powered by Google Gemini AI and RAG (Retrieval-Augmented Generation) technology, designed for Microsoft Teams integration.

## 🌟 Features

- **Multi-Regional Support**: Separate instances for Jordan (jo) and US markets
- **Intelligent RAG**: Context-aware responses using company knowledge base
- **Real-time Streaming**: Fast, responsive conversations with Microsoft Teams streaming
- **Smart Session Management**: Automatic greeting cards and conversation flow
- **Crisis Response**: Region-aware safety interventions with local emergency numbers
- **Feedback System**: Integrated user feedback collection and analytics
- **Production Ready**: Comprehensive deployment, monitoring, and backup solutions

## 🚀 Quick Start

### Prerequisites

- Docker 20.10+ with Docker Compose v2
- 4GB+ RAM available
- Microsoft Teams app registration
- Google Cloud project with Vertex AI enabled

### 1. Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd custom-chatbot

# Copy and customize environment files
cp env.jo.example .env.jo
cp env.us.example .env.us

# Edit with your configuration
nano .env.jo  # Jordan instance settings
nano .env.us  # US instance settings
```

### 2. Deploy Single Instance

```bash
# Deploy Jordan instance
./scripts/deploy.sh single jo

# Or deploy US instance
./scripts/deploy.sh single us
```

### 3. Deploy Multi-App (Both Instances)

```bash
# Deploy both instances with nginx proxy
./scripts/deploy.sh multi
```

### 4. Verify Deployment

```bash
# Check service status
./scripts/deploy.sh status

# Check health
./scripts/deploy.sh health

# View logs
./scripts/deploy.sh logs
```

## 📋 Deployment Options

### Single Instance Mode
- **Use Case**: Deploy one regional instance
- **Services**: App instance + Database + Redis
- **Ports**: 3978 (jo) or 3979 (us)

### Multi-App Mode  
- **Use Case**: Deploy both regions simultaneously
- **Services**: Both app instances + Database + Redis + Nginx proxy
- **Ports**: 3978 (jo), 3979 (us), 80/443 (nginx)

## 🛠️ Management Commands

```bash
# Deployment
./scripts/deploy.sh single jo          # Deploy Jordan only
./scripts/deploy.sh single us          # Deploy US only  
./scripts/deploy.sh multi              # Deploy both instances

# Monitoring
./scripts/deploy.sh status             # Service status
./scripts/deploy.sh health             # Health checks
./scripts/deploy.sh logs [service]     # View logs

# Maintenance
./scripts/deploy.sh restart [service]  # Restart services
./scripts/deploy.sh stop               # Stop all services
./scripts/deploy.sh build              # Rebuild images
./scripts/deploy.sh cleanup            # Full cleanup

# Utilities
./scripts/deploy.sh shell jo           # Open shell in container
./scripts/deploy.sh backup             # Backup data volumes
./scripts/deploy.sh restore backup.tar.gz  # Restore from backup
```

## 🏗️ Architecture

### Multi-Regional Design
- **Jordan Instance**: Supports NOI (Notice of Investigation), local crisis resources
- **US Instance**: US-specific features and emergency contacts
- **Shared Infrastructure**: Database, Redis, and core services

### Technology Stack
- **Backend**: FastAPI with async/await
- **AI**: Google Gemini 2.0 Flash with Vertex AI
- **Vector Store**: Custom NumPy-based with FAISS support
- **Database**: PostgreSQL with async SQLAlchemy
- **Cache**: Redis for embeddings and session data
- **Deployment**: Docker Compose with profiles

### Key Components
- **RAG Engine**: Intelligent document retrieval and response generation
- **Teams Adapter**: Microsoft Teams streaming protocol implementation
- **Session Tracker**: Smart conversation state management
- **Content Classification**: LLM-powered conversation flow analysis
- **Crisis Response**: Region-aware safety intervention system

## 📁 Project Structure

```
custom-chatbot/
├── src/hrbot/                 # Application source code
│   ├── api/                   # FastAPI routers and endpoints
│   ├── core/                  # RAG engine and document processing
│   ├── infrastructure/        # External service adapters
│   ├── services/              # Business logic services
│   └── utils/                 # Utility functions
├── data/                      # Instance-specific data
│   ├── knowledge/             # Knowledge base documents
│   │   ├── jo/               # Jordan documents
│   │   └── us/               # US documents
│   ├── embeddings/           # Vector embeddings
│   └── prompts/              # LLM prompts
├── scripts/                   # Deployment and utility scripts
├── docker/                    # Docker configuration
├── .env.jo                   # Jordan instance environment
├── .env.us                   # US instance environment
├── docker-compose.yml        # Unified deployment configuration
└── instances.yaml            # App instance definitions
```

## ⚙️ Configuration

### Environment Variables

Each instance has its own environment file with clean variable names:

```bash
# Teams App Configuration
APP_ID=your-teams-app-id
APP_PASSWORD=your-teams-app-password
TENANT_ID=your-azure-tenant-id

# AWS Configuration (optional)
USE_AWS_SECRETS=true
AWS_REGION=us-west-1

# Google Cloud Configuration  
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Performance Settings
ENABLE_STREAMING=true
CACHE_EMBEDDINGS=true
SESSION_IDLE_MINUTES=30
```

### Docker Compose Profiles

The unified `docker-compose.yml` uses profiles for flexible deployment:

- `jo`: Jordan instance with infrastructure
- `us`: US instance with infrastructure
- `multi-app`: Both instances with nginx proxy
- `default`: Jordan instance (default)

## 🔧 Development

### Local Development Setup

```bash
# Install dependencies
poetry install

# Set up environment
cp .env.jo .env
export APP_INSTANCE=jo

# Run locally
poetry run uvicorn hrbot.api.app:app --reload --port 3978
```

### Testing

```bash
# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=hrbot

# Load testing
python scripts/performance_stress_test.py
```

### Adding Knowledge Base Content

```bash
# Add documents to instance-specific directories
cp new-policy.pdf data/knowledge/jo/
cp new-policy.pdf data/knowledge/us/

# Restart to reload knowledge base
./scripts/deploy.sh restart hrbot-jo
```

## 📊 Monitoring & Observability

### Health Checks
- Application: `/health` endpoint
- Database: PostgreSQL connection test
- Redis: Ping command
- Services: Docker health checks

### Logging
- Structured JSON logging
- Instance-specific log volumes
- Centralized log aggregation ready

### Metrics
- Response time tracking
- Vector search performance
- User interaction analytics
- Resource usage monitoring

## 🔒 Security

### Production Security Features
- Non-root container execution
- Secrets management via AWS Secrets Manager
- Network isolation with Docker networks
- Input validation and sanitization
- Rate limiting and request throttling

### Crisis Response
- Region-aware emergency contacts
- Local crisis hotline numbers
- Automatic safety intervention
- Escalation procedures

## 🚀 Production Deployment

### Prerequisites
- Docker Swarm or Kubernetes cluster
- Load balancer (nginx, ALB, etc.)
- SSL certificates
- Monitoring stack (Prometheus, Grafana)

### Deployment Steps
1. Configure environment files
2. Set up secrets management
3. Deploy infrastructure services
4. Deploy application instances
5. Configure load balancer
6. Set up monitoring and alerts

### Backup Strategy
```bash
# Automated daily backups
0 2 * * * /path/to/scripts/deploy.sh backup

# Restore from backup
./scripts/deploy.sh restore /path/to/backup.tar.gz
```

## Architecture Overview

This bot uses a **multi-app architecture** where multiple app registrations exist within the same Azure AD tenant:

- **Single Azure AD Tenant**: All app instances share the same tenant infrastructure
- **Multiple App Registrations**: Each region/purpose has its own app registration (Jordan HR Bot, US HR Bot, etc.)
- **Shared Resources**: Common database, AI models, and services
- **App-Specific Data**: Each app has its own knowledge base and embeddings

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

- **Intelligent Q&A**: Uses Gemini AI with RAG for accurate, context-aware responses
- **Multi-App Support**: Deploy multiple bot instances for different regions/purposes
- **Real-time Streaming**: Fast responses with Microsoft Teams streaming API
- **Smart Feedback**: Intelligent feedback collection based on conversation flow
- **AWS Integration**: Secure credential management with AWS Secrets Manager
- **Document Processing**: Automatic knowledge base updates from PDF/DOCX files
- **Session Management**: Intelligent conversation tracking and memory
- **Feature Flags**: App-specific features (e.g., NOI for Jordan only)

---

## ✨ Key Features

| | |
|---|---|
| **Conversational HR assistant** | Warm, empathetic replies; automatically links to "Open an HR support request ➜ ..." when needed |
| **Microsoft Teams native** | Shows typing indicators, progressive ("streaming") answers and Adaptive Cards |
| **Retrieval-Augmented Generation** | Searches your own HR PDFs / docs, then lets Gemini craft an answer citing the sources |
| **Feedback-aware** | Collects 1–5 ★ ratings + free-text feedback to keep improving the bot |
| **Self-contained** | Pure FastAPI + NumPy, easier to deploy and debug |

## 🆘 Support
For support and questions:
- Check the [Troubleshooting Guide](docs/troubleshooting.md)
- Review application logs: `./scripts/deploy.sh logs`
- Contact the development team
---

## 🧠 How RAG Works

<pre>
  User question
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ 1️⃣ Similarity search                                │
│   • Vertex AI embeddings (768-dim)                  │
│   • NumPy/ndarray vector store (disk-backed)        │
└───────────────────────┬─────────────────────────────┘
                        │ top-k relevant chunks
                        ▼
┌─────────────────────────────────────────────────────┐
│ 2️⃣ Prompt builder                                   │
│   SYSTEM + FLOW_RULES + KNOWLEDGE + HISTORY + USER  │
└───────────────────────┬─────────────────────────────┘
                        │ final prompt
                        ▼
┌─────────────────────────────────────────────────────┐
│ 3️⃣ Google Gemini                                    │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│ 4️⃣ Answer (with citations) → Teams (streamed)       │
└─────────────────────────────────────────────────────┘
</pre>
**Built with ❤️ for efficient HR support across multiple regions**