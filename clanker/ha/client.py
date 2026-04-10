"""Home Assistant WebSocket + REST client.

Handles authentication, reconnection, event subscription, state queries,
and service calls. This is Clanker's sole interface to Home Assistant —
all device interaction flows through here.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

import httpx
import structlog
import websockets
from websockets.asyncio.client import ClientConnection

logger = structlog.get_logger(__name__)

# Type alias for event callbacks
EventCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class HAClientError(Exception):
    """Raised when an HA API call fails."""


class HAClient:
    """Async Home Assistant client using WebSocket and REST APIs.

    Usage::

        client = HAClient(url="http://ha.local:8123", token="...")
        await client.connect()
        await client.subscribe_events(callback, event_type="state_changed")
        state = await client.get_state("sensor.temperature")
        await client.call_service("light", "turn_on", entity_id="light.living_room")
        await client.close()
    """

    def __init__(self, url: str, token: str) -> None:
        """Initialize the HA client.

        Args:
            url: Base URL of the HA instance (e.g. http://ha.local:8123).
            token: Long-lived access token.
        """
        self._base_url = url.rstrip("/")
        self._token = token
        self._ws: ClientConnection | None = None
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._subscriptions: dict[int, EventCallback] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._closing = False
        self._reconnect_delay = 1.0

    @property
    def connected(self) -> bool:
        """Whether the WebSocket connection is active."""
        return self._connected.is_set()

    def _next_id(self) -> int:
        """Get the next message ID for the WebSocket protocol."""
        self._msg_id += 1
        return self._msg_id

    async def connect(self) -> None:
        """Establish WebSocket connection and authenticate.

        Starts the background listener task for incoming messages.
        """
        ws_url = self._base_url.replace("http", "ws", 1) + "/api/websocket"
        logger.info("ha.connecting", url=ws_url)

        self._ws = await websockets.connect(ws_url)

        # HA sends auth_required on connect
        auth_required = json.loads(await self._ws.recv())
        if auth_required.get("type") != "auth_required":
            msg = f"Unexpected initial message: {auth_required}"
            raise HAClientError(msg)

        # Send auth
        await self._ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        auth_result = json.loads(await self._ws.recv())

        if auth_result.get("type") != "auth_ok":
            msg = f"Authentication failed: {auth_result.get('message', 'unknown error')}"
            raise HAClientError(msg)

        logger.info("ha.connected", ha_version=auth_result.get("ha_version"))
        self._connected.set()
        self._reconnect_delay = 1.0

        # Start background listener
        self._listen_task = asyncio.create_task(self._listen(), name="ha_ws_listener")

    async def _listen(self) -> None:
        """Background task: read messages from WebSocket and dispatch."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                msg_id = msg.get("id")

                if msg_type == "event" and msg_id in self._subscriptions:
                    callback = self._subscriptions[msg_id]
                    event_data = msg.get("event", {})
                    asyncio.create_task(callback(event_data))
                elif msg_type == "result" and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        if msg.get("success"):
                            future.set_result(msg.get("result"))  # type: ignore[arg-type]
                        else:
                            error = msg.get("error", {})
                            future.set_exception(
                                HAClientError(
                                    f"{error.get('code', 'unknown')}: "
                                    f"{error.get('message', 'unknown error')}"
                                )
                            )
                elif msg_type == "pong":
                    if msg_id in self._pending:
                        future = self._pending.pop(msg_id)
                        if not future.done():
                            future.set_result({})
        except websockets.ConnectionClosed:
            logger.warning("ha.ws_disconnected")
            self._connected.clear()
            if not self._closing:
                await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while not self._closing:
            delay = min(self._reconnect_delay, 60.0)
            logger.info("ha.reconnecting", delay=delay)
            await asyncio.sleep(delay)
            self._reconnect_delay *= 2

            try:
                await self.connect()
                # Re-subscribe to events
                old_subs = dict(self._subscriptions)
                self._subscriptions.clear()
                for _sub_id, callback in old_subs.items():
                    await self.subscribe_events(callback)
                logger.info("ha.reconnected", resubscribed=len(old_subs))
                return
            except Exception:
                logger.warning("ha.reconnect_failed", delay=delay, exc_info=True)

    async def _send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a command over WebSocket and wait for the result.

        Args:
            payload: Command payload (type and parameters, id is added automatically).

        Returns:
            The result dict from HA.

        Raises:
            HAClientError: If not connected or the command fails.
        """
        if not self._ws or not self._connected.is_set():
            msg = "Not connected to Home Assistant"
            raise HAClientError(msg)

        msg_id = self._next_id()
        payload["id"] = msg_id

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send(json.dumps(payload))
        return await asyncio.wait_for(future, timeout=30.0)

    async def subscribe_events(
        self,
        callback: EventCallback,
        event_type: str | None = None,
    ) -> int:
        """Subscribe to HA events via WebSocket.

        Args:
            callback: Async function called with each event dict.
            event_type: Optional event type filter (e.g. "state_changed").

        Returns:
            Subscription ID.
        """
        payload: dict[str, Any] = {"type": "subscribe_events"}
        if event_type:
            payload["event_type"] = event_type

        msg_id = self._next_id()
        payload["id"] = msg_id

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        assert self._ws is not None
        await self._ws.send(json.dumps(payload))
        await asyncio.wait_for(future, timeout=10.0)

        self._subscriptions[msg_id] = callback
        logger.info("ha.subscribed", event_type=event_type, subscription_id=msg_id)
        return msg_id

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Get the current state of an entity via REST API.

        Args:
            entity_id: HA entity ID (e.g. "sensor.temperature").

        Returns:
            Entity state dict with state, attributes, etc.

        Raises:
            HAClientError: If the entity is not found or the request fails.
        """
        response = await self._http.get(f"/api/states/{entity_id}")
        if response.status_code == 404:
            msg = f"Entity not found: {entity_id}"
            raise HAClientError(msg)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_states(self) -> list[dict[str, Any]]:
        """Get all entity states via REST API.

        Returns:
            List of all entity state dicts.
        """
        response = await self._http.get("/api/states")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a Home Assistant service.

        Args:
            domain: Service domain (e.g. "light", "tts").
            service: Service name (e.g. "turn_on", "speak").
            entity_id: Target entity ID.
            data: Additional service data.

        Returns:
            Service call result.
        """
        payload: dict[str, Any] = {
            "type": "call_service",
            "domain": domain,
            "service": service,
        }
        service_data = dict(data or {})
        if entity_id:
            payload["target"] = {"entity_id": entity_id}
        if service_data:
            payload["service_data"] = service_data

        logger.info("ha.call_service", domain=domain, service=service, entity_id=entity_id)
        return await self._send_command(payload)

    async def find_entities(self, pattern: str) -> list[dict[str, Any]]:
        """Find entities matching a pattern in their entity_id or friendly_name.

        Args:
            pattern: Substring to match (case-insensitive).

        Returns:
            List of matching entity state dicts.
        """
        all_states = await self.get_states()
        pattern_lower = pattern.lower()
        return [
            s
            for s in all_states
            if pattern_lower in s.get("entity_id", "").lower()
            or pattern_lower in s.get("attributes", {}).get("friendly_name", "").lower()
        ]

    async def ping(self) -> None:
        """Send a ping to verify the WebSocket connection is alive.

        Raises:
            HAClientError: If not connected or ping times out.
        """
        await self._send_command({"type": "ping"})

    async def close(self) -> None:
        """Close WebSocket and HTTP connections gracefully."""
        self._closing = True
        self._connected.clear()

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        await self._http.aclose()

        # Resolve any pending futures
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        logger.info("ha.closed")
