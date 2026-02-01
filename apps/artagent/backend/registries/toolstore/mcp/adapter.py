"""
MCP to OpenAI Schema Adapter.

Converts MCP tool schemas to OpenAI function calling format for use
with the tool registry and Azure OpenAI.
"""

from __future__ import annotations

from typing import Any

from utils.ml_logging import get_logger

from .client import MCPToolInfo

logger = get_logger("mcp.adapter")


def mcp_schema_to_openai(tool: MCPToolInfo, *, use_prefix: bool = True) -> dict[str, Any]:
    """
    Convert an MCP tool schema to OpenAI function calling format.

    Args:
        tool: MCP tool information with schema
        use_prefix: If True, prefix tool name with server name for uniqueness

    Returns:
        OpenAI-compatible function schema dict
    """
    name = tool.prefixed_name if use_prefix else tool.name

    # Build the function schema
    schema = {
        "name": name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }

    # Ensure parameters has required structure
    if "type" not in schema["parameters"]:
        schema["parameters"]["type"] = "object"
    if "properties" not in schema["parameters"]:
        schema["parameters"]["properties"] = {}

    return schema


class MCPToolAdapter:
    """
    Adapter for managing MCP tools and converting to registry format.

    Provides utilities for:
    - Converting MCP tool schemas to OpenAI format
    - Building registry-compatible tool definitions
    - Creating tool executors that proxy to MCP servers
    """

    def __init__(self, server_name: str) -> None:
        """
        Initialize adapter for a specific MCP server.

        Args:
            server_name: Name of the MCP server (used for tool prefixes)
        """
        self.server_name = server_name

    def to_openai_schema(self, tool: MCPToolInfo) -> dict[str, Any]:
        """
        Convert MCP tool to OpenAI function schema.

        Args:
            tool: MCP tool information

        Returns:
            OpenAI-compatible function schema
        """
        return mcp_schema_to_openai(tool, use_prefix=True)

    def to_openai_tool(self, tool: MCPToolInfo) -> dict[str, Any]:
        """
        Convert MCP tool to full OpenAI tool format.

        Args:
            tool: MCP tool information

        Returns:
            Dict with type and function schema
        """
        return {
            "type": "function",
            "function": self.to_openai_schema(tool),
        }

    def to_openai_tools(self, tools: list[MCPToolInfo]) -> list[dict[str, Any]]:
        """
        Convert multiple MCP tools to OpenAI format.

        Args:
            tools: List of MCP tool information

        Returns:
            List of OpenAI-compatible tool dicts
        """
        return [self.to_openai_tool(tool) for tool in tools]

    @staticmethod
    def extract_server_and_tool(prefixed_name: str) -> tuple[str, str]:
        """
        Extract server name and tool name from prefixed name.

        Args:
            prefixed_name: Tool name with server prefix (e.g., "cardapi_lookup_decline_code")

        Returns:
            Tuple of (server_name, tool_name)

        Raises:
            ValueError: If name doesn't contain a valid prefix
        """
        parts = prefixed_name.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid prefixed tool name: {prefixed_name}")
        return parts[0], parts[1]

    @staticmethod
    def is_mcp_tool(tool_name: str, known_servers: set[str]) -> bool:
        """
        Check if a tool name appears to be from an MCP server.

        Args:
            tool_name: The tool name to check
            known_servers: Set of known MCP server names

        Returns:
            True if the tool name starts with a known server prefix
        """
        for server in known_servers:
            if tool_name.startswith(f"{server}_"):
                return True
        return False
