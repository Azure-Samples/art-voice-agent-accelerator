"""
Customer Support Agent Tools

This module contains the business logic functions for the customer support agent.
These tools handle product searches, order management, returns, and escalations.
"""

import json
from datetime import datetime
from typing import Dict, Any


# Mock database for demonstration
PRODUCT_CATALOG = {
    "laptop-001": {
        "name": "Demo Laptop Pro",
        "price": 1299.99,
        "specs": "Intel i7, 16GB RAM, 512GB SSD",
        "availability": "In Stock",
    },
    "phone-001": {
        "name": "Demo Phone X",
        "price": 899.99,
        "specs": "6.1 inch display, 128GB storage",
        "availability": "Limited Stock",
    },
}

ORDER_DATABASE = {
    "ORD123456": {
        "status": "Shipped",
        "tracking": "1Z999AA1234567890",
        "items": ["Demo Laptop Pro"],
        "estimated_delivery": "2024-08-22",
    },
    "ORD789012": {
        "status": "Processing",
        "tracking": None,
        "items": ["Demo Phone X"],
        "estimated_delivery": "2024-08-25",
    },
}


async def search_product_catalog(params: Dict[str, Any]) -> str:
    """
    Search the product catalog for information.

    Args:
        params: {"query": "search term or product ID"}

    Returns:
        JSON string with product information
    """
    query = params.get("query", "").lower()

    # Search by product ID
    if query in PRODUCT_CATALOG:
        product = PRODUCT_CATALOG[query]
        return json.dumps(
            {
                "success": True,
                "product": product,
                "message": f"Found product: {product['name']}",
            }
        )

    # Search by name
    matches = []
    for pid, product in PRODUCT_CATALOG.items():
        if query in product["name"].lower():
            matches.append({"id": pid, **product})

    if matches:
        return json.dumps(
            {
                "success": True,
                "products": matches,
                "message": f"Found {len(matches)} matching products",
            }
        )

    return json.dumps(
        {"success": False, "message": "No products found matching your search"}
    )


async def check_order_status(params: Dict[str, Any]) -> str:
    """
    Check the status of a customer order.

    Args:
        params: {"order_id": "ORD123456"}

    Returns:
        JSON string with order status information
    """
    order_id = params.get("order_id", "").upper()

    if order_id in ORDER_DATABASE:
        order = ORDER_DATABASE[order_id]
        return json.dumps(
            {
                "success": True,
                "order": order,
                "message": f"Order {order_id} status: {order['status']}",
            }
        )

    return json.dumps(
        {
            "success": False,
            "message": "Order not found. Please check your order number.",
        }
    )


async def create_return_request(params: Dict[str, Any]) -> str:
    """
    Create a return request for a customer.

    Args:
        params: {"order_id": "ORD123456", "reason": "defective item"}

    Returns:
        JSON string with return request confirmation
    """
    order_id = params.get("order_id", "")
    reason = params.get("reason", "No reason provided")

    # Generate return request ID
    return_id = f"RET{datetime.now().strftime('%Y%m%d%H%M%S')}"

    return json.dumps(
        {
            "success": True,
            "return_id": return_id,
            "order_id": order_id,
            "reason": reason,
            "message": f"Return request {return_id} created successfully. You will receive return instructions via email.",
        }
    )


async def escalate_to_human(params: Dict[str, Any]) -> str:
    """
    Escalate the conversation to a human agent.

    Args:
        params: {"reason": "complex technical issue"}

    Returns:
        JSON string with escalation confirmation
    """
    reason = params.get("reason", "Customer requested human assistance")

    return json.dumps(
        {
            "success": True,
            "escalated": True,
            "reason": reason,
            "message": "I'm connecting you with a human agent who can better assist you. Please hold for a moment.",
        }
    )
