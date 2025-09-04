"""
Tool Registry for Customer Support Agent

This module provides the tool registry that maps function names to their implementations
and schemas. It follows the same pattern as the production system for consistency.
"""

from typing import Any, Callable, Dict, List

# Import tool functions
from .customer_support_tools import (
    search_product_catalog,
    check_order_status,
    create_return_request,
    escalate_to_human,
)

# Import tool schemas
from .schemas import (
    search_product_catalog_schema,
    check_order_status_schema,
    create_return_request_schema,
    escalate_to_human_schema,
)


# Function mapping registry - maps tool names to actual functions
function_mapping: Dict[str, Callable[..., Any]] = {
    "search_product_catalog": search_product_catalog,
    "check_order_status": check_order_status,
    "create_return_request": create_return_request,
    "escalate_to_human": escalate_to_human,
}

# Available tools list - formatted for OpenAI function calling API
available_tools: List[Dict[str, Any]] = [
    {"type": "function", "function": search_product_catalog_schema},
    {"type": "function", "function": check_order_status_schema},
    {"type": "function", "function": create_return_request_schema},
    {"type": "function", "function": escalate_to_human_schema},
]

# Tool registry - provides easy lookup by tool name
TOOL_REGISTRY: Dict[str, Dict] = {
    tool["function"]["name"]: tool for tool in available_tools
}


def get_tool_function(tool_name: str) -> Callable[..., Any]:
    """
    Get the function implementation for a given tool name.

    Args:
        tool_name: The name of the tool function

    Returns:
        The callable function for the tool

    Raises:
        KeyError: If the tool name is not found in the registry
    """
    if tool_name not in function_mapping:
        raise KeyError(f"Tool '{tool_name}' not found in function mapping")
    return function_mapping[tool_name]


def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """
    Get the schema for a given tool name.

    Args:
        tool_name: The name of the tool

    Returns:
        The tool schema dictionary

    Raises:
        KeyError: If the tool name is not found in the registry
    """
    if tool_name not in TOOL_REGISTRY:
        raise KeyError(f"Tool '{tool_name}' not found in tool registry")
    return TOOL_REGISTRY[tool_name]


def list_available_tools() -> List[str]:
    """
    Get a list of all available tool names.

    Returns:
        List of tool names
    """
    return list(function_mapping.keys())


def validate_tool_registry() -> bool:
    """
    Validate that all tools have both functions and schemas registered.

    Returns:
        True if registry is valid, False otherwise
    """
    function_names = set(function_mapping.keys())
    schema_names = set(TOOL_REGISTRY.keys())

    if function_names != schema_names:
        missing_functions = schema_names - function_names
        missing_schemas = function_names - schema_names

        if missing_functions:
            print(f"Missing functions for schemas: {missing_functions}")
        if missing_schemas:
            print(f"Missing schemas for functions: {missing_schemas}")
        return False

    return True


# Validate registry on import
if __name__ == "__main__":
    if validate_tool_registry():
        print("✅ Tool registry validation passed!")
        print(f"📋 Registered {len(function_mapping)} tools:")
        for tool_name in list_available_tools():
            print(f"  - {tool_name}")
    else:
        print("❌ Tool registry validation failed!")
