#!/usr/bin/env python3
"""
Evaluation CLI
==============

Simplified CLI for running evaluations.

Usage:
    # Run a scenario (auto-detects single vs A/B comparison)
    python -m tests.evaluation.cli run \
        --input tests/evaluation/scenarios/smoke/basic_identity_verification.yaml

    # Run A/B comparison (auto-detected from YAML)
    python -m tests.evaluation.cli run \
        --input tests/evaluation/scenarios/ab_tests/fraud_detection_comparison.yaml

    # Submit results to Azure AI Foundry
    python -m tests.evaluation.cli submit \
        --data runs/my_scenario/foundry_eval.jsonl
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
# Subcommand: run (unified scenario + comparison)
# =============================================================================


def cmd_run(args: argparse.Namespace) -> int:
    """Run scenario or A/B comparison (auto-detected from YAML)."""
    import yaml
    from tests.evaluation.scenario_runner import ScenarioRunner, ComparisonRunner

    # Validate input
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    # Load YAML to determine type
    with open(args.input, encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)

    is_comparison = "variants" in scenario_data

    try:
        if is_comparison:
            logger.info(f"Detected A/B comparison: {args.input.name}")
            runner = ComparisonRunner(
                comparison_path=args.input,
                output_dir=args.output,
            )
            results = asyncio.run(runner.run())
            logger.info(f"✅ Comparison complete: {len(results)} variants")
        else:
            logger.info(f"Running scenario: {args.input.name}")
            runner = ScenarioRunner(
                scenario_path=args.input,
                output_dir=args.output,
            )
            summary = asyncio.run(runner.run())
            logger.info(f"✅ Scenario complete: {summary.scenario_name}")

        return 0

    except Exception as e:
        logger.exception(f"❌ Error running evaluation: {e}")
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
        description="Evaluation CLI - Run scenarios and submit to Foundry",
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
    # Subcommand: run (auto-detects scenario vs comparison)
    # -------------------------------------------------------------------------
    run_parser = subparsers.add_parser(
        "run",
        help="Run scenario or A/B comparison (auto-detected from YAML)",
    )
    run_parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to scenario or comparison YAML file",
    )
    run_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: runs/)",
    )
    run_parser.set_defaults(func=cmd_run)

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
