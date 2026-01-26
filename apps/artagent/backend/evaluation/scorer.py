"""
Metrics Scorer
==============

Computes evaluation metrics from recorded events.

Metrics computed:
- Tool calls: precision, recall, efficiency
- Groundedness: grounded span ratio, unsupported claims
- Latency: E2E percentiles, TTFT
- Verbosity: token budget compliance (API-aware)
- Handoffs: routing accuracy
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np

from apps.artagent.backend.evaluation.schemas import (
    RunSummary,
    ScenarioExpectations,
    TurnEvent,
    TurnScore,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class MetricsScorer:
    """
    Computes evaluation metrics from TurnEvent records.

    Design principles:
    - Stateless: Each method is pure function
    - Flexible: Works with or without scenario expectations
    - API-aware: Adjusts budgets for Chat vs Responses API
    - Cheap: Uses string matching for groundedness (LLM judge optional)
    """

    def __init__(self):
        """Initialize scorer."""
        self.logger = logger

    # =========================================================================
    # TOOL CALL METRICS
    # =========================================================================

    def compute_tool_precision(
        self,
        actual_calls: List[str],
        expected_calls: List[str],
    ) -> float:
        """
        Compute tool call precision.

        precision = executed_expected / executed_total

        Args:
            actual_calls: List of tool names that were called
            expected_calls: List of tool names that should be called

        Returns:
            Precision score (0.0 to 1.0)
        """
        if not actual_calls:
            return 1.0  # No false positives

        executed_expected = len(set(actual_calls) & set(expected_calls))
        return executed_expected / len(actual_calls)

    def compute_tool_recall(
        self,
        actual_calls: List[str],
        expected_calls: List[str],
    ) -> float:
        """
        Compute tool call recall.

        recall = executed_expected / expected_total

        Args:
            actual_calls: List of tool names that were called
            expected_calls: List of tool names that should be called

        Returns:
            Recall score (0.0 to 1.0)
        """
        if not expected_calls:
            return 1.0  # No expectations to miss

        executed_expected = len(set(actual_calls) & set(expected_calls))
        return executed_expected / len(expected_calls)

    def compute_tool_efficiency(self, turn: TurnEvent) -> float:
        """
        Compute tool call efficiency (penalize redundant calls).

        efficiency = 1 - (redundant_calls / total_calls)

        Redundant = same tool+args within 30s window.

        Args:
            turn: TurnEvent with tool calls

        Returns:
            Efficiency score (0.0 to 1.0)
        """
        if not turn.tool_calls:
            return 1.0

        seen: Dict[str, float] = {}  # (tool_name, args_hash) -> timestamp
        redundant = 0

        for tc in turn.tool_calls:
            # Hash arguments for deduplication
            args_hash = hashlib.sha256(
                str(sorted(tc.arguments.items())).encode()
            ).hexdigest()[:16]

            key = f"{tc.name}:{args_hash}"

            if key in seen and (tc.start_ts - seen[key]) < 30:
                redundant += 1

            seen[key] = tc.start_ts

        return 1.0 - (redundant / len(turn.tool_calls))

    # =========================================================================
    # GROUNDEDNESS METRICS (Cheap String Matching)
    # =========================================================================

    def extract_factual_spans(self, text: str) -> Set[str]:
        """
        Extract factual spans from text using regex heuristics.

        Extracts:
        - Numbers (amounts, IDs, dates)
        - Dates (MM/DD/YYYY, Month DD, YYYY)
        - Proper nouns (capitalized sequences)

        Args:
            text: Text to extract spans from

        Returns:
            Set of factual span strings
        """
        spans: Set[str] = set()

        # Numbers (amounts, IDs, dates)
        spans.update(re.findall(r'\$?[\d,]+\.?\d*', text))

        # Dates (simple patterns)
        spans.update(re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text))
        spans.update(
            re.findall(
                r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b',
                text,
            )
        )

        # Proper nouns (capitalized sequences)
        # Filter out common words to reduce noise
        common_words = {'I', 'The', 'A', 'An', 'This', 'That', 'These', 'Those'}
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        spans.update(pn for pn in proper_nouns if pn not in common_words)

        return spans

    def compute_groundedness(
        self,
        turn: TurnEvent,
    ) -> Dict[str, Any]:
        """
        Compute groundedness score using cheap string matching.

        Checks if factual spans in response appear in:
        - Tool outputs (from evidence_blobs)
        - Context data (caller_name, customer_intelligence, etc.)

        Args:
            turn: TurnEvent with response and evidence

        Returns:
            Dict with:
            - grounded_span_ratio: fraction of spans found in evidence
            - unsupported_claim_count: count of spans NOT found
            - total_spans: total factual spans extracted
        """
        spans = self.extract_factual_spans(turn.response_text)

        if not spans:
            return {
                "grounded_span_ratio": 1.0,
                "unsupported_claim_count": 0,
                "total_spans": 0,
            }

        # Build evidence corpus
        evidence_text = " ".join(blob.content_excerpt for blob in turn.evidence_blobs)

        # Check each span
        grounded_count = 0
        for span in spans:
            if span.lower() in evidence_text.lower():
                grounded_count += 1

        return {
            "grounded_span_ratio": grounded_count / len(spans),
            "unsupported_claim_count": len(spans) - grounded_count,
            "total_spans": len(spans),
        }

    # =========================================================================
    # LATENCY METRICS
    # =========================================================================

    def compute_latency_metrics(self, turns: List[TurnEvent]) -> Dict[str, float]:
        """
        Compute latency percentiles across turns.

        Args:
            turns: List of TurnEvents

        Returns:
            Dict with p50/p95/p99 for e2e and ttft
        """
        e2e_times = [t.e2e_ms for t in turns if t.e2e_ms is not None]
        ttft_times = [t.ttft_ms for t in turns if t.ttft_ms is not None]

        metrics = {}

        if e2e_times:
            metrics["e2e_p50_ms"] = float(np.percentile(e2e_times, 50))
            metrics["e2e_p95_ms"] = float(np.percentile(e2e_times, 95))
            metrics["e2e_p99_ms"] = float(np.percentile(e2e_times, 99))
            metrics["e2e_mean_ms"] = float(np.mean(e2e_times))

        if ttft_times:
            metrics["ttft_p50_ms"] = float(np.percentile(ttft_times, 50))
            metrics["ttft_p95_ms"] = float(np.percentile(ttft_times, 95))
            metrics["ttft_mean_ms"] = float(np.mean(ttft_times))

        return metrics

    # =========================================================================
    # VERBOSITY METRICS (API-Aware)
    # =========================================================================

    def compute_verbosity_score(
        self,
        turn: TurnEvent,
        budget: int = 150,
    ) -> Dict[str, Any]:
        """
        Compute verbosity score with API-aware budget adjustments.

        For Responses API:
        - verbosity=0: 30% smaller budget
        - verbosity=2: 50% larger budget

        For reasoning models (o1/o3/o4):
        - include_reasoning=true: 2x budget

        Args:
            turn: TurnEvent with response tokens
            budget: Base token budget (default: 150)

        Returns:
            Dict with tokens, budget, violation, score
        """
        response_tokens = turn.response_tokens or len(turn.response_text.split())
        endpoint = turn.eval_model_config.endpoint_used

        # Adjust budget for Responses API verbosity
        if endpoint == "responses":
            # Use 'is not None' check to avoid treating 0 as falsy
            verbosity_level = (
                turn.eval_model_config.verbosity
                if turn.eval_model_config.verbosity is not None
                else 1
            )
            if verbosity_level == 0:
                budget = int(budget * 0.7)  # 30% reduction for minimal mode
            elif verbosity_level == 2:
                budget = int(budget * 1.5)  # 50% increase for detailed mode

        # Adjust for reasoning models
        model_family = turn.eval_model_config.model_family
        if model_family in ["o1", "o3", "o4"]:
            include_reasoning = turn.eval_model_config.include_reasoning or False
            if include_reasoning:
                budget = int(budget * 2.0)  # 2x budget for reasoning tokens

        violation = max(0, response_tokens - budget)

        return {
            "tokens": response_tokens,
            "budget": budget,
            "violation": violation,
            "score": 1.0 - min(violation / budget, 1.0) if budget > 0 else 0.0,
            "api_adjusted": endpoint == "responses",
        }

    # =========================================================================
    # HANDOFF METRICS
    # =========================================================================

    def compute_handoff_accuracy(
        self,
        turns: List[TurnEvent],
        expected_handoffs: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Compute handoff routing accuracy.

        Args:
            turns: List of TurnEvents
            expected_handoffs: Optional list of expected handoffs
                [{"from": "Concierge", "to": "FraudAgent"}, ...]

        Returns:
            Dict with total_handoffs, correct_handoffs, accuracy
        """
        handoffs = [t.handoff for t in turns if t.handoff is not None]

        if not expected_handoffs:
            return {
                "total_handoffs": len(handoffs),
                "correct_handoffs": None,
                "handoff_accuracy": None,
            }

        correct = 0
        for expected in expected_handoffs:
            for handoff in handoffs:
                if (
                    handoff.source_agent == expected["from"]
                    and handoff.target_agent == expected["to"]
                ):
                    correct += 1
                    break

        return {
            "total_handoffs": len(handoffs),
            "correct_handoffs": correct,
            "handoff_accuracy": correct / len(expected_handoffs) if expected_handoffs else None,
        }

    # =========================================================================
    # COST TRACKING
    # =========================================================================

    def compute_cost_analysis(self, turns: List[TurnEvent]) -> Dict[str, Any]:
        """
        Compute cost analysis across turns.

        Args:
            turns: List of TurnEvents

        Returns:
            Dict with total tokens, estimated cost, breakdown by model
        """
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        model_breakdown: Dict[str, Dict[str, Any]] = {}

        # Simple pricing (update with actual pricing)
        pricing = {
            "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
            "gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.06},
            "o1-preview": {
                "input_per_1k": 0.015,
                "output_per_1k": 0.06,
                "reasoning_per_1k": 0.06,
            },
            "default": {"input_per_1k": 0.005, "output_per_1k": 0.015},
        }

        for turn in turns:
            input_tok = turn.input_tokens or 0
            output_tok = turn.response_tokens or 0
            reasoning_tok = turn.reasoning_tokens or 0

            total_input_tokens += input_tok
            total_output_tokens += output_tok
            total_reasoning_tokens += reasoning_tok

            model_name = turn.eval_model_config.model_name
            endpoint = turn.eval_model_config.endpoint_used

            if model_name not in model_breakdown:
                model_breakdown[model_name] = {
                    "endpoint": endpoint,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost_usd": 0.0,
                }

            breakdown = model_breakdown[model_name]
            breakdown["input_tokens"] += input_tok
            breakdown["output_tokens"] += output_tok
            breakdown["reasoning_tokens"] += reasoning_tok

            # Get pricing for this model
            model_pricing = pricing.get(model_name, pricing["default"])
            breakdown["cost_usd"] += (
                (input_tok / 1000) * model_pricing.get("input_per_1k", 0)
                + (output_tok / 1000) * model_pricing.get("output_per_1k", 0)
                + (reasoning_tok / 1000) * model_pricing.get("reasoning_per_1k", 0)
            )

        total_cost = sum(b["cost_usd"] for b in model_breakdown.values())

        return {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "reasoning_tokens": total_reasoning_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            "model_breakdown": model_breakdown,
        }

    # =========================================================================
    # AGGREGATE SCORING
    # =========================================================================

    def score_turn(
        self,
        turn: TurnEvent,
        expectations: Optional[ScenarioExpectations] = None,
    ) -> TurnScore:
        """
        Score a single turn.

        Args:
            turn: TurnEvent to score
            expectations: Optional expectations for validation

        Returns:
            TurnScore with all computed metrics
        """
        # Tool metrics
        actual_tools = [tc.name for tc in turn.tool_calls]
        expected_tools = expectations.tools_called if expectations else []

        tool_precision = self.compute_tool_precision(actual_tools, expected_tools)
        tool_recall = self.compute_tool_recall(actual_tools, expected_tools)
        tool_efficiency = self.compute_tool_efficiency(turn)

        # Groundedness
        groundedness = self.compute_groundedness(turn)

        # Verbosity
        budget = 150
        if expectations and expectations.response_constraints:
            budget = expectations.response_constraints.get("max_tokens", 150)

        verbosity = self.compute_verbosity_score(turn, budget)

        return TurnScore(
            turn_id=turn.turn_id,
            tool_precision=tool_precision,
            tool_recall=tool_recall,
            tool_efficiency=tool_efficiency,
            grounded_span_ratio=groundedness["grounded_span_ratio"],
            unsupported_claim_count=groundedness["unsupported_claim_count"],
            e2e_ms=turn.e2e_ms,
            ttft_ms=turn.ttft_ms,
            verbosity_score=verbosity["score"],
            verbosity_tokens=verbosity["tokens"],
            verbosity_budget=verbosity["budget"],
        )

    def generate_summary(
        self,
        turns: List[TurnEvent],
        scenario_name: Optional[str] = None,
        expectations: Optional[Dict[str, Any]] = None,
    ) -> RunSummary:
        """
        Generate summary of all turns.

        Args:
            turns: List of TurnEvents
            scenario_name: Optional scenario name
            expectations: Optional scenario expectations dict

        Returns:
            RunSummary with aggregated metrics
        """
        if not turns:
            raise ValueError("No turns to score")

        # Score all turns
        scores = [self.score_turn(turn) for turn in turns]

        # Aggregate tool metrics
        tool_metrics = {
            "total_calls": sum(len(t.tool_calls) for t in turns),
            "precision": float(np.mean([s.tool_precision for s in scores])),
            "recall": float(np.mean([s.tool_recall for s in scores])),
            "efficiency": float(np.mean([s.tool_efficiency for s in scores])),
            "redundant_calls": sum(
                int((1 - s.tool_efficiency) * len(t.tool_calls))
                for s, t in zip(scores, turns)
            ),
        }

        # Aggregate latency
        latency_metrics = self.compute_latency_metrics(turns)

        # Aggregate groundedness
        groundedness_metrics = {
            "avg_grounded_span_ratio": float(
                np.mean([s.grounded_span_ratio for s in scores])
            ),
            "avg_unsupported_claims": float(
                np.mean([s.unsupported_claim_count for s in scores])
            ),
        }

        # Aggregate verbosity
        verbosity_metrics = {
            "avg_response_tokens": float(
                np.mean([s.verbosity_tokens for s in scores])
            ),
            "budget_per_turn": scores[0].verbosity_budget if scores else 150,
            "budget_violations": sum(1 for s in scores if s.verbosity_score < 1.0),
        }

        # Handoff metrics
        handoff_metrics = self.compute_handoff_accuracy(turns, None)

        # Cost analysis
        cost_analysis = self.compute_cost_analysis(turns)

        # Get first turn's config for summary
        first_turn = turns[0]

        return RunSummary(
            run_id=first_turn.session_id,
            scenario_name=scenario_name or first_turn.scenario_name or "unknown",
            agent_name=first_turn.agent_name,
            total_turns=len(turns),
            eval_model_config=first_turn.eval_model_config,
            tool_metrics=tool_metrics,
            latency_metrics=latency_metrics,
            groundedness_metrics=groundedness_metrics,
            verbosity_metrics=verbosity_metrics,
            handoff_metrics=handoff_metrics,
            cost_analysis=cost_analysis,
            commit_sha=first_turn.commit_sha,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    # =========================================================================
    # FILE I/O
    # =========================================================================

    def load_events(self, events_path: Path) -> List[TurnEvent]:
        """
        Load events from JSONL file.

        Args:
            events_path: Path to events.jsonl

        Returns:
            List of TurnEvent objects
        """
        events = []
        with open(events_path) as f:
            for line in f:
                if line.strip():
                    events.append(TurnEvent.model_validate_json(line))

        logger.info(f"Loaded {len(events)} events from {events_path}")
        return events

    # =========================================================================
    # COMPARISON UTILITIES
    # =========================================================================

    def compare_summaries(
        self,
        summaries: Dict[str, RunSummary],
        metrics: List[str] | None = None,
    ) -> dict[str, Any]:
        """
        Compare multiple run summaries (for A/B testing).

        Args:
            summaries: Dict mapping variant_id -> RunSummary
            metrics: List of metric names to compare (optional)

        Returns:
            Comparison report with winners per metric
        """
        if not summaries:
            raise ValueError("Must provide at least one summary to compare")

        if len(summaries) < 2:
            logger.warning("Comparison with < 2 variants is not meaningful")

        # Default metrics to compare
        if metrics is None:
            metrics = [
                "tool_precision",
                "tool_recall",
                "latency_p95_ms",
                "cost_per_turn_usd",
                "grounded_span_ratio",
            ]

        # Build comparison report
        report: dict[str, Any] = {
            "variants": {},
            "winners": {},
            "deltas": {},
        }

        # Extract metrics for each variant
        for variant_id, summary in summaries.items():
            cost_per_turn = (
                summary.cost_analysis["estimated_cost_usd"] / summary.total_turns
                if summary.total_turns > 0
                else 0
            )

            report["variants"][variant_id] = {
                "scenario_name": summary.scenario_name,
                "model_config": summary.eval_model_config.model_dump() if summary.eval_model_config else {},
                "metrics": {
                    "tool_precision": summary.tool_metrics.get("precision", 0),
                    "tool_recall": summary.tool_metrics.get("recall", 0),
                    "tool_efficiency": summary.tool_metrics.get("efficiency", 0),
                    "latency_p50_ms": summary.latency_metrics.get("e2e_p50_ms", 0),
                    "latency_p95_ms": summary.latency_metrics.get("e2e_p95_ms", 0),
                    "grounded_span_ratio": summary.groundedness_metrics.get("avg_grounded_span_ratio", 0),
                    "cost_per_turn_usd": cost_per_turn,
                    "total_cost_usd": summary.cost_analysis.get("estimated_cost_usd", 0),
                },
            }

        # Determine winners for each metric
        for metric in metrics:
            values = {}
            for variant_id in summaries.keys():
                values[variant_id] = report["variants"][variant_id]["metrics"].get(metric, 0)

            if not values:
                continue

            # Lower is better for latency and cost
            if "latency" in metric or "cost" in metric:
                winner = min(values.keys(), key=lambda k: values[k])
                best_value = min(values.values())
                worst_value = max(values.values())
            else:
                # Higher is better for precision, recall, etc.
                winner = max(values.keys(), key=lambda k: values[k])
                best_value = max(values.values())
                worst_value = min(values.values())

            report["winners"][metric] = {
                "variant": winner,
                "value": values[winner],
            }

            # Calculate delta (improvement) vs worst
            if worst_value != 0:
                if "latency" in metric or "cost" in metric:
                    # For metrics where lower is better
                    pct_improvement = ((worst_value - best_value) / worst_value) * 100
                else:
                    # For metrics where higher is better
                    pct_improvement = ((best_value - worst_value) / worst_value) * 100

                report["deltas"][metric] = {
                    "best_value": best_value,
                    "worst_value": worst_value,
                    "improvement_pct": round(pct_improvement, 1),
                }

        return report

    def print_comparison(self, comparison: dict[str, Any]):
        """
        Pretty-print comparison report.

        Args:
            comparison: Report from compare_summaries()
        """
        print("\n" + "=" * 70)
        print("📊 A/B COMPARISON REPORT")
        print("=" * 70)

        # Print each variant
        for variant_id, data in comparison["variants"].items():
            print(f"\n{variant_id}:")
            print(f"  Model: {data['model_config'].get('model_name', 'unknown')}")
            metrics = data["metrics"]
            print(f"  Precision:    {metrics['tool_precision']:.2%}")
            print(f"  Recall:       {metrics['tool_recall']:.2%}")
            print(f"  Latency P95:  {metrics['latency_p95_ms']:.0f}ms")
            print(f"  Cost/turn:    ${metrics['cost_per_turn_usd']:.4f}")
            print(f"  Grounded:     {metrics['grounded_span_ratio']:.2%}")

        # Print winners
        if comparison["winners"]:
            print("\n🏆 Winners:")
            for metric, info in comparison["winners"].items():
                variant = info["variant"]
                value = info["value"]

                # Format value based on metric type
                if "pct" in metric or "precision" in metric or "recall" in metric or "ratio" in metric:
                    value_str = f"{value:.2%}"
                elif "cost" in metric:
                    value_str = f"${value:.4f}"
                elif "latency" in metric or "ms" in metric:
                    value_str = f"{value:.0f}ms"
                else:
                    value_str = f"{value:.2f}"

                print(f"  {metric}: {variant} ({value_str})")

        # Print deltas
        if comparison["deltas"]:
            print("\n📈 Improvements:")
            for metric, delta in comparison["deltas"].items():
                pct = delta["improvement_pct"]
                if pct > 0:
                    print(f"  {metric}: {pct:.1f}% better")

        print("=" * 70 + "\n")


__all__ = ["MetricsScorer"]
