"""
Personalized Greeting Tool
==========================

Generates ultra-personalized greetings using customer intelligence.
Part of the banking scenario for high-touch private banking experience.

Usage:
    The agent calls this tool to get a personalized greeting based on:
    - Customer's relationship tier (Platinum, Gold, Silver, Bronze)
    - Communication style preference
    - Account health status
    - Active alerts or pending items
    - Relationship duration

Example tool call:
    {
        "name": "generate_personalized_greeting",
        "arguments": {
            "agent_name": "AuthAgent",
            "caller_name": "John Smith",
            "customer_intelligence": {...}
        }
    }
"""

from __future__ import annotations

from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.personalized_greeting")


# ═══════════════════════════════════════════════════════════════════════════════
# GREETING GENERATION LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

AGENT_DISPLAY_NAMES = {
    "AuthAgent": "Authentication",
    "FraudAgent": "Fraud Detection",
    "Fraud": "Fraud Detection",
    "Concierge": "Concierge",
    "ComplianceDesk": "Compliance",
    "Compliance": "Compliance",
    "InvestmentAdvisor": "Investment",
    "Trading": "Trading",
    "CardRecommendation": "Card Services",
    "Agency": "Transfer Agency",
    "TransferAgency": "Transfer Agency",
}


def _get_display_name(agent_name: str) -> str:
    """Map internal agent name to friendly display name."""
    return AGENT_DISPLAY_NAMES.get(agent_name, agent_name)


def _extract_first_name(full_name: str | None) -> str:
    """Extract first name from full name."""
    if not full_name:
        return "there"
    parts = full_name.strip().split()
    return parts[0] if parts else "there"


def generate_personalized_greeting(
    agent_name: str,
    caller_name: str | None = None,
    institution_name: str | None = None,
    customer_intelligence: dict[str, Any] | None = None,
    is_return_visit: bool = False,
) -> dict[str, Any]:
    """
    Generate a personalized greeting based on customer intelligence.

    Args:
        agent_name: Name of the agent generating the greeting
        caller_name: Customer's name
        institution_name: Bank/institution name
        customer_intelligence: Customer data including relationship tier,
            communication style, account health, alerts, etc.
        is_return_visit: Whether this is a return visit to this agent

    Returns:
        Dictionary with greeting text and metadata
    """
    try:
        # Extract customer data
        ci = customer_intelligence or {}
        relationship = ci.get("relationship_context", {})
        account_status = ci.get("account_status", {})
        memory_score = ci.get("memory_score", {})

        # Core fields
        first_name = _extract_first_name(caller_name)
        institution = institution_name or "our firm"
        display_name = _get_display_name(agent_name)

        # Relationship data
        tier = (relationship.get("relationship_tier") or "valued").lower()
        years = relationship.get("relationship_duration_years") or 0
        style = memory_score.get("communication_style") or "Direct/Business-focused"
        health = account_status.get("account_health_score") or 95
        alerts = ci.get("active_alerts") or []

        # ───────────────────────────────────────────────────────────────────
        # Return visit greeting (simpler)
        # ───────────────────────────────────────────────────────────────────
        if is_return_visit:
            greeting = (
                f"Welcome back, {first_name}. This is your {display_name} specialist again. "
                f"As a {tier} client, you have my full attention. "
                f"What else can I help you with today?"
            )
            return {
                "success": True,
                "greeting": greeting,
                "tier": tier,
                "is_personalized": True,
                "is_return": True,
            }

        # ───────────────────────────────────────────────────────────────────
        # First visit - full personalized greeting
        # ───────────────────────────────────────────────────────────────────

        # Base greeting based on communication style
        if "Direct" in style or "Business" in style:
            base_greeting = (
                f"Good morning {first_name}. This is your {display_name} "
                f"specialist at {institution}"
            )
        elif "Relationship" in style:
            base_greeting = (
                f"Hello {first_name}, it's great to hear from you. "
                f"This is your dedicated {display_name} specialist"
            )
        else:  # Detail-oriented or other
            base_greeting = (
                f"Good morning {first_name}. I'm your {display_name} specialist, "
                f"and I have your complete account profile ready"
            )

        # Loyalty recognition
        if years >= 3:
            loyalty_note = f"I see you've been with us for {int(years)} years as a {tier} client"
        elif tier in ["platinum", "gold"]:
            loyalty_note = f"As our {tier} client, you have priority access to our specialist team"
        else:
            loyalty_note = f"I have your complete {tier} account profile here"

        # Service context based on account status
        if alerts:
            alert_count = len(alerts)
            service_note = f"I see you have {alert_count} account update{'s' if alert_count > 1 else ''} I can address"
        elif health >= 95:
            service_note = (
                "Your account is in excellent standing, and I'm here to ensure it stays that way"
            )
        elif health >= 80:
            service_note = "I'm here to help optimize your account experience"
        else:
            service_note = "I'm here to help with any concerns about your account"

        greeting = f"{base_greeting}. {loyalty_note}. {service_note}. How can I assist you today?"

        return {
            "success": True,
            "greeting": greeting,
            "tier": tier,
            "communication_style": style,
            "account_health": health,
            "alerts_count": len(alerts),
            "is_personalized": True,
            "is_return": False,
        }

    except Exception as e:
        logger.warning("Error generating personalized greeting: %s", e)
        # Fallback to simple greeting
        first_name = _extract_first_name(caller_name)
        display_name = _get_display_name(agent_name)

        return {
            "success": True,
            "greeting": f"Hello {first_name}. I'm your {display_name} specialist. How can I help you today?",
            "is_personalized": False,
            "fallback_reason": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

PERSONALIZED_GREETING_SCHEMA = {
    "name": "generate_personalized_greeting",
    "description": (
        "Generate a personalized greeting for the caller based on their "
        "relationship tier, communication preferences, and account status. "
        "Use this at the start of a conversation to create a high-touch experience."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the current agent (e.g., 'AuthAgent', 'Concierge')",
            },
            "caller_name": {
                "type": "string",
                "description": "The caller's name if known",
            },
            "institution_name": {
                "type": "string",
                "description": "Name of the financial institution",
            },
            "is_return_visit": {
                "type": "boolean",
                "description": "Whether the caller has visited this agent before in the current session",
                "default": False,
            },
        },
        "required": ["agent_name"],
    },
}


def _execute_personalized_greeting(args: dict[str, Any]) -> dict[str, Any]:
    """Tool executor wrapper."""
    return generate_personalized_greeting(
        agent_name=args.get("agent_name", "Agent"),
        caller_name=args.get("caller_name"),
        institution_name=args.get("institution_name"),
        customer_intelligence=args.get("customer_intelligence"),
        is_return_visit=args.get("is_return_visit", False),
    )


# Register the tool
register_tool(
    name="generate_personalized_greeting",
    schema=PERSONALIZED_GREETING_SCHEMA,
    executor=_execute_personalized_greeting,
    is_handoff=False,
    tags={"banking", "greeting", "personalization"},
)


__all__ = [
    "generate_personalized_greeting",
    "PERSONALIZED_GREETING_SCHEMA",
]
