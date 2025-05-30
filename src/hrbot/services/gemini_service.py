"""
Gemini LLM service implementation.

This module provides:
1. Integration with Google's Gemini model via Vertex AI
2. Both standard and streaming response modes
3. Conversation and prompt handling
4. Error handling and recovery
"""

import logging
import asyncio
import os
from typing import List, Dict, AsyncGenerator
import time

# Google Generative AI imports
import google.generativeai as genai  # Used when API-key flow is chosen
from google.api_core import exceptions as google_api_exceptions
from google.auth import exceptions as google_auth_exceptions

from google.cloud import aiplatform
from vertexai.preview.generative_models import (
    GenerativeModel,
    SafetySetting,
    HarmCategory,
    HarmBlockThreshold,
)

from hrbot.utils.result import Result, Success, Error
from hrbot.utils.error import LLMError, ErrorCode
from hrbot.config.settings import settings
from hrbot.config.environment import get_env_var_bool

logger = logging.getLogger(__name__)

class GeminiService:
    """
    Service for interacting with Google's Gemini models via Vertex AI.
    
    Provides:
    - Standard and streaming response modes
    - Context handling for conversations
    - Error recovery and logging
    """
    
    def __init__(self):
        """Configure Gemini service – heavy model load deferred until first use."""
        # Store config only
        self.model_name = settings.gemini.model_name
        self.temperature = settings.gemini.temperature
        self.max_output_tokens = settings.gemini.max_output_tokens

        # Generation + safety defaults
        self.generation_config = {
            "temperature": self.temperature, 
            "top_p": 1, 
            "top_k": 32,
            "max_output_tokens": self.max_output_tokens,
        }
        # Default dict-form list (compatible with google-generative-ai client).
        self._safety_settings_dicts = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

        # Vertex-AI specific object list (created lazily to avoid importing until needed)
        self._safety_settings_vertex: List[SafetySetting] | None = None

        self._model = None  # lazy initialization
        self.use_vertex = True  # Always use Vertex AI with service account

        # Option to initialize eagerly
        if get_env_var_bool("GEMINI_EAGER_INIT", False):
            try:
                self._ensure_model()
                logger.info("Gemini model eagerly initialized")
            except Exception as e:
                logger.warning(f"Failed to eagerly initialize Gemini: {e}")

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
            # Ensure model is available
            self._ensure_model()

            # Get the last message as the current query
            current_message = messages[-1]
            
            # Get previous messages as history
            history = messages[:-1] if len(messages) > 1 else []
            
            model = self._model

            # Use Vertex AI - simply concatenate history + current message
            prompt = "\n".join(history + [current_message]) if history else current_message
            
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
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
            # Ensure model is available
            self._ensure_model()

            # Get the last message as the current query
            current_message = messages[-1]
            
            # Get previous messages as history
            history = messages[:-1] if len(messages) > 1 else []
            
            model = self._model

            prompt = "\n".join(history + [current_message]) if history else current_message
            
            # Vertex AI streaming
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings,
                stream=True,
            )
            
            for chunk in response:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
                
        except Exception as e:
            logger.error(f"Error in streaming response: {str(e)}")
            yield f"I'm having trouble processing your request right now: {str(e)}"
    
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

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _ensure_model(self, retries: int = 3):
        """Lazily create the GenerativeModel with simple exponential back-off."""
        if self._model is not None:
            return

        delay = 1.0
        last_err: Exception | None = None
        
        for attempt in range(1, retries + 1):
            try:
                # Check if we have service account credentials
                creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or settings.google_cloud.project_id
                location = os.environ.get("GOOGLE_CLOUD_LOCATION") or settings.google_cloud.location
                
                # Prefer service-account creds dropped by AWS Secrets Manager.
                # If they are not present we fall back to API-key auth.
                if not creds_path:
                    # Try API key approach as fallback
                    api_key = settings.gemini.api_key or os.environ.get("GOOGLE_API_KEY")
                    if api_key:
                        logger.info("Using API key for Gemini authentication")
                        genai.configure(api_key=api_key)
                        self._model = genai.GenerativeModel(
                            model_name=self.model_name,
                            generation_config=self.generation_config,
                            safety_settings=self.safety_settings,
                        )
                        self.use_vertex = False
                        # Use the dict form for google-generative-ai
                        self.safety_settings = self._safety_settings_dicts
                        logger.info("Gemini model initialized with API key on attempt %d", attempt)
                        return
                    else:
                        raise ValueError("No Google credentials found - neither service account nor API key")
                
                # Use Vertex AI with service account
                if not project_id:
                    raise ValueError("GOOGLE_CLOUD_PROJECT not set")
                
                logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
                aiplatform.init(project=project_id, location=location)
                self._model = GenerativeModel(model_name=self.model_name)
                self.use_vertex = True
                
                # Build SafetySetting objects once
                if self._safety_settings_vertex is None:
                    self._safety_settings_vertex = [
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
                    ]

                self.safety_settings = self._safety_settings_vertex
                
                logger.info("Gemini model initialized with Vertex AI on attempt %d", attempt)
                return
                
            except Exception as e:
                last_err = e
                logger.warning(f"Gemini init attempt {attempt} failed: {e}")
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
        
        # After retries
        raise LLMError(
            code=ErrorCode.INITIALIZATION_ERROR, 
            message=f"Failed to initialize Gemini after {retries} attempts", 
            cause=last_err
        )