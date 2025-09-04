"""
Tool Schemas for Customer Support Agent

This module defines the OpenAI function calling schemas for all customer support tools.
These schemas define the parameters, types, and descriptions for each tool function.
"""

# Tool schema for product catalog search
search_product_catalog_schema = {
    "name": "search_product_catalog",
    "description": "Search the product catalog for information about products including specs, pricing, and availability",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search term or product ID to look up in catalog",
            }
        },
        "required": ["query"],
    },
}

# Tool schema for order status checking
check_order_status_schema = {
    "name": "check_order_status",
    "description": "Check the status and tracking information for a customer order",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID to look up (e.g., ORD123456)",
            }
        },
        "required": ["order_id"],
    },
}

# Tool schema for return request creation
create_return_request_schema = {
    "name": "create_return_request",
    "description": "Create a return request for a customer order",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID for the return request",
            },
            "reason": {
                "type": "string",
                "description": "Reason for the return (e.g., defective item, wrong size)",
            },
        },
        "required": ["order_id", "reason"],
    },
}

# Tool schema for human escalation
escalate_to_human_schema = {
    "name": "escalate_to_human",
    "description": "Escalate the conversation to a human agent when the issue is too complex",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Reason for escalation (e.g., complex technical issue, customer request)",
            }
        },
        "required": ["reason"],
    },
}
