from __future__ import annotations

"""
Voicemail detection helper for the AutoAuth agent.

When the agent is confident the caller is a voicemail greeting or an answering
machine, it can invoke this tool to signal that the call should be ended
gracefully. The orchestration layer will handle the actual termination once it
sees the structured response returned here.
"""

from typing import Any, Dict, Optional, TypedDict

from utils.ml_logging import get_logger

logger = get_logger("tool_store.voicemail")


class VoicemailDetectionArgs(TypedDict, total=False):
    """Input schema for :pyfunc:`detect_voicemail_and_end_call`."""

    voicemail_cues: str
    confidence: float


async def detect_voicemail_and_end_call(
    args: VoicemailDetectionArgs,
) -> Dict[str, Any]:
    """
    Signal that the current interaction is a voicemail and should be terminated.

    Returns a structured payload consumed by the orchestration layer. The tool
    itself does not close the call; it simply reports the detection so upstream
    code can hang up and clean up resources.
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type for voicemail tool: %s", type(args))
        return {
            "voicemail_detected": False,
            "terminate_session": False,
            "error": "Invalid request format. Expected an object with voicemail cues.",
        }

    cues = (args.get("voicemail_cues") or "").strip()
    confidence_raw: Optional[float] = args.get("confidence")

    confidence: Optional[float] = None
    if confidence_raw is not None:
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            logger.debug(
                "Unable to coerce voicemail confidence '%s' to float; ignoring.",
                confidence_raw,
            )

    if not cues:
        cues = "No explicit cues provided."

    logger.info(
        "Voicemail detection signalled – cues='%s' confidence=%s",
        cues,
        confidence,
    )

    return {
        "voicemail_detected": True,
        "terminate_session": True,
        "termination_reason": "voicemail_detected",
        "summary": cues,
        "confidence": confidence,
    }
