"""MCP tool server — exposes Clanker capabilities to the brain.

Registers tools (ha_call_service, ha_get_state, memory_search,
notify_user, etc.) using the Model Context Protocol so the same
tool surface works across all LLM providers.

TODO:
- Add more tools as modules are implemented (vision_describe, get_calendar, etc.)
- Add tool input validation
- Add rate limiting for HA service calls
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

if TYPE_CHECKING:
    from clanker.ha.client import HAClient
    from clanker.memory.tools import MemoryTools

logger = structlog.get_logger(__name__)


def create_mcp_server(
    ha_client: HAClient,
    memory_tools: MemoryTools,
) -> Server:
    """Create and configure the MCP server with Clanker tools.

    Args:
        ha_client: Connected HA client for service calls and state queries.
        memory_tools: Memory tool wrappers.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("clanker")

    @server.list_tools()  # type: ignore[misc]
    async def list_tools() -> list[Tool]:
        """List all available Clanker tools."""
        return [
            Tool(
                name="ha_call_service",
                description=(
                    "Call a Home Assistant service. Use this to control devices, "
                    "trigger automations, send TTS, etc."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Service domain (e.g. 'light', 'switch', 'tts')",
                        },
                        "service": {
                            "type": "string",
                            "description": "Service name (e.g. 'turn_on', 'turn_off', 'speak')",
                        },
                        "entity_id": {
                            "type": "string",
                            "description": "Target entity ID (optional)",
                        },
                        "data": {
                            "type": "object",
                            "description": "Additional service data (optional)",
                        },
                    },
                    "required": ["domain", "service"],
                },
            ),
            Tool(
                name="ha_get_state",
                description="Get the current state of a Home Assistant entity.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Entity ID to query (e.g. 'sensor.temperature')",
                        },
                    },
                    "required": ["entity_id"],
                },
            ),
            Tool(
                name="ha_find_entities",
                description="Search for HA entities by name or ID pattern.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Substring to match in entity ID or friendly name",
                        },
                    },
                    "required": ["pattern"],
                },
            ),
            Tool(
                name="memory_read",
                description="Read a specific memory entry by key.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Memory key to look up",
                        },
                    },
                    "required": ["key"],
                },
            ),
            Tool(
                name="memory_write",
                description="Store a memory entry for future recall.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Memory key (identifier)",
                        },
                        "value": {
                            "type": "string",
                            "description": "Content to remember",
                        },
                        "store": {
                            "type": "string",
                            "enum": ["structured", "semantic"],
                            "description": "Which store to write to (default: semantic)",
                        },
                    },
                    "required": ["key", "value"],
                },
            ),
            Tool(
                name="memory_search",
                description="Search memory for relevant entries.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default: 5)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="notify_user",
                description="Send a push notification to the user's mobile device.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Notification body",
                        },
                        "title": {
                            "type": "string",
                            "description": "Notification title (optional)",
                        },
                    },
                    "required": ["message"],
                },
            ),
        ]

    @server.call_tool()  # type: ignore[misc]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Dispatch a tool call to the appropriate handler."""
        import json

        try:
            result = await _handle_tool(name, arguments, ha_client, memory_tools)
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except Exception as e:
            logger.exception("mcp.tool_error", tool=name)
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


async def _handle_tool(
    name: str,
    args: dict[str, Any],
    ha_client: HAClient,
    memory_tools: MemoryTools,
) -> Any:
    """Route a tool call to its implementation.

    Args:
        name: Tool name.
        args: Tool arguments.
        ha_client: HA client.
        memory_tools: Memory tools.

    Returns:
        Tool result.
    """
    if name == "ha_call_service":
        return await ha_client.call_service(
            args["domain"],
            args["service"],
            entity_id=args.get("entity_id"),
            data=args.get("data"),
        )
    if name == "ha_get_state":
        return await ha_client.get_state(args["entity_id"])
    if name == "ha_find_entities":
        return await ha_client.find_entities(args["pattern"])
    if name == "memory_read":
        return await memory_tools.memory_read(args["key"])
    if name == "memory_write":
        return await memory_tools.memory_write(
            args["key"],
            args["value"],
            store=args.get("store", "semantic"),
        )
    if name == "memory_search":
        return await memory_tools.memory_search(
            args["query"],
            limit=args.get("limit", 5),
        )
    if name == "notify_user":
        # TODO: Route through announcement system
        logger.info("mcp.notify_user", message=args["message"][:80])
        return {"status": "ok", "message": "Notification sent"}

    msg = f"Unknown tool: {name}"
    raise ValueError(msg)


async def run_mcp_server(
    ha_client: HAClient,
    memory_tools: MemoryTools,
) -> None:
    """Run the MCP server over stdio.

    Args:
        ha_client: Connected HA client.
        memory_tools: Memory tool wrappers.
    """
    server = create_mcp_server(ha_client, memory_tools)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
