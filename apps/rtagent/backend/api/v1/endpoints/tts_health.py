"""
Lightweight TTS Pool Health Monitoring

Minimal overhead health check endpoint for monitoring the dedicated TTS pool performance.
Optimized for low latency and minimal resource usage.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
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
        # Fast metrics collection - no complex calculations
        metrics = await manager.get_metrics()

        # Simplified health indicators for speed
        dedicated_count = metrics.get("dedicated_client_count", 0)
        warm_count = metrics.get("warm_pool_size", 0)

        # Binary health status for speed
        is_healthy = dedicated_count >= 0 and warm_count >= 0

        health_status = {
            "status": "healthy" if is_healthy else "degraded",
            "dedicated_clients": dedicated_count,
            "warm_pool_size": warm_count,
            "timestamp": metrics.get("timestamp"),
        }

        logger.info(
            f"[PERF] TTS Health: {health_status['status']}, "
            f"dedicated={dedicated_count}, warm={warm_count}"
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
        # Get raw metrics only - no expensive calculations
        metrics = await manager.get_metrics()

        # Return minimal set for performance
        essential_metrics = {
            "dedicated_client_count": metrics.get("dedicated_client_count", 0),
            "warm_pool_size": metrics.get("warm_pool_size", 0),
            "total_allocations": metrics.get("total_allocations", 0),
            "allocation_failures": metrics.get("allocation_failures", 0),
            "timestamp": metrics.get("timestamp"),
        }

        logger.info(f"[PERF] TTS metrics collected: {essential_metrics}")
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
        # Ultra-fast check - just verify manager is responsive
        metrics = await asyncio.wait_for(manager.get_metrics(), timeout=1.0)

        return {"status": "ok", "timestamp": metrics.get("timestamp")}

    except asyncio.TimeoutError:
        return {"status": "timeout"}
    except Exception:
        return {"status": "error"}
