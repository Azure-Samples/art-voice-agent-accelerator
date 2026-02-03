"""
Tool Registry for Unified Agents
================================

Self-contained tool registry for the unified agent structure.
Supports both local tools and MCP (Model Context Protocol) server tools.

Architecture:
- registry.py: Core registration and execution logic
- schemas/: Tool schema definitions (OpenAI function calling format)
- executors/: Tool implementation functions
- handoffs.py: Handoff tool implementations
- mcp/: MCP client integration for external tool servers

Usage:
    from apps.artagent.backend.registries.toolstore import (
        register_tool,
        get_tool_schema,
        get_tool_executor,
        get_tools_for_agent,
        execute_tool,
        initialize_tools,
    )

    # Initialize all tools
    initialize_tools()

    # Get tools for an agent
    tools = get_tools_for_agent(["get_account_summary", "handoff_fraud_agent"])

    # Execute a tool
    result = await execute_tool("get_account_summary", {"client_id": "123"})
"""

from apps.artagent.backend.registries.toolstore.registry import (
    # Types
    ToolDefinition,
    ToolExecutor,
    ToolSource,
    # Core registration
    execute_tool,
    get_tool_definition,
    get_tool_executor,
    get_tool_schema,
    get_tool_source,
    get_tools_for_agent,
    initialize_tools,
    is_handoff_tool,
    is_mcp_tool,
    list_mcp_tools,
    list_tools,
    register_mcp_tool,
    register_tool,
    unregister_mcp_tools,
)

__all__ = [
    # Core registration
    "register_tool",
    "get_tool_schema",
    "get_tool_executor",
    "get_tool_definition",
    "is_handoff_tool",
    "list_tools",
    "get_tools_for_agent",
    "execute_tool",
    "initialize_tools",
    # Types
    "ToolDefinition",
    "ToolExecutor",
    "ToolSource",
    # MCP support
    "register_mcp_tool",
    "unregister_mcp_tools",
    "list_mcp_tools",
    "get_tool_source",
    "is_mcp_tool",
]
