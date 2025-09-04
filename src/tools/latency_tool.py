from __future__ import annotations

from typing import Any, Dict, Optional

from utils.ml_logging import get_logger
from src.tools.latency_helpers import PersistentLatency

logger = get_logger("tools.latency")


class LatencyTool:
    """
    Backwards-compatible wrapper used at WS layer.

    start(stage) / stop(stage, redis_mgr) keep working,
    but data is written into CoreMemory["latency"] with a per-run grouping.
    """

    def __init__(self, cm):
        self.cm = cm
        self._store = PersistentLatency(cm)
        # Track active timers to prevent start/stop mismatches
        self._active_timers = set()

    # Optional: set current run for this connection
    def set_current_run(self, run_id: str) -> None:
        self._store.set_current_run(run_id)

    def get_current_run(self) -> Optional[str]:
        return self._store.current_run_id()

    def begin_run(self, label: str = "turn") -> str:
        rid = self._store.begin_run(label=label)
        return rid

    def start(self, stage: str) -> None:
        # Track timer state to prevent duplicate starts
        if stage in self._active_timers:
            logger.debug(
                f"[PERF] Timer '{stage}' already running, skipping duplicate start"
            )
            return

        self._active_timers.add(stage)
        self._store.start(stage)

    def stop(
        self, stage: str, redis_mgr, *, meta: Optional[Dict[str, Any]] = None
    ) -> None:
        # Check timer state before stopping
        if stage not in self._active_timers:
            logger.debug(f"[PERF] Timer '{stage}' not running, skipping stop")
            return

        self._active_timers.discard(stage)  # Remove from active set
        self._store.stop(stage, redis_mgr=redis_mgr, meta=meta)

    # convenient summaries for dashboards
    def session_summary(self):
        return self._store.session_summary()

    def run_summary(self, run_id: str):
        return self._store.run_summary(run_id)

    def cleanup_timers(self) -> None:
        """Clean up active timers on session disconnect."""
        if self._active_timers:
            logger.debug(
                f"[PERF] Cleaning up {len(self._active_timers)} active timers: {self._active_timers}"
            )
            self._active_timers.clear()
