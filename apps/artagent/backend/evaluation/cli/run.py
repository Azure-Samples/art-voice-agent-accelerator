#!/usr/bin/env python3
"""
Evaluation CLI - Score Events
==============================

Score recorded events from JSONL file.

Usage:
    python -m apps.artagent.backend.evaluation.cli.run --input runs/test_001_events.jsonl

    # With scenario expectations
    python -m apps.artagent.backend.evaluation.cli.run \
        --input runs/test_001_events.jsonl \
        --scenario tests/eval_scenarios/fraud_detection_basic.yaml

    # Custom output directory
    python -m apps.artagent.backend.evaluation.cli.run \
        --input runs/test_001_events.jsonl \
        --output runs/test_001

Output:
    - <output_dir>/scores.jsonl  (per-turn scores)
    - <output_dir>/summary.json  (aggregated metrics)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

from apps.artagent.backend.evaluation.schemas import ScenarioExpectations
from apps.artagent.backend.evaluation.scorer import MetricsScorer
from utils.ml_logging import get_logger

logger = get_logger(__name__)


def load_scenario_expectations(
    scenario_path: Path,
) -> tuple[Optional[str], Optional[dict]]:
    """
    Load scenario YAML and extract expectations.

    Args:
        scenario_path: Path to scenario YAML file

    Returns:
        Tuple of (scenario_name, expectations_dict)
    """
    try:
        with open(scenario_path) as f:
            scenario = yaml.safe_load(f)

        scenario_name = scenario.get("scenario_name")
        # Expectations are per-turn, so we'll return the full scenario
        # and let the scorer match them up
        return scenario_name, scenario

    except Exception as e:
        logger.warning(f"Failed to load scenario: {e}")
        return None, None


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Score evaluation events from JSONL file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to events.jsonl file",
    )

    parser.add_argument(
        "--scenario",
        "-s",
        type=Path,
        help="Optional path to scenario YAML (for expectations)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: same as input file parent)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Validate input file exists
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        output_dir = args.input.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load scenario expectations if provided
    scenario_name = None
    scenario_data = None
    if args.scenario:
        scenario_name, scenario_data = load_scenario_expectations(args.scenario)
        if scenario_name:
            logger.info(f"Loaded scenario: {scenario_name}")

    # Initialize scorer
    scorer = MetricsScorer()

    try:
        # Load events
        logger.info(f"Loading events from: {args.input}")
        events = scorer.load_events(args.input)

        if not events:
            logger.error("No events found in input file")
            sys.exit(1)

        logger.info(f"Loaded {len(events)} events")

        # Score each turn
        scores = []
        for event in events:
            # TODO: Match turn-specific expectations from scenario
            score = scorer.score_turn(event, expectations=None)
            scores.append(score)

            if args.verbose:
                logger.info(
                    f"Turn {score.turn_id}: "
                    f"precision={score.tool_precision:.2f} "
                    f"recall={score.tool_recall:.2f} "
                    f"grounded={score.grounded_span_ratio:.2f} "
                    f"e2e={score.e2e_ms:.1f}ms"
                )

        # Write scores.jsonl
        scores_path = output_dir / "scores.jsonl"
        with open(scores_path, "w") as f:
            for score in scores:
                f.write(score.model_dump_json() + "\n")

        logger.info(f"✅ Wrote {len(scores)} scores to: {scores_path}")

        # Generate summary
        summary = scorer.generate_summary(
            events,
            scenario_name=scenario_name,
            expectations=scenario_data,
        )

        # Write summary.json
        summary_path = output_dir / "summary.json"
        with open(summary_path, "w") as f:
            f.write(summary.model_dump_json(indent=2))

        logger.info(f"✅ Wrote summary to: {summary_path}")

        # Print summary to console
        print("\n" + "=" * 70)
        print(f"📊 EVALUATION SUMMARY: {summary.scenario_name}")
        print("=" * 70)
        print(f"\n🔧 Tool Metrics:")
        print(f"  Total calls: {summary.tool_metrics['total_calls']}")
        print(f"  Precision:   {summary.tool_metrics['precision']:.2%}")
        print(f"  Recall:      {summary.tool_metrics['recall']:.2%}")
        print(f"  Efficiency:  {summary.tool_metrics['efficiency']:.2%}")

        print(f"\n⏱️  Latency Metrics:")
        if "e2e_p50_ms" in summary.latency_metrics:
            print(f"  E2E P50:     {summary.latency_metrics['e2e_p50_ms']:.1f}ms")
            print(f"  E2E P95:     {summary.latency_metrics['e2e_p95_ms']:.1f}ms")
        if "ttft_p50_ms" in summary.latency_metrics:
            print(f"  TTFT P50:    {summary.latency_metrics['ttft_p50_ms']:.1f}ms")

        print(f"\n✓ Groundedness:")
        print(
            f"  Grounded span ratio: {summary.groundedness_metrics['avg_grounded_span_ratio']:.2%}"
        )
        print(
            f"  Unsupported claims:  {summary.groundedness_metrics['avg_unsupported_claims']:.1f} avg"
        )

        print(f"\n📝 Verbosity:")
        print(f"  Avg response tokens: {summary.verbosity_metrics['avg_response_tokens']:.0f}")
        print(f"  Budget per turn:     {summary.verbosity_metrics['budget_per_turn']}")
        print(f"  Budget violations:   {summary.verbosity_metrics['budget_violations']}")

        print(f"\n💰 Cost Analysis:")
        print(f"  Total input tokens:  {summary.cost_analysis['total_input_tokens']:,}")
        print(f"  Total output tokens: {summary.cost_analysis['total_output_tokens']:,}")
        print(f"  Estimated cost:      ${summary.cost_analysis['estimated_cost_usd']:.4f}")

        print("\n" + "=" * 70)
        print(f"✅ Evaluation complete!")
        print(f"   Scores:  {scores_path}")
        print(f"   Summary: {summary_path}")
        print("=" * 70 + "\n")

        return 0

    except Exception as e:
        logger.exception(f"❌ Error during evaluation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
