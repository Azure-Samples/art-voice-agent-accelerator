"""
Scenario Runner
===============

Runs evaluation scenarios from YAML files.

Design principles:
- Simple and focused - just load YAML and run turns
- Delegates to existing components (EventRecorder, Wrapper, Scorer)
- No duplication of orchestrator logic
- Supports both single scenarios and A/B comparisons
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from apps.artagent.backend.evaluation.mocks import MockMemoManager, build_context
from apps.artagent.backend.evaluation.recorder import EventRecorder
from apps.artagent.backend.evaluation.schemas import RunSummary
from apps.artagent.backend.evaluation.scorer import MetricsScorer
from apps.artagent.backend.evaluation.wrappers import EvaluationOrchestratorWrapper
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class ScenarioRunner:
    """
    Runs evaluation scenarios from YAML files.

    Handles:
    - Loading YAML scenario definitions
    - Setting up mock dependencies
    - Running multi-turn conversations
    - Delegating to EventRecorder for recording
    - Delegating to MetricsScorer for scoring
    """

    def __init__(
        self,
        scenario_path: Path,
        output_dir: Path | None = None,
    ):
        """
        Initialize scenario runner.

        Args:
            scenario_path: Path to YAML scenario file
            output_dir: Output directory for results (default: runs/)
        """
        self.scenario_path = scenario_path
        self.scenario = self._load_scenario(scenario_path)
        self.output_dir = output_dir or Path("runs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_scenario(self, path: Path) -> dict[str, Any]:
        """Load and validate scenario YAML."""
        logger.info(f"Loading scenario from: {path}")

        with open(path) as f:
            scenario = yaml.safe_load(f)

        # Basic validation
        if "scenario_name" not in scenario:
            raise ValueError("Scenario must have 'scenario_name' field")

        if "turns" not in scenario:
            raise ValueError("Scenario must have 'turns' field")

        logger.info(f"Loaded scenario: {scenario['scenario_name']}")
        return scenario

    def _create_orchestrator(
        self,
        agent_name: str,
        model_override: dict[str, Any] | None = None,
    ):
        """
        Create orchestrator for scenario.

        NOTE: This is a placeholder. In real usage, you would:
        1. Load agent config from agentstore
        2. Apply model_override if provided
        3. Create CascadeOrchestratorAdapter

        For now, this returns a mock that can be wrapped by EvaluationOrchestratorWrapper.
        """
        # TODO: Implement real orchestrator creation
        # from apps.artagent.backend.registries.agentstore import get_agent
        # from apps.artagent.backend.voice.speech_cascade.orchestrator import CascadeOrchestratorAdapter
        #
        # agent_config = get_agent(agent_name)
        # if model_override:
        #     agent_config.model.update(model_override)
        #
        # return CascadeOrchestratorAdapter.create(...)

        raise NotImplementedError(
            "Orchestrator creation not yet implemented. "
            "This requires integration with the agent registry and orchestrator."
        )

    async def run(self) -> RunSummary:
        """
        Run the scenario and return summary.

        Returns:
            RunSummary with aggregated metrics
        """
        scenario_name = self.scenario["scenario_name"]
        agent_name = self.scenario.get("agent", "unknown")

        logger.info(f"Running scenario: {scenario_name}")

        # Create mock dependencies
        session_id = self.scenario.get("metadata", {}).get("session_id", f"eval_{scenario_name}")
        context_vars = self.scenario.get("metadata", {}).get("context", {})
        memo_manager = MockMemoManager(session_id, context_vars)

        # Create recorder
        run_id = f"{scenario_name}_{int(time.time())}"
        recorder = EventRecorder(run_id=run_id, output_dir=self.output_dir)

        # Create orchestrator (wrapped for recording)
        # NOTE: This will be implemented when we integrate with real orchestrator
        model_override = self.scenario.get("model_override")
        orchestrator = self._create_orchestrator(agent_name, model_override)
        eval_orchestrator = EvaluationOrchestratorWrapper(
            orchestrator=orchestrator,
            recorder=recorder,
        )

        # Run turns
        for turn_data in self.scenario["turns"]:
            turn_id = turn_data["turn_id"]
            user_input = turn_data["user_input"]

            logger.info(f"Turn {turn_id}: {user_input[:50]}...")

            # Build context
            context = build_context(
                session_id=session_id,
                user_text=user_input,
                turn_id=turn_id,
                conversation_history=memo_manager.get_history(agent_name),
                metadata={
                    "scenario_name": scenario_name,
                    **context_vars,
                },
            )

            # Run turn (this will be recorded automatically)
            result = await eval_orchestrator.process_turn(context)

            # Update conversation history
            memo_manager.append_to_history(agent_name, "user", user_input)
            memo_manager.append_to_history(agent_name, "assistant", result.response_text)

            logger.info(f"Turn {turn_id} complete: {len(result.response_text)} chars")

        # Score the results
        scorer = MetricsScorer()
        events = scorer.load_events(self.output_dir / f"{run_id}_events.jsonl")

        summary = scorer.generate_summary(
            events,
            scenario_name=scenario_name,
            expectations=self.scenario,
        )

        # Save summary
        summary_path = self.output_dir / run_id / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w") as f:
            f.write(summary.model_dump_json(indent=2))

        logger.info(f"Scenario complete! Summary: {summary_path}")

        return summary


class ComparisonRunner:
    """
    Runs A/B comparison scenarios.

    Handles scenarios with multiple variants (e.g., comparing GPT-4o vs o1).
    """

    def __init__(
        self,
        comparison_path: Path,
        output_dir: Path | None = None,
    ):
        """
        Initialize comparison runner.

        Args:
            comparison_path: Path to comparison YAML file
            output_dir: Output directory for results
        """
        self.comparison_path = comparison_path
        self.comparison = self._load_comparison(comparison_path)
        self.output_dir = output_dir or Path("runs")

    def _load_comparison(self, path: Path) -> dict[str, Any]:
        """Load and validate comparison YAML."""
        logger.info(f"Loading comparison from: {path}")

        with open(path) as f:
            comparison = yaml.safe_load(f)

        # Validate
        if "comparison_name" not in comparison:
            raise ValueError("Comparison must have 'comparison_name' field")

        if "variants" not in comparison:
            raise ValueError("Comparison must have 'variants' field")

        if len(comparison["variants"]) < 2:
            raise ValueError("Comparison must have at least 2 variants")

        logger.info(f"Loaded comparison: {comparison['comparison_name']}")
        return comparison

    async def run(self) -> dict[str, RunSummary]:
        """
        Run all variants and compare.

        Returns:
            Dict mapping variant_id -> RunSummary
        """
        comparison_name = self.comparison["comparison_name"]
        logger.info(f"Running comparison: {comparison_name}")

        # Create output directory for this comparison
        comparison_dir = self.output_dir / comparison_name
        comparison_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # Run each variant
        for variant in self.comparison["variants"]:
            variant_id = variant["variant_id"]
            logger.info(f"Running variant: {variant_id}")

            # Build scenario for this variant
            scenario = {
                "scenario_name": f"{comparison_name}_{variant_id}",
                "agent": variant.get("agent"),
                "model_override": variant.get("model_override"),
                "turns": self.comparison["turns"],
                "metadata": self.comparison.get("metadata", {}),
            }

            # Create temporary scenario file
            scenario_path = comparison_dir / f"{variant_id}_scenario.yaml"
            with open(scenario_path, "w") as f:
                yaml.dump(scenario, f)

            # Run scenario
            runner = ScenarioRunner(
                scenario_path=scenario_path,
                output_dir=comparison_dir / variant_id,
            )

            summary = await runner.run()
            results[variant_id] = summary

            logger.info(f"Variant {variant_id} complete")

        # Compare results
        logger.info("Comparing variants...")
        self._compare_variants(results, comparison_dir)

        return results

    def _compare_variants(
        self,
        results: dict[str, RunSummary],
        output_dir: Path,
    ):
        """
        Compare variant results and save comparison report.

        Args:
            results: Dict of variant_id -> RunSummary
            output_dir: Directory to save comparison
        """
        comparison_metrics = self.comparison.get("comparison_metrics", [])

        # Build comparison report
        report = {
            "comparison_name": self.comparison["comparison_name"],
            "variants": {},
            "comparison": {},
        }

        # Extract metrics for each variant
        for variant_id, summary in results.items():
            report["variants"][variant_id] = {
                "model_config": summary.model_config,
                "metrics": {
                    "tool_precision": summary.tool_metrics.get("precision", 0),
                    "tool_recall": summary.tool_metrics.get("recall", 0),
                    "latency_p95_ms": summary.latency_metrics.get("e2e_p95_ms", 0),
                    "cost_per_turn_usd": (
                        summary.cost_analysis.get("estimated_cost_usd", 0)
                        / summary.total_turns
                        if summary.total_turns > 0
                        else 0
                    ),
                },
            }

        # Determine winners for each metric
        if comparison_metrics:
            for metric in comparison_metrics:
                values = {
                    vid: report["variants"][vid]["metrics"].get(metric, 0)
                    for vid in results.keys()
                }

                # Lower is better for latency and cost
                if "latency" in metric or "cost" in metric:
                    winner = min(values.keys(), key=lambda k: values[k])
                else:
                    winner = max(values.keys(), key=lambda k: values[k])

                report["comparison"][f"winner_{metric}"] = winner

        # Save comparison report
        comparison_path = output_dir / "comparison.json"
        with open(comparison_path, "w") as f:
            import json
            json.dump(report, f, indent=2)

        logger.info(f"Comparison report saved: {comparison_path}")

        # Print summary
        print("\n" + "=" * 70)
        print(f"📊 COMPARISON: {self.comparison['comparison_name']}")
        print("=" * 70)

        for variant_id, data in report["variants"].items():
            print(f"\n{variant_id}:")
            print(f"  Model: {data['model_config'].get('model_name', 'unknown')}")
            print(f"  Precision: {data['metrics']['tool_precision']:.2%}")
            print(f"  Latency P95: {data['metrics']['latency_p95_ms']:.0f}ms")
            print(f"  Cost/turn: ${data['metrics']['cost_per_turn_usd']:.4f}")

        if report["comparison"]:
            print("\nWinners:")
            for metric, winner in report["comparison"].items():
                print(f"  {metric}: {winner}")

        print("=" * 70 + "\n")


__all__ = [
    "ScenarioRunner",
    "ComparisonRunner",
]
