"""
Gemini LLM service implementation.

This module provides:
1. Integration with Google's Gemini model
2. Both standard and streaming response modes
3. Conversation and prompt handling
4. Error handling and recovery
"""

import logging
import asyncio
import os
import json
from typing import List, Dict, Any, AsyncGenerator, Optional, Protocol

# Google Generative AI imports
import google.generativeai as genai  # Used when API-key flow is chosen
from google.api_core import exceptions as google_api_exceptions
from google.auth import exceptions as google_auth_exceptions

# Vertex-AI imports (for service-account flow)
from google.cloud import aiplatform
from vertexai.preview.generative_models import GenerativeModel

from hrbot.utils.result import Result, Success, Error
from hrbot.utils.error import LLMError, ErrorCode
from hrbot.config.settings import settings

logger = logging.getLogger(__name__)

# Define LLMProvider Protocol for type hinting
class LLMProvider(Protocol):
    """Protocol defining the interface for LLM providers."""
    
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        """Generate a response from a prompt."""
        ...
        
    async def generate_response_streaming(self, prompt: str) -> AsyncGenerator[str, None]:
        """Generate a streaming response from a prompt."""
        ...

class GeminiService:
    """
    Service for interacting with Google's Gemini models.
    
    Provides:
    - Standard and streaming response modes
    - Context handling for conversations
    - Error recovery and logging
    """
    
    def __init__(self):
        """Initialize the Gemini service with configuration from settings."""
        try:
            # Configure the API
            self.model_name = settings.gemini.model_name
            self.temperature = settings.gemini.temperature
            self.max_output_tokens = settings.gemini.max_output_tokens
            
            # Determine API key
            api_key = settings.gemini.api_key or os.environ.get("GOOGLE_API_KEY")
            self.use_vertex = False
            if api_key:
                # AI-Studio / API-key path
                os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)  # SA JSON ignored for GenAI
                genai.configure(api_key=api_key)
                # Build once and reuse to avoid re-handshake latency
                self._model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=self.generation_config,
                    safety_settings=self.safety_settings,
                )
            else:
                # Vertex-AI path with ADC / service-account
                self.use_vertex = True
                aiplatform.init(project=settings.google_cloud.project_id,
                                location=settings.google_cloud.location)
                self._model = GenerativeModel(model_name=self.model_name)
            
            # Initialize the model
            self.generation_config = {
                "temperature": self.temperature,
                "top_p": 1,
                "top_k": 32,
                "max_output_tokens": self.max_output_tokens,
            }
            
            self.safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]
            
            logger.info(f"Initialized Gemini service with model {self.model_name}")
            
        except Exception as e:
            logger.error(f"Error initializing Gemini service: {str(e)}")
            raise LLMError(
                code=ErrorCode.INITIALIZATION_ERROR,
                message=f"Failed to initialize Gemini service: {str(e)}",
                severity="CRITICAL",
                cause=e
            )
    
    def _get_api_key(self) -> str:
        """
        Get API key from credentials file.
        
        Returns:
            The API key as string
            
        Raises:
            LLMError: If API key cannot be retrieved
        """
        try:
            # Try to get from env var first
            api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key:
                return api_key
            
            # Try to get from credentials file
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not creds_path or not os.path.exists(creds_path):
                raise FileNotFoundError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set or file not found")
            
            with open(creds_path, 'r') as f:
                creds = json.load(f)
            
            # For Vertex AI credentials, the API key might be in different formats
            api_key = creds.get('api_key') or creds.get('private_key')
            if not api_key:
                # This is likely a service account key, which doesn't have an explicit API key
                # For service accounts, the Vertex AI SDK should use the credentials file directly
                logger.info("Using service account credentials for Gemini")
                return "service_account"
                
            return api_key
        
        except Exception as e:
            logger.error(f"Error getting API key: {str(e)}")
            raise LLMError(
                code=ErrorCode.INVALID_CREDENTIALS,
                message=f"Failed to get Gemini API key: {str(e)}",
                cause=e
            )
    
    async def analyze_messages(self, messages: List[str]) -> Result[Dict]:
        """
        Analyze a batch of chat messages (or questions) using Gemini.
        
        Args:
            messages: List of message strings (last one is the current query)
            
        Returns:
            Result containing the LLM's output or error
        """
        if not messages:
            return Error(LLMError(
                code=ErrorCode.PROMPT_TOO_LONG,
                message="No messages provided for analysis",
                user_message="I need a question to answer."
            ))
        
        try:
            # Get the last message as the current query
            current_message = messages[-1]
            
            # Get previous messages as history
            history = messages[:-1] if len(messages) > 1 else []
            
            model = self._model

            if self.use_vertex:
                # Vertex path – simply concatenate history + current message
                prompt = "\n".join(history + [current_message]) if history else current_message
                response = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                )
                response_text = response.text
            else:
                # AI-Studio path using chat interface
                chat = model.start_chat(history=[
                    {"role": "user" if i % 2 == 0 else "model", "parts": [msg]}
                    for i, msg in enumerate(history)
                ] if history else [])
                response = await asyncio.to_thread(
                    chat.send_message,
                    current_message,
                    generation_config=self.generation_config,
                    safety_settings=self.safety_settings,
                )
                response_text = response.text
            
            # Return successful result
            return Success({
                "response": response_text,
                "model": self.model_name,
                "prompt_tokens": getattr(response, "prompt_token_count", 0),
                "completion_tokens": getattr(response, "candidate_token_count", 0)
            })
            
        except google_auth_exceptions.DefaultCredentialsError as e:
            logger.error(f"Authentication error with Gemini: {str(e)}")
            return Error(LLMError(
                code=ErrorCode.INVALID_CREDENTIALS,
                message=f"Authentication error with Gemini: {str(e)}",
                user_message="There was an issue with AI system authentication."
            ))
        except google_api_exceptions.ResourceExhausted as e:
            logger.error(f"Resource exhaustion error with Gemini: {str(e)}")
            return Error(LLMError(
                code=ErrorCode.TOKEN_LIMIT_EXCEEDED,
                message=f"Token limit exceeded with Gemini: {str(e)}",
                user_message="Your query is too complex for me to process right now."
            ))
        except google_api_exceptions.InvalidArgument as e:
            logger.error(f"Invalid argument error with Gemini: {str(e)}")
            return Error(LLMError(
                code=ErrorCode.PROMPT_TOO_LONG,
                message=f"Invalid argument: {str(e)}",
                user_message="I couldn't process your request due to input constraints."
            ))
        except Exception as e:
            logger.error(f"Error analyzing messages with Gemini: {str(e)}")
            return Error(LLMError(
                code=ErrorCode.LLM_UNAVAILABLE,
                message=f"Error analyzing messages with Gemini: {str(e)}",
                user_message="I'm having trouble processing your request right now."
            ))
    
    async def analyze_messages_streaming(self, messages: List[str]) -> AsyncGenerator[str, None]:
        """
        Analyze messages with streaming response.
        
        Args:
            messages: List of message strings
            
        Yields:
            Chunks of the response as they are generated
        """
        if not messages:
            yield "I need a question to answer."
            return
        
        try:
            # Get the last message as the current query
            current_message = messages[-1]
            
            # Get previous messages as history
            history = messages[:-1] if len(messages) > 1 else []
            
            model = self._model

            if self.use_vertex:
                prompt = "\n".join(history + [current_message]) if history else current_message
                # Vertex streaming
                stream = model.generate_content(prompt, stream=True)
                for chunk in stream:
                    if hasattr(chunk, "text") and chunk.text:
                        yield chunk.text
            else:
                chat = model.start_chat(history=[
                    {"role": "user" if i % 2 == 0 else "model", "parts": [msg]}
                    for i, msg in enumerate(history)
                ] if history else [])

                response = await asyncio.to_thread(
                    chat.send_message_async,
                    current_message,
                    generation_config=self.generation_config,
                    safety_settings=self.safety_settings,
                    stream=True,
                )

                async for chunk in response:
                    if hasattr(chunk, 'text') and chunk.text:
                        yield chunk.text
                
        except Exception as e:
            logger.error(f"Error in streaming response: {str(e)}")
            yield f"I'm having trouble processing your request right now: {str(e)}"
    
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        """
        Generate a response from a prompt (LLMProvider protocol method).
        
        Args:
            prompt: The prompt to send to the LLM
            
        Returns:
            Result containing the response or error
        """
        # Simply forward to analyze_messages with a single message
        return await self.analyze_messages([prompt])
    
    async def generate_response_streaming(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from a prompt (LLMProvider protocol method).
        
        Args:
            prompt: The prompt to send to the LLM
            
        Yields:
            Chunks of the response as they are generated
        """
        # Forward to analyze_messages_streaming with a single message
        async for chunk in self.analyze_messages_streaming([prompt]):
            yield chunk
    
    async def test_connection(self) -> bool:
        """
        Test the connection to the Gemini API.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try a simple query
            result = await self.analyze_messages(["Hello, are you working?"])
            return result.is_success()
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False 