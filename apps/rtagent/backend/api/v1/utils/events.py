"""
event Event Utilities for V1 API
=================================

Lightweight event utilities focused on real-time voice operations.
Replaces the complex event system with event, direct patterns.
"""

import time
from typing import Dict, Any, Optional
from utils.ml_logging import get_logger

logger = get_logger("v1.events")


async def emit_call_lifecycle_event(
    event_type: str, call_id: str, data: Optional[Dict[str, Any]] = None
) -> None:
    """
    event call lifecycle event emission for REST API tracking.

    Args:
        event_type: Type of event (call.initiated, call.connected, etc.)
        call_id: Call connection ID for correlation
        data: Optional additional data
    """
    event_data = {
        "event_type": event_type,
        "call_id": call_id,
        "timestamp": time.time(),
        **(data or {}),
    }

    logger.info(
        f"Call Event: {event_type}",
        extra={"call_connection_id": call_id, "event_type": event_type, **event_data},
    )


def get_event_health_status() -> Dict[str, Any]:
    """
    event health status without complex event registry overhead.

    Returns:
        Basic health information for monitoring
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "api_version": "v1",
        "architecture": "three_thread",
    }


def get_system_metrics() -> Dict[str, Any]:
    """
    event system metrics without event registry complexity.

    Returns:
        Basic system metrics for monitoring
    """
    return {
        "uptime_seconds": time.time(),
        "memory_usage": "available_via_separate_monitoring",
        "active_calls": "tracked_via_call_state",
        "api_version": "v1",
    }
