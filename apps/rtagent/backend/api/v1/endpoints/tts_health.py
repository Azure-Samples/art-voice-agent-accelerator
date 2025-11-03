"""
Lightweight TTS Pool Health Monitoring

Minimal overhead health check endpoint for monitoring the dedicated TTS pool performance.
Optimized for low latency and minimal resource usage.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging
import asyncio
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter()


async def get_dedicated_tts_manager():
    """Lightweight dependency to get the dedicated TTS manager."""
    try:
        # Direct import to avoid circular dependencies
        import sys

        if "apps.rtagent.backend.main" in sys.modules:
            main_module = sys.modules["apps.rtagent.backend.main"]
            return main_module.app.state.tts_pool
    except Exception as e:
        logger.warning(f"Could not access dedicated TTS manager: {e}")

    raise HTTPException(status_code=503, detail="Dedicated TTS manager not available")


@router.get("/tts/dedicated/health")
async def get_dedicated_tts_health(
    manager=Depends(get_dedicated_tts_manager),
) -> Dict[str, Any]:
    """
    🚀 PHASE 1: Lightweight health status of the dedicated TTS pool system.

    Optimized for minimal latency - returns essential health indicators only.
    """
    try:
        snapshot = manager.snapshot()  # type: ignore[attr-defined]
        active_sessions = snapshot.get("active_sessions", 0)
        ready = snapshot.get("ready", False)

        health_status = {
            "status": "healthy" if ready else "degraded",
            "active_sessions": active_sessions,
            "session_awareness": snapshot.get("session_awareness"),
            "timestamp": snapshot.get("metrics", {}).get("timestamp"),
        }

        logger.info(
            "[PERF] TTS Health: %s active_sessions=%s",
            health_status["status"],
            active_sessions,
        )

        return health_status

    except Exception as e:
        logger.error(f"[PERF] TTS health check failed: {e}")
        return {"status": "unhealthy", "error": str(e), "timestamp": None}


@router.get("/tts/dedicated/metrics")
async def get_tts_metrics(manager=Depends(get_dedicated_tts_manager)) -> Dict[str, Any]:
    """
    Essential performance metrics for dedicated TTS pool.

    Returns core metrics needed for performance monitoring.
    """
    try:
        snapshot = manager.snapshot()  # type: ignore[attr-defined]
        metrics = snapshot.get("metrics", {})

        essential_metrics = {
            "active_sessions": snapshot.get("active_sessions", 0),
            "allocations_total": metrics.get("allocations_total", 0),
            "allocations_cached": metrics.get("allocations_cached", 0),
            "allocations_new": metrics.get("allocations_new", 0),
            "timestamp": metrics.get("timestamp"),
        }

        logger.info("[PERF] TTS metrics collected: %s", essential_metrics)
        return essential_metrics

    except Exception as e:
        logger.error(f"[PERF] Failed to collect TTS metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics collection failed: {e}")


@router.get("/tts/dedicated/status")
async def get_simple_status(
    manager=Depends(get_dedicated_tts_manager),
) -> Dict[str, Any]:
    """
    🚀 PHASE 1: Ultra-fast status check for load balancer health checks.

    Minimal overhead endpoint for external monitoring systems.
    """
    try:
        snapshot = await asyncio.wait_for(
            asyncio.to_thread(manager.snapshot), timeout=1.0
        )

        return {"status": "ok", "timestamp": snapshot.get("metrics", {}).get("timestamp")}

    except asyncio.TimeoutError:
        return {"status": "timeout"}
    except Exception:
        return {"status": "error"}
