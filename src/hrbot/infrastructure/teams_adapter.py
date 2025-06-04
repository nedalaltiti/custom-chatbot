"""
Teams adapter — low-latency variant following Microsoft Teams streaming requirements.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional, Dict, Any, List
from collections import deque
from datetime import datetime

import httpx

from hrbot.config.settings import settings

logger = logging.getLogger(__name__)


_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(http2=True, timeout=10.0)
    return _http


class TeamsAdapter:
    SAFETY_WINDOW = 60  # refresh token 60 s before real expiry
    BOT_TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"

    def __init__(self) -> None:
        self.app_id = settings.teams.app_id
        self.app_password = settings.teams.app_password

        # Separate tokens for different APIs
        self._bot_token: str | None = None
        self._bot_token_expiry: float = 0.0
        self._graph_token: str | None = None
        self._graph_token_expiry: float = 0.0
        self._token_lock = asyncio.Lock()

        logger.info("Teams adapter initialised")

    async def get_bot_token(self) -> str:
        """Get Bot Framework token for Teams messaging APIs."""
        now = time.time()
        if self._bot_token and now < self._bot_token_expiry - self.SAFETY_WINDOW:
            return self._bot_token

        async with self._token_lock:
            if self._bot_token and now < self._bot_token_expiry - self.SAFETY_WINDOW:
                return self._bot_token

            payload = {
                "grant_type": "client_credentials",
                "client_id": self.app_id,
                "client_secret": self.app_password,
                "scope": "https://api.botframework.com/.default",
            }
            resp = await _get_http().post(self.BOT_TOKEN_URL, data=payload)
            resp.raise_for_status()

            body = resp.json()
            self._bot_token = body["access_token"]
            self._bot_token_expiry = now + int(body.get("expires_in", 3600))
            logger.debug("Bot Framework token cached (expires in %ss)", body.get("expires_in"))
            return self._bot_token

    async def get_graph_token(self) -> str:
        """Get Microsoft Graph token for user profile APIs."""
        now = time.time()
        if self._graph_token and now < self._graph_token_expiry - self.SAFETY_WINDOW:
            return self._graph_token

        async with self._token_lock:
            if self._graph_token and now < self._graph_token_expiry - self.SAFETY_WINDOW:
                return self._graph_token

            token_url = f"https://login.microsoftonline.com/{settings.teams.tenant_id}/oauth2/v2.0/token"
            payload = {
                "grant_type": "client_credentials",
                "client_id": settings.teams.client_id or self.app_id,
                "client_secret": settings.teams.client_secret or self.app_password,
                "scope": "https://graph.microsoft.com/.default"
            }

            resp = await _get_http().post(token_url, data=payload)
            resp.raise_for_status()

            body = resp.json()
            self._graph_token = body["access_token"]
            self._graph_token_expiry = now + int(body.get("expires_in", 3600))
            logger.debug("Graph token cached (expires in %ss)", body.get("expires_in"))
            return self._graph_token
        
    async def get_user_profile(self, aad_object_id: str) -> dict:
        """Fetch the user's Azure AD profile (displayName + jobTitle)."""
        try:
            token = await self.get_graph_token()
            url = (
                f"https://graph.microsoft.com/v1.0/"
                f"users/{aad_object_id}"
                f"?$select=displayName,jobTitle"
            )
            headers = {"Authorization": f"Bearer {token}"}
            resp = await _get_http().get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Successfully retrieved user profile for {aad_object_id}: {data}")
            return data
        except Exception as e:
            logger.error(f"Error getting user profile: {str(e)}")
            if isinstance(e, httpx.HTTPStatusError):
                logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            return {"displayName": "Unknown", "jobTitle": "Unknown"}

    async def list_user_positions(self, aad_id: str) -> list[dict]:
        """GET https://graph.microsoft.com/beta/users/{aad_id}/profile/positions"""
        token = await self.get_graph_token()
        url = f"https://graph.microsoft.com/beta/users/{aad_id}/profile/positions"
        headers = {"Authorization": f"Bearer {token}"}
        resp = await _get_http().get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])

    async def send_typing(self, svc_url: str, conv_id: str) -> bool:
        return await self._post_activity(svc_url, conv_id, {"type": "typing"})

    async def send_message(self, svc_url: str, conv_id: str, text: str) -> Optional[str]:
        payload = {
            "type": "message", 
            "text": text, 
            "textFormat": "markdown",
            "entities": [
                {
                    "type": "https://schema.org/Message",
                    "@type": "Message",
                    "@context": "https://schema.org",
                    "additionalType": ["AIGeneratedContent"]  # AI label as per Microsoft docs
                }
            ],
            "channelData": {
                "feedbackLoop": {
                    "type": "default"  # Enable feedback buttons
                }
            }
        }
        ok, activity_id = await self._post_activity(svc_url, conv_id, payload, return_id=True)
        return activity_id if ok else None

    async def send_card(self, svc_url: str, conv_id: str, card: dict) -> Optional[str]:
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }
        ok, activity_id = await self._post_activity(svc_url, conv_id, payload, return_id=True)
        return activity_id if ok else None

    async def update_card(self, svc_url: str, conv_id: str, act_id: str, card: dict) -> bool:
        token = await self.get_bot_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{svc_url.rstrip('/')}/v3/conversations/{conv_id}/activities/{act_id}"
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }
        resp = await _get_http().put(url, headers=headers, json=payload)
        if resp.is_success:
            return True
        logger.warning("update_card failed %s – %s", resp.status_code, resp.text)
        return False
    
    async def delete_activity(self, svc_url: str, conv_id: str, act_id: str) -> bool:
        """Delete a previously-posted activity so it disappears from the chat."""
        token = await self.get_bot_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        url = f"{svc_url.rstrip('/')}/v3/conversations/{conv_id}/activities/{act_id}"
        resp = await _get_http().delete(url, headers=headers)
        if resp.is_success:
            return True
        logger.warning("delete_activity failed %s – %s", resp.status_code, resp.text)
        return False

    async def send_informative_update(self, svc_url: str, conv_id: str, message: str, stream_sequence: int = 1) -> Optional[str]:
        """Send an informative update (blue progress bar) following Teams streaming protocol."""
        payload = {
            "type": "typing",
            "text": message,
            "entities": [{
                "type": "streaminfo",  # Lowercase as per Microsoft docs
                "streamType": "informative",
                "streamSequence": stream_sequence
            }]
        }
        ok, stream_id = await self._post_activity(svc_url, conv_id, payload, return_id=True)
        return stream_id if ok else None

    async def stream_message(
        self,
        service_url: str,
        conversation_id: str,
        text_generator,
        informative: str = "I'm analyzing your request...",
    ) -> bool:
        """Stream message following Microsoft Teams streaming requirements."""
        streamer = _MicrosoftTeamsStreamer(self, service_url, conversation_id)
        try:
            await streamer.run(text_generator, informative=informative)
            return True
        except Exception as exc:
            logger.error("stream_message error: %s", exc)
            return False

    async def _post_activity(
        self,
        svc_url: str,
        conv_id: str,
        payload: dict,
        *,
        return_id: bool = False,
    ) -> tuple[bool, Optional[str]]:
        try:
            token = await self.get_bot_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            url = f"{svc_url.rstrip('/')}/v3/conversations/{conv_id}/activities"
            resp = await _get_http().post(url, headers=headers, json=payload)
            if resp.is_success:
                act_id = None
                if return_id:
                    try:
                        act_id = resp.json().get("id")
                    except Exception:
                        pass
                return True, act_id
            logger.warning("Teams POST %s – %s", resp.status_code, resp.text)
            return False, None
        except Exception as exc:
            logger.error("Teams POST error: %s", exc)
            return False, None


class _MicrosoftTeamsStreamer:
    """Microsoft Teams streaming implementation following official documentation with latency optimizations."""
    
    def __init__(self, adapter: TeamsAdapter, svc_url: str, conv_id: str) -> None:
        self.adapter = adapter
        self.svc_url = svc_url.rstrip("/")
        self.conv_id = conv_id

        self.stream_id: str | None = None
        self.buffer: str = ""
        self.seq = 1
        self.finished = False
        
        # LATENCY OPTIMIZATION: Adaptive rate limiting based on performance settings
        self.last_request_time = 0.0
        self.min_interval = settings.performance.streaming_delay  # Use optimized delay from settings
        self.adaptive_delay = True  # Enable adaptive delays for better perceived performance
        
        # Performance monitoring
        self.chunk_count = 0
        self.start_time = time.time()

    async def _post(self, body: dict) -> bool:
        # ADAPTIVE RATE LIMITING: Faster for small responses, compliant for large ones
        now = time.time()
        time_since_last = now - self.last_request_time
        
        # Adaptive delay based on content size and performance
        if self.adaptive_delay:
            content_size = len(body.get('text', ''))
            if content_size < 100:  # Small content can be faster
                required_delay = max(0.8, self.min_interval)  # Microsoft minimum
            else:
                required_delay = self.min_interval
        else:
            required_delay = self.min_interval
            
        if time_since_last < required_delay:
            sleep_time = required_delay - time_since_last
            await asyncio.sleep(sleep_time)
        
        # Log the body we're about to send for debugging (only in debug mode)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Sending Teams activity: {body}")
        
        ok, act_id = await self.adapter._post_activity(self.svc_url, self.conv_id, body, return_id=True)
        self.last_request_time = time.time()
        
        if ok and not self.stream_id:
            self.stream_id = act_id
            logger.debug(f"Got stream_id: {act_id}")
        elif not ok:
            logger.error(f"Failed to post activity")
            
        return ok

    async def run(self, gen: AsyncGenerator[str, None], informative: str) -> bool:
        """Follow Microsoft Teams streaming sequence with latency optimizations: Start -> Continue -> Final"""
        
        # 1) Start streaming with informative message
        start_body = {
            "type": "typing",
            "text": informative or "Processing...",  # Always provide a default
            "entities": [{
                "type": "streaminfo",  # Lowercase as per Microsoft docs
                "streamType": "informative",
                "streamSequence": self.seq,
            }],
        }
        if not await self._post(start_body):
            logger.error("Failed to start streaming")
            return False

        self.buffer = ""  # Start with empty buffer
        self.seq += 1
        
        logger.info(f"Started streaming with informative message, next sequence: {self.seq}")

        # 2) Response streaming - OPTIMIZED CHUNK PROCESSING
        chunk_count = 0
        last_chunk = ""
        small_chunks_buffer = ""  # Buffer for small chunks to reduce API calls
        
        async for chunk in gen:
            if not chunk.strip():  # Skip empty chunks
                logger.debug(f"Skipping empty chunk at position {chunk_count}")
                continue
                
            # LATENCY OPTIMIZATION: Buffer small chunks to reduce API calls
            if len(chunk) < 30 and len(small_chunks_buffer) < settings.performance.max_chunk_size:
                small_chunks_buffer += chunk
                continue
                
            # Process buffered small chunks
            if small_chunks_buffer:
                self.buffer += small_chunks_buffer
                if not await self._update():
                    logger.error(f"Failed to send buffered streaming update {self.seq}")
                    return False
                small_chunks_buffer = ""
                chunk_count += 1
                
            # Build cumulative buffer (Microsoft requirement)
            self.buffer += chunk
            last_chunk = chunk
            chunk_count += 1
            
            # Send streaming update with cumulative content
            if not await self._update():
                logger.error(f"Failed to send streaming update {self.seq}")
                return False
                
            # PERFORMANCE MONITORING: Log only for debug
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Sent streaming chunk {chunk_count}, sequence {self.seq-1}, buffer length: {len(self.buffer)}")
            
        # Process any remaining buffered content
        if small_chunks_buffer:
            self.buffer += small_chunks_buffer
            if not await self._update():
                logger.error(f"Failed to send final buffered update")
                return False
            chunk_count += 1
            
        # Log performance metrics
        elapsed_time = time.time() - self.start_time
        if chunk_count == 0:
            logger.warning("Streaming completed with 0 chunks - no content was generated")
        elif chunk_count < 3:
            logger.info(f"Short streaming session: only {chunk_count} chunks. Last chunk: '{last_chunk[:50]}'")
        else:
            logger.info(f"Streaming performance: {chunk_count} chunks in {elapsed_time:.2f}s ({chunk_count/elapsed_time:.1f} chunks/sec)")

        # 3) Final message
        success = await self._finish()
        if success:
            logger.info(f"Completed streaming with {chunk_count} chunks, final length: {len(self.buffer)}")
        else:
            logger.error("Failed to finish streaming")
        return success

    async def _update(self) -> bool:
        """Send streaming update with cumulative content (Microsoft requirement) - OPTIMIZED."""
        if not self.stream_id:
            logger.error("No stream ID available for update")
            return False
            
        body = {
            "type": "typing",
            "text": self.buffer,  # Cumulative content as required by Microsoft
            "textFormat": "markdown",  # Preserve formatting
            "entities": [{
                "type": "streaminfo",  # Lowercase as per Microsoft docs
                "streamId": self.stream_id,
                "streamType": "streaming",
                "streamSequence": self.seq,
            }],
        }
        
        success = await self._post(body)
        if success:
            self.seq += 1  # Increment sequence after successful post
        else:
            # RESILIENCE: Don't fail entire stream for single update failure
            logger.warning(f"Streaming update failed for sequence {self.seq}, continuing...")
        return success

    async def _finish(self) -> bool:
        """Send final message with AI labels and feedback buttons - OPTIMIZED."""
        if self.finished:
            return True
            
        # LATENCY OPTIMIZATION: Prepare final message efficiently
        body = {
            "type": "message",
            "text": self.buffer,
            "textFormat": "markdown",
            "entities": [
                {
                    "type": "streaminfo",  # Lowercase as per Microsoft docs
                    "streamId": self.stream_id,
                    "streamType": "final",
                    # Note: No streamSequence for final message as per Microsoft docs
                },
                {
                    "type": "https://schema.org/Message",
                    "@type": "Message", 
                    "@context": "https://schema.org",
                    "additionalType": ["AIGeneratedContent"]  # AI label
                }
            ],
            "channelData": {
                "feedbackLoop": {
                    "type": "default"  # Enable feedback buttons
                }
            }
        }
        
        # RESILIENCE: Retry final message if it fails (critical for user experience)
        for attempt in range(2):
            self.finished = await self._post(body)
            if self.finished:
                break
            elif attempt == 0:
                logger.warning("Final message failed, retrying...")
                await asyncio.sleep(0.5)
            else:
                logger.error("Final message failed after retry")
                
        return self.finished