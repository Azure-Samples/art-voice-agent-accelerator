#!/usr/bin/env python3
"""
Evaluation CLI
==============

Unified CLI for running evaluations with subcommands.

Usage:
    # Score existing events
    python -m tests.evaluation.cli score \
        --input runs/test_001_events.jsonl

    # Run a single scenario
    python -m tests.evaluation.cli scenario \
        --input tests/eval_scenarios/fraud_basic.yaml

    # Run A/B comparison
    python -m tests.evaluation.cli compare \
        --input tests/eval_scenarios/ab_tests/fraud_detection_comparison.yaml

Consolidation:
    This replaces multiple separate CLI files with a single entry point.
    Much simpler to maintain and use.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from utils.ml_logging import get_logger

logger = get_logger(__name__)


def _bootstrap_runtime(verbose: bool = False) -> dict[str, str | bool | None]:
    """Mirror runtime config loading for evaluations."""

    status: dict[str, str | bool | None] = {"env_file": None, "appconfig": False}

    try:
        from apps.artagent.backend.lifecycle import bootstrap as lifecycle_bootstrap
        from config.appconfig_provider import bootstrap_appconfig, get_provider_status
    except Exception as exc:  # noqa: BLE001 - narrow scope and continue
        logger.warning("Bootstrap modules unavailable: %s", exc)
        return status

    try:
        env_file = lifecycle_bootstrap.load_environment()
        status["env_file"] = str(env_file) if env_file else None
        logger.info("Environment loaded from %s", env_file or "ambient environment")
    except Exception as exc:  # noqa: BLE001 - fallback to ambient env
        logger.warning("Environment load skipped: %s", exc)

    try:
        # Use provider directly to respect "enabled" flag and return value
        appconfig_loaded = bootstrap_appconfig()
        provider_status = get_provider_status()
        status["appconfig"] = appconfig_loaded and provider_status.get("loaded", False)

        if status["appconfig"]:
            logger.info(
                "App Config loaded | endpoint=%s label=%s",
                provider_status.get("endpoint"),
                provider_status.get("label"),
            )
        else:
            logger.info("App Config not configured; using environment variables")
    except Exception as exc:  # noqa: BLE001 - leave status as-is
        logger.warning("App Config load failed: %s", exc)

    return status


# =============================================================================
# Subcommand: score
# =============================================================================


def cmd_score(args: argparse.Namespace) -> int:
    """Score existing events from JSONL file."""
    from tests.evaluation.scorer import MetricsScorer

    # Validate input
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    # Determine output directory
    output_dir = args.output or args.input.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load scenario expectations if provided
    scenario_data = None
    scenario_name = None
    if args.scenario:
        import yaml
        with open(args.scenario, encoding="utf-8") as f:
            scenario_data = yaml.safe_load(f)
            scenario_name = scenario_data.get("scenario_name")
            logger.info(f"Loaded scenario: {scenario_name}")

    # Initialize scorer
    scorer = MetricsScorer()

    try:
        # Load and score events
        logger.info(f"Loading events from: {args.input}")
        events = scorer.load_events(args.input)

        if not events:
            logger.error("No events found in input file")
            return 1

        logger.info(f"Loaded {len(events)} events")

        # Score each turn
        scores = []
        for event in events:
            score = scorer.score_turn(event, expectations=None)
            scores.append(score)

            if args.verbose:
                logger.info(
                    f"Turn {score.turn_id}: "
                    f"precision={score.tool_precision:.2f} "
                    f"recall={score.tool_recall:.2f} "
                    f"e2e={score.e2e_ms:.1f}ms"
                )

        # Write scores
        scores_path = output_dir / "scores.jsonl"
        with open(scores_path, "w", encoding="utf-8") as f:
            for score in scores:
                f.write(score.model_dump_json() + "\n")

        logger.info(f"✅ Wrote scores to: {scores_path}")

        # Generate and write summary
        summary = scorer.generate_summary(
            events,
            scenario_name=scenario_name,
            expectations=scenario_data,
        )

        summary_path = output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary.model_dump_json(indent=2))

        logger.info(f"✅ Wrote summary to: {summary_path}")

        # Print summary
        print("\n" + "=" * 70)
        print(f"📊 EVALUATION SUMMARY: {summary.scenario_name}")
        print("=" * 70)
        print(f"\n🔧 Tool Metrics:")
        print(f"  Precision:   {summary.tool_metrics['precision']:.2%}")
        print(f"  Recall:      {summary.tool_metrics['recall']:.2%}")
        print(f"  Efficiency:  {summary.tool_metrics['efficiency']:.2%}")
        print(f"\n⏱️  Latency P95: {summary.latency_metrics.get('e2e_p95_ms', 0):.1f}ms")
        print(f"💰 Total Cost: ${summary.cost_analysis['estimated_cost_usd']:.4f}")
        print("=" * 70 + "\n")

        return 0

    except Exception as e:
        logger.exception(f"❌ Error during scoring: {e}")
        return 1


# =============================================================================
# Subcommand: scenario
# =============================================================================


def cmd_scenario(args: argparse.Namespace) -> int:
    """Run a single scenario from YAML."""
    from tests.evaluation.scenario_runner import ScenarioRunner

    try:
        runner = ScenarioRunner(
            scenario_path=args.input,
            output_dir=args.output,
        )

        # Run scenario (async)
        summary = asyncio.run(runner.run())

        logger.info(f"✅ Scenario complete: {summary.scenario_name}")
        return 0

    except NotImplementedError as e:
        logger.error(f"❌ {e}")
        logger.error(
            "NOTE: Scenario runner requires integration with the orchestrator. "
            "This will be implemented when connecting to the real system."
        )
        return 1

    except Exception as e:
        logger.exception(f"❌ Error running scenario: {e}")
        return 1


# =============================================================================
# Subcommand: compare
# =============================================================================


def cmd_compare(args: argparse.Namespace) -> int:
    """Run A/B comparison from YAML."""
    from tests.evaluation.scenario_runner import ComparisonRunner

    try:
        runner = ComparisonRunner(
            comparison_path=args.input,
            output_dir=args.output,
        )

        # Run comparison (async)
        results = asyncio.run(runner.run())

        logger.info(f"✅ Comparison complete: {len(results)} variants")
        return 0

    except NotImplementedError as e:
        logger.error(f"❌ {e}")
        logger.error(
            "NOTE: Comparison runner requires integration with the orchestrator. "
            "This will be implemented when connecting to the real system."
        )
        return 1

    except Exception as e:
        logger.exception(f"❌ Error running comparison: {e}")
        return 1


# =============================================================================
# Subcommand: submit (Foundry cloud evaluation)
# =============================================================================


def cmd_submit(args: argparse.Namespace) -> int:
    """Submit evaluation to Azure AI Foundry for cloud evaluation."""
    from tests.evaluation.foundry_exporter import submit_to_foundry_sync

    try:
        # Find data and config files
        data_path = args.data
        config_path = args.config

        # If data_path is a directory, look for foundry_eval.jsonl
        if data_path.is_dir():
            jsonl_files = list(data_path.glob("**/foundry_eval.jsonl"))
            if not jsonl_files:
                logger.error(f"❌ No foundry_eval.jsonl found in {data_path}")
                return 1
            data_path = jsonl_files[0]
            logger.info(f"Found data file: {data_path}")

        # If config not provided, look for it next to data file
        if not config_path:
            potential_config = data_path.parent / "foundry_evaluators.json"
            if potential_config.exists():
                config_path = potential_config
                logger.info(f"Found config file: {config_path}")

        # Submit to Foundry
        result = submit_to_foundry_sync(
            data_path=data_path,
            evaluators_config_path=config_path,
            project_endpoint=args.endpoint,
            dataset_name=args.dataset_name,
            evaluation_name=args.evaluation_name,
            model_deployment_name=args.model_deployment,
        )

        print("\n" + "=" * 60)
        print("🚀 FOUNDRY EVALUATION COMPLETE")
        print("=" * 60)
        print(f"  Name:           {result['evaluation_name']}")
        print(f"  Status:         {result['status']}")
        print(f"  Rows Evaluated: {result['rows_evaluated']}")
        print(f"  Output Path:    {result['output_path']}")
        print(f"\n  Metrics:")
        for metric, value in result.get('metrics', {}).items():
            if isinstance(value, float):
                print(f"    {metric}: {value:.3f}")
            else:
                print(f"    {metric}: {value}")
        if result.get('studio_url'):
            print(f"\n  🔗 AI Foundry Studio URL:")
            print(f"     {result['studio_url']}")
        print("=" * 60 + "\n")

        return 0

    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        return 1

    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        return 1

    except Exception as e:
        logger.exception(f"❌ Error submitting to Foundry: {e}")
        return 1


# =============================================================================
# Main CLI
# =============================================================================


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluation CLI - Score events, run scenarios, and compare models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        required=True,
    )

    # -------------------------------------------------------------------------
    # Subcommand: score
    # -------------------------------------------------------------------------
    score_parser = subparsers.add_parser(
        "score",
        help="Score existing events from JSONL file",
    )
    score_parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to events.jsonl file",
    )
    score_parser.add_argument(
        "--scenario",
        "-s",
        type=Path,
        help="Optional scenario YAML (for expectations)",
    )
    score_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: same as input)",
    )
    score_parser.set_defaults(func=cmd_score)

    # -------------------------------------------------------------------------
    # Subcommand: scenario
    # -------------------------------------------------------------------------
    scenario_parser = subparsers.add_parser(
        "scenario",
        help="Run a single scenario from YAML",
    )
    scenario_parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to scenario YAML file",
    )
    scenario_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: runs/)",
    )
    scenario_parser.set_defaults(func=cmd_scenario)

    # -------------------------------------------------------------------------
    # Subcommand: compare
    # -------------------------------------------------------------------------
    compare_parser = subparsers.add_parser(
        "compare",
        help="Run A/B comparison from YAML",
    )
    compare_parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to comparison YAML file",
    )
    compare_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: runs/)",
    )
    compare_parser.set_defaults(func=cmd_compare)

    # -------------------------------------------------------------------------
    # Subcommand: submit (Foundry cloud evaluation)
    # -------------------------------------------------------------------------
    submit_parser = subparsers.add_parser(
        "submit",
        help="Submit evaluation data to Azure AI Foundry for cloud evaluation",
    )
    submit_parser.add_argument(
        "--data",
        "-d",
        required=True,
        type=Path,
        help="Path to foundry_eval.jsonl file or directory containing it",
    )
    submit_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to foundry_evaluators.json (optional, auto-detected if next to data)",
    )
    submit_parser.add_argument(
        "--endpoint",
        "-e",
        type=str,
        help="Azure AI Foundry project endpoint (default: AZURE_AI_FOUNDRY_PROJECT_ENDPOINT from config)",
    )
    submit_parser.add_argument(
        "--dataset-name",
        type=str,
        help="Name for the uploaded dataset (default: auto-generated)",
    )
    submit_parser.add_argument(
        "--evaluation-name",
        type=str,
        help="Name for the evaluation run (default: auto-generated)",
    )
    submit_parser.add_argument(
        "--model-deployment",
        "-m",
        type=str,
        default="gpt-4o",
        help="Model deployment for AI-based evaluators (default: gpt-4o)",
    )
    submit_parser.set_defaults(func=cmd_submit)

    # Parse and execute
    args = parser.parse_args()

    # Ensure environment/App Config match runtime pipeline before loading orchestrator
    _bootstrap_runtime(verbose=args.verbose)

    # Execute subcommand
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
