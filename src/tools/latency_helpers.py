from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger("tools.latency_helpers")

# Limits to keep Redis payloads bounded (tweak via env)
MAX_RUNS = int(os.getenv("LAT_MAX_RUNS", "200"))
MAX_SAMPLES_PER_RUN = int(os.getenv("LAT_MAX_SAMPLES_PER_RUN", "200"))


@dataclass
class StageSample:
    stage: str
    start: float
    end: float
    dur: float
    meta: dict[str, Any] | None = None


@dataclass
class RunRecord:
    run_id: str
    label: str
    created_at: float
    samples: list[StageSample]


_CORE_KEY = "latency"  # lives under CoreMemory["latency"]


def _now() -> float:
    # monotonic high-res (duration safe)
    return time.perf_counter()


class PersistentLatency:
    """
    Writes latency to CoreMemory so it survives Redis round-trips.

    CoreMemory layout (JSON-serializable):
    corememory["latency"] = {
      "current_run_id": "abc123",
      "runs": {
         "abc123": {
           "run_id": "abc123",
           "label": "turn",
           "created_at": 123456.78,
           "samples": [
              {"stage": "stt", "start": ..., "end": ..., "dur": ..., "meta": {...}},
              ...
           ]
         },
         ...
      },
      "order": ["abc123", "def456", ...]  # recency list to enforce MAX_RUNS
    }
    """

    def __init__(self, cm) -> None:
        self.cm = cm
        self._inflight: dict[tuple[str, str], float] = {}

    # ---------- run management ----------
    def begin_run(self, label: str = "turn", run_id: str | None = None) -> str:
        rid = run_id or uuid.uuid4().hex[:12]
        lat = self._get_bucket()
        if "runs" not in lat:
            lat["runs"] = {}
        if "order" not in lat:
            lat["order"] = []

        lat["current_run_id"] = rid
        lat["runs"][rid] = asdict(RunRecord(run_id=rid, label=label, created_at=_now(), samples=[]))

        lat["order"].append(rid)
        # enforce limits
        while len(lat["order"]) > MAX_RUNS:
            oldest = lat["order"].pop(0)
            lat["runs"].pop(oldest, None)
        self._set_bucket(lat)
        return rid

    def set_current_run(self, run_id: str) -> None:
        lat = self._get_bucket()
        if run_id in lat.get("runs", {}):
            lat["current_run_id"] = run_id
            self._set_bucket(lat)

    def current_run_id(self) -> str | None:
        return self._get_bucket().get("current_run_id")

    # ---------- stage timings ----------
    def start(self, stage: str, *, run_id: str | None = None) -> None:
        rid = run_id or self.current_run_id() or self.begin_run()
        self._inflight[(rid, stage)] = _now()

    def stop(
        self,
        stage: str,
        *,
        redis_mgr,
        run_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> StageSample | None:
        rid = run_id or self.current_run_id()
        if not rid:
            logger.warning("[Latency] stop(%s) called but no run_id; creating new run", stage)
            rid = self.begin_run()
        start = self._inflight.pop((rid, stage), None)
        if start is None:
            logger.warning("[Latency] stop(%s) without matching start (run=%s)", stage, rid)
            return None
        end = _now()
        sample = StageSample(stage=stage, start=start, end=end, dur=end - start, meta=meta or {})
        self._append_sample(rid, sample)
        # persist immediately for live dashboards
        try:
            self.cm.persist_to_redis(redis_mgr)
        except Exception as e:
            logger.error("Failed to persist latency to Redis: %s", e)
        logger.info("[Latency] %s run=%s: %.3f s", stage, rid, sample.dur)
        return sample

    # ---------- summaries ----------
    def session_summary(self) -> dict[str, dict[str, float]]:
        """
        Aggregate across all runs, per stage.
        Returns { stage: {count, avg, min, max, total} }
        """
        lat = self._get_bucket()
        out: dict[str, dict[str, float]] = {}
        for rid in lat.get("order", []):
            for s in lat["runs"].get(rid, {}).get("samples", []):
                d = s["dur"]
                st = s["stage"]
                acc = out.setdefault(st, {"count": 0, "avg": 0.0, "min": d, "max": d, "total": 0.0})
                acc["count"] += 1
                acc["total"] += d
                if d < acc["min"]:
                    acc["min"] = d
                if d > acc["max"]:
                    acc["max"] = d
        for st, acc in out.items():
            acc["avg"] = acc["total"] / acc["count"] if acc["count"] else 0.0
        return out

    def run_summary(self, run_id: str) -> dict[str, dict[str, float]]:
        """
        Aggregate for a single run, per stage.
        """
        lat = self._get_bucket()
        run = lat.get("runs", {}).get(run_id)
        out: dict[str, dict[str, float]] = {}
        if not run:
            return out
        for s in run.get("samples", []):
            d = s["dur"]
            st = s["stage"]
            acc = out.setdefault(st, {"count": 0, "avg": 0.0, "min": d, "max": d, "total": 0.0})
            acc["count"] += 1
            acc["total"] += d
            if d < acc["min"]:
                acc["min"] = d
            if d > acc["max"]:
                acc["max"] = d
        for st, acc in out.items():
            acc["avg"] = acc["total"] / acc["count"] if acc["count"] else 0.0
        return out

    # ---------- helpers ----------
    def _append_sample(self, run_id: str, sample: StageSample) -> None:
        lat = self._get_bucket()
        run = lat.setdefault("runs", {}).get(run_id)
        if not run:
            # create missing run bucket if someone forgot begin_run()
            run = asdict(RunRecord(run_id=run_id, label="turn", created_at=_now(), samples=[]))
            lat.setdefault("runs", {})[run_id] = run
            lat.setdefault("order", []).append(run_id)

        samples: list[dict[str, Any]] = run["samples"]
        samples.append(asdict(sample))
        # cap samples to avoid unbounded growth
        if len(samples) > MAX_SAMPLES_PER_RUN:
            del samples[0 : len(samples) - MAX_SAMPLES_PER_RUN]
        self._set_bucket(lat)

    def _get_bucket(self) -> dict[str, Any]:
        return self.cm.get_context(_CORE_KEY, {"runs": {}, "order": []})

    def _set_bucket(self, value: dict[str, Any]) -> None:
        self.cm.set_context(_CORE_KEY, value)
