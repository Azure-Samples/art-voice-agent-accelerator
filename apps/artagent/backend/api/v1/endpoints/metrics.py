"""
Session Metrics Endpoints
=========================

REST API endpoints for exposing session telemetry and latency metrics.
Supports Phase 3 Dashboard Integration for the telemetry plan.

Endpoints:
- GET /api/v1/metrics/sessions - List active sessions with basic metrics
- GET /api/v1/metrics/session/{session_id} - Get detailed metrics for a session
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from utils.ml_logging import get_logger

from ..schemas.metrics import (
    ActiveSessionsResponse,
    LatencyStats,
    LatencyBreakdownItem,
    PerformanceInsight,
    InsightsSummary,
    SessionMetricsResponse,
    TokenUsage,
    TurnMetrics,
)

logger = get_logger(__name__)

router = APIRouter()


def _get_latency_stats(samples: list[float]) -> LatencyStats:
    """Calculate latency statistics from a list of samples."""
    if not samples:
        return LatencyStats(avg_ms=0, min_ms=0, max_ms=0, count=0)

    sorted_samples = sorted(samples)
    n = len(sorted_samples)

    return LatencyStats(
        avg_ms=sum(samples) / n,
        min_ms=min(samples),
        max_ms=max(samples),
        p50_ms=sorted_samples[n // 2] if n > 0 else None,
        p95_ms=sorted_samples[int(n * 0.95)] if n >= 20 else None,
        p99_ms=sorted_samples[int(n * 0.99)] if n >= 100 else None,
        count=n,
    )


async def _get_session_metrics_from_redis(
    request: Request, session_id: str
) -> dict[str, Any] | None:
    """
    Retrieve session metrics from Redis.

    Session data is stored at key: session:{session_id}
    with fields 'corememory' and 'chat_history' as JSON strings.
    """
    try:
        redis_manager = getattr(request.app.state, "redis", None)
        if not redis_manager:
            logger.warning("Redis manager not available for metrics retrieval")
            return None

        # Session data is stored at key: session:{session_id}
        session_key = f"session:{session_id}"

        # Use sync client since that's what AzureRedisManager exposes
        session_data = redis_manager.get_session_data(session_key)

        if session_data:
            result = {}
            # Parse corememory JSON if present
            if "corememory" in session_data:
                try:
                    cm_data = session_data["corememory"]
                    if isinstance(cm_data, str):
                        result["corememory"] = json.loads(cm_data)
                    else:
                        result["corememory"] = cm_data
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse corememory: {e}")

            # Parse chat_history JSON if present
            if "chat_history" in session_data:
                try:
                    ch_data = session_data["chat_history"]
                    if isinstance(ch_data, str):
                        result["chat_history"] = json.loads(ch_data)
                    else:
                        result["chat_history"] = ch_data
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse chat_history: {e}")

            return result if result else None

        return None

    except Exception as e:
        logger.error(f"Failed to retrieve session metrics from Redis: {e}")
        return None


async def _get_session_manager_data(request: Request) -> dict[str, Any]:
    """Get active session data from ThreadSafeSessionManager."""
    session_manager = getattr(request.app.state, "session_manager", None)
    if not session_manager:
        return {"sessions": {}, "count": 0}

    try:
        count = await session_manager.get_session_count()
        snapshot = await session_manager.get_all_sessions_snapshot()
        return {"sessions": snapshot, "count": count}
    except Exception as e:
        logger.error(f"Failed to get session manager data: {e}")
        return {"sessions": {}, "count": 0}


async def _get_session_metrics_data(request: Request) -> dict[str, Any]:
    """Get metrics from ThreadSafeSessionMetrics."""
    session_metrics = getattr(request.app.state, "session_metrics", None)
    if not session_metrics:
        return {
            "active_connections": 0,
            "total_connected": 0,
            "total_disconnected": 0,
        }

    try:
        return await session_metrics.get_snapshot()
    except Exception as e:
        logger.error(f"Failed to get session metrics: {e}")
        return {
            "active_connections": 0,
            "total_connected": 0,
            "total_disconnected": 0,
        }


@router.get(
    "/sessions",
    response_model=ActiveSessionsResponse,
    summary="List active sessions",
    description="Get a list of all active sessions with basic metrics.",
    tags=["Session Metrics"],
)
async def list_active_sessions(request: Request) -> ActiveSessionsResponse:
    """
    List all active sessions with summary metrics.

    Returns counts of active media and browser sessions, plus basic
    session information for each active session.
    """
    # Get data from both session manager and metrics
    manager_data = await _get_session_manager_data(request)
    metrics_data = await _get_session_metrics_data(request)
    media_sessions = 0

    # Count ACS media sessions using connection manager call mappings
    conn_manager = getattr(request.app.state, "conn_manager", None)
    if conn_manager and hasattr(conn_manager, "stats"):
        try:
            conn_stats = await conn_manager.stats()
            by_call = conn_stats.get("by_call") or {}
            media_sessions = sum(1 for count in by_call.values() if count)
        except Exception as e:
            logger.error(f"Failed to get ACS session data: {e}")

    # Build session summaries from session manager
    sessions = []
    for session_id, session_info in manager_data["sessions"].items():
        start_time = session_info.get("start_time")
        sessions.append(
            {
                "session_id": session_id,
                "transport_type": "BROWSER",  # Session manager tracks browser sessions
                "status": "active",
                "start_time": start_time.isoformat() if start_time else None,
            }
        )

    return ActiveSessionsResponse(
        total_active=metrics_data.get("active_connections", 0),
        media_sessions=media_sessions,
        browser_sessions=manager_data["count"],
        total_disconnected=metrics_data.get("total_disconnected", 0),
        sessions=sessions,
    )


@router.get(
    "/session/{session_id}",
    response_model=SessionMetricsResponse,
    summary="Get session metrics",
    description="Get detailed latency and telemetry metrics for a specific session.",
    tags=["Session Metrics"],
)
async def get_session_metrics(
    request: Request,
    session_id: str,
    include_turns: bool = Query(False, description="Include per-turn breakdown (can be large)"),
) -> SessionMetricsResponse:
    """
    Get detailed metrics for a specific session.

    Returns latency statistics, token usage, and optionally per-turn
    breakdown for the specified session.

    Args:
        session_id: The session identifier
        include_turns: Whether to include per-turn breakdown

    Raises:
        HTTPException: 404 if session not found
    """
    # Check if session is active in session manager
    session_manager = getattr(request.app.state, "session_manager", None)
    is_active = False
    session_context = None

    if session_manager:
        session_context = await session_manager.get_session_context(session_id)
        is_active = session_context is not None

    # Try to get metrics from Redis
    redis_data = await _get_session_metrics_from_redis(request, session_id)

    # If no data found and session not active, return 404
    if not redis_data and not is_active:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or has no metrics data",
        )

    # Parse metrics from Redis corememory
    latency_summary: dict[str, LatencyStats] = {}
    latency_breakdown: list[LatencyBreakdownItem] = []
    insights: list[PerformanceInsight] = []
    insights_summary: InsightsSummary | None = None
    turns: list[TurnMetrics] = []
    token_usage = None
    turn_count = 0
    session_duration_ms = None
    start_time = None

    if redis_data and "corememory" in redis_data:
        corememory = redis_data["corememory"]

        # Extract latency data if present
        latency_data = corememory.get("latency", {})
        if latency_data:
            # PRIORITY 1: Try core_memory_metrics structure first (recent_turns)
            recent_turns = latency_data.get("recent_turns", [])
            if recent_turns:
                # This is the newer structure from core_memory_metrics
                turn_count = len(recent_turns)

                # Aggregate samples by metric type from recent_turns
                samples_by_stage: dict[str, list[float]] = {}
                for turn in recent_turns:
                    metrics = turn.get("metrics", {})
                    for metric_type, metric_data in metrics.items():
                        value_ms = metric_data.get("value_ms")
                        if value_ms is not None:
                            if metric_type not in samples_by_stage:
                                samples_by_stage[metric_type] = []
                            samples_by_stage[metric_type].append(value_ms)

                # Calculate stats for each metric type
                for stage, samples in samples_by_stage.items():
                    latency_summary[stage] = _get_latency_stats(samples)

            else:
                # FALLBACK: Parse legacy latency data structure (pre-OTel migration)
                runs = latency_data.get("runs", {})
                turn_count = len(runs)

                # Aggregate samples by stage
                samples_by_stage: dict[str, list[float]] = {}
                for run_id, run_data in runs.items():
                    for sample in run_data.get("samples", []):
                        stage = sample.get("stage", "unknown")
                        # Duration is in seconds, convert to ms
                        dur_ms = sample.get("dur", 0) * 1000
                        if stage not in samples_by_stage:
                            samples_by_stage[stage] = []
                        samples_by_stage[stage].append(dur_ms)

                # Calculate stats for each stage
                for stage, samples in samples_by_stage.items():
                    latency_summary[stage] = _get_latency_stats(samples)

            if latency_summary:
                max_avg_ms = max((stats.avg_ms for stats in latency_summary.values()), default=0)
                for stage, stats in sorted(latency_summary.items()):
                    if stats.avg_ms >= 1000:
                        severity = "error"
                    elif stats.avg_ms >= 500:
                        severity = "warning"
                    else:
                        severity = "success"

                    relative_pct = (stats.avg_ms / max_avg_ms * 100) if max_avg_ms else 0.0

                    latency_breakdown.append(
                        LatencyBreakdownItem(
                            stage=stage,
                            avg_ms=stats.avg_ms,
                            min_ms=stats.min_ms,
                            max_ms=stats.max_ms,
                            p50_ms=stats.p50_ms,
                            p95_ms=stats.p95_ms,
                            p99_ms=stats.p99_ms,
                            count=stats.count,
                            severity=severity,
                            relative_pct=relative_pct,
                        )
                    )

                    if severity in {"warning", "error"}:
                        insights.append(
                            PerformanceInsight(
                                type="high_latency",
                                stage=stage,
                                severity=severity,
                                message=f"{stage} averaging {stats.avg_ms:.1f}ms",
                            )
                        )

                    if stats.count >= 10:
                        insights.append(
                            PerformanceInsight(
                                type="high_frequency",
                                stage=stage,
                                severity="warning",
                                message=f"{stage} recorded {stats.count} times",
                            )
                        )

        # Extract token usage if tracked in corememory
        token_data = corememory.get("token_usage", {})
        if token_data:
            total_input = token_data.get("total_input_tokens", 0)
            total_output = token_data.get("total_output_tokens", 0)
            token_usage = TokenUsage(
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                total_tokens=total_input + total_output,
                avg_input_per_turn=total_input / turn_count if turn_count > 0 else 0,
                avg_output_per_turn=total_output / turn_count if turn_count > 0 else 0,
            )

    # Get start time from session context if available
    if session_context and hasattr(session_context, "start_time"):
        start_time = session_context.start_time.timestamp() if session_context.start_time else None

    # Determine session status
    status = "active" if is_active else "completed"

    return SessionMetricsResponse(
        session_id=session_id,
        call_connection_id=None,  # Browser sessions don't have ACS call connection ID
        transport_type="BROWSER" if is_active else None,
        turn_count=turn_count,
        session_duration_ms=session_duration_ms,
        latency_summary=latency_summary,
        latency_breakdown=latency_breakdown,
        token_usage=token_usage,
        turns=turns if include_turns and turns else None,
        status=status,
        error_count=0,
        start_time=start_time,
        insights=insights,
        insights_summary=(
            InsightsSummary(
                severity=(
                    "error"
                    if any(item.severity == "error" for item in insights)
                    else "warning"
                    if any(item.severity == "warning" for item in insights)
                    else "info"
                ),
                count=len(insights),
            )
            if insights
            else None
        ),
    )


@router.get(
    "/summary",
    summary="Get aggregated metrics summary",
    description="Get aggregated latency metrics across all recent sessions.",
    tags=["Session Metrics"],
)
async def get_metrics_summary(
    request: Request,
    window_minutes: int = Query(60, ge=1, le=1440, description="Time window in minutes (1-1440)"),
) -> dict[str, Any]:
    """
    Get aggregated metrics summary across recent sessions.

    This endpoint provides a high-level overview of system performance
    without requiring a specific session ID.

    Args:
        window_minutes: Time window to aggregate (default 60 minutes)
    """
    manager_data = await _get_session_manager_data(request)
    metrics_data = await _get_session_metrics_data(request)

    return {
        "window_minutes": window_minutes,
        "active_connections": metrics_data.get("active_connections", 0),
        "browser_sessions": manager_data["count"],
        "total_connected": metrics_data.get("total_connected", 0),
        "total_disconnected": metrics_data.get("total_disconnected", 0),
        "last_updated": metrics_data.get("last_updated"),
        "session_ids": list(manager_data["sessions"].keys()),
        "note": "For detailed latency analysis, use Application Insights KQL queries from TELEMETRY_PLAN.md",
    }
