"""
This module contains the Teams adapter.
"""

import httpx
import logging
import time
from typing import Optional
from hrbot.config.settings import settings
import asyncio

logger = logging.getLogger(__name__)

class TeamsAdapter:
    """
    Adapter for Microsoft Teams Bot Framework integration.
    
    Provides methods to interact with the Teams Bot Framework API,
    including sending typing indicators and messages.
    """
    
    def __init__(self):
        """Initialize the Teams adapter with credentials from settings."""
        self.app_id = settings.teams.app_id
        self.app_password = settings.teams.app_password
        self.token = None
        self.token_expiry = 0  # Unix timestamp
        logger.info("Initialized Teams adapter")

    async def get_token(self) -> str:
        """
        Get OAuth token for Bot Framework, with caching and refresh.
        
        Returns:
            str: The access token for Bot Framework API
        """
        current_time = time.time()
        
        # Check if token exists and is not expired (with 5 minute buffer)
        if self.token and current_time < self.token_expiry - 300:
            return self.token
            
        # Get new token
        url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.app_id,
            "client_secret": self.app_password,
            "scope": "https://api.botframework.com/.default"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=data)
                resp.raise_for_status()
                token_data = resp.json()
                self.token = token_data["access_token"]
                # Set expiry time (subtract 5 minutes for safety)
                self.token_expiry = current_time + token_data.get("expires_in", 3600)
                logger.info("Successfully obtained new Teams Bot Framework token")
                return self.token
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting Teams token: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to get Teams Bot Framework token: {e}")
            raise

    async def send_typing(self, service_url: str, conversation_id: str) -> bool:
        """
        Send typing indicator to conversation.
        
        Args:
            service_url: The Teams service URL
            conversation_id: The conversation ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            token = await self.get_token()
            url = f"{service_url}/v3/conversations/{conversation_id}/activities"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {"type": "typing"}
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Error sending typing indicator: {e}")
            return False

    async def send_message(self, service_url: str, conversation_id: str, text: str) -> bool:
        """
        Send text message to conversation.
        
        Args:
            service_url: The Teams service URL
            conversation_id: The conversation ID
            text: The message text to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Sending message to conversation {conversation_id[:8]}...")
            token = await self.get_token()
            url = f"{service_url}/v3/conversations/{conversation_id}/activities"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # Structured payload as per Microsoft Bot Framework specs
            payload = {
                "type": "message",
                "text": text,
                "textFormat": "markdown"
            }
            
            async with httpx.AsyncClient() as client:
                logger.debug(f"Sending to URL: {url}")
                logger.debug(f"Payload: {payload}")
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if resp.status_code >= 400:
                    logger.error(f"Error response: Status {resp.status_code} - {resp.text}")
                    return False
                    
                resp.raise_for_status()
                logger.info(f"Successfully sent message to Teams conversation {conversation_id[:8]}...")
                return True
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending message: {e.response.status_code} - {e.response.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Request error sending message: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    async def send_message_streaming(self, service_url: str, conversation_id: str, async_generator, *, initial_text: str = "...") -> bool:
        """
        Send messages in a streaming fashion to a Teams conversation.
        
        Args:
            service_url: The Teams service URL
            conversation_id: The conversation ID
            async_generator: An async generator that yields text chunks
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Starting streaming message to conversation {conversation_id[:8]}...")
            token = await self.get_token()
            url = f"{service_url}/v3/conversations/{conversation_id}/activities"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # Send an initial blank message (will be invisible until updated)
            initial_id = None
            initial_payload = {
                "type": "message",
                "text": initial_text or " ",
                "textFormat": "markdown"
            }
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=initial_payload, timeout=10.0)
                if resp.status_code >= 400:
                    logger.error(f"Error starting streaming: {resp.status_code} - {resp.text}")
                    return False
                
                # Save the activity ID for updates
                try:
                    initial_id = resp.json().get("id")
                except:
                    logger.warning("Could not get activity ID for streaming updates")
            
            # If we have an activity ID, use update endpoint for streaming
            update_url = None
            if initial_id:
                update_url = f"{service_url}/v3/conversations/{conversation_id}/activities/{initial_id}"
            
            # Accumulate characters
            full_message = ""
            char_count = 0
            last_update_time = time.time()
            update_interval = 0.2  # Update every 200ms maximum
            
            STREAM_INTERVAL = 1.1  # Bot Framework allows ~1 request per second

            async for char in async_generator:
                full_message += char
                char_count += 1
                
                current_time = time.time()
                time_since_update = current_time - last_update_time
                
                # Send update at regular intervals or after collecting enough characters
                if char_count >= 5 or time_since_update >= update_interval:
                    update_payload = {
                        "type": "message",
                        "text": full_message,
                        "textFormat": "markdown"
                    }
                    
                    # If we can update the existing message, do so
                    if update_url:
                        async with httpx.AsyncClient() as client:
                            resp = await client.put(update_url, headers=headers, json=update_payload, timeout=10.0)
                            if resp.status_code >= 400:
                                logger.warning(f"Streaming update failed, falling back to new message: {resp.status_code}")
                                update_url = None  # Fall back to sending new messages
                    
                    # If we can't update, send a new message
                    if not update_url:
                        async with httpx.AsyncClient() as client:
                            resp = await client.post(url, headers=headers, json=update_payload, timeout=10.0)
                            if resp.status_code >= 400:
                                logger.error(f"Error in streaming: {resp.status_code} - {resp.text}")
                                return False
                    
                    char_count = 0  # Reset counter after update
                    last_update_time = current_time
            
            # Send final message if there are any remaining characters
            if char_count > 0:
                final_payload = {
                    "type": "message",
                    "text": full_message,
                    "textFormat": "markdown"
                }
                
                if update_url:
                    async with httpx.AsyncClient() as client:
                        resp = await client.put(update_url, headers=headers, json=final_payload, timeout=10.0)
                else:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(url, headers=headers, json=final_payload, timeout=10.0)
            
            logger.info(f"Finished streaming message to Teams conversation {conversation_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error sending streaming message: {str(e)}")
            return False

    async def send_card(self, service_url: str, conversation_id: str, card_content: dict) -> bool:
        """
        Send an adaptive card to a Teams conversation.
        
        Args:
            service_url: The Teams service URL
            conversation_id: The conversation ID
            card_content: The adaptive card content
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Sending card to conversation {conversation_id[:8]}...")
            token = await self.get_token()
            url = f"{service_url}/v3/conversations/{conversation_id}/activities"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # Create the payload with the card
            payload = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card_content
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                logger.debug(f"Sending to URL: {url}")
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if resp.status_code >= 400:
                    logger.error(f"Error response: Status {resp.status_code} - {resp.text}")
                    return False
                    
                resp.raise_for_status()
                logger.info(f"Successfully sent card to Teams conversation {conversation_id[:8]}...")
                return True
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending card: {e.response.status_code} - {e.response.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Request error sending card: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending card: {str(e)}")
            return False

# ---------------------------------------------------------------------------
# Module-level streaming helper
# ---------------------------------------------------------------------------

class _TeamsStreamer:
    """Encapsulates one streaming lifecycle for a single message."""

    def __init__(self, adapter: "TeamsAdapter", service_url: str, conv_id: str):
        self.adapter = adapter
        self.service_url = service_url.rstrip("/")
        self.conv_id = conv_id
        self.stream_id: str | None = None
        self.seq: int = 1
        self.buffer: str = ""

    async def _post(self, payload: dict) -> int:
        try:
            token = await self.adapter.get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            url = f"{self.service_url}/v3/conversations/{self.conv_id}/activities"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    logger.warning(f"Streaming POST failed: {resp.status_code} - {resp.text}")
                    return resp.status_code
                if not self.stream_id:
                    # First call returns the activity id which doubles as streamId
                    try:
                        self.stream_id = resp.json().get("id")
                    except Exception:
                        pass
                return resp.status_code
        except Exception as e:
            logger.error(f"Streaming POST error: {e}")
            return 500

    async def start(self, informative: str = "Thinking…") -> bool:
        body = {
            "type": "typing",
            "text": informative,
            "entities": [{
                "type": "streamInfo",
                "streamType": "informative",
                "streamSequence": self.seq,
            }],
        }
        status = await self._post(body)
        if status >= 400:
            return False

        # keep buffer consistent
        self.buffer = informative

        last_update = asyncio.get_event_loop().time()
        return True

    async def update(self, new_text: str) -> bool:
        if not self.stream_id:
            logger.error("stream_id missing during update")
            return False
        self.seq += 1
        self.buffer = new_text
        body = {
            "type": "typing",
            "text": self.buffer,
            "entities": [{
                "type": "streamInfo",
                "streamId": self.stream_id,
                "streamType": "streaming",
                "streamSequence": self.seq,
            }],
        }
        return await self._post(body)

    async def finish(self) -> bool:
        if not self.stream_id:
            logger.error("stream_id missing during finish")
            return False
        body = {
            "type": "message",
            "text": self.buffer,
            "entities": [{
                "type": "streamInfo",
                "streamId": self.stream_id,
                "streamType": "final",
            }],
        }
        return await self._post(body)

    async def run_stream(self, text_gen, informative: str = "Thinking…") -> None:
        """High-level helper: stream generator output under Teams rules."""
        status = await self.start(informative)
        if status >= 400:
            return

        self.buffer = informative      # keep buffer
        last_update = 0                # force immediate update

        STREAM_INTERVAL = 1.1  # Bot Framework allows ~1 request per second

        async for chunk in text_gen:
            self.buffer += chunk
            now = asyncio.get_event_loop().time()
            if now - last_update >= STREAM_INTERVAL:
                status = await self.update(self.buffer)
                if status in (403, 429):
                    return
                last_update = now

        await self.finish()

# Adapter-level facade -------------------------------------------------------------

async def stream_message(adapter: "TeamsAdapter", service_url: str, conversation_id: str, text_generator, informative: str = "Thinking…") -> bool:
    """Helper that can be imported and used by routers to stream messages."""
    streamer = _TeamsStreamer(adapter, service_url, conversation_id)
    try:
        await streamer.run_stream(text_generator, informative=informative)
        return True
    except Exception as e:
        logger.error(f"stream_message error: {e}")
        return False