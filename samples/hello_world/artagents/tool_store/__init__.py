"""
Customer Support Agent Tool Store

This package contains all the tools, schemas, and registry for the customer support agent.
"""

from .customer_support_tools import (
    search_product_catalog,
    check_order_status,
    create_return_request,
    escalate_to_human,
)

from .schemas import (
    search_product_catalog_schema,
    check_order_status_schema,
    create_return_request_schema,
    escalate_to_human_schema,
)

from .tool_registry import (
    function_mapping,
    available_tools,
    TOOL_REGISTRY,
    get_tool_function,
    get_tool_schema,
    list_available_tools,
    validate_tool_registry,
)

__all__ = [
    # Tool functions
    "search_product_catalog",
    "check_order_status",
    "create_return_request",
    "escalate_to_human",
    # Tool schemas
    "search_product_catalog_schema",
    "check_order_status_schema",
    "create_return_request_schema",
    "escalate_to_human_schema",
    # Registry components
    "function_mapping",
    "available_tools",
    "TOOL_REGISTRY",
    "get_tool_function",
    "get_tool_schema",
    "list_available_tools",
    "validate_tool_registry",
]
