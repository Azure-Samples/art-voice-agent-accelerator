"""
MCP Client Integration Module
=============================

Provides MCP (Model Context Protocol) client support for the tool registry,
enabling dynamic discovery and execution of tools from external MCP servers.

This module enables agents to:
- Connect to MCP servers at session start
- Discover available tools via MCP protocol
- Execute tools through MCP with automatic schema conversion
- Clean up connections on session end

Key Components:
- MCPClientSession: Connection lifecycle management
- MCPToolAdapter: Convert MCP schemas to OpenAI function format
- MCPSessionManager: Per-session MCP connection coordination

Usage:
    from apps.artagent.backend.registries.toolstore.mcp import (
        MCPSessionManager,
        MCPServerConfig,
        get_mcp_configs_for_agent,
    )

    # Initialize at session start
    manager = MCPSessionManager(session_id="abc123")
    
    # Get configs for an agent's mcp_servers list
    configs = get_mcp_configs_for_agent(agent.mcp_servers)
    await manager.connect_servers(configs)

    # Get tools for agent
    tools = manager.get_tool_schemas()

    # Execute tool
    result = await manager.execute_tool("cardapi_lookup_decline_code", {"code": "51"})

    # Cleanup on session end
    await manager.disconnect_all()
"""

from .client import MCPClientSession, MCPServerConfig, MCPTransport
from .adapter import MCPToolAdapter, mcp_schema_to_openai
from .session_manager import MCPSessionManager


def get_mcp_configs_for_agent(mcp_server_names: list[str]) -> list[MCPServerConfig]:
    """
    Get MCPServerConfig objects for a list of server names.
    
    Resolves server names to their full configuration from settings.
    Only returns configs for servers that have valid URLs configured.
    
    Args:
        mcp_server_names: List of MCP server names from agent.mcp_servers
        
    Returns:
        List of MCPServerConfig objects ready for connection
        
    Example:
        # In agent.yaml:
        # mcp_servers:
        #   - cardapi
        
        configs = get_mcp_configs_for_agent(["cardapi"])
        # Returns [MCPServerConfig(name="cardapi", url="http://...")]
    """
    from apps.artagent.backend.config.settings import get_mcp_server_config
    
    configs: list[MCPServerConfig] = []
    
    for name in mcp_server_names:
        config_dict = get_mcp_server_config(name)
        if not config_dict or not config_dict.get("url"):
            continue
            
        configs.append(MCPServerConfig(
            name=config_dict["name"],
            url=config_dict["url"],
            transport=MCPTransport(config_dict.get("transport", "streamable-http")),
            timeout=config_dict.get("timeout", 30.0),
        ))
        
    return configs


__all__ = [
    "MCPClientSession",
    "MCPServerConfig",
    "MCPTransport",
    "MCPToolAdapter",
    "mcp_schema_to_openai",
    "MCPSessionManager",
    "get_mcp_configs_for_agent",
]
