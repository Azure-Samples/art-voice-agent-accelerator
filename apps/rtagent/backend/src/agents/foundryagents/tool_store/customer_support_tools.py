"""
Customer Support Tools for Azure Foundry Agents

This module contains customer support tools following Azure AI Foundry best practices
with proper type hints, docstrings, and clear tool descriptions for the AI model.
"""

import json
from typing import Dict, Any

# Simple logger for standalone operation
import logging
logger = logging.getLogger("customer_support_tools")
logging.basicConfig(level=logging.INFO)


def check_order_status(order_id: str) -> Dict[str, Any]:
    """
    Check the current status and details of a customer order.
    
    Use this tool when customers ask about:
    - Order status updates ("Where is my order?")
    - Tracking information ("Track my package")
    - Delivery estimates ("When will my order arrive?")
    - Order details or items ("What did I order?")
    
    Example queries: "Where is my order ORD-12345?", "Track order 67890", "When will my order arrive?"
    
    Args:
        order_id: The unique order identifier (e.g., "ORD-12345", "67890")
        
    Returns:
        Dictionary with order status, tracking info, delivery date, and item details
    """
    logger.info(f"Checking order status for order ID: {order_id}")
    
    # Simulate order lookup - in production this would call an actual API
    return {
        "order_id": order_id,
        "status": "In Transit",
        "estimated_delivery": "2025-09-05",
        "tracking_number": f"TRK{order_id}2025",
        "items": ["Wireless Headphones", "Phone Case"],
        "total": "$89.99",
        "shipping_carrier": "FedEx",
        "last_update": "Package left distribution center"
    }


def search_knowledge_base(query: str) -> Dict[str, Any]:
    """
    Search the company knowledge base for policies, procedures, and product information.
    
    Use this tool when customers ask about:
    - Return and refund policies ("Can I return this?", "What's your return policy?")
    - Shipping information ("How much is shipping?", "Do you ship internationally?")
    - Product warranties ("Is this covered by warranty?")
    - Payment methods ("Do you accept PayPal?", "What payment options do you have?")
    - General company policies ("What are your business hours?")
    
    Example queries: "What's your return policy?", "How much is shipping?", "Do you accept cryptocurrency?"
    
    Args:
        query: The customer's question or search terms
        
    Returns:
        Dictionary with relevant information from the knowledge base
    """
    logger.info(f"Searching knowledge base for: {query}")
    
    # Simulate knowledge base search - in production this would use Azure AI Search
    knowledge_base = {
        "return": "You can return items within 30 days of purchase. Items must be in original condition with tags attached. Refunds processed within 5-7 business days.",
        "shipping": "Free shipping on orders over $50. Standard delivery takes 3-5 business days. Express shipping available for $9.99 (1-2 days). International shipping available.",
        "warranty": "All products come with a 1-year manufacturer warranty covering defects. Extended warranties available at purchase. Warranty claims processed within 7-10 business days.",
        "payment": "We accept all major credit cards (Visa, MasterCard, Amex), PayPal, Apple Pay, Google Pay, and bank transfers. Payment is processed securely at checkout.",
        "hours": "Customer service available 24/7 via chat. Phone support: Mon-Fri 8AM-8PM EST, Sat-Sun 10AM-6PM EST."
    }
    
    # Search for relevant information
    query_lower = query.lower()
    for topic, info in knowledge_base.items():
        if topic in query_lower or any(word in query_lower for word in topic.split()):
            return {
                "query": query,
                "topic": topic.title(),
                "information": info,
                "confidence": 0.95,
                "source": "Company Knowledge Base"
            }
    
    return {
        "query": query,
        "message": "No specific information found. Please contact support for personalized assistance.",
        "confidence": 0.1,
        "suggestion": "Try rephrasing your question or contact our support team directly.",
        "source": "Knowledge Base Search"
    }


def create_support_ticket(customer_email: str, issue_description: str, priority: str = "medium") -> Dict[str, Any]:
    """
    Create a new support ticket for customer issues that require follow-up or investigation.
    
    Use this tool when:
    - Customer has a complex issue requiring investigation ("My order is damaged")
    - Problem cannot be resolved immediately ("I can't log into my account")
    - Customer requests callback or email follow-up ("Please call me back")
    - Issue needs technical team involvement ("Product stopped working")
    - Billing or payment disputes require review
    
    Example scenarios: "My order arrived damaged", "I can't access my account", "Charge on my card is wrong"
    
    Args:
        customer_email: Customer's email address for follow-up communication
        issue_description: Detailed description of the customer's problem
        priority: Urgency level - "low", "medium", "high", or "urgent" (default: "medium")
        
    Returns:
        Dictionary with ticket ID, status, and expected response time
    """
    logger.info(f"Creating support ticket for: {customer_email}")
    
    # Generate ticket ID
    import random
    ticket_id = f"TKT-{random.randint(100000, 999999)}"
    
    # Determine response time based on priority
    response_times = {
        "low": "48 hours",
        "medium": "24 hours", 
        "high": "4 hours",
        "urgent": "1 hour"
    }
    
    return {
        "ticket_id": ticket_id,
        "customer_email": customer_email,
        "issue_description": issue_description,
        "priority": priority,
        "status": "Open",
        "created_date": "2025-09-02",
        "estimated_response": response_times.get(priority, "24 hours"),
        "assigned_team": "Customer Support",
        "next_steps": "Our support team will review and respond via email with detailed assistance"
    }


def escalate_to_human(ticket_id: str, reason: str) -> Dict[str, Any]:
    """
    Escalate a customer issue to a human support agent for immediate personal assistance.
    
    Use this tool when:
    - Customer is frustrated, angry, or dissatisfied ("I want to speak to a manager")
    - Issue is too complex for automated resolution ("This is very complicated")
    - Customer specifically requests to speak with a person ("I need to talk to someone")
    - Multiple attempts to resolve have failed ("Nothing is working")
    - Urgent issues requiring immediate attention ("This is an emergency")
    - Sensitive matters requiring human empathy
    
    Example scenarios: "I want to speak to a manager", "This is urgent", "I'm not satisfied", "I need human help"
    
    Args:
        ticket_id: Existing support ticket ID (if available) or "NEW" for immediate escalation
        reason: Clear explanation of why escalation is needed
        
    Returns:
        Dictionary with escalation details and next steps for human contact
    """
    logger.info(f"Escalating ticket {ticket_id} to human agent")
    
    return {
        "ticket_id": ticket_id,
        "escalation_reason": reason,
        "escalated_to": "Senior Customer Support Manager",
        "escalation_time": "2025-09-02 10:30:00",
        "priority": "High",
        "expected_response": "Within 2 hours",
        "status": "Escalated - Human Agent Assigned",
        "contact_method": "Phone call priority, then email",
        "queue_position": 1,
        "message": "A senior human agent will contact you personally within 2 hours to resolve this issue with the attention it deserves."
    }
