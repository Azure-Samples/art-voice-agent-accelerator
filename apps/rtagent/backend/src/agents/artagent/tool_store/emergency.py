from typing import Any, Dict, TypedDict

from apps.rtagent.backend.src.agents.artagent.tool_store.functions_helper import _json
from utils.ml_logging import get_logger

logger = get_logger("tool_store.emergency")


class EscalateEmergencyArgs(TypedDict):
    reason: str
    caller_name: str
    policy_id: str


async def escalate_emergency(args: EscalateEmergencyArgs) -> Dict[str, Any]:
    """
    Escalate the call to a live insurance agent and stop the bot session.
    """
    # Input type validation to prevent 400 errors
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return {
            "escalated": False,
            "escalation_reason": "Invalid request format. Please provide emergency details.",
            "handoff": None,
            "caller_name": None,
            "policy_id": None,
        }

    try:
        reason = args.get("reason", "").strip()
        caller_name = args.get("caller_name", "").strip()
        policy_id = args.get("policy_id", "").strip()

        if not reason:
            return {
                "escalated": False,
                "escalation_reason": "Reason for escalation is required.",
                "handoff": None,
                "caller_name": caller_name,
                "policy_id": policy_id,
            }

        if not caller_name:
            return {
                "escalated": False,
                "escalation_reason": "Caller name is required for emergency escalation.",
                "handoff": None,
                "caller_name": None,
                "policy_id": policy_id,
            }

        if not policy_id:
            return {
                "escalated": False,
                "escalation_reason": "Policy ID is required for emergency escalation.",
                "handoff": None,
                "caller_name": caller_name,
                "policy_id": None,
            }

        logger.info(
            "🔴 Escalating to human agent – %s (caller: %s, policy: %s)",
            reason,
            caller_name,
            policy_id,
        )

        # The sentinel that upstream code will look for
        return {
            "escalated": True,
            "escalation_reason": f"Emergency escalation for {caller_name} (Policy: {policy_id}): {reason}",
            "handoff": "human_agent",
            "caller_name": caller_name,
            "policy_id": policy_id,
        }
    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        logger.error("Emergency escalation failed: %s", exc, exc_info=True)
        return {
            "escalated": False,
            "escalation_reason": "Technical error during escalation. Please try again.",
            "handoff": None,
            "caller_name": args.get("caller_name") if isinstance(args, dict) else None,
            "policy_id": args.get("policy_id") if isinstance(args, dict) else None,
        }
