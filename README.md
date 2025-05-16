# HR Teams Chatbot

A conversational AI assistant for HR departments, built with FastAPI, LangChain, and Google's Gemini LLM.

## Features

- **Interactive HR Assistant**: Natural conversational interface for HR inquiries
- **Teams Integration**: Seamlessly works within Microsoft Teams
- **Document Knowledge Base**: Powered by RAG (Retrieval-Augmented Generation)
- **Self-improving**: Collects user feedback for continuous improvement

## RAG Pipeline

This chatbot uses a state-of-the-art RAG (Retrieval-Augmented Generation) pipeline to answer questions based on your organization's HR documents:

1. **Document Processing**
   - Supports PDF, TXT, and Markdown files
   - Preserves document structure during extraction
   - Intelligent chunking with configurable size and overlap

2. **Vector Storage**
   - FAISS-based vector database for semantic search
   - Google Vertex AI embeddings integration
   - Persistent storage with automatic synchronization

3. **Retrieval & Generation**
   - Semantic search based on user queries
   - Smart routing between RAG and pure LLM based on query content
   - Source attribution for trustworthy responses

## Setup & Installation

### Prerequisites

- Python 3.11+
- Google Cloud account with Vertex AI access
- Microsoft Teams Bot registration

### Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd custom-chatbot
```

2. Set up a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install poetry
poetry install
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

## Usage

### Starting the server

```bash
python -m hrbot.api
```

### Managing Documents

Upload HR documents through the admin API:

```bash
curl -X POST -F "file=@hr_policy.pdf" http://localhost:3978/admin/upload
```

### Deploying to Teams

1. Register a Teams bot in the Azure portal
2. Configure the messaging endpoint to your deployed bot URL
3. Configure settings in your .env file

## Development

### Project Structure

- `src/hrbot/`: Main application code
  - `api/`: FastAPI application and endpoints
  - `core/`: Core RAG functionality (chunking, document processing)
  - `infrastructure/`: Integrations and storage
  - `services/`: Business logic and service layer
  - `prompts/`: LLM prompts and templates

### Adding Documents

Add documents to the knowledge base through:
1. Admin API: `/admin/upload` endpoint
2. Direct file placement: Add files to `data/knowledge/` and run `/admin/knowledge/reload`

## License

[MIT License](LICENSE)
