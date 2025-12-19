"""
Handoff Tools
=============

Agent handoff tools for multi-agent orchestration.
These tools trigger agent transfers in both VoiceLive and SpeechCascade orchestrators.

Each handoff tool returns a standardized payload:
{
    "handoff": True,
    "target_agent": "AgentName",
    "message": "Transition message to speak",
    "handoff_summary": "Brief summary",
    "handoff_context": {...}
}

IMPORTANT: Handoffs are SILENT - the agent must NOT say "Let me connect you" or
similar before calling a handoff tool. The target agent will greet the customer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.handoffs")

# Suffix to add to all handoff tool descriptions to reinforce silent handoff behavior
SILENT_HANDOFF_NOTE = " IMPORTANT: Call this tool immediately without saying anything first. The target agent will greet the customer."


def _utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def _cleanup_context(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None, empty strings, and control flags from context."""
    return {
        key: value for key, value in (data or {}).items() if value not in (None, "", [], {}, False)
    }


def _build_handoff_payload(
    *,
    target_agent: str,
    message: str,
    summary: str,
    context: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build standardized handoff payload for orchestrator."""
    payload = {
        "handoff": True,
        "target_agent": target_agent,
        "message": message,
        "handoff_summary": summary,
        "handoff_context": _cleanup_context(context),
    }
    if extra:
        payload.update(extra)
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

handoff_concierge_schema: dict[str, Any] = {
    "name": "handoff_concierge",
    "description": (
        "Return customer to Erica Concierge (main banking assistant). "
        "Use after completing specialist task or when customer needs different help."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "previous_topic": {"type": "string", "description": "What you helped with"},
            "resolution_summary": {"type": "string", "description": "Brief summary of resolution"},
        },
        "required": ["client_id"],
    },
}

handoff_fraud_agent_schema: dict[str, Any] = {
    "name": "handoff_fraud_agent",
    "description": (
        "Transfer to Fraud Detection Agent for suspicious activity investigation. "
        "Use when customer reports fraud, unauthorized charges, or suspicious transactions."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "fraud_type": {
                "type": "string",
                "description": "Type of fraud (unauthorized_charge, identity_theft, card_stolen, etc.)",
            },
            "issue_summary": {
                "type": "string",
                "description": "Brief summary of the fraud concern",
            },
        },
        "required": ["client_id"],
    },
}

handoff_to_auth_schema: dict[str, Any] = {
    "name": "handoff_to_auth",
    "description": (
        "Transfer to Authentication Agent for identity verification. "
        "Use when MFA or additional identity verification is required." + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "reason": {"type": "string", "description": "Reason for authentication required"},
        },
        "required": ["client_id"],
    },
}

handoff_card_recommendation_schema: dict[str, Any] = {
    "name": "handoff_card_recommendation",
    "description": (
        "Transfer to Card Recommendation Agent for credit card advice. "
        "Use when customer asks about new cards, rewards, or upgrades." + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "customer_goal": {
                "type": "string",
                "description": "What they want (lower fees, better rewards, travel perks)",
            },
            "spending_preferences": {
                "type": "string",
                "description": "Where they spend most (travel, dining, groceries)",
            },
            "current_cards": {"type": "string", "description": "Cards they currently have"},
        },
        "required": ["client_id"],
    },
}

handoff_investment_advisor_schema: dict[str, Any] = {
    "name": "handoff_investment_advisor",
    "description": (
        "Transfer to Investment Advisor for retirement and investment questions. "
        "Use for 401(k) rollover, IRA, retirement planning topics." + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "topic": {"type": "string", "description": "Main topic (rollover, IRA, retirement)"},
            "employment_change": {
                "type": "string",
                "description": "Job change details if applicable",
            },
            "retirement_question": {
                "type": "string",
                "description": "Specific retirement question",
            },
        },
        "required": ["client_id"],
    },
}

handoff_compliance_desk_schema: dict[str, Any] = {
    "name": "handoff_compliance_desk",
    "description": (
        "Transfer to Compliance Desk for AML/FATCA verification and regulatory review. "
        "Use for compliance issues, sanctions screening, or regulatory requirements."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer or client code"},
            "compliance_issue": {"type": "string", "description": "Type of compliance issue"},
            "urgency": {
                "type": "string",
                "enum": ["normal", "high", "expedited"],
                "description": "Urgency level",
            },
            "transaction_details": {"type": "string", "description": "Transaction context"},
        },
        "required": ["client_id"],
    },
}

handoff_transfer_agency_agent_schema: dict[str, Any] = {
    "name": "handoff_transfer_agency_agent",
    "description": (
        "Transfer to Transfer Agency Agent for DRIP liquidations and institutional services. "
        "Use for dividend reinvestment, institutional client codes, position inquiries."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "request_type": {
                "type": "string",
                "description": "Type of request (drip_liquidation, compliance_inquiry, position_inquiry)",
            },
            "client_code": {
                "type": "string",
                "description": "Institutional client code (e.g., GCA-48273)",
            },
            "drip_symbols": {"type": "string", "description": "Stock symbols to liquidate"},
        },
        "required": [],
    },
}

handoff_bank_advisor_schema: dict[str, Any] = {
    "name": "handoff_bank_advisor",
    "description": (
        "Schedule callback with Merrill human advisor for personalized investment advice. "
        "Use when customer needs human specialist for complex investment decisions."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "reason": {"type": "string", "description": "Reason for advisor callback"},
            "context": {"type": "string", "description": "Summary of conversation and needs"},
        },
        "required": ["client_id", "reason"],
    },
}

handoff_to_trading_schema: dict[str, Any] = {
    "name": "handoff_to_trading",
    "description": (
        "Transfer to Trading Desk for complex execution. "
        "Use for FX conversions, large trades, or institutional execution." + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "trade_details": {"type": "string", "description": "Details of the trade"},
            "complexity_level": {
                "type": "string",
                "enum": ["standard", "institutional"],
                "description": "Complexity",
            },
        },
        "required": ["client_id"],
    },
}

handoff_general_kb_schema: dict[str, Any] = {
    "name": "handoff_general_kb",
    "description": (
        "Transfer to General Knowledge Base agent for general inquiries. "
        "No authentication required. Use for product info, FAQs, policies, and general questions."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic of inquiry (products, policies, faq, general)",
            },
            "question": {
                "type": "string",
                "description": "The user's question or topic of interest",
            },
        },
        "required": [],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC HANDOFF SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

handoff_to_agent_schema: dict[str, Any] = {
    "name": "handoff_to_agent",
    "description": (
        "Generic handoff tool to transfer to any available agent. "
        "Use when there is no specific handoff tool for the target agent. "
        "The target_agent must be a valid agent name in the current scenario."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "The name of the agent to transfer to (e.g., 'FraudAgent', 'InvestmentAdvisor')",
            },
            "reason": {
                "type": "string",
                "description": "Brief reason for the handoff - why is this transfer needed?",
            },
            "context": {
                "type": "string",
                "description": "Summary of conversation context to pass to the target agent",
            },
            "client_id": {
                "type": "string",
                "description": "Customer identifier if available",
            },
        },
        "required": ["target_agent", "reason"],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# INSURANCE HANDOFF SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

handoff_policy_advisor_schema: dict[str, Any] = {
    "name": "handoff_policy_advisor",
    "description": (
        "Transfer to Policy Advisor for insurance policy questions and changes. "
        "Use for policy modifications, renewals, coverage questions, or cancellations."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier from verify_client_identity"},
            "caller_name": {"type": "string", "description": "Customer name from verify_client_identity"},
            "policy_type": {
                "type": "string",
                "description": "Type of policy (auto, home, health, life, umbrella)",
            },
            "request_type": {
                "type": "string",
                "description": "What they need (change, renewal, question, cancellation)",
            },
            "policy_number": {"type": "string", "description": "Policy number if known"},
        },
        "required": ["client_id", "caller_name"],
    },
}

handoff_fnol_agent_schema: dict[str, Any] = {
    "name": "handoff_fnol_agent",
    "description": (
        "Transfer to FNOL (First Notice of Loss) Agent for filing insurance claims. "
        "Use when customer needs to report an accident, damage, theft, or other loss."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier from verify_client_identity"},
            "caller_name": {"type": "string", "description": "Customer name from verify_client_identity"},
            "incident_type": {
                "type": "string",
                "description": "Type of incident (auto_accident, property_damage, theft, injury, other)",
            },
            "incident_date": {"type": "string", "description": "Date of incident if known"},
            "policy_number": {"type": "string", "description": "Policy number if known"},
            "urgency": {
                "type": "string",
                "enum": ["normal", "urgent", "emergency"],
                "description": "Urgency level of the claim",
            },
        },
        "required": ["client_id", "caller_name"],
    },
}



handoff_subro_agent_schema: dict[str, Any] = {
    "name": "handoff_subro_agent",
    "description": (
        "Transfer to Subrogation Agent for B2B Claimant Carrier inquiries. "
        "Use when caller is from another insurance company asking about subrogation "
        "demand status, liability, coverage, or limits on a claim. "
        "Requires: claim_number, cc_company (their insurance company), caller_name."
        + SILENT_HANDOFF_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number from verify_cc_caller",
            },
            "cc_company": {
                "type": "string",
                "description": "Claimant Carrier company name from verify_cc_caller",
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the CC representative from verify_cc_caller",
            },
            "claimant_name": {
                "type": "string",
                "description": "Name of the claimant (their insured) from verify_cc_caller",
            },
            "loss_date": {
                "type": "string",
                "description": "Date of loss from verify_cc_caller (YYYY-MM-DD)",
            },
            "inquiry_type": {
                "type": "string",
                "description": "Type of inquiry (demand_status, liability, coverage, limits, payment, other)",
            },
        },
        "required": ["claim_number", "cc_company", "caller_name"],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def handoff_concierge(args: dict[str, Any]) -> dict[str, Any]:
    """Return customer to Erica Concierge from specialist agent."""
    client_id = (args.get("client_id") or "").strip()
    previous_topic = (args.get("previous_topic") or "").strip()
    resolution_summary = (args.get("resolution_summary") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("🔄 Handoff to Concierge | client=%s", client_id)

    return _build_handoff_payload(
        target_agent="Concierge",
        message="",
        summary=f"Returning from {previous_topic}",
        context={
            "client_id": client_id,
            "previous_topic": previous_topic,
            "resolution_summary": resolution_summary,
            "handoff_timestamp": _utc_now(),
        },
    )


async def handoff_fraud_agent(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Fraud Detection Agent."""
    client_id = (args.get("client_id") or "").strip()
    fraud_type = (args.get("fraud_type") or "").strip()
    issue_summary = (args.get("issue_summary") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("🚨 Handoff to FraudAgent | client=%s type=%s", client_id, fraud_type)

    return _build_handoff_payload(
        target_agent="FraudAgent",
        message="Let me connect you with our fraud specialist.",
        summary=f"Fraud investigation: {fraud_type or 'suspicious activity'}",
        context={
            "client_id": client_id,
            "fraud_type": fraud_type,
            "issue_summary": issue_summary,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "Concierge",
        },
        extra={"should_interrupt_playback": True},
    )


async def handoff_to_auth(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Authentication Agent."""
    client_id = (args.get("client_id") or "").strip()
    reason = (args.get("reason") or "identity verification required").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("🔐 Handoff to AuthAgent | client=%s", client_id)

    return _build_handoff_payload(
        target_agent="AuthAgent",
        message="I need to verify your identity before we continue.",
        summary=f"Authentication required: {reason}",
        context={
            "client_id": client_id,
            "reason": reason,
            "handoff_timestamp": _utc_now(),
        },
    )


async def handoff_card_recommendation(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Card Recommendation Agent."""
    client_id = (args.get("client_id") or "").strip()
    customer_goal = (args.get("customer_goal") or "").strip()
    spending_prefs = (args.get("spending_preferences") or "").strip()
    current_cards = (args.get("current_cards") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("💳 Handoff to CardRecommendation | client=%s goal=%s", client_id, customer_goal)

    return _build_handoff_payload(
        target_agent="CardRecommendation",
        message="Let me find the best card options for you.",
        summary=f"Card recommendation: {customer_goal or 'general inquiry'}",
        context={
            "client_id": client_id,
            "customer_goal": customer_goal,
            "spending_preferences": spending_prefs,
            "current_cards": current_cards,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "Concierge",
        },
        extra={"should_interrupt_playback": True},
    )


async def handoff_investment_advisor(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Investment Advisor Agent."""
    client_id = (args.get("client_id") or "").strip()
    topic = (args.get("topic") or "retirement planning").strip()
    employment_change = (args.get("employment_change") or "").strip()
    retirement_question = (args.get("retirement_question") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("🏦 Handoff to InvestmentAdvisor | client=%s topic=%s", client_id, topic)

    return _build_handoff_payload(
        target_agent="InvestmentAdvisor",
        message="Let me look at your retirement accounts and options.",
        summary=f"Retirement inquiry: {topic}",
        context={
            "client_id": client_id,
            "topic": topic,
            "employment_change": employment_change,
            "retirement_question": retirement_question,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "Concierge",
        },
        extra={"should_interrupt_playback": True},
    )


async def handoff_compliance_desk(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Compliance Desk Agent."""
    client_id = (args.get("client_id") or "").strip()
    compliance_issue = (args.get("compliance_issue") or "").strip()
    urgency = (args.get("urgency") or "normal").strip()
    transaction_details = (args.get("transaction_details") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("📋 Handoff to ComplianceDesk | client=%s issue=%s", client_id, compliance_issue)

    return _build_handoff_payload(
        target_agent="ComplianceDesk",
        message="Let me review the compliance requirements for your transaction.",
        summary=f"Compliance review: {compliance_issue or 'verification required'}",
        context={
            "client_id": client_id,
            "compliance_issue": compliance_issue,
            "urgency": urgency,
            "transaction_details": transaction_details,
            "handoff_timestamp": _utc_now(),
        },
    )


async def handoff_transfer_agency_agent(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Transfer Agency Agent."""
    client_id = (args.get("client_id") or "").strip()
    request_type = (args.get("request_type") or "drip_liquidation").strip()
    client_code = (args.get("client_code") or "").strip()
    drip_symbols = (args.get("drip_symbols") or "").strip()

    logger.info("🏛️ Handoff to TransferAgency | type=%s code=%s", request_type, client_code)

    context = {
        "request_type": request_type,
        "client_code": client_code,
        "drip_symbols": drip_symbols,
        "handoff_timestamp": _utc_now(),
        "previous_agent": "Concierge",
    }
    if client_id:
        context["client_id"] = client_id

    return _build_handoff_payload(
        target_agent="TransferAgencyAgent",
        message="Let me connect you with our Transfer Agency specialist.",
        summary=f"Transfer agency: {request_type}",
        context=context,
        extra={"should_interrupt_playback": True},
    )


async def handoff_bank_advisor(args: dict[str, Any]) -> dict[str, Any]:
    """Schedule callback with Merrill human advisor."""
    client_id = (args.get("client_id") or "").strip()
    reason = (args.get("reason") or "").strip()
    context_summary = (args.get("context") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}
    if not reason:
        return {"success": False, "message": "reason is required."}

    logger.info("👤 Merrill Advisor callback scheduled | client=%s reason=%s", client_id, reason)

    # This is a callback scheduling, not a live transfer
    return {
        "success": True,
        "callback_scheduled": True,
        "target_agent": "MerrillAdvisor",
        "message": f"Callback scheduled for {reason}",
        "handoff_context": {
            "client_id": client_id,
            "reason": reason,
            "context": context_summary,
            "scheduled_at": _utc_now(),
        },
    }


async def handoff_to_trading(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Trading Desk."""
    client_id = (args.get("client_id") or "").strip()
    trade_details = (args.get("trade_details") or "").strip()
    complexity = (args.get("complexity_level") or "standard").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("📈 Handoff to Trading | client=%s complexity=%s", client_id, complexity)

    return _build_handoff_payload(
        target_agent="TradingDesk",
        message="Connecting you with our trading desk.",
        summary=f"Trade execution: {complexity}",
        context={
            "client_id": client_id,
            "trade_details": trade_details,
            "complexity_level": complexity,
            "handoff_timestamp": _utc_now(),
        },
    )


async def handoff_general_kb(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to General Knowledge Base agent for general inquiries."""
    topic = (args.get("topic") or "general").strip()
    question = (args.get("question") or "").strip()

    logger.info("📚 Handoff to GeneralKBAgent | topic=%s", topic)

    return _build_handoff_payload(
        target_agent="GeneralKBAgent",
        message="I'll connect you with our knowledge assistant who can help with general questions.",
        summary=f"General inquiry: {topic}",
        context={
            "topic": topic,
            "question": question,
            "handoff_timestamp": _utc_now(),
        },
    )


async def handoff_claims_specialist(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Claims Specialist for claims processing and FNOL."""
    client_id = (args.get("client_id") or "").strip()
    reason = (args.get("reason") or "claims_inquiry").strip()
    incident_summary = (args.get("incident_summary") or "").strip()

    logger.info("📋 Handoff to ClaimsSpecialist | client=%s reason=%s", client_id, reason)

    return _build_handoff_payload(
        target_agent="ClaimsSpecialist",
        message="",  # Silent handoff - claims specialist will greet
        summary=f"Claims handoff: {reason}",
        context={
            "client_id": client_id,
            "reason": reason,
            "incident_summary": incident_summary,
            "handoff_timestamp": _utc_now(),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC HANDOFF EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════


async def handoff_to_agent(args: dict[str, Any]) -> dict[str, Any]:
    """
    Generic handoff to any target agent.

    This tool enables dynamic agent transfers without requiring a dedicated
    handoff tool for each agent pair. The target agent must be valid within
    the current scenario's allowed targets.

    Args:
        args: Dictionary containing:
            - target_agent (required): Name of the agent to transfer to
            - reason (required): Why this handoff is needed
            - context: Conversation context to pass along
            - client_id: Customer identifier if available

    Returns:
        Standard handoff payload with target_agent set dynamically.
    """
    target_agent = (args.get("target_agent") or "").strip()
    reason = (args.get("reason") or "").strip()
    context_summary = (args.get("context") or "").strip()
    client_id = (args.get("client_id") or "").strip()

    if not target_agent:
        return {"success": False, "message": "target_agent is required."}
    if not reason:
        return {"success": False, "message": "reason is required."}

    logger.info(
        "🔀 Generic handoff to %s | reason=%s client=%s",
        target_agent,
        reason,
        client_id or "(no client_id)",
    )

    context: dict[str, Any] = {
        "reason": reason,
        "handoff_timestamp": _utc_now(),
    }

    if context_summary:
        context["context_summary"] = context_summary
    if client_id:
        context["client_id"] = client_id

    return _build_handoff_payload(
        target_agent=target_agent,
        message="",  # Silent - target agent will provide greeting if configured
        summary=f"Generic handoff: {reason}",
        context=context,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# INSURANCE HANDOFF EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def handoff_policy_advisor(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Policy Advisor Agent for policy questions and changes."""
    client_id = (args.get("client_id") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()
    policy_type = (args.get("policy_type") or "").strip()
    request_type = (args.get("request_type") or "").strip()
    policy_number = (args.get("policy_number") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}
    if not caller_name:
        return {"success": False, "message": "caller_name is required."}

    logger.info(
        "📋 Handoff to PolicyAdvisor | client=%s caller=%s policy_type=%s request=%s",
        client_id, caller_name, policy_type, request_type
    )

    return _build_handoff_payload(
        target_agent="PolicyAdvisor",
        message="Let me connect you with our policy advisor.",
        summary=f"Policy inquiry: {request_type or policy_type or 'general'}",
        context={
            "client_id": client_id,
            "caller_name": caller_name,
            "policy_id": policy_number or client_id,  # Alias for prompt template
            "policy_type": policy_type,
            "request_type": request_type,
            "policy_number": policy_number,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "AuthAgent",
        },
        extra={"should_interrupt_playback": True},
    )


async def handoff_fnol_agent(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to FNOL Agent for filing insurance claims."""
    client_id = (args.get("client_id") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()
    incident_type = (args.get("incident_type") or "").strip()
    incident_date = (args.get("incident_date") or "").strip()
    policy_number = (args.get("policy_number") or "").strip()
    urgency = (args.get("urgency") or "normal").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}
    if not caller_name:
        return {"success": False, "message": "caller_name is required."}

    logger.info(
        "🚨 Handoff to FNOLAgent | client=%s caller=%s incident=%s urgency=%s",
        client_id, caller_name, incident_type, urgency
    )

    return _build_handoff_payload(
        target_agent="FNOLAgent",
        message="I'll connect you with our claims specialist to help file your claim.",
        summary=f"FNOL: {incident_type or 'incident report'}",
        context={
            "client_id": client_id,
            "caller_name": caller_name,
            "policy_id": policy_number or client_id,  # Alias for prompt template
            "incident_type": incident_type,
            "incident_date": incident_date,
            "policy_number": policy_number,
            "urgency": urgency,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "AuthAgent",
        },
        extra={"should_interrupt_playback": urgency == "emergency"},
    )

async def handoff_subro_agent(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer to Subrogation Agent for B2B Claimant Carrier inquiries."""
    claim_number = (args.get("claim_number") or "").strip()
    cc_company = (args.get("cc_company") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()
    claimant_name = (args.get("claimant_name") or "").strip()
    loss_date = (args.get("loss_date") or "").strip()
    inquiry_type = (args.get("inquiry_type") or "").strip()

    if not claim_number:
        return {"success": False, "message": "claim_number is required."}
    if not cc_company:
        return {"success": False, "message": "cc_company is required."}
    if not caller_name:
        return {"success": False, "message": "caller_name is required."}

    logger.info(
        "📋 Handoff to SubroAgent | claim=%s cc=%s caller=%s inquiry=%s",
        claim_number, cc_company, caller_name, inquiry_type
    )

    # NOTE: No message for discrete handoffs - the transfer should be seamless
    # The orchestration.yaml sets type: discrete for AuthAgent -> SubroAgent
    return _build_handoff_payload(
        target_agent="SubroAgent",
        message="",  # Empty - discrete handoff, no announcement
        summary=f"Subro inquiry: {inquiry_type or 'demand status'}",
        context={
            "claim_number": claim_number,
            "cc_company": cc_company,
            "caller_name": caller_name,
            "claimant_name": claimant_name,
            "loss_date": loss_date,
            "inquiry_type": inquiry_type,
            "handoff_timestamp": _utc_now(),
            "previous_agent": "AuthAgent",
            "is_b2b": True,
        },
        extra={"should_interrupt_playback": True},
    )



# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

# Register all handoff tools
register_tool(
    "handoff_concierge",
    handoff_concierge_schema,
    handoff_concierge,
    is_handoff=True,
    tags={"handoff"},
)
register_tool(
    "handoff_fraud_agent",
    handoff_fraud_agent_schema,
    handoff_fraud_agent,
    is_handoff=True,
    tags={"handoff", "fraud"},
)
register_tool(
    "handoff_to_auth",
    handoff_to_auth_schema,
    handoff_to_auth,
    is_handoff=True,
    tags={"handoff", "auth"},
)
register_tool(
    "handoff_card_recommendation",
    handoff_card_recommendation_schema,
    handoff_card_recommendation,
    is_handoff=True,
    tags={"handoff", "banking"},
)
register_tool(
    "handoff_investment_advisor",
    handoff_investment_advisor_schema,
    handoff_investment_advisor,
    is_handoff=True,
    tags={"handoff", "investment"},
)
register_tool(
    "handoff_compliance_desk",
    handoff_compliance_desk_schema,
    handoff_compliance_desk,
    is_handoff=True,
    tags={"handoff", "compliance"},
)
register_tool(
    "handoff_transfer_agency_agent",
    handoff_transfer_agency_agent_schema,
    handoff_transfer_agency_agent,
    is_handoff=True,
    tags={"handoff", "transfer_agency"},
)
register_tool(
    "handoff_bank_advisor",
    handoff_bank_advisor_schema,
    handoff_bank_advisor,
    is_handoff=True,
    tags={"handoff", "investment"},
)
register_tool(
    "handoff_to_trading",
    handoff_to_trading_schema,
    handoff_to_trading,
    is_handoff=True,
    tags={"handoff", "trading"},
)
register_tool(
    "handoff_general_kb",
    handoff_general_kb_schema,
    handoff_general_kb,
    is_handoff=True,
    tags={"handoff", "knowledge_base"},
)

# Insurance handoff tools
register_tool(
    "handoff_policy_advisor",
    handoff_policy_advisor_schema,
    handoff_policy_advisor,
    is_handoff=True,
    tags={"handoff", "insurance", "policy"},
)
register_tool(
    "handoff_subro_agent",
    handoff_subro_agent_schema,
    handoff_subro_agent,
    is_handoff=True,
    tags={"handoff", "insurance", "subro", "b2b"},
)

register_tool(
    "handoff_fnol_agent",
    handoff_fnol_agent_schema,
    handoff_fnol_agent,
    is_handoff=True,
    tags={"handoff", "insurance", "claims"},
)

# Generic handoff tool - enables dynamic routing without explicit handoff tools
register_tool(
    "handoff_to_agent",
    handoff_to_agent_schema,
    handoff_to_agent,
    is_handoff=True,
    tags={"handoff", "generic"},
)
