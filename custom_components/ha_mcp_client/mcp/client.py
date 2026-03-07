"""MCP Client for connecting to external MCP servers."""

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)


class MCPClient:
    """MCP Client for SSE/HTTP transport."""

    def __init__(
        self,
        server_url: str,
        auth_token: str | None = None,
    ) -> None:
        """Initialize the MCP client."""
        self.server_url = server_url.rstrip("/")
        self.auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
        self._message_endpoint: str | None = None
        self._tools: list[dict[str, Any]] = []
        self._resources: list[dict[str, Any]] = []
        self._connected = False
        self._sse_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Return available tools."""
        return self._tools

    @property
    def resources(self) -> list[dict[str, Any]]:
        """Return available resources."""
        return self._resources

    async def connect(self) -> bool:
        """Connect to the MCP server."""
        if self._connected:
            return True

        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers=headers,
        )

        try:
            # Start SSE connection
            self._sse_task = asyncio.create_task(self._sse_loop())

            # Wait for endpoint to be received
            for _ in range(50):  # 5 second timeout
                if self._message_endpoint:
                    break
                await asyncio.sleep(0.1)

            if not self._message_endpoint:
                raise ConnectionError("Failed to receive message endpoint")

            # Initialize
            response = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "ha-mcp-client",
                        "version": "0.1.0",
                    },
                },
            )

            if "error" in response:
                raise ConnectionError(f"Initialize failed: {response['error']}")

            # Send initialized notification
            await self._send_notification("initialized", {})

            # List tools
            tools_response = await self._send_request("tools/list", {})
            self._tools = tools_response.get("result", {}).get("tools", [])

            # List resources
            resources_response = await self._send_request("resources/list", {})
            self._resources = resources_response.get("result", {}).get("resources", [])

            self._connected = True
            _LOGGER.info(
                "Connected to MCP server with %d tools and %d resources",
                len(self._tools),
                len(self._resources),
            )
            return True

        except Exception as e:
            _LOGGER.error("Failed to connect to MCP server: %s", e)
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None

        if self._client:
            await self._client.aclose()
            self._client = None

        self._message_endpoint = None
        self._tools = []
        self._resources = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        if not self._connected:
            raise ConnectionError("Not connected to MCP server")

        response = await self._send_request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

        if "error" in response:
            raise Exception(f"Tool call failed: {response['error']}")

        return response.get("result", {})

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource from the MCP server."""
        if not self._connected:
            raise ConnectionError("Not connected to MCP server")

        response = await self._send_request(
            "resources/read",
            {"uri": uri},
        )

        if "error" in response:
            raise Exception(f"Resource read failed: {response['error']}")

        return response.get("result", {})

    async def _sse_loop(self) -> None:
        """SSE connection loop."""
        if not self._client:
            return

        try:
            async with self._client.stream("GET", f"{self.server_url}/sse") as response:
                event_type: str | None = None
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        if event_type == "endpoint":
                            self._message_endpoint = data
                            _LOGGER.debug("Received message endpoint: %s", data)
                        elif event_type == "message":
                            try:
                                message = json.loads(data)
                                await self._handle_message(message)
                            except json.JSONDecodeError:
                                _LOGGER.warning("Invalid JSON in SSE message")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOGGER.error("SSE connection error: %s", e)
            self._connected = False

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming SSE message."""
        # Store response for pending requests
        msg_id = message.get("id")
        if msg_id and hasattr(self, "_pending_requests"):
            future = self._pending_requests.get(msg_id)
            if future and not future.done():
                future.set_result(message)

    async def _send_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        if not self._client or not self._message_endpoint:
            raise ConnectionError("Not connected")

        msg_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }

        # Setup response future
        if not hasattr(self, "_pending_requests"):
            self._pending_requests: dict[str, asyncio.Future] = {}

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending_requests[msg_id] = future

        try:
            # Send request
            response = await self._client.post(
                self._message_endpoint,
                json=message,
            )
            response.raise_for_status()

            # Wait for response via SSE
            result = await asyncio.wait_for(future, timeout=30.0)
            return result

        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {method} timed out")
        finally:
            self._pending_requests.pop(msg_id, None)

    async def _send_notification(
        self, method: str, params: dict[str, Any]
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._client or not self._message_endpoint:
            raise ConnectionError("Not connected")

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        response = await self._client.post(
            self._message_endpoint,
            json=message,
        )
        response.raise_for_status()
