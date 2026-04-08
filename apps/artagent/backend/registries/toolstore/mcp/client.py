"""
MCP Client Session Management.

Provides async client for connecting to and interacting with MCP servers.
Supports SSE (Server-Sent Events) transport for HTTP-based MCP servers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from utils.ml_logging import get_logger

logger = get_logger("mcp.client")


class MCPTransport(str, Enum):
    """Supported MCP transport types.

    Per MCP spec 2025-11-25:
    - STREAMABLE_HTTP: New HTTP-based transport (recommended for deployed servers)
    - SSE: Server-Sent Events (legacy, still supported)
    - STDIO: Standard I/O for local CLI usage
    - HTTP: Generic HTTP (alias for streamable-http)
    """

    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    STDIO = "stdio"
    HTTP = "http"

    @classmethod
    def _missing_(cls, value: object) -> "MCPTransport | None":
        """Handle transport type aliases and normalize values."""
        if isinstance(value, str):
            normalized = value.lower().replace("_", "-")
            # Map aliases to canonical values
            aliases = {
                "streamable-http": cls.STREAMABLE_HTTP,
                "streamablehttp": cls.STREAMABLE_HTTP,
                "http": cls.HTTP,
                "sse": cls.SSE,
                "stdio": cls.STDIO,
            }
            return aliases.get(normalized)
        return None


@dataclass
class MCPServerConfig:
    """Configuration for connecting to an MCP server."""

    name: str
    url: str
    transport: MCPTransport | str = MCPTransport.STREAMABLE_HTTP
    timeout: float = 30.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.transport, str):
            try:
                self.transport = MCPTransport(self.transport.lower())
            except ValueError:
                logger.warning(
                    f"Unknown transport '{self.transport}', defaulting to streamable-http"
                )
                self.transport = MCPTransport.STREAMABLE_HTTP


@dataclass
class MCPToolInfo:
    """Information about a tool discovered from an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str

    @property
    def prefixed_name(self) -> str:
        """Get the tool name with server prefix for uniqueness."""
        return f"{self.server_name}_{self.name}"


@dataclass
class MCPResourceInfo:
    """Information about a resource from an MCP server."""

    uri: str
    name: str
    description: str
    mime_type: str
    server_name: str


class MCPClientSession:
    """
    Async client session for communicating with an MCP server.

    Handles connection lifecycle, tool discovery, and tool execution
    via the MCP protocol over HTTP/SSE transport.

    Example:
        async with MCPClientSession(config) as session:
            tools = await session.list_tools()
            result = await session.call_tool("lookup_decline_code", {"code": "51"})
    """

    def __init__(self, config: MCPServerConfig) -> None:
        """
        Initialize MCP client session.

        Args:
            config: Server configuration with connection details
        """
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False
        self._tools: list[MCPToolInfo] = []
        self._resources: list[MCPResourceInfo] = []
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if the session is connected."""
        return self._connected and self._client is not None

    @property
    def server_name(self) -> str:
        """Get the server name for this session."""
        return self.config.name

    @property
    def tools(self) -> list[MCPToolInfo]:
        """Get cached list of discovered tools."""
        return self._tools.copy()

    async def connect(self) -> bool:
        """
        Establish connection to the MCP server.

        Returns:
            True if connection was successful, False otherwise
        """
        async with self._lock:
            if self._connected:
                return True

            try:
                # Strip /mcp suffix - health endpoints are at root /health, not /mcp/health
                base_url = self.config.url.rstrip("/")
                if base_url.endswith("/mcp"):
                    base_url = base_url[:-4]

                self._client = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=self.config.timeout,
                    headers=self.config.headers,
                )

                # Verify connection with health check
                response = await self._client.get("/health")
                if response.status_code != 200:
                    logger.warning(
                        f"MCP server {self.config.name} health check failed: {response.status_code}"
                    )
                    return False

                self._connected = True
                logger.info(f"Connected to MCP server: {self.config.name} at {self.config.url}")

                # Auto-discover tools on connect
                await self._discover_tools()
                return True

            except httpx.ConnectError as e:
                logger.error(f"Failed to connect to MCP server {self.config.name}: {e}")
                return False
            except Exception as e:
                logger.error(
                    f"Unexpected error connecting to MCP server {self.config.name}: {e}",
                    exc_info=True,
                )
                return False

    async def disconnect(self) -> None:
        """Close the connection to the MCP server."""
        async with self._lock:
            if self._client:
                await self._client.aclose()
                self._client = None
            self._connected = False
            self._tools.clear()
            self._resources.clear()
            logger.info(f"Disconnected from MCP server: {self.config.name}")

    async def reconnect(self) -> bool:
        """
        Reconnect to the MCP server.

        Returns:
            True if reconnection was successful
        """
        await self.disconnect()
        for attempt in range(self.config.retry_attempts):
            if await self.connect():
                return True
            await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        return False

    async def _discover_tools(self) -> None:
        """
        Discover available tools from the MCP server.

        Fetches tool schemas from the /tools/list endpoint. All MCP servers
        (including CardAPI) should expose this endpoint for dynamic discovery.
        """
        try:
            # Try to get tools via /tools/list endpoint (dynamic discovery)
            response = await self._client.get("/tools/list")
            if response.status_code == 200:
                data = response.json()
                tools_data = data.get("tools", [])
                self._tools = [
                    MCPToolInfo(
                        name=t["name"],
                        description=t.get("description", f"Tool: {t['name']}"),
                        input_schema=t.get("input_schema", {"type": "object", "properties": {}}),
                        server_name=self.config.name,
                    )
                    for t in tools_data
                ]
                logger.info(
                    f"Discovered {len(self._tools)} tools from MCP server {self.config.name} via /tools/list"
                )
                return

            logger.warning(
                "MCP server %s returned %s for /tools/list; no fallback available",
                self.config.name,
                response.status_code,
            )
            self._tools = []
            return
        except Exception as e:
            logger.warning(
                "Dynamic tool discovery failed for %s via /tools/list: %s",
                self.config.name,
                e,
            )
            self._tools = []

    async def list_tools(self) -> list[MCPToolInfo]:
        """
        Get list of available tools from the MCP server.

        Returns:
            List of tool information objects
        """
        if not self._tools:
            await self._discover_tools()
        return self._tools.copy()

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call (without server prefix)
            arguments: Tool arguments as a dictionary

        Returns:
            Tool execution result
        """
        if not self.is_connected:
            return {
                "success": False,
                "error": f"Not connected to MCP server {self.config.name}",
            }

        try:
            # Map tool names to HTTP endpoints (CardAPI-specific)
            endpoint_map = {
                "lookup_decline_code": "/tools/lookup_decline_code",
                "search_decline_codes": "/tools/search_decline_codes",
            }

            endpoint = endpoint_map.get(tool_name)
            if endpoint:
                response = await self._client.get(endpoint, params=arguments)
                response.raise_for_status()
                data = response.json()
                return {
                    "success": data.get("success", True),
                    "result": data.get("result", data),
                }

            # Default: try POST to /tools/{tool_name}
            response = await self._client.post(
                f"/tools/{tool_name}",
                json=arguments,
            )
            response.raise_for_status()
            return {"success": True, "result": response.json()}

        except httpx.HTTPStatusError as e:
            error_msg = f"Tool {tool_name} returned error: {e.response.status_code}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Failed to call tool {tool_name}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    async def __aenter__(self) -> MCPClientSession:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
