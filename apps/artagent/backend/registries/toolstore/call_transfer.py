"""
Call Transfer Tools
===================

Tools for transferring calls to external destinations or call centers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.call_transfer")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

transfer_call_to_destination_schema: dict[str, Any] = {
    "name": "transfer_call_to_destination",
    "description": (
        "Transfer the call to a specific phone number or SIP destination. "
        "Use for external transfers outside the agent network."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "Phone number or SIP URI to transfer to",
            },
            "reason": {
                "type": "string",
                "description": "Reason for transfer",
            },
            "transfer_type": {
                "type": "string",
                "enum": ["cold", "warm", "blind"],
                "description": "Type of transfer (cold=no announcement, warm=with context)",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary to provide to receiving party (for warm transfers)",
            },
        },
        "required": ["destination", "reason"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def transfer_call_to_destination(args: dict[str, Any]) -> dict[str, Any]:
    """Transfer call to external destination."""
    destination = (args.get("destination") or "").strip()
    reason = (args.get("reason") or "").strip()
    transfer_type = (args.get("transfer_type") or "cold").strip()
    context_summary = (args.get("context_summary") or "").strip()

    if not destination:
        return {"success": False, "message": "Destination is required."}
    if not reason:
        return {"success": False, "message": "Reason is required."}

    logger.info("📞 Call transfer initiated: %s -> %s (%s)", reason, destination, transfer_type)

    return {
        "success": True,
        "transfer_initiated": True,
        "destination": destination,
        "transfer_type": transfer_type,
        "reason": reason,
        "context_transferred": bool(context_summary),
        "timestamp": datetime.now(UTC).isoformat(),
        "message": f"Transferring call to {destination}.",
        # Signal to orchestrator to perform transfer
        "perform_transfer": True,
        "transfer_destination": destination,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "transfer_call_to_destination",
    transfer_call_to_destination_schema,
    transfer_call_to_destination,
    tags={"call_transfer", "telephony"},
)
