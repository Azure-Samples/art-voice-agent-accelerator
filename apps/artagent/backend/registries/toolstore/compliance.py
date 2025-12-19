"""
Compliance Tools
================

Tools for compliance checks, client data, and knowledge base searches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.compliance")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

get_client_data_schema: dict[str, Any] = {
    "name": "get_client_data",
    "description": (
        "Retrieve comprehensive client data for compliance review including "
        "account status, KYC information, and regulatory flags."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "include_history": {
                "type": "boolean",
                "description": "Include historical compliance events",
            },
        },
        "required": ["client_id"],
    },
}

check_compliance_status_schema: dict[str, Any] = {
    "name": "check_compliance_status",
    "description": (
        "Check compliance status for a client or transaction. "
        "Returns any holds, restrictions, or required actions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "check_type": {
                "type": "string",
                "enum": ["kyc", "aml", "sanctions", "pep", "general"],
                "description": "Type of compliance check",
            },
        },
        "required": ["client_id"],
    },
}

search_knowledge_base_schema: dict[str, Any] = {
    "name": "search_knowledge_base",
    "description": (
        "Search the compliance knowledge base for policies, procedures, and regulatory guidance."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "category": {
                "type": "string",
                "enum": ["regulations", "policies", "procedures", "guidance", "all"],
                "description": "Category to search",
            },
        },
        "required": ["query"],
    },
}

log_compliance_event_schema: dict[str, Any] = {
    "name": "log_compliance_event",
    "description": (
        "Log a compliance-relevant event for audit trail. "
        "Required for certain regulatory reporting."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "event_type": {
                "type": "string",
                "enum": [
                    "kyc_update",
                    "document_received",
                    "exception_granted",
                    "escalation",
                    "review_completed",
                ],
                "description": "Type of compliance event",
            },
            "description": {"type": "string", "description": "Event description"},
            "officer_notes": {"type": "string", "description": "Compliance officer notes"},
        },
        "required": ["client_id", "event_type", "description"],
    },
}

request_document_schema: dict[str, Any] = {
    "name": "request_document",
    "description": (
        "Request a document from the client for compliance purposes. "
        "Triggers secure upload link via email."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "document_type": {
                "type": "string",
                "enum": [
                    "id_verification",
                    "proof_of_address",
                    "source_of_funds",
                    "tax_form",
                    "other",
                ],
                "description": "Type of document needed",
            },
            "reason": {"type": "string", "description": "Why document is needed"},
            "deadline_days": {"type": "integer", "description": "Days to provide document"},
        },
        "required": ["client_id", "document_type", "reason"],
    },
}

apply_account_restriction_schema: dict[str, Any] = {
    "name": "apply_account_restriction",
    "description": (
        "Apply a restriction to a client account. Requires compliance officer authorization."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "restriction_type": {
                "type": "string",
                "enum": [
                    "withdrawal_limit",
                    "trading_suspension",
                    "account_freeze",
                    "deposit_only",
                ],
                "description": "Type of restriction",
            },
            "reason": {"type": "string", "description": "Reason for restriction"},
            "duration_days": {
                "type": "integer",
                "description": "Duration of restriction (0 for indefinite)",
            },
        },
        "required": ["client_id", "restriction_type", "reason"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════════════════════════

_COMPLIANCE_STATUSES = {
    "CLT-001-JS": {
        "kyc_status": "current",
        "aml_status": "clear",
        "sanctions_status": "clear",
        "pep_status": "not_applicable",
        "last_review": "2024-06-15",
        "next_review": "2025-06-15",
        "restrictions": [],
    },
    "CLT-002-JD": {
        "kyc_status": "review_required",
        "aml_status": "clear",
        "sanctions_status": "clear",
        "pep_status": "not_applicable",
        "last_review": "2023-12-01",
        "next_review": "2024-12-01",
        "restrictions": [],
        "pending_documents": ["proof_of_address"],
    },
}

_KNOWLEDGE_BASE = {
    "regulations": [
        {
            "title": "Bank Secrecy Act (BSA)",
            "summary": "Requires financial institutions to assist government agencies in detecting and preventing money laundering.",
            "key_requirements": [
                "CTR filing for cash >$10k",
                "SAR filing for suspicious activity",
                "CDD/KYC requirements",
            ],
        },
        {
            "title": "OFAC Sanctions",
            "summary": "Prohibits transactions with sanctioned individuals, entities, and countries.",
            "key_requirements": [
                "Screen all transactions",
                "Block prohibited transactions",
                "Report matches",
            ],
        },
    ],
    "policies": [
        {
            "title": "Customer Identification Program (CIP)",
            "summary": "Requirements for verifying customer identity at account opening.",
            "key_requirements": ["Government ID", "SSN verification", "Address verification"],
        },
        {
            "title": "Enhanced Due Diligence (EDD)",
            "summary": "Additional review requirements for high-risk customers.",
            "triggers": ["PEP status", "High-risk country", "Unusual activity patterns"],
        },
    ],
}

_COMPLIANCE_EVENTS: dict[str, list] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def get_client_data(args: dict[str, Any]) -> dict[str, Any]:
    """Get client compliance data."""
    client_id = (args.get("client_id") or "").strip()
    include_history = args.get("include_history", False)

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    status = _COMPLIANCE_STATUSES.get(client_id)
    if not status:
        return {"success": False, "message": f"No compliance record for {client_id}"}

    result = {
        "success": True,
        "client_id": client_id,
        "compliance_data": status,
        "risk_rating": "low" if status["kyc_status"] == "current" else "medium",
    }

    if include_history:
        result["compliance_history"] = _COMPLIANCE_EVENTS.get(client_id, [])

    logger.info("📋 Compliance data retrieved: %s", client_id)

    return result


async def check_compliance_status(args: dict[str, Any]) -> dict[str, Any]:
    """Check compliance status."""
    client_id = (args.get("client_id") or "").strip()
    check_type = (args.get("check_type") or "general").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    status = _COMPLIANCE_STATUSES.get(client_id, {})

    if check_type == "kyc":
        result_status = status.get("kyc_status", "unknown")
        is_clear = result_status == "current"
    elif check_type == "aml":
        result_status = status.get("aml_status", "unknown")
        is_clear = result_status == "clear"
    elif check_type == "sanctions":
        result_status = status.get("sanctions_status", "unknown")
        is_clear = result_status == "clear"
    elif check_type == "pep":
        result_status = status.get("pep_status", "unknown")
        is_clear = result_status in ["clear", "not_applicable"]
    else:
        # General check
        is_clear = all(
            [
                status.get("kyc_status") == "current",
                status.get("aml_status") == "clear",
                status.get("sanctions_status") == "clear",
            ]
        )
        result_status = "clear" if is_clear else "review_required"

    return {
        "success": True,
        "client_id": client_id,
        "check_type": check_type,
        "status": result_status,
        "is_clear": is_clear,
        "restrictions": status.get("restrictions", []),
        "pending_documents": status.get("pending_documents", []),
        "last_review": status.get("last_review"),
        "next_review": status.get("next_review"),
    }


async def search_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
    """Search compliance knowledge base."""
    query = (args.get("query") or "").strip().lower()
    category = (args.get("category") or "all").strip()

    if not query:
        return {"success": False, "message": "query is required."}

    results = []
    categories_to_search = [category] if category != "all" else list(_KNOWLEDGE_BASE.keys())

    for cat in categories_to_search:
        items = _KNOWLEDGE_BASE.get(cat, [])
        for item in items:
            if any(
                word in item["title"].lower() or word in item["summary"].lower()
                for word in query.split()
            ):
                results.append({**item, "category": cat})

    return {
        "success": True,
        "query": query,
        "results": results,
        "result_count": len(results),
    }


async def log_compliance_event(args: dict[str, Any]) -> dict[str, Any]:
    """Log compliance event."""
    client_id = (args.get("client_id") or "").strip()
    event_type = (args.get("event_type") or "").strip()
    description = (args.get("description") or "").strip()
    officer_notes = (args.get("officer_notes") or "").strip()

    if not client_id or not event_type or not description:
        return {"success": False, "message": "client_id, event_type, and description required."}

    event = {
        "event_id": f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "event_type": event_type,
        "description": description,
        "officer_notes": officer_notes,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if client_id not in _COMPLIANCE_EVENTS:
        _COMPLIANCE_EVENTS[client_id] = []
    _COMPLIANCE_EVENTS[client_id].append(event)

    logger.info("📝 Compliance event logged: %s - %s", client_id, event_type)

    return {
        "success": True,
        "event_logged": True,
        "event_id": event["event_id"],
        "timestamp": event["timestamp"],
    }


async def request_document(args: dict[str, Any]) -> dict[str, Any]:
    """Request document from client."""
    client_id = (args.get("client_id") or "").strip()
    document_type = (args.get("document_type") or "").strip()
    reason = (args.get("reason") or "").strip()
    deadline_days = args.get("deadline_days", 14)

    if not client_id or not document_type or not reason:
        return {"success": False, "message": "client_id, document_type, and reason required."}

    deadline = (datetime.now(UTC) + timedelta(days=deadline_days)).isoformat()

    logger.info("📄 Document requested: %s - %s", client_id, document_type)

    return {
        "success": True,
        "request_sent": True,
        "document_type": document_type,
        "deadline": deadline,
        "secure_upload_link": f"https://secure.bank.com/upload/{client_id}/{document_type}",
        "reminder_schedule": "Day 7, Day 10, Day 13",
        "message": f"Secure upload link sent to customer's email. Due in {deadline_days} days.",
    }


async def apply_account_restriction(args: dict[str, Any]) -> dict[str, Any]:
    """Apply account restriction."""
    client_id = (args.get("client_id") or "").strip()
    restriction_type = (args.get("restriction_type") or "").strip()
    reason = (args.get("reason") or "").strip()
    duration_days = args.get("duration_days", 0)

    if not client_id or not restriction_type or not reason:
        return {"success": False, "message": "client_id, restriction_type, and reason required."}

    restriction = {
        "type": restriction_type,
        "reason": reason,
        "applied_at": datetime.now(UTC).isoformat(),
        "expires_at": (
            (datetime.now(UTC) + timedelta(days=duration_days)).isoformat()
            if duration_days > 0
            else None
        ),
    }

    # Add to compliance status
    if client_id in _COMPLIANCE_STATUSES:
        _COMPLIANCE_STATUSES[client_id]["restrictions"].append(restriction)

    logger.warning("🚫 Account restriction applied: %s - %s", client_id, restriction_type)

    return {
        "success": True,
        "restriction_applied": True,
        "restriction_type": restriction_type,
        "duration": f"{duration_days} days" if duration_days > 0 else "indefinite",
        "requires_officer_approval": True,
        "customer_notification": "Customer will be notified via secure message",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "get_client_data", get_client_data_schema, get_client_data, tags={"compliance", "data"}
)
register_tool(
    "check_compliance_status",
    check_compliance_status_schema,
    check_compliance_status,
    tags={"compliance", "kyc", "aml"},
)
register_tool(
    "search_knowledge_base",
    search_knowledge_base_schema,
    search_knowledge_base,
    tags={"compliance", "knowledge"},
)
register_tool(
    "log_compliance_event",
    log_compliance_event_schema,
    log_compliance_event,
    tags={"compliance", "audit"},
)
register_tool(
    "request_document", request_document_schema, request_document, tags={"compliance", "documents"}
)
register_tool(
    "apply_account_restriction",
    apply_account_restriction_schema,
    apply_account_restriction,
    tags={"compliance", "restrictions"},
)
