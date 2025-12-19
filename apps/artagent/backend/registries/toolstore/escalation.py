"""
Escalation Tools
================

Tools for escalating calls to humans, emergencies, or call centers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.escalation")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

escalate_human_schema: dict[str, Any] = {
    "name": "escalate_human",
    "description": (
        "Transfer call to a human agent. Use when customer explicitly requests to speak with a person, "
        "or when the situation requires human judgment. Captures reason and context for warm transfer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why escalation is needed",
            },
            "department": {
                "type": "string",
                "enum": ["general", "fraud", "loans", "investments", "complaints", "retention"],
                "description": "Target department for transfer",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary of conversation so far for the human agent",
            },
            "priority": {
                "type": "string",
                "enum": ["normal", "high", "urgent"],
                "description": "Priority level for queue placement",
            },
        },
        "required": ["reason"],
    },
}

escalate_emergency_schema: dict[str, Any] = {
    "name": "escalate_emergency",
    "description": (
        "Emergency escalation for critical situations. Use for confirmed fraud in progress, "
        "security threats, or safety concerns. Immediate priority queue placement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "emergency_type": {
                "type": "string",
                "enum": [
                    "fraud_in_progress",
                    "security_threat",
                    "safety_concern",
                    "elder_abuse",
                    "other",
                ],
                "description": "Type of emergency",
            },
            "description": {
                "type": "string",
                "description": "Description of the emergency",
            },
            "client_id": {
                "type": "string",
                "description": "Customer identifier if known",
            },
        },
        "required": ["emergency_type", "description"],
    },
}

transfer_call_to_call_center_schema: dict[str, Any] = {
    "name": "transfer_call_to_call_center",
    "description": (
        "Cold transfer to call center queue. Use when warm transfer not needed "
        "or customer prefers to wait in queue."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "queue_id": {
                "type": "string",
                "description": "Target queue identifier",
            },
            "reason": {
                "type": "string",
                "description": "Reason for transfer",
            },
        },
        "required": ["reason"],
    },
}

schedule_callback_schema: dict[str, Any] = {
    "name": "schedule_callback",
    "description": (
        "Schedule a callback from a human agent at a specific time. "
        "Alternative to waiting in queue."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "phone_number": {"type": "string", "description": "Phone number to call back"},
            "preferred_time": {"type": "string", "description": "Preferred callback time"},
            "reason": {"type": "string", "description": "Reason for callback"},
            "department": {
                "type": "string",
                "enum": ["general", "fraud", "loans", "investments"],
                "description": "Department to schedule with",
            },
        },
        "required": ["client_id", "reason"],
    },
}

submit_complaint_schema: dict[str, Any] = {
    "name": "submit_complaint",
    "description": (
        "Submit a formal complaint on behalf of the customer. "
        "Creates tracking case and triggers review process."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "complaint_type": {
                "type": "string",
                "enum": ["service", "fees", "product", "employee", "policy", "other"],
                "description": "Category of complaint",
            },
            "description": {"type": "string", "description": "Detailed complaint description"},
            "desired_resolution": {
                "type": "string",
                "description": "What customer wants as resolution",
            },
        },
        "required": ["client_id", "complaint_type", "description"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════════════════════════

_QUEUE_WAIT_TIMES = {
    "general": "5-10 minutes",
    "fraud": "2-3 minutes",
    "loans": "8-12 minutes",
    "investments": "3-5 minutes",
    "complaints": "5-7 minutes",
    "retention": "1-2 minutes",
}

_CALLBACKS: dict[str, dict] = {}
_COMPLAINTS: dict[str, dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def escalate_human(args: dict[str, Any]) -> dict[str, Any]:
    """Escalate to human agent."""
    reason = (args.get("reason") or "").strip()
    department = (args.get("department") or "general").strip()
    context = (args.get("context_summary") or "").strip()
    priority = (args.get("priority") or "normal").strip()

    if not reason:
        return {"success": False, "message": "Reason is required for escalation."}

    wait_time = _QUEUE_WAIT_TIMES.get(department, "5-10 minutes")
    if priority == "urgent":
        wait_time = "1-2 minutes"
    elif priority == "high":
        wait_time = "2-4 minutes"

    logger.info("👤 Escalating to human: dept=%s priority=%s", department, priority)

    return {
        "success": True,
        "escalation_initiated": True,
        "department": department,
        "priority": priority,
        "estimated_wait": wait_time,
        "reference_id": f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "context_transferred": bool(context),
        "message": f"Transferring you to our {department} team. Estimated wait: {wait_time}.",
    }


async def escalate_emergency(args: dict[str, Any]) -> dict[str, Any]:
    """Emergency escalation."""
    emergency_type = (args.get("emergency_type") or "other").strip()
    description = (args.get("description") or "").strip()
    client_id = (args.get("client_id") or "").strip()

    if not description:
        return {"success": False, "message": "Description is required for emergency escalation."}

    logger.critical("🚨 EMERGENCY ESCALATION: type=%s client=%s", emergency_type, client_id)

    return {
        "success": True,
        "emergency_escalation": True,
        "type": emergency_type,
        "priority": "critical",
        "immediate_response": True,
        "reference_id": f"EMRG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "actions_taken": [
            "Priority alert sent to emergency response team",
            "Account flagged for immediate review",
            "Supervisor notified",
        ],
        "message": "Connecting you immediately to our emergency response team.",
    }


async def transfer_call_to_call_center(args: dict[str, Any]) -> dict[str, Any]:
    """Cold transfer to call center."""
    queue_id = (args.get("queue_id") or "general").strip()
    reason = (args.get("reason") or "").strip()

    if not reason:
        return {"success": False, "message": "Reason is required for transfer."}

    logger.info("📞 Cold transfer: queue=%s", queue_id)

    return {
        "success": True,
        "transfer_initiated": True,
        "queue_id": queue_id,
        "estimated_wait": _QUEUE_WAIT_TIMES.get(queue_id, "5-10 minutes"),
        "message": "Transferring you to our call center. Please hold.",
    }


async def schedule_callback(args: dict[str, Any]) -> dict[str, Any]:
    """Schedule callback from human agent."""
    client_id = (args.get("client_id") or "").strip()
    phone = (args.get("phone_number") or "").strip()
    preferred_time = (args.get("preferred_time") or "").strip()
    reason = (args.get("reason") or "").strip()
    department = (args.get("department") or "general").strip()

    if not client_id or not reason:
        return {"success": False, "message": "client_id and reason required."}

    callback_id = f"CB-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    callback = {
        "callback_id": callback_id,
        "client_id": client_id,
        "phone": phone or "on file",
        "preferred_time": preferred_time or "next available",
        "reason": reason,
        "department": department,
        "scheduled_at": datetime.now(UTC).isoformat(),
    }

    _CALLBACKS[callback_id] = callback

    logger.info("📅 Callback scheduled: %s for %s", callback_id, client_id)

    return {
        "success": True,
        "callback_scheduled": True,
        "callback_id": callback_id,
        "department": department,
        "estimated_callback": preferred_time or "within 2 hours",
        "confirmation_sent": True,
        "message": "Callback has been scheduled. You'll receive a text confirmation.",
    }


async def submit_complaint(args: dict[str, Any]) -> dict[str, Any]:
    """Submit formal complaint."""
    client_id = (args.get("client_id") or "").strip()
    complaint_type = (args.get("complaint_type") or "other").strip()
    description = (args.get("description") or "").strip()
    desired_resolution = (args.get("desired_resolution") or "").strip()

    if not client_id or not description:
        return {"success": False, "message": "client_id and description required."}

    case_id = f"CMP-{datetime.now().strftime('%Y%m%d')}-{len(_COMPLAINTS) + 1:04d}"

    complaint = {
        "case_id": case_id,
        "client_id": client_id,
        "type": complaint_type,
        "description": description,
        "desired_resolution": desired_resolution,
        "status": "submitted",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    _COMPLAINTS[case_id] = complaint

    logger.info("📝 Complaint submitted: %s - type: %s", case_id, complaint_type)

    return {
        "success": True,
        "complaint_submitted": True,
        "case_id": case_id,
        "type": complaint_type,
        "response_timeframe": "3-5 business days",
        "escalation_path": "If not resolved, can escalate to executive relations",
        "message": f"Your complaint has been logged. Reference number: {case_id}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "escalate_human", escalate_human_schema, escalate_human, tags={"escalation", "transfer"}
)
register_tool(
    "escalate_emergency",
    escalate_emergency_schema,
    escalate_emergency,
    tags={"escalation", "emergency"},
)
register_tool(
    "transfer_call_to_call_center",
    transfer_call_to_call_center_schema,
    transfer_call_to_call_center,
    tags={"escalation", "transfer"},
)
register_tool(
    "schedule_callback",
    schedule_callback_schema,
    schedule_callback,
    tags={"escalation", "callback"},
)
register_tool(
    "submit_complaint", submit_complaint_schema, submit_complaint, tags={"escalation", "complaint"}
)
