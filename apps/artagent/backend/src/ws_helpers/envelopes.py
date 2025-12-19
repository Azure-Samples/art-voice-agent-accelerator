"""
WebSocket Message Envelopes - Simplified
========================================

Clean, focused message formatting for WebSocket communications.
Provides standardized envelope format with minimal complexity.
"""

from datetime import UTC, datetime
from typing import Any, Literal

EnvelopeType = Literal[
    "event", "status", "assistant", "assistant_streaming", "exit", "error", "debug"
]
TopicType = Literal["dashboard", "session", "call", "user", "system", "media"]
SenderType = Literal["Assistant", "User", "System", "ACS", "STT", "TTS"]


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(UTC).isoformat()


def make_envelope(
    *,
    etype: EnvelopeType,
    sender: SenderType,
    payload: dict[str, Any],
    topic: TopicType,
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Build standard WebSocket message envelope."""
    return {
        "type": etype,
        "topic": topic,
        "session_id": session_id,
        "call_id": call_id,
        "user_id": user_id,
        "sender": sender,
        "ts": _utc_now_iso(),
        "payload": payload,
        "speaker_id": sender,
    }


def make_status_envelope(
    message: str,
    *,
    sender: SenderType = "System",
    topic: TopicType = "system",
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Create status message envelope."""
    payload = {"message": message}
    if label:
        payload["label"] = label

    payload.setdefault("timestamp", _utc_now_iso())

    return make_envelope(
        etype="status",
        sender=sender,
        payload=payload,
        topic=topic,
        session_id=session_id,
        call_id=call_id,
        user_id=user_id,
    )


def make_assistant_envelope(
    content: str,
    *,
    sender: SenderType = "Assistant",
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create non-streaming assistant response envelope."""
    return make_envelope(
        etype="assistant",
        sender=sender,
        payload={"content": content, "message": content, "streaming": False},
        topic="session",
        session_id=session_id,
        call_id=call_id,
        user_id=user_id,
    )


def make_assistant_streaming_envelope(
    content: str,
    *,
    sender: SenderType = "Assistant",
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create assistant streaming response envelope."""
    return make_envelope(
        etype="assistant_streaming",
        sender=sender,
        payload={"content": content, "streaming": True},
        topic="session",
        session_id=session_id,
        call_id=call_id,
        user_id=user_id,
    )


def make_event_envelope(
    event_type: str,
    event_data: dict[str, Any],
    *,
    sender: SenderType = "System",
    topic: TopicType = "system",
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    payload_data = dict(event_data or {})
    payload_data.setdefault("timestamp", _utc_now_iso())
    """Create system event envelope."""
    return make_envelope(
        etype="event",
        sender=sender,
        payload={"event_type": event_type, "data": payload_data},
        topic=topic,
        session_id=session_id,
        call_id=call_id,
        user_id=user_id,
    )


def make_error_envelope(
    error_message: str,
    error_type: str = "unknown",
    *,
    sender: SenderType = "System",
    topic: TopicType = "system",
    session_id: str | None = None,
    call_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create error message envelope."""
    return make_envelope(
        etype="error",
        sender=sender,
        payload={"error_message": error_message, "error_type": error_type},
        topic=topic,
        session_id=session_id,
        call_id=call_id,
        user_id=user_id,
    )
