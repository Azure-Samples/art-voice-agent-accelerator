from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from opentelemetry import trace
from utils.ml_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


@asynccontextmanager
async def track_latency(timer, label: str, redis_mgr, *, meta: Optional[Dict[str, Any]] = None):
    """
    Context manager for tracking and storing conversation latency metrics.

    :param timer: Latency tool (supports start/stop and optionally meta)
    :param label: Stage label
    :param redis_mgr: Redis manager for persistence
    :param meta: Optional structured metadata for the latency record
    :return: Async context
    """
    t0 = time.perf_counter()
    timer.start(label)
    try:
        yield
    finally:
        sample = None
        try:
            sample = timer.stop(label, redis_mgr, meta=meta or {})
        except TypeError:
            timer.stop(label, redis_mgr)
        except Exception as exc:
            logger.error("Latency stop error for stage '%s': %s", label, exc)

        t1 = time.perf_counter()
        try:
            span = trace.get_current_span()
            attrs: Dict[str, Any] = {"latency.stage": label, "latency.elapsed": t1 - t0}
            get_run = getattr(timer, "get_current_run", None)
            if callable(get_run):
                rid = get_run()
                if rid:
                    attrs["run.id"] = rid
            if hasattr(sample, "dur"):
                attrs["latency.recorded"] = getattr(sample, "dur")
            elif isinstance(sample, dict) and "dur" in sample:
                attrs["latency.recorded"] = sample["dur"]
            span.add_event("latency.stop", attributes=attrs)
        except Exception:
            pass
