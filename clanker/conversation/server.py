"""Async HTTP server for the conversation API.

Exposes a single endpoint that the HA custom component calls to process
voice/text input through Clanker's brain.  Uses only the stdlib
``asyncio`` module — no web framework needed.

Default: ``http://0.0.0.0:8472/api/conversation/process``
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.conversation.agent import ConversationAgent

logger = structlog.get_logger(__name__)

_MAX_BODY = 1024 * 64  # 64 KB


class ConversationServer:
    """Lightweight async HTTP server for the conversation API."""

    def __init__(
        self,
        agent: ConversationAgent,
        host: str = "0.0.0.0",
        port: int = 8472,
    ) -> None:
        self._agent = agent
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start listening for connections."""
        self._server = await asyncio.start_server(
            self._handle, self._host, self._port
        )
        logger.info("conversation_server.started", host=self._host, port=self._port)

    async def stop(self) -> None:
        """Shut down the server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("conversation_server.stopped")

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single HTTP connection."""
        try:
            method, path, body = await self._read_request(reader)

            if method == "POST" and path == "/api/conversation/process":
                result = await self._handle_conversation(body)
                await self._send_json(writer, 200, result)
            elif method == "GET" and path == "/api/health":
                await self._send_json(writer, 200, {"ok": True})
            else:
                await self._send_json(writer, 404, {"error": "not found"})
        except Exception:
            logger.exception("conversation_server.error")
            with contextlib.suppress(Exception):
                await self._send_json(writer, 500, {"error": "internal error"})
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _handle_conversation(self, body: dict[str, Any]) -> dict[str, Any]:
        """Process a conversation request."""
        text = body.get("text", body.get("query", ""))
        if not text:
            return {"error": "Missing 'text' field"}

        result = await self._agent.process(
            text,
            conversation_id=body.get("conversation_id"),
            language=body.get("language", "en"),
            device_id=body.get("device_id"),
        )
        return result

    @staticmethod
    async def _read_request(
        reader: asyncio.StreamReader,
    ) -> tuple[str, str, dict[str, Any]]:
        """Parse an HTTP request into method, path, and JSON body."""
        # Request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        parts = request_line.decode("utf-8", errors="replace").strip().split()
        method = parts[0] if parts else "GET"
        path = parts[1] if len(parts) > 1 else "/"

        # Headers
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("utf-8", errors="replace").lower()
            if decoded.startswith("content-length:"):
                content_length = int(decoded.split(":", 1)[1].strip())

        # Body
        body: dict[str, Any] = {}
        if content_length > 0:
            raw = await asyncio.wait_for(
                reader.read(min(content_length, _MAX_BODY)), timeout=30.0
            )
            with contextlib.suppress(json.JSONDecodeError):
                body = json.loads(raw)

        return method, path, body

    @staticmethod
    async def _send_json(
        writer: asyncio.StreamWriter, status: int, data: Any
    ) -> None:
        """Write an HTTP JSON response."""
        payload = json.dumps(data).encode("utf-8")
        reason = {200: "OK", 404: "Not Found", 500: "Internal Server Error"}.get(
            status, "OK"
        )
        writer.write(f"HTTP/1.1 {status} {reason}\r\n".encode())
        writer.write(b"Content-Type: application/json\r\n")
        writer.write(f"Content-Length: {len(payload)}\r\n".encode())
        writer.write(b"Access-Control-Allow-Origin: *\r\n")
        writer.write(b"Connection: close\r\n")
        writer.write(b"\r\n")
        writer.write(payload)
        await writer.drain()
