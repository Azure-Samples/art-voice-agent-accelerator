from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

Number = float


def compute_latency_statistics(
    payload: dict[str, Any],
    *,
    stage_thresholds: dict[str, Number] | None = None,
) -> dict[str, Any]:
    """
    Ingest a latency payload shaped like the example you posted and produce:
      - per-stage stats (count, sum, avg, min, max, p50, p90, p95)
      - per-agent stats (auth/general/claim stages)
      - per-voice stats for tts:synthesis
      - per-run summaries (totals + maxima)
      - SLA rollups against optional thresholds
      - front-end friendly bar chart series

    Args:
        payload: Dict with keys like 'runs', 'order', optionally 'current_run_id'.
        stage_thresholds: Optional thresholds (seconds) per stage to flag breaches.
                          e.g. {'tts': 1.5, 'greeting_ttfb': 2.0, 'auth_agent': 8.0}

    Returns:
        Dict[str, Any] of aggregated stats and chart data.
    """

    # ---------------- helpers ----------------
    def _percentiles(values: list[Number], ps: Iterable[Number]) -> dict[str, Number]:
        if not values:
            return {f"p{int(p)}": 0.0 for p in ps}
        xs = sorted(values)
        n = len(xs)
        out: dict[str, Number] = {}
        for p in ps:
            if n == 1:
                out[f"p{int(p)}"] = xs[0]
                continue
            k = (p / 100.0) * (n - 1)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                val = xs[int(k)]
            else:
                val = xs[f] + (xs[c] - xs[f]) * (k - f)
            out[f"p{int(p)}"] = float(val)
        return out

    def _agg(values: list[Number]) -> dict[str, Number]:
        if not values:
            return dict(count=0, total=0.0, avg=0.0, min=0.0, max=0.0, p50=0.0, p90=0.0, p95=0.0)
        total = float(sum(values))
        return {
            "count": len(values),
            "total": total,
            "avg": total / len(values),
            "min": float(min(values)),
            "max": float(max(values)),
            **_percentiles(values, [50, 90, 95]),
        }

    def _pct(num: int, den: int) -> float:
        return 0.0 if den <= 0 else (100.0 * num / den)

    # --------------- ingest -------------------
    runs: dict[str, Any] = payload.get("runs", {}) or {}
    order: list[str] = payload.get("order") or list(runs.keys())
    stage_thresholds = stage_thresholds or {"tts": 1.5, "greeting_ttfb": 2.0}

    per_stage: dict[str, list[Number]] = defaultdict(list)
    per_agent_stage: dict[str, list[Number]] = defaultdict(list)
    per_voice_synth: dict[str, list[Number]] = defaultdict(list)

    per_run_summary: list[dict[str, Any]] = []
    threshold_breaches: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for run_id in order:
        r = runs.get(run_id) or {}
        samples = r.get("samples", []) or []

        tts_segments: list[Number] = []
        synth_segments: list[Number] = []
        send_segments: list[Number] = []

        greet_ttfb: Number | None = None
        agent_times: dict[str, Number] = {}  # auth_agent/general_agent/claim_agent

        for s in samples:
            stage = s.get("stage")
            dur = float(s.get("dur", 0.0) or 0.0)
            per_stage[stage].append(dur)

            if stage in ("auth_agent", "general_agent", "claim_agent"):
                per_agent_stage[stage].append(dur)
                agent_times[stage] = agent_times.get(stage, 0.0) + dur

            if stage == "tts":
                tts_segments.append(dur)
            elif stage == "tts:synthesis":
                synth_segments.append(dur)
                meta = s.get("meta") or {}
                voice = meta.get("voice")
                if voice:
                    per_voice_synth[voice].append(dur)
            elif stage == "tts:send_frames":
                send_segments.append(dur)
            elif stage == "greeting_ttfb":
                greet_ttfb = dur

            # threshold tracking per-stage per-run
            if stage in stage_thresholds and dur > float(stage_thresholds[stage]):
                threshold_breaches[stage].append(
                    {
                        "run_id": run_id,
                        "duration": dur,
                        "threshold": float(stage_thresholds[stage]),
                    }
                )

        per_run_summary.append(
            {
                "run_id": run_id,
                "tts": {
                    "segments": len(tts_segments),
                    "sum": float(sum(tts_segments)),
                    "max_single": float(max(tts_segments) if tts_segments else 0.0),
                },
                "synthesis_sum": float(sum(synth_segments)),
                "send_frames_sum": float(sum(send_segments)),
                "greeting_ttfb": greet_ttfb if greet_ttfb is not None else 0.0,
                "agent_times": agent_times,
            }
        )

    # --------------- aggregates ----------------
    stage_stats = {stage: _agg(vals) for stage, vals in per_stage.items()}
    agent_stats = {agent: _agg(vals) for agent, vals in per_agent_stage.items()}
    voice_stats = {voice: _agg(vals) for voice, vals in per_voice_synth.items()}

    # SLA rollups (examples)
    n_runs = len(per_run_summary)
    runs_with_tts_le_1_5 = sum(1 for r in per_run_summary if r["tts"]["max_single"] <= 1.5)
    runs_with_ttfb_le_2_0 = sum(
        1
        for r in per_run_summary
        if r.get("greeting_ttfb", 0.0) <= 2.0 and r.get("greeting_ttfb", 0.0) > 0.0
    )

    sla = {
        "runs": n_runs,
        "tts_max_single_le_1_5s_pct": _pct(runs_with_tts_le_1_5, n_runs),
        "greeting_ttfb_le_2_0s_pct": _pct(runs_with_ttfb_le_2_0, n_runs),
    }

    # --------------- chart series (front-end ready) ---------------
    # bar: average duration by stage (top 10)
    stage_avg_bar = sorted(
        [
            {
                "stage": st,
                "avg_ms": stage_stats[st]["avg"] * 1000.0,
                "count": stage_stats[st]["count"],
            }
            for st in stage_stats
        ],
        key=lambda x: x["avg_ms"],
        reverse=True,
    )[:10]

    # bar: average tts:synthesis by voice
    voice_avg_bar = sorted(
        [
            {
                "voice": v,
                "avg_ms": voice_stats[v]["avg"] * 1000.0,
                "count": voice_stats[v]["count"],
            }
            for v in voice_stats
        ],
        key=lambda x: x["avg_ms"],
        reverse=True,
    )

    # bar: agent stage averages
    agent_avg_bar = sorted(
        [
            {
                "agent_stage": a,
                "avg_ms": agent_stats[a]["avg"] * 1000.0,
                "count": agent_stats[a]["count"],
            }
            for a in agent_stats
        ],
        key=lambda x: x["avg_ms"],
        reverse=True,
    )

    # line-ish series: per run tts maxima (ms) in order
    tts_per_run_series = [
        {
            "run_id": r["run_id"],
            "max_single_ms": r["tts"]["max_single"] * 1000.0,
            "sum_ms": r["tts"]["sum"] * 1000.0,
        }
        for r in per_run_summary
    ]

    # --------------- result ----------------
    return {
        "stage_stats": stage_stats,
        "agent_stats": agent_stats,
        "voice_stats": voice_stats,
        "per_run": per_run_summary,
        "sla": sla,
        "threshold_breaches": dict(threshold_breaches),
        "charts": {
            # 👇 at least one bar chart dataset for your FE
            "bar_stage_avg": stage_avg_bar,
            "bar_voice_synth_avg": voice_avg_bar,
            "bar_agent_stage_avg": agent_avg_bar,
            "series_tts_per_run": tts_per_run_series,
        },
        "meta": {
            "current_run_id": payload.get("current_run_id"),
            "order": order,
            "thresholds": stage_thresholds,
        },
    }
