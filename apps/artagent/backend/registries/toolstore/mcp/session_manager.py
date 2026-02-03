"""
MCP Session Manager.

Manages per-session MCP server connections and tool registration.
Coordinates tool discovery and execution across multiple MCP servers
for a single voice session.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from utils.ml_logging import get_logger

from .adapter import MCPToolAdapter
from .client import MCPClientSession, MCPServerConfig, MCPToolInfo

logger = get_logger("mcp.session_manager")


@dataclass
class MCPSessionManager:
    """
    Session-scoped manager for MCP server connections.

    Coordinates connections to multiple MCP servers, discovers tools,
    and routes tool execution requests to the appropriate server.

    Example:
        manager = MCPSessionManager(session_id="abc123")
        await manager.connect_servers([
            MCPServerConfig(name="cardapi", url="http://localhost:80"),
        ])

        # Get all discovered tools
        tools = manager.get_tool_schemas()

        # Execute a tool
        result = await manager.execute_tool("cardapi_lookup_decline_code", {"code": "51"})

        # Cleanup
        await manager.disconnect_all()
    """

    session_id: str
    _sessions: dict[str, MCPClientSession] = field(default_factory=dict, repr=False)
    _tools_cache: dict[str, MCPToolInfo] = field(default_factory=dict, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def connected_servers(self) -> list[str]:
        """Get list of connected server names."""
        return [name for name, session in self._sessions.items() if session.is_connected]

    @property
    def available_tools(self) -> list[str]:
        """Get list of all available tool names (with prefixes)."""
        return list(self._tools_cache.keys())

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """
        Connect to a single MCP server.

        Args:
            config: Server configuration

        Returns:
            True if connection was successful
        """
        async with self._lock:
            if config.name in self._sessions:
                existing = self._sessions[config.name]
                if existing.is_connected:
                    logger.debug(f"MCP server {config.name} already connected")
                    return True

            session = MCPClientSession(config)
            if await session.connect():
                self._sessions[config.name] = session

                # Cache discovered tools with prefixed names
                for tool in session.tools:
                    prefixed_name = tool.prefixed_name
                    self._tools_cache[prefixed_name] = tool
                    logger.debug(f"Cached MCP tool: {prefixed_name}")

                logger.info(
                    f"[{self.session_id}] Connected to MCP server {config.name}, "
                    f"discovered {len(session.tools)} tools"
                )
                return True

            logger.warning(f"[{self.session_id}] Failed to connect to MCP server {config.name}")
            return False

    async def connect_servers(self, configs: list[MCPServerConfig]) -> dict[str, bool]:
        """
        Connect to multiple MCP servers.

        Args:
            configs: List of server configurations

        Returns:
            Dict mapping server names to connection success status
        """
        results = {}
        for config in configs:
            results[config.name] = await self.connect_server(config)
        return results

    async def disconnect_server(self, server_name: str) -> None:
        """
        Disconnect from a specific MCP server.

        Args:
            server_name: Name of the server to disconnect
        """
        async with self._lock:
            session = self._sessions.pop(server_name, None)
            if session:
                await session.disconnect()

                # Remove cached tools for this server
                to_remove = [
                    name for name, tool in self._tools_cache.items()
                    if tool.server_name == server_name
                ]
                for name in to_remove:
                    del self._tools_cache[name]

                logger.info(f"[{self.session_id}] Disconnected from MCP server {server_name}")

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        async with self._lock:
            for session in self._sessions.values():
                await session.disconnect()
            self._sessions.clear()
            self._tools_cache.clear()
            logger.info(f"[{self.session_id}] Disconnected from all MCP servers")

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas for all discovered MCP tools.

        Returns:
            List of tool schemas in OpenAI format
        """
        schemas = []
        adapter = MCPToolAdapter("")  # Server name not needed for schema generation

        for tool in self._tools_cache.values():
            schemas.append(adapter.to_openai_tool(tool))

        return schemas

    def get_tools_for_server(self, server_name: str) -> list[dict[str, Any]]:
        """
        Get tool schemas for a specific MCP server.

        Args:
            server_name: Name of the MCP server

        Returns:
            List of tool schemas from that server
        """
        adapter = MCPToolAdapter(server_name)
        return [
            adapter.to_openai_tool(tool)
            for tool in self._tools_cache.values()
            if tool.server_name == server_name
        ]

    def is_mcp_tool(self, tool_name: str) -> bool:
        """
        Check if a tool name corresponds to an MCP tool.

        Args:
            tool_name: The tool name to check

        Returns:
            True if the tool is from an MCP server
        """
        return tool_name in self._tools_cache

    def get_tool_server(self, tool_name: str) -> str | None:
        """
        Get the server name for a tool.

        Args:
            tool_name: The prefixed tool name

        Returns:
            Server name, or None if tool not found
        """
        tool = self._tools_cache.get(tool_name)
        return tool.server_name if tool else None

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute an MCP tool.

        Args:
            tool_name: The prefixed tool name (e.g., "cardapi_lookup_decline_code")
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        tool_info = self._tools_cache.get(tool_name)
        if not tool_info:
            return {
                "success": False,
                "error": f"MCP tool not found: {tool_name}",
            }

        session = self._sessions.get(tool_info.server_name)
        if not session or not session.is_connected:
            return {
                "success": False,
                "error": f"MCP server not connected: {tool_info.server_name}",
            }

        # Call the tool using the original (non-prefixed) name
        logger.info(
            f"[{self.session_id}] Executing MCP tool {tool_name} "
            f"(server={tool_info.server_name}, args={arguments})"
        )
        return await session.call_tool(tool_info.name, arguments)

    async def refresh_tools(self, server_name: str | None = None) -> int:
        """
        Refresh tool discovery from MCP server(s).

        Args:
            server_name: Specific server to refresh, or None for all

        Returns:
            Number of tools discovered
        """
        total = 0
        async with self._lock:
            servers = (
                [server_name] if server_name else list(self._sessions.keys())
            )

            for name in servers:
                session = self._sessions.get(name)
                if session and session.is_connected:
                    # Clear existing tools for this server
                    to_remove = [
                        tool_name for tool_name, tool in self._tools_cache.items()
                        if tool.server_name == name
                    ]
                    for tool_name in to_remove:
                        del self._tools_cache[tool_name]

                    # Re-discover tools
                    tools = await session.list_tools()
                    for tool in tools:
                        self._tools_cache[tool.prefixed_name] = tool
                    total += len(tools)

        logger.info(f"[{self.session_id}] Refreshed tools, total available: {total}")
        return total

    def __len__(self) -> int:
        """Get number of connected servers."""
        return len(self.connected_servers)
