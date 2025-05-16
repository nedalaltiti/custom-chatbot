# Gemini API Integration

This document explains how to use the Google Generative AI (Gemini) directly in the HR bot application without relying on LangChain.

## Background

We encountered dependency conflicts between LangChain packages and Google's Generative AI library. To resolve this, we've implemented a direct integration with the Gemini API.

## Setup

1. Install the required dependencies:
   ```bash
   poetry add google-generativeai@0.8.5
   ```

2. Make sure your credentials are set up:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/credentials.json
   ```

3. Update your `.env` file with the appropriate configuration:
   ```
   GEMINI_MODEL_NAME=gemini-2.0-flash-001
   GEMINI_TEMPERATURE=0.0
   GEMINI_MAX_OUTPUT_TOKENS=1024
   ```

## Code Structure

- `gemini_service.py`: Core implementation for Google Generative AI integration
- `processor.py`: Simplified processor that uses the Gemini service

## Usage Example

```python
from hrbot.services.gemini_service import GeminiService
from hrbot.services.processor import ChatProcessor

# Initialize the service
service = GeminiService()

# Test a simple query directly
result = await service.analyze_messages(["What is the capital of France?"])
if result.is_success():
    response = result.unwrap()
    print(f"Response: {response['response']}")

# Use the processor for conversation handling
processor = ChatProcessor(service)
processor_result = await processor.process_message(
    "Tell me about the benefits of exercise",
    chat_history=["I want to learn about healthy habits"]
)

if processor_result.is_success():
    processor_response = processor_result.unwrap()
    print(f"Processor response: {processor_response['response']}")
```

## Streaming Responses

The implementation supports streaming responses:

```python
# Stream a response
async for chunk in service.analyze_messages_streaming(["Tell me a story"]):
    print(chunk, end="", flush=True)
```

## Troubleshooting

If you encounter authentication issues:

1. Verify your credentials file exists and has the correct format
2. Ensure the `GOOGLE_APPLICATION_CREDENTIALS` environment variable is set
3. Try using an API key directly:
   ```
   export GOOGLE_API_KEY=your_api_key
   ```

## References

- [Google Generative AI Python SDK](https://github.com/google/generative-ai-python)
- [Gemini API Documentation](https://ai.google.dev/docs/gemini_api_overview) 