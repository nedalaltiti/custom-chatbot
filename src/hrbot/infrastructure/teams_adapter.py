"""
Teams adapter — low-latency variant.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

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
            token = await self.get_graph_token()  # ✅ Graph token for Graph API
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
        token = await self.get_graph_token()  # ✅ Graph token for Graph API
        url = f"https://graph.microsoft.com/beta/users/{aad_id}/profile/positions"
        headers = {"Authorization": f"Bearer {token}"}
        resp = await _get_http().get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])

    async def send_typing(self, svc_url: str, conv_id: str) -> bool:
        return await self._post_activity(svc_url, conv_id, {"type": "typing"})

    async def send_message(self, svc_url: str, conv_id: str, text: str) -> bool:
        payload = {"type": "message", "text": text, "textFormat": "markdown"}
        return await self._post_activity(svc_url, conv_id, payload)

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
        token = await self.get_bot_token()  # ✅ Fixed: Bot token for Bot Framework API
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
        token = await self.get_bot_token()  # ✅ Fixed: Bot token for Bot Framework API
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

    async def stream_message(
        self,
        service_url: str,
        conversation_id: str,
        text_generator,
        informative: str = "Thinking…",
    ) -> bool:
        """Helper that routers import to stream chunked text."""
        streamer = _TeamsStreamer(self, service_url, conversation_id)
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
            token = await self.get_bot_token()  # ✅ Fixed: Bot token for Bot Framework API
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


class _TeamsStreamer:
    MAX_BURST = 3           # immediate updates before we throttle
    REFILL_RATE = 1.0       # tokens per second

    def __init__(self, adapter: TeamsAdapter, svc_url: str, conv_id: str) -> None:
        self.adapter = adapter
        self.svc_url = svc_url.rstrip("/")
        self.conv_id = conv_id

        self.stream_id: str | None = None
        self.buffer: str = ""
        self.seq = 1
        self.finished = False

    async def _post(self, body: dict) -> bool:
        ok, act_id = await self.adapter._post_activity(self.svc_url, self.conv_id, body, return_id=True)
        if ok and not self.stream_id:
            self.stream_id = act_id
        return ok

    async def run(self, gen: AsyncGenerator[str, None], informative: str) -> bool:
        # 1) start (typing + informative text)
        start_body = {
            "type": "typing",
            "text": informative,
            "entities": [{
                "type": "streamInfo",
                "streamType": "informative",
                "streamSequence": self.seq,
            }],
        }
        if not await self._post(start_body):
            return False

        self.buffer = informative

        tokens: float = self.MAX_BURST          # start with a full bucket
        last_time     = time.monotonic()

        # 2) incremental updates
        async for chunk in gen:
            self.buffer += chunk
            now   = time.monotonic()
            delta = now - last_time
            tokens = min(self.MAX_BURST, tokens + delta * self.REFILL_RATE)  # refill
            last_time = now

            if tokens >= 1:
                if not await self._update():
                    return False
                tokens -= 1

        # 3) final
        return await self._finish()

    async def _update(self) -> bool:
        if not self.stream_id:
            return False
        self.seq += 1
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

    async def _finish(self) -> bool:
        if self.finished:
            return True
        body = {
            "type": "message",
            "text": self.buffer,
            "entities": [{
                "type": "streamInfo",
                "streamId": self.stream_id,
                "streamType": "final",
            }],
        }
        self.finished = await self._post(body)
        return self.finished