"""MCP SSE Server for Home Assistant."""

import asyncio
import json
import logging
import uuid
from typing import Any
from collections.abc import Callable

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.network import get_url

from .tools import ToolRegistry

_LOGGER = logging.getLogger(__name__)

# MCP Protocol version
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPServer:
    """MCP Server implementation using SSE transport.

    Note: The MCP server uses Home Assistant's built-in HTTP server.
    The port parameter is stored for documentation purposes but the actual
    endpoint is available at /api/ha_mcp_client/sse on HA's HTTP port.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        port: int = 8087,
        tool_registry: "ToolRegistry | None" = None,
    ) -> None:
        """Initialize the MCP server."""
        self.hass = hass
        self.port = port  # Stored for reference, actual endpoint uses HA's HTTP port
        # Use provided tool_registry or create a new one
        self.tool_registry = tool_registry if tool_registry is not None else ToolRegistry(hass)
        self._sessions: dict[str, "MCPSession"] = {}
        self._running = False

    async def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            return

        # Register HTTP views
        self.hass.http.register_view(MCPSSEView(self))
        self.hass.http.register_view(MCPMessageView(self))

        self._running = True
        _LOGGER.info(
            "MCP Server started. Endpoint available at /api/ha_mcp_client/sse"
        )

    async def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False

        # Close all sessions
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()

        _LOGGER.info("MCP Server stopped")

    def create_session(self) -> "MCPSession":
        """Create a new MCP session."""
        session = MCPSession(self)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> "MCPSession | None":
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def get_tools_list(self) -> list[dict[str, Any]]:
        """Get list of available tools in MCP format."""
        tools = []
        for tool in self.tool_registry.get_all():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
            )
        return tools


class MCPSession:
    """Represents an MCP session."""

    def __init__(self, server: MCPServer) -> None:
        """Initialize the session."""
        self.server = server
        self.session_id = str(uuid.uuid4())
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False
        self._initialized = False

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send a message to the client."""
        if not self._closed:
            await self._message_queue.put(message)

    async def receive_message(self) -> dict[str, Any] | None:
        """Receive a message from the queue."""
        if self._closed:
            return None
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=30.0)
        except asyncio.TimeoutError:
            return None

    async def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle an incoming MCP message."""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        _LOGGER.debug("Received MCP message: %s", method)

        if method == "initialize":
            return await self._handle_initialize(msg_id, params)
        elif method == "initialized":
            return await self._handle_initialized(msg_id)
        elif method == "tools/list":
            return await self._handle_tools_list(msg_id)
        elif method == "tools/call":
            return await self._handle_tools_call(msg_id, params)
        elif method == "resources/list":
            return await self._handle_resources_list(msg_id)
        elif method == "ping":
            return await self._handle_ping(msg_id)
        else:
            return self._error_response(msg_id, -32601, f"Unknown method: {method}")

    async def _handle_initialize(
        self, msg_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        _LOGGER.info(
            "MCP client connected: %s %s",
            client_info.get("name", "Unknown"),
            client_info.get("version", ""),
        )

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"listChanged": True},
                },
                "serverInfo": {
                    "name": "ha-mcp-client",
                    "version": "0.1.0",
                },
            },
        }

    async def _handle_initialized(self, msg_id: Any) -> None:
        """Handle initialized notification."""
        self._initialized = True
        _LOGGER.debug("MCP session initialized")
        return None  # Notifications don't get responses

    async def _handle_tools_list(self, msg_id: Any) -> dict[str, Any]:
        """Handle tools/list request."""
        tools = self.server.get_tools_list()
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tools},
        }

    async def _handle_tools_call(
        self, msg_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = await self.server.tool_registry.execute(tool_name, arguments)

            # Convert result to content format
            if isinstance(result, dict):
                content_text = json.dumps(result, indent=2, default=str)
            elif isinstance(result, list):
                content_text = json.dumps(result, indent=2, default=str)
            else:
                content_text = str(result)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": content_text}],
                    "isError": False,
                },
            }
        except Exception as e:
            _LOGGER.error("Tool execution error: %s", e)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True,
                },
            }

    async def _handle_resources_list(self, msg_id: Any) -> dict[str, Any]:
        """Handle resources/list request."""
        # For now, return empty resources list
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": []},
        }

    async def _handle_ping(self, msg_id: Any) -> dict[str, Any]:
        """Handle ping request."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {},
        }

    def _error_response(
        self, msg_id: Any, code: int, message: str
    ) -> dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }

    async def close(self) -> None:
        """Close the session."""
        self._closed = True


class MCPSSEView(HomeAssistantView):
    """View for MCP SSE endpoint."""

    url = "/api/ha_mcp_client/sse"
    name = "api:ha_mcp_client:sse"
    requires_auth = True

    def __init__(self, server: MCPServer) -> None:
        """Initialize the view."""
        self.server = server

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Handle SSE connection."""
        session = self.server.create_session()

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

        await response.prepare(request)

        # Send endpoint event with message URL
        base_url = get_url(self.server.hass, prefer_external=False)
        endpoint = f"{base_url}/api/ha_mcp_client/sse/messages?sessionId={session.session_id}"
        await response.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())

        try:
            while not session._closed:
                message = await session.receive_message()
                if message is not None:
                    data = json.dumps(message)
                    await response.write(f"event: message\ndata: {data}\n\n".encode())
                else:
                    # Send keepalive
                    await response.write(b": keepalive\n\n")
        except asyncio.CancelledError:
            pass
        finally:
            self.server.remove_session(session.session_id)

        return response


class MCPMessageView(HomeAssistantView):
    """View for MCP message endpoint."""

    url = "/api/ha_mcp_client/sse/messages"
    name = "api:ha_mcp_client:sse:messages"
    requires_auth = True

    def __init__(self, server: MCPServer) -> None:
        """Initialize the view."""
        self.server = server

    async def post(self, request: web.Request) -> web.Response:
        """Handle incoming MCP message."""
        session_id = request.query.get("sessionId")
        if not session_id:
            return web.Response(status=400, text="Missing sessionId")

        session = self.server.get_session(session_id)
        if session is None:
            return web.Response(status=404, text="Session not found")

        try:
            message = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        # Handle the message
        response = await session.handle_message(message)

        # If there's a response, send it via SSE
        if response is not None:
            await session.send_message(response)

        return web.Response(status=202, text="Accepted")
