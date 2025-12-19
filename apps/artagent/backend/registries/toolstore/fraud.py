"""
Fraud Detection Tools
=====================

Tools for fraud analysis, suspicious activity, and emergency card actions.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.fraud")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

analyze_recent_transactions_schema: dict[str, Any] = {
    "name": "analyze_recent_transactions",
    "description": (
        "Analyze customer's recent transactions for fraud patterns, unusual activity, or anomalies. "
        "Returns risk assessment and flagged transactions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "days_back": {
                "type": "integer",
                "description": "Number of days to analyze (default 30)",
            },
        },
        "required": ["client_id"],
    },
}

check_suspicious_activity_schema: dict[str, Any] = {
    "name": "check_suspicious_activity",
    "description": (
        "Check if there's been any suspicious activity or fraud alerts on the account. "
        "Returns existing fraud alerts and security status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

create_fraud_case_schema: dict[str, Any] = {
    "name": "create_fraud_case",
    "description": (
        "Create a new fraud investigation case for disputed transactions. "
        "Captures transaction details and customer statement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "transaction_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of disputed transaction IDs",
            },
            "dispute_reason": {"type": "string", "description": "Why customer is disputing these"},
            "customer_statement": {
                "type": "string",
                "description": "Customer's statement about the fraud",
            },
        },
        "required": ["client_id", "dispute_reason"],
    },
}

block_card_emergency_schema: dict[str, Any] = {
    "name": "block_card_emergency",
    "description": (
        "Emergency block on customer's card. Use when fraud is confirmed or strongly suspected. "
        "Immediately prevents all transactions. Irreversible without issuing new card."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "card_last4": {"type": "string", "description": "Last 4 digits of card to block"},
            "reason": {"type": "string", "description": "Reason for blocking"},
        },
        "required": ["client_id", "reason"],
    },
}

ship_replacement_card_schema: dict[str, Any] = {
    "name": "ship_replacement_card",
    "description": (
        "Order a replacement card after blocking. Can expedite shipping for emergency situations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "expedited": {"type": "boolean", "description": "Rush delivery (1-2 days vs 5-7)"},
            "ship_to_address": {"type": "string", "description": "Optional alternate address"},
        },
        "required": ["client_id"],
    },
}

report_lost_stolen_card_schema: dict[str, Any] = {
    "name": "report_lost_stolen_card",
    "description": (
        "Report a card as lost or stolen. Immediately blocks the card and initiates replacement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "card_last4": {"type": "string", "description": "Last 4 digits of lost/stolen card"},
            "lost_or_stolen": {
                "type": "string",
                "enum": ["lost", "stolen"],
                "description": "Whether card is lost or confirmed stolen",
            },
            "last_legitimate_use": {
                "type": "string",
                "description": "When/where card was last legitimately used",
            },
        },
        "required": ["client_id", "lost_or_stolen"],
    },
}

create_transaction_dispute_schema: dict[str, Any] = {
    "name": "create_transaction_dispute",
    "description": (
        "Create a formal dispute for unauthorized or incorrect transactions. "
        "Initiates investigation and potential provisional credit."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "transaction_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of transaction IDs to dispute",
            },
            "dispute_type": {
                "type": "string",
                "enum": [
                    "unauthorized",
                    "duplicate",
                    "incorrect_amount",
                    "merchandise_not_received",
                    "other",
                ],
                "description": "Type of dispute",
            },
            "description": {"type": "string", "description": "Customer's description of the issue"},
        },
        "required": ["client_id", "dispute_type", "description"],
    },
}

send_fraud_case_email_schema: dict[str, Any] = {
    "name": "send_fraud_case_email",
    "description": (
        "Send confirmation email with fraud case details to customer. "
        "Includes case number, next steps, and timeline."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "case_id": {"type": "string", "description": "Fraud case ID"},
            "include_steps": {"type": "boolean", "description": "Include next steps in email"},
        },
        "required": ["client_id", "case_id"],
    },
}

provide_fraud_education_schema: dict[str, Any] = {
    "name": "provide_fraud_education",
    "description": (
        "Provide customer with fraud prevention education and tips. "
        "Returns relevant prevention advice based on their situation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fraud_type": {
                "type": "string",
                "enum": ["card_fraud", "phishing", "account_takeover", "identity_theft", "general"],
                "description": "Type of fraud to educate about",
            },
        },
        "required": ["fraud_type"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_SUSPICIOUS_TRANSACTIONS = [
    {
        "id": "TXN-SUSP-001",
        "merchant": "CRYPTO EXCHANGE XYZ",
        "amount": 2500.00,
        "date": "2024-12-01",
        "location": "Unknown - IP: 185.234.x.x",
        "risk_score": 0.92,
        "flags": ["unusual_amount", "high_risk_merchant", "foreign_ip"],
    },
    {
        "id": "TXN-SUSP-002",
        "merchant": "ELECTRONICS STORE",
        "amount": 1899.99,
        "date": "2024-11-30",
        "location": "Miami, FL",
        "risk_score": 0.78,
        "flags": ["velocity_anomaly", "geographic_jump"],
    },
    {
        "id": "TXN-SUSP-003",
        "merchant": "WIRE TRANSFER INTL",
        "amount": 5000.00,
        "date": "2024-11-29",
        "location": "N/A",
        "risk_score": 0.85,
        "flags": ["wire_transfer", "unusual_amount", "first_time_recipient"],
    },
]

_FRAUD_CASES: dict[str, dict] = {}
_BLOCKED_CARDS: dict[str, dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def analyze_recent_transactions(args: dict[str, Any]) -> dict[str, Any]:
    """Analyze transactions for fraud patterns."""
    client_id = (args.get("client_id") or "").strip()
    days_back = args.get("days_back", 30)

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # Simulate analysis
    flagged = random.sample(
        _MOCK_SUSPICIOUS_TRANSACTIONS, k=min(2, len(_MOCK_SUSPICIOUS_TRANSACTIONS))
    )

    overall_risk = max([t["risk_score"] for t in flagged]) if flagged else 0.15

    logger.info("🔍 Fraud analysis: %s - risk_score: %.2f", client_id, overall_risk)

    return {
        "success": True,
        "analysis": {
            "period_days": days_back,
            "total_transactions": random.randint(45, 120),
            "flagged_count": len(flagged),
            "overall_risk_score": overall_risk,
            "risk_level": (
                "high" if overall_risk > 0.7 else "medium" if overall_risk > 0.4 else "low"
            ),
            "flagged_transactions": flagged,
        },
    }


async def check_suspicious_activity(args: dict[str, Any]) -> dict[str, Any]:
    """Check for existing fraud alerts."""
    client_id = (args.get("client_id") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # Check if card is blocked
    blocked = _BLOCKED_CARDS.get(client_id)
    open_case = _FRAUD_CASES.get(client_id)

    alerts = []
    if blocked:
        alerts.append(
            {
                "type": "card_blocked",
                "date": blocked["blocked_at"],
                "reason": blocked["reason"],
            }
        )
    if open_case:
        alerts.append(
            {
                "type": "fraud_case_open",
                "case_id": open_case["case_id"],
                "status": open_case["status"],
            }
        )

    # Simulate recent alerts
    if random.random() > 0.6:
        alerts.append(
            {
                "type": "velocity_alert",
                "triggered_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                "message": "Multiple transactions in short period",
            }
        )

    return {
        "success": True,
        "has_alerts": len(alerts) > 0,
        "alerts": alerts,
        "security_status": "blocked" if blocked else "normal",
    }


async def create_fraud_case(args: dict[str, Any]) -> dict[str, Any]:
    """Create fraud investigation case."""
    client_id = (args.get("client_id") or "").strip()
    transaction_ids = args.get("transaction_ids", [])
    dispute_reason = (args.get("dispute_reason") or "").strip()
    customer_statement = (args.get("customer_statement") or "").strip()

    if not client_id or not dispute_reason:
        return {"success": False, "message": "client_id and dispute_reason required."}

    case_id = f"FRD-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    case = {
        "case_id": case_id,
        "client_id": client_id,
        "transaction_ids": transaction_ids,
        "dispute_reason": dispute_reason,
        "customer_statement": customer_statement,
        "status": "open",
        "created_at": datetime.now(UTC).isoformat(),
        "provisional_credit_eligible": True,
    }

    _FRAUD_CASES[client_id] = case

    logger.info("📝 Fraud case created: %s for %s", case_id, client_id)

    return {
        "success": True,
        "case_id": case_id,
        "status": "open",
        "next_steps": [
            "Investigation will complete within 10 business days",
            "Provisional credit may be issued within 5 business days",
            "You'll receive email updates on case progress",
        ],
        "reference_number": case_id,
    }


async def block_card_emergency(args: dict[str, Any]) -> dict[str, Any]:
    """Emergency block on card."""
    client_id = (args.get("client_id") or "").strip()
    card_last4 = (args.get("card_last4") or "****").strip()
    reason = (args.get("reason") or "fraud_suspected").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    _BLOCKED_CARDS[client_id] = {
        "card_last4": card_last4,
        "reason": reason,
        "blocked_at": datetime.now(UTC).isoformat(),
    }

    logger.warning("🚨 Card blocked: %s - ****%s - reason: %s", client_id, card_last4, reason)

    return {
        "success": True,
        "blocked": True,
        "card_last4": card_last4,
        "blocked_at": datetime.now(UTC).isoformat(),
        "message": "Card has been immediately blocked. No further transactions will be authorized.",
        "next_step": "Order replacement card or visit branch with ID",
    }


async def ship_replacement_card(args: dict[str, Any]) -> dict[str, Any]:
    """Order replacement card."""
    client_id = (args.get("client_id") or "").strip()
    expedited = args.get("expedited", False)
    ship_to = (args.get("ship_to_address") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    delivery = "1-2 business days" if expedited else "5-7 business days"
    fee = 25.00 if expedited else 0.00

    logger.info("📦 Replacement card ordered: %s - expedited: %s", client_id, expedited)

    return {
        "success": True,
        "replacement_ordered": True,
        "expedited": expedited,
        "delivery_estimate": delivery,
        "fee": fee,
        "fee_waived": True,  # Often waived for fraud
        "tracking_available_in": "24 hours",
        "digital_wallet_note": "Add new card to digital wallet once received",
    }


async def report_lost_stolen_card(args: dict[str, Any]) -> dict[str, Any]:
    """Report lost or stolen card."""
    client_id = (args.get("client_id") or "").strip()
    card_last4 = (args.get("card_last4") or "****").strip()
    lost_or_stolen = (args.get("lost_or_stolen") or "lost").strip()
    last_use = (args.get("last_legitimate_use") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # Block the card immediately
    _BLOCKED_CARDS[client_id] = {
        "card_last4": card_last4,
        "reason": f"reported_{lost_or_stolen}",
        "blocked_at": datetime.now(UTC).isoformat(),
    }

    logger.warning("🔒 Card reported %s: %s - ****%s", lost_or_stolen, client_id, card_last4)

    return {
        "success": True,
        "reported": True,
        "status": lost_or_stolen,
        "card_blocked": True,
        "replacement_ordered": True,
        "delivery_estimate": "5-7 business days",
        "fraud_monitoring_enhanced": True,
        "message": f"Card ending in {card_last4} has been blocked. Replacement is on the way.",
    }


async def create_transaction_dispute(args: dict[str, Any]) -> dict[str, Any]:
    """Create formal transaction dispute."""
    client_id = (args.get("client_id") or "").strip()
    transaction_ids = args.get("transaction_ids", [])
    dispute_type = (args.get("dispute_type") or "other").strip()
    description = (args.get("description") or "").strip()

    if not client_id or not description:
        return {"success": False, "message": "client_id and description required."}

    dispute_id = f"DSP-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    logger.info("📝 Transaction dispute created: %s - %s", dispute_id, dispute_type)

    return {
        "success": True,
        "dispute_id": dispute_id,
        "dispute_type": dispute_type,
        "transactions": transaction_ids,
        "status": "under_review",
        "provisional_credit_eligible": dispute_type in ["unauthorized", "duplicate"],
        "estimated_resolution": "10 business days",
        "next_steps": [
            "Investigation will begin within 1 business day",
            "Provisional credit may be issued within 5 days for eligible disputes",
            "You'll receive updates via email",
        ],
    }


async def send_fraud_case_email(args: dict[str, Any]) -> dict[str, Any]:
    """Send fraud case confirmation email."""
    client_id = (args.get("client_id") or "").strip()
    case_id = (args.get("case_id") or "").strip()
    include_steps = args.get("include_steps", True)

    if not client_id or not case_id:
        return {"success": False, "message": "client_id and case_id required."}

    logger.info("📧 Fraud case email sent: %s - case: %s", client_id, case_id)

    return {
        "success": True,
        "email_sent": True,
        "recipient": f"{client_id}@email.com",
        "case_id": case_id,
        "content_included": {
            "case_details": True,
            "timeline": True,
            "next_steps": include_steps,
            "contact_info": True,
        },
    }


_FRAUD_EDUCATION = {
    "card_fraud": [
        "Never share your card details over phone or email unless you initiated contact",
        "Review statements regularly for unfamiliar transactions",
        "Enable transaction alerts on your mobile app",
        "Use virtual card numbers for online shopping",
    ],
    "phishing": [
        "We will never ask for your password via email or text",
        "Verify sender email addresses carefully",
        "Don't click links in suspicious messages - go directly to our app",
        "Report suspicious messages to security@bank.com",
    ],
    "account_takeover": [
        "Use strong, unique passwords for your accounts",
        "Enable multi-factor authentication",
        "Monitor login alerts and review device history",
        "Never share one-time codes with anyone",
    ],
    "identity_theft": [
        "Shred documents with personal information",
        "Monitor your credit reports regularly",
        "Consider a credit freeze if you suspect identity theft",
        "Use our free identity monitoring service",
    ],
    "general": [
        "Trust your instincts - if something feels wrong, hang up and call us",
        "Keep your contact information up to date",
        "Review account activity weekly",
        "Report suspicious activity immediately",
    ],
}


async def provide_fraud_education(args: dict[str, Any]) -> dict[str, Any]:
    """Provide fraud prevention education."""
    fraud_type = (args.get("fraud_type") or "general").strip()

    tips = _FRAUD_EDUCATION.get(fraud_type, _FRAUD_EDUCATION["general"])

    return {
        "success": True,
        "fraud_type": fraud_type,
        "prevention_tips": tips,
        "additional_resources": {
            "security_center": "https://bank.com/security",
            "fraud_reporting": "1-800-FRAUD",
            "identity_monitoring": "https://bank.com/id-protect",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "analyze_recent_transactions",
    analyze_recent_transactions_schema,
    analyze_recent_transactions,
    tags={"fraud", "analysis"},
)
register_tool(
    "check_suspicious_activity",
    check_suspicious_activity_schema,
    check_suspicious_activity,
    tags={"fraud", "alerts"},
)
register_tool(
    "create_fraud_case", create_fraud_case_schema, create_fraud_case, tags={"fraud", "dispute"}
)
register_tool(
    "block_card_emergency",
    block_card_emergency_schema,
    block_card_emergency,
    tags={"fraud", "emergency", "cards"},
)
register_tool(
    "ship_replacement_card",
    ship_replacement_card_schema,
    ship_replacement_card,
    tags={"fraud", "cards"},
)
register_tool(
    "report_lost_stolen_card",
    report_lost_stolen_card_schema,
    report_lost_stolen_card,
    tags={"fraud", "cards", "emergency"},
)
register_tool(
    "create_transaction_dispute",
    create_transaction_dispute_schema,
    create_transaction_dispute,
    tags={"fraud", "dispute"},
)
register_tool(
    "send_fraud_case_email",
    send_fraud_case_email_schema,
    send_fraud_case_email,
    tags={"fraud", "communication"},
)
register_tool(
    "provide_fraud_education",
    provide_fraud_education_schema,
    provide_fraud_education,
    tags={"fraud", "education"},
)
