"""
Voicemail Detection Tools
=========================

Tools for detecting and handling voicemail scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.voicemail")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

detect_voicemail_and_end_call_schema: dict[str, Any] = {
    "name": "detect_voicemail_and_end_call",
    "description": (
        "Detect if call has reached a voicemail system and end the call gracefully. "
        "Use when you hear voicemail greeting, beep tones, or automated messages. "
        "This will leave a brief message and disconnect."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why voicemail was detected (greeting heard, beep tone, etc.)",
            },
            "leave_message": {
                "type": "boolean",
                "description": "Whether to leave a callback message",
            },
            "callback_number": {
                "type": "string",
                "description": "Callback number to include in message",
            },
        },
        "required": ["reason"],
    },
}

confirm_voicemail_and_end_call_schema: dict[str, Any] = {
    "name": "confirm_voicemail_and_end_call",
    "description": (
        "Confirm voicemail detection and end call after leaving message. "
        "Use after voicemail beep to leave a brief callback message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message_left": {
                "type": "string",
                "description": "Brief message left on voicemail",
            },
            "callback_scheduled": {
                "type": "boolean",
                "description": "Whether callback was scheduled",
            },
        },
        "required": [],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def detect_voicemail_and_end_call(args: dict[str, Any]) -> dict[str, Any]:
    """Detect voicemail and prepare to end call."""
    reason = (args.get("reason") or "voicemail detected").strip()
    leave_message = args.get("leave_message", True)
    callback_number = (args.get("callback_number") or "").strip()

    logger.info("📞 Voicemail detected: %s", reason)

    return {
        "success": True,
        "voicemail_detected": True,
        "reason": reason,
        "action": "ending_call",
        "leave_message": leave_message,
        "callback_number": callback_number or "main line",
        "message": "Voicemail detected. Leaving message and ending call.",
        # Signal to orchestrator to end call
        "end_call": True,
    }


async def confirm_voicemail_and_end_call(args: dict[str, Any]) -> dict[str, Any]:
    """Confirm voicemail message left and end call."""
    message_left = (args.get("message_left") or "").strip()
    callback_scheduled = args.get("callback_scheduled", False)

    logger.info("📞 Voicemail message left, ending call")

    return {
        "success": True,
        "message_left": bool(message_left),
        "callback_scheduled": callback_scheduled,
        "call_ended": True,
        "timestamp": datetime.now(UTC).isoformat(),
        # Signal to orchestrator to end call
        "end_call": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "detect_voicemail_and_end_call",
    detect_voicemail_and_end_call_schema,
    detect_voicemail_and_end_call,
    tags={"voicemail", "call_control"},
)
register_tool(
    "confirm_voicemail_and_end_call",
    confirm_voicemail_and_end_call_schema,
    confirm_voicemail_and_end_call,
    tags={"voicemail", "call_control"},
)
