"""
Pytest Evaluation Runner (End-to-End)
=====================================

Automated end-to-end evaluation testing:
1. Run evaluation scenario/comparison (generates events + metrics)
2. Validate expectations (tools, handoffs, response constraints)
3. Assert metric thresholds (precision, latency, grounding)
4. Optionally submit to Azure AI Foundry

Usage
-----
# Run all A/B comparisons with full validation
pytest tests/evaluation/test_scenarios.py -v

# Run with Foundry submission
pytest tests/evaluation/test_scenarios.py --submit-to-foundry

# Run specific scenario
pytest tests/evaluation/test_scenarios.py -k "fraud_detection" -v

# Skip slow tests (run expectations only on existing data)
pytest tests/evaluation/test_scenarios.py -m "not slow"

# With custom thresholds (via env vars)
EVAL_MIN_PRECISION=0.8 EVAL_MAX_LATENCY_MS=5000 pytest tests/evaluation/test_scenarios.py

Supported Expectations
----------------------
In your YAML scenario, each turn can define:

```yaml
turns:
  - turn_id: turn_1
    user_input: "Check my account"
    expectations:
      # Required tools (MUST be called)
      tools_called:
        - verify_client_identity
        - get_account_balance

      # Optional tools (won't fail if missing)
      tools_optional:
        - get_user_preferences

      # Forbidden tools (MUST NOT be called)
      tools_forbidden:
        - transfer_funds
        - delete_account

      # Handoff expectations
      handoff:
        to_agent: AccountSpecialist

      # Or assert no handoff
      no_handoff: true

      # Response content checks
      response_constraints:
        max_tokens: 150
        must_include:
          - "balance"
          - "$"
        must_not_include:
          - "error"
          - "failed"

      # Grounding requirement
      min_grounded_ratio: 0.7

      # Performance threshold
      max_latency_ms: 5000
```
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.evaluation.scenario_runner import ComparisonRunner, ScenarioRunner
from tests.evaluation.foundry_exporter import submit_to_foundry
from tests.evaluation.scorer import MetricsScorer
from tests.evaluation.validator import ExpectationValidator, TurnValidationResult
from tests.evaluation.schemas import RunSummary
from utils.ml_logging import get_logger

logger = get_logger(__name__)


def discover_ab_scenarios() -> list[Path]:
    """Discover all A/B test scenarios."""
    scenarios_dir = Path(__file__).parent / "scenarios" / "ab_tests"
    if not scenarios_dir.exists():
        return []
    return sorted(scenarios_dir.glob("*.yaml"))


def discover_session_scenarios() -> list[Path]:
    """Discover session-based evaluation scenarios."""
    scenarios_dir = Path(__file__).parent / "scenarios" / "session_based"
    if not scenarios_dir.exists():
        return []
    return sorted(scenarios_dir.glob("*.yaml"))


def discover_single_scenarios() -> list[Path]:
    """Discover single-agent evaluation scenarios."""
    scenarios_dir = Path(__file__).parent / "scenarios" / "agents"
    if not scenarios_dir.exists():
        return []
    return sorted(scenarios_dir.glob("*.yaml"))


def get_scenario_id(scenario_path: Path) -> str:
    """Extract scenario ID from path for test naming."""
    return scenario_path.stem


def get_thresholds(scenario_thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get evaluation thresholds from scenario, env vars, or defaults.
    
    Priority: scenario YAML > environment variables > defaults
    """
    defaults = {
        "min_tool_precision": float(os.environ.get("EVAL_MIN_PRECISION", "0.5")),
        "min_tool_recall": float(os.environ.get("EVAL_MIN_RECALL", "0.7")),
        "max_latency_p95_ms": int(os.environ.get("EVAL_MAX_LATENCY_MS", "15000")),
        "min_grounded_ratio": float(os.environ.get("EVAL_MIN_GROUNDED", "0.3")),
    }
    
    # Override with scenario-specific thresholds if provided
    if scenario_thresholds:
        for key in defaults:
            if key in scenario_thresholds:
                defaults[key] = scenario_thresholds[key]
    
    return defaults


# Parametrize tests with discovered scenarios
AB_SCENARIOS = discover_ab_scenarios()
SESSION_SCENARIOS = discover_session_scenarios()
SINGLE_SCENARIOS = discover_single_scenarios()


@pytest.mark.asyncio
@pytest.mark.evaluation
@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario_path",
    AB_SCENARIOS,
    ids=[get_scenario_id(s) for s in AB_SCENARIOS],
)
async def test_ab_comparison_e2e(
    scenario_path: Path,
    eval_output_dir: Path,
    submit_to_foundry_flag: bool,
    foundry_endpoint: str | None,
    foundry_model: str,
) -> None:
    """
    End-to-end A/B comparison test.

    Steps:
    1. Run comparison (all variants)
    2. Validate turn expectations for each variant
    3. Assert metric thresholds
    4. Optionally submit to Foundry
    """
    logger.info(f"🚀 Running E2E A/B comparison: {scenario_path.name}")

    # Create output directory for this scenario
    scenario_output = eval_output_dir / scenario_path.stem
    scenario_output.mkdir(parents=True, exist_ok=True)

    # --- STEP 1: Run Comparison ---
    runner = ComparisonRunner(
        comparison_path=scenario_path,
        output_dir=scenario_output,
    )

    results = await runner.run()

    # Basic validation - ensure we got results for all variants
    assert len(results) >= 2, f"A/B comparison should have at least 2 variants, got {len(results)}"

    # Load scenario YAML for expectations (also needed to get comparison_name)
    with open(scenario_path, encoding="utf-8") as f:
        scenario_yaml = yaml.safe_load(f)

    # Get the actual comparison directory (includes comparison_name)
    comparison_name = scenario_yaml.get("comparison_name", scenario_path.stem)
    comparison_dir = scenario_output / comparison_name

    # --- STEP 2: Validate Expectations for Each Variant ---
    validator = ExpectationValidator()
    scorer = MetricsScorer()

    all_validation_results: dict[str, list[TurnValidationResult]] = {}

    for variant_id, summary in results.items():
        variant_dir = comparison_dir / variant_id

        # Load events for this variant
        events_files = list(variant_dir.rglob("*_events.jsonl"))
        if not events_files:
            logger.warning(f"No *_events.jsonl found for variant {variant_id}")
            continue

        events = scorer.load_events(events_files[0])

        # Compute groundedness scores for validation
        groundedness_scores = {}
        for event in events:
            gs = scorer.compute_groundedness(event)
            groundedness_scores[event.turn_id] = gs["grounded_span_ratio"]

        # Validate against expectations
        validation_results = validator.validate_run(
            events=events,
            scenario=scenario_yaml,
            groundedness_scores=groundedness_scores,
        )

        all_validation_results[variant_id] = validation_results

        # Log validation report
        report = validator.format_report(validation_results)
        logger.info(f"\n{variant_id}:\n{report}")

        # Save validation report
        validation_path = variant_dir / "validation_report.json"
        with open(validation_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "turn_id": r.turn_id,
                        "passed": r.passed,
                        "failed_checks": r.failed_checks,
                        "checks": [
                            {
                                "check_name": c.check_name,
                                "passed": c.passed,
                                "message": c.message,
                                "expected": str(c.expected),
                                "actual": str(c.actual),
                            }
                            for c in r.checks
                        ],
                    }
                    for r in validation_results
                ],
                f,
                indent=2,
            )

    # --- STEP 3: Submit to Foundry (if enabled) ---
    # Submit BEFORE assertions so we get full Foundry view even if thresholds fail
    if submit_to_foundry_flag:
        await _submit_variants_to_foundry(
            results=results,
            scenario_output=comparison_dir,
            endpoint=foundry_endpoint,
            model=foundry_model,
        )

    # --- STEP 4: Assert All Variants Pass Expectations ---
    for variant_id, validations in all_validation_results.items():
        failed_turns = [v for v in validations if not v.passed]
        assert len(failed_turns) == 0, (
            f"Variant {variant_id} failed {len(failed_turns)} expectation checks:\n"
            + "\n".join(v.message for v in failed_turns)
        )

    # --- STEP 5: Assert Metric Thresholds ---
    # Use scenario-specific thresholds if defined, otherwise defaults
    thresholds = get_thresholds(scenario_yaml.get("thresholds"))

    for variant_id, summary in results.items():
        # Tool precision
        precision = summary.tool_metrics.get("precision", 0)
        assert precision >= thresholds["min_tool_precision"], (
            f"{variant_id}: Tool precision {precision:.2%} below threshold {thresholds['min_tool_precision']:.2%}"
        )

        # Tool recall
        recall = summary.tool_metrics.get("recall", 0)
        assert recall >= thresholds["min_tool_recall"], (
            f"{variant_id}: Tool recall {recall:.2%} below threshold {thresholds['min_tool_recall']:.2%}"
        )

        # Latency
        p95 = summary.latency_metrics.get("e2e_p95_ms", 0)
        assert p95 <= thresholds["max_latency_p95_ms"], (
            f"{variant_id}: P95 latency {p95:.0f}ms exceeds threshold {thresholds['max_latency_p95_ms']}ms"
        )

        # Groundedness
        grounded = summary.groundedness_metrics.get("avg_grounded_span_ratio", 0)
        assert grounded >= thresholds["min_grounded_ratio"], (
            f"{variant_id}: Groundedness {grounded:.2%} below threshold {thresholds['min_grounded_ratio']:.2%}"
        )

    logger.info(f"✅ All variants pass thresholds")


# =============================================================================
# SESSION-BASED SCENARIO TESTS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.evaluation
@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario_path",
    SESSION_SCENARIOS,
    ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
)
async def test_session_scenario_e2e(
    scenario_path: Path,
    eval_output_dir: Path,
    submit_to_foundry_flag: bool,
    foundry_endpoint: str | None,
    foundry_model: str,
) -> None:
    """
    End-to-end session-based scenario test.

    Steps:
    1. Run session scenario (multi-agent with dynamic routing)
    2. Validate turn expectations
    3. Assert metric thresholds
    4. Optionally submit to Foundry
    """
    logger.info(f"🚀 Running E2E session scenario: {scenario_path.name}")

    # Create output directory for this scenario
    scenario_output = eval_output_dir / scenario_path.stem
    scenario_output.mkdir(parents=True, exist_ok=True)

    # --- STEP 1: Run Scenario ---
    runner = ScenarioRunner(
        scenario_path=scenario_path,
        output_dir=scenario_output,
    )

    summary = await runner.run()

    # Basic validation - ensure we got results
    assert summary is not None, "Scenario run should return a summary"
    assert summary.total_turns > 0, "Scenario should have at least 1 turn"

    # Load scenario YAML for expectations
    with open(scenario_path, encoding="utf-8") as f:
        scenario_yaml = yaml.safe_load(f)

    # --- STEP 2: Validate Expectations ---
    validator = ExpectationValidator()
    scorer = MetricsScorer()

    # Find events file (newest first to use latest run)
    events_files = sorted(
        scenario_output.rglob("*_events.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not events_files:
        pytest.fail(f"No events.jsonl found in {scenario_output}")

    events = scorer.load_events(events_files[0])

    # Compute groundedness scores for validation
    groundedness_scores = {}
    for event in events:
        gs = scorer.compute_groundedness(event)
        groundedness_scores[event.turn_id] = gs["grounded_span_ratio"]

    # Validate against expectations
    validation_results = validator.validate_run(
        events=events,
        scenario=scenario_yaml,
        groundedness_scores=groundedness_scores,
    )

    # Log validation report
    report = validator.format_report(validation_results)
    logger.info(f"\n{scenario_path.stem}:\n{report}")

    # Save validation report
    validation_path = scenario_output / "validation_report.json"
    with open(validation_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "turn_id": r.turn_id,
                    "passed": r.passed,
                    "failed_checks": r.failed_checks,
                    "checks": [
                        {
                            "check_name": c.check_name,
                            "passed": c.passed,
                            "message": c.message,
                            "expected": str(c.expected),
                            "actual": str(c.actual),
                        }
                        for c in r.checks
                    ],
                }
                for r in validation_results
            ],
            f,
            indent=2,
        )

    # --- STEP 3: Submit to Foundry (if enabled) ---
    if submit_to_foundry_flag:
        if not foundry_endpoint:
            pytest.fail(
                "❌ --submit-to-foundry requires a Foundry endpoint. "
                "Set --foundry-endpoint or AZURE_AI_FOUNDRY_PROJECT_ENDPOINT environment variable."
            )

        # Find foundry_eval.jsonl
        foundry_files = list(scenario_output.rglob("foundry_eval.jsonl"))
        if not foundry_files:
            pytest.fail(
                f"❌ No foundry_eval.jsonl found in {scenario_output}. "
                f"Ensure scenario YAML has 'foundry_export.enabled: true'"
            )
        
        data_path = foundry_files[0]
        config_path = data_path.parent / "evaluators_config.json"
        eval_name = f"eval_{scenario_output.name}_{int(time.time())}"
        
        result = await submit_to_foundry(
            data_path=data_path,
            evaluators_config_path=config_path if config_path.exists() else None,
            project_endpoint=foundry_endpoint,
            evaluation_name=eval_name,
            model_deployment_name=foundry_model,
        )

        studio_url = result.get("studio_url")
        if studio_url:
            logger.info(f"✅ Foundry submission complete")
            logger.info(f"🔗 View in portal: {studio_url}")
        else:
            logger.warning(
                "⚠️ Foundry submission completed but no studio_url returned. "
                "Check Foundry prerequisites: storage account must be connected to project."
            )

    # --- STEP 4: Assert Expectations Pass ---
    failed_turns = [v for v in validation_results if not v.passed]
    assert len(failed_turns) == 0, (
        f"Scenario failed {len(failed_turns)} expectation checks:\n"
        + "\n".join(v.message for v in failed_turns)
    )

    # --- STEP 5: Assert Metric Thresholds ---
    thresholds = get_thresholds(scenario_yaml.get("thresholds"))

    # Tool precision
    precision = summary.tool_metrics.get("precision", 0)
    assert precision >= thresholds["min_tool_precision"], (
        f"Tool precision {precision:.2%} below threshold {thresholds['min_tool_precision']:.2%}"
    )

    # Tool recall
    recall = summary.tool_metrics.get("recall", 0)
    assert recall >= thresholds["min_tool_recall"], (
        f"Tool recall {recall:.2%} below threshold {thresholds['min_tool_recall']:.2%}"
    )

    # Latency
    p95 = summary.latency_metrics.get("e2e_p95_ms", 0)
    assert p95 <= thresholds["max_latency_p95_ms"], (
        f"P95 latency {p95:.0f}ms exceeds threshold {thresholds['max_latency_p95_ms']}ms"
    )

    # Groundedness
    grounded = summary.groundedness_metrics.get("avg_grounded_span_ratio", 0)
    assert grounded >= thresholds["min_grounded_ratio"], (
        f"Groundedness {grounded:.2%} below threshold {thresholds['min_grounded_ratio']:.2%}"
    )

    logger.info(f"✅ Session scenario passed all thresholds")


# =============================================================================
# EXPECTATION-ONLY TESTS (Fast - use existing data)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.evaluation
@pytest.mark.parametrize(
    "scenario_path",
    SESSION_SCENARIOS,
    ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
)
async def test_session_expectations_from_existing_data(
    scenario_path: Path,
    eval_output_dir: Path,
) -> None:
    """
    Validate expectations against existing session data (no re-execution).

    Use this for fast iteration when tuning expectations for session scenarios.
    """
    scenario_output = eval_output_dir / scenario_path.stem

    # Check if data exists
    if not scenario_output.exists():
        pytest.skip(f"No existing data at {scenario_output}. Run test_session_scenario_e2e first.")

    # Load scenario YAML
    with open(scenario_path, encoding="utf-8") as f:
        scenario_yaml = yaml.safe_load(f)

    validator = ExpectationValidator()
    scorer = MetricsScorer()

    # Find events file (session scenarios use *_events.jsonl pattern, newest first)
    events_files = sorted(
        scenario_output.rglob("*_events.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not events_files:
        pytest.skip("No events data found")

    events = scorer.load_events(events_files[0])

    # Compute groundedness
    groundedness_scores = {}
    for event in events:
        gs = scorer.compute_groundedness(event)
        groundedness_scores[event.turn_id] = gs["grounded_span_ratio"]

    # Validate
    validation_results = validator.validate_run(
        events=events,
        scenario=scenario_yaml,
        groundedness_scores=groundedness_scores,
    )

    # Assert
    failed = [v for v in validation_results if not v.passed]
    assert len(failed) == 0, (
        f"Scenario {scenario_path.stem} failed {len(failed)} checks:\n"
        + "\n".join(v.message for v in failed)
    )


@pytest.mark.asyncio
@pytest.mark.evaluation
@pytest.mark.parametrize(
    "scenario_path",
    AB_SCENARIOS,
    ids=[get_scenario_id(s) for s in AB_SCENARIOS],
)
async def test_expectations_from_existing_data(
    scenario_path: Path,
    eval_output_dir: Path,
) -> None:
    """
    Validate expectations against existing run data (no re-execution).

    Use this for fast iteration when tuning expectations.
    """
    scenario_output = eval_output_dir / scenario_path.stem

    # Check if data exists
    if not scenario_output.exists():
        pytest.skip(f"No existing data at {scenario_output}. Run test_ab_comparison_e2e first.")

    # Load scenario YAML
    with open(scenario_path, encoding="utf-8") as f:
        scenario_yaml = yaml.safe_load(f)

    validator = ExpectationValidator()
    scorer = MetricsScorer()

    # Find all variant directories
    variant_dirs = [d for d in scenario_output.iterdir() if d.is_dir()]

    if not variant_dirs:
        pytest.skip("No variant data found")

    for variant_dir in variant_dirs:
        variant_id = variant_dir.name

        # Load events
        events_files = list(variant_dir.rglob("*_events.jsonl"))
        if not events_files:
            continue

        events = scorer.load_events(events_files[0])

        # Compute groundedness
        groundedness_scores = {}
        for event in events:
            gs = scorer.compute_groundedness(event)
            groundedness_scores[event.turn_id] = gs["grounded_span_ratio"]

        # Validate
        validation_results = validator.validate_run(
            events=events,
            scenario=scenario_yaml,
            groundedness_scores=groundedness_scores,
        )

        # Assert
        failed = [v for v in validation_results if not v.passed]
        assert len(failed) == 0, (
            f"Variant {variant_id} failed {len(failed)} checks:\n"
            + "\n".join(v.message for v in failed)
        )


async def _submit_variants_to_foundry(
    results: dict[str, RunSummary],
    scenario_output: Path,
    endpoint: str | None,
    model: str,
) -> None:
    """Submit all variant results to Azure AI Foundry."""
    if not endpoint:
        pytest.skip("Foundry endpoint not configured (use --foundry-endpoint or set AZURE_AI_FOUNDRY_PROJECT_ENDPOINT)")

    for variant_id, summary in results.items():
        variant_dir = scenario_output / variant_id

        # Find foundry data file - use the MOST RECENT one
        foundry_files = list(variant_dir.rglob("foundry_eval.jsonl"))
        if not foundry_files:
            logger.warning(f"No foundry_eval.jsonl found for variant {variant_id}")
            continue

        # Sort by modification time, newest first
        foundry_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        data_path = foundry_files[0]
        config_path = data_path.parent / "foundry_evaluators.json"

        # Include timestamp in evaluation name to distinguish runs
        run_id = data_path.parent.name.split("_")[-1]  # Extract timestamp from directory name
        eval_name = f"{scenario_output.name}_{variant_id}_{run_id}"

        logger.info(f"📤 Submitting {variant_id} to Foundry: {data_path}")

        try:
            result = await submit_to_foundry(
                data_path=data_path,
                evaluators_config_path=config_path if config_path.exists() else None,
                project_endpoint=endpoint,
                evaluation_name=eval_name,
                model_deployment_name=model,
            )

            # Log success with studio_url prominently
            studio_url = result.get("studio_url")
            if studio_url:
                logger.info(f"✅ Foundry submission complete for {variant_id}")
                logger.info(f"🔗 View in portal: {studio_url}")
            else:
                logger.warning(
                    f"⚠️ Foundry submission completed for {variant_id} but no studio_url returned. "
                    "Check Foundry prerequisites: storage account must be connected to project."
                )

            logger.info(f"📊 Metrics: {result.get('metrics', {})}")

            # Save Foundry result
            foundry_result_path = variant_dir / "foundry_result.json"
            with open(foundry_result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"❌ Foundry submission failed for {variant_id}: {e}")
            # Don't fail the test, just log the error
            pytest.xfail(f"Foundry submission failed: {e}")


class TestEvaluationMetrics:
    """Test evaluation metric thresholds against existing comparison data."""

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        AB_SCENARIOS,
        ids=[get_scenario_id(s) for s in AB_SCENARIOS],
    )
    def test_tool_precision_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify all variants meet minimum tool precision."""
        comparison = self._load_comparison(scenario_path, eval_output_dir)
        if not comparison:
            pytest.skip("No comparison data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_tool_precision"]

        for variant_id, data in comparison.get("variants", {}).items():
            precision = data.get("metrics", {}).get("tool_precision", 0)
            assert precision >= threshold, (
                f"{variant_id}: precision {precision:.2%} < {threshold:.2%}"
            )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        AB_SCENARIOS,
        ids=[get_scenario_id(s) for s in AB_SCENARIOS],
    )
    def test_tool_recall_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify all variants meet minimum tool recall."""
        comparison = self._load_comparison(scenario_path, eval_output_dir)
        if not comparison:
            pytest.skip("No comparison data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_tool_recall"]

        for variant_id, data in comparison.get("variants", {}).items():
            recall = data.get("metrics", {}).get("tool_recall", 0)
            assert recall >= threshold, (
                f"{variant_id}: recall {recall:.2%} < {threshold:.2%}"
            )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        AB_SCENARIOS,
        ids=[get_scenario_id(s) for s in AB_SCENARIOS],
    )
    def test_latency_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify all variants meet maximum latency threshold."""
        comparison = self._load_comparison(scenario_path, eval_output_dir)
        if not comparison:
            pytest.skip("No comparison data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["max_latency_p95_ms"]

        for variant_id, data in comparison.get("variants", {}).items():
            p95 = data.get("metrics", {}).get("latency_p95_ms", 0)
            assert p95 <= threshold, (
                f"{variant_id}: P95 {p95:.0f}ms > {threshold}ms"
            )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        AB_SCENARIOS,
        ids=[get_scenario_id(s) for s in AB_SCENARIOS],
    )
    def test_groundedness_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify all variants meet minimum groundedness ratio."""
        comparison = self._load_comparison(scenario_path, eval_output_dir)
        if not comparison:
            pytest.skip("No comparison data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_grounded_ratio"]

        for variant_id, data in comparison.get("variants", {}).items():
            grounded = data.get("metrics", {}).get("grounded_span_ratio", 0)
            assert grounded >= threshold, (
                f"{variant_id}: groundedness {grounded:.2%} < {threshold:.2%}"
            )

    def _load_comparison(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> dict | None:
        """Load comparison.json for a scenario."""
        scenario_output = eval_output_dir / scenario_path.stem

        comparison_files = list(scenario_output.rglob("comparison.json"))
        if not comparison_files:
            return None

        with open(comparison_files[0], encoding="utf-8") as f:
            return json.load(f)

    def _load_scenario_thresholds(self, scenario_path: Path) -> dict[str, Any] | None:
        """Load threshold overrides from scenario YAML."""
        with open(scenario_path, encoding="utf-8") as f:
            scenario_yaml = yaml.safe_load(f)
        return scenario_yaml.get("thresholds")


class TestSessionMetrics:
    """Test evaluation metric thresholds against existing session scenario data."""

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        SESSION_SCENARIOS,
        ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
    )
    def test_tool_precision_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify session scenario meets minimum tool precision."""
        summary = self._load_summary(scenario_path, eval_output_dir)
        if not summary:
            pytest.skip("No summary data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_tool_precision"]

        precision = summary.get("tool_metrics", {}).get("precision", 0)
        assert precision >= threshold, (
            f"precision {precision:.2%} < {threshold:.2%}"
        )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        SESSION_SCENARIOS,
        ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
    )
    def test_tool_recall_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify session scenario meets minimum tool recall."""
        summary = self._load_summary(scenario_path, eval_output_dir)
        if not summary:
            pytest.skip("No summary data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_tool_recall"]

        recall = summary.get("tool_metrics", {}).get("recall", 0)
        assert recall >= threshold, (
            f"recall {recall:.2%} < {threshold:.2%}"
        )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        SESSION_SCENARIOS,
        ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
    )
    def test_latency_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify session scenario meets maximum latency threshold."""
        summary = self._load_summary(scenario_path, eval_output_dir)
        if not summary:
            pytest.skip("No summary data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["max_latency_p95_ms"]

        p95 = summary.get("latency_metrics", {}).get("e2e_p95_ms", 0)
        assert p95 <= threshold, (
            f"P95 {p95:.0f}ms > {threshold}ms"
        )

    @pytest.mark.evaluation
    @pytest.mark.parametrize(
        "scenario_path",
        SESSION_SCENARIOS,
        ids=[get_scenario_id(s) for s in SESSION_SCENARIOS],
    )
    def test_groundedness_threshold(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> None:
        """Verify session scenario meets minimum groundedness ratio."""
        summary = self._load_summary(scenario_path, eval_output_dir)
        if not summary:
            pytest.skip("No summary data found")

        scenario_thresholds = self._load_scenario_thresholds(scenario_path)
        threshold = get_thresholds(scenario_thresholds)["min_grounded_ratio"]

        grounded = summary.get("groundedness_metrics", {}).get("avg_grounded_span_ratio", 0)
        assert grounded >= threshold, (
            f"groundedness {grounded:.2%} < {threshold:.2%}"
        )

    def _load_summary(
        self,
        scenario_path: Path,
        eval_output_dir: Path,
    ) -> dict | None:
        """Load run_summary.json for a session scenario."""
        scenario_output = eval_output_dir / scenario_path.stem

        summary_files = list(scenario_output.rglob("run_summary.json"))
        if not summary_files:
            return None

        with open(summary_files[0], encoding="utf-8") as f:
            return json.load(f)

    def _load_scenario_thresholds(self, scenario_path: Path) -> dict[str, Any] | None:
        """Load threshold overrides from scenario YAML."""
        with open(scenario_path, encoding="utf-8") as f:
            scenario_yaml = yaml.safe_load(f)
        return scenario_yaml.get("thresholds")


# Allow running standalone
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "evaluation"])
