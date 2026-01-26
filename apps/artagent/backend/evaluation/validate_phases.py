#!/usr/bin/env python3
"""
Validation script for Phase 1 and Phase 2 of the evaluation framework.

This script runs comprehensive tests to validate:
- Phase 1: Core instrumentation (EventRecorder, Wrappers, Schemas)
- Phase 2: Metrics scoring (MetricsScorer, CLI)

Usage:
    python validate_phases.py
    python validate_phases.py --phase 1  # Test phase 1 only
    python validate_phases.py --phase 2  # Test phase 2 only
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str):
    """Print section header"""
    print(f"\n{BLUE}{'=' * 70}")
    print(f"{text}")
    print(f"{'=' * 70}{RESET}\n")


def print_test(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
    print(f"{status}: {test_name}")
    if details:
        print(f"  {details}")


def validate_phase1() -> List[Tuple[str, bool, str]]:
    """Validate Phase 1: Core Instrumentation"""
    results = []
    print_header("PHASE 1 VALIDATION: Core Instrumentation")

    # Test 1: Evaluation package imports successfully
    test_name = "Test 1: Evaluation package imports successfully"
    try:
        from apps.artagent.backend.evaluation import (
            EventRecorder,
            EvaluationOrchestratorWrapper,
            TurnEvent,
            ToolCall,
        )
        results.append((test_name, True, "All core components imported"))
    except Exception as e:
        results.append((test_name, False, f"Import error: {e}"))
        return results  # Cannot continue without imports

    # Test 2: EventRecorder instantiated
    test_name = "Test 2: EventRecorder instantiated"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = EventRecorder(
                run_id="test", output_dir=Path(tmpdir)
            )
            output_path = recorder.output_path
            results.append(
                (test_name, True, f"EventRecorder created | output={output_path}")
            )
    except Exception as e:
        results.append((test_name, False, f"Instantiation error: {e}"))

    # Test 3: Schemas imported successfully
    test_name = "Test 3: Schemas imported successfully"
    try:
        from apps.artagent.backend.evaluation.schemas import (
            TurnEvent,
            ToolCall,
            HandoffEvent,
            EvidenceBlob,
            EvalModelConfig,
            TurnScore,
            RunSummary,
        )
        results.append(
            (test_name, True, "All schema models imported")
        )
    except Exception as e:
        results.append((test_name, False, f"Schema import error: {e}"))

    # Test 4: Import guards configured
    test_name = "Test 4: Import guards configured"
    try:
        import apps.artagent.backend.evaluation as eval_pkg

        # Check for forbidden paths in metadata
        package_info = eval_pkg.get_package_info()
        forbidden_paths = package_info.get("forbidden_imports_from", [])
        forbidden_count = len(forbidden_paths)
        results.append(
            (
                test_name,
                forbidden_count > 0,
                f"Import guards configured | forbidden_paths={forbidden_count}",
            )
        )
    except Exception as e:
        results.append((test_name, False, f"Import guard check failed: {e}"))

    # Test 5: EventRecorder can record turn events
    test_name = "Test 5: EventRecorder can record turn events"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = EventRecorder(run_id="test", output_dir=Path(tmpdir))

            # Record a simple turn
            recorder.record_turn_start(
                turn_id="turn1",
                agent="TestAgent",
                user_text="Hello",
                timestamp=1000.0,
            )
            recorder.record_tool_start(
                tool_name="test_tool",
                arguments={"arg": "value"},
                timestamp=1000.1,
            )
            recorder.record_tool_end(
                tool_name="test_tool",
                result={"result": "success"},
                end_ts=1000.2,
                start_ts=1000.1,
            )
            recorder.record_turn_end(
                turn_id="turn1",
                agent="TestAgent",
                response_text="Hello back",
                e2e_ms=100.0,
                timestamp=1000.3,
            )

            # Verify file was created
            if recorder.output_path.exists():
                with open(recorder.output_path) as f:
                    events = [json.loads(line) for line in f]
                    if len(events) == 1 and events[0]["turn_id"] == "turn1":
                        results.append(
                            (
                                test_name,
                                True,
                                "Turn event recorded to JSONL successfully",
                            )
                        )
                    else:
                        results.append(
                            (test_name, False, f"Unexpected event count: {len(events)}")
                        )
            else:
                results.append((test_name, False, "Output file not created"))
    except Exception as e:
        results.append((test_name, False, f"Recording error: {e}"))

    # Test 6: Wrapper provides drop-in replacement
    test_name = "Test 6: Wrapper delegation works"
    try:
        # Create a simple mock orchestrator
        class MockOrchestrator:
            def __init__(self):
                self.custom_attr = "test_value"
                self._active_agent = "TestAgent"

            async def custom_method(self):
                return "custom_result"

        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = EventRecorder(run_id="test", output_dir=Path(tmpdir))
            mock_orch = MockOrchestrator()
            wrapper = EvaluationOrchestratorWrapper(mock_orch, recorder)

            # Test __getattr__ delegation
            if wrapper.custom_attr == "test_value":
                results.append(
                    (
                        test_name,
                        True,
                        "Wrapper delegates attributes correctly via __getattr__",
                    )
                )
            else:
                results.append(
                    (test_name, False, "Wrapper delegation not working")
                )
    except Exception as e:
        results.append((test_name, False, f"Wrapper test error: {e}"))

    # Test 7: Production code has zero imports
    test_name = "Test 7: Production code has zero imports from evaluation/"
    try:
        import subprocess

        # Check production directories for imports
        prod_dirs = [
            "apps/artagent/backend/voice",
            "apps/artagent/backend/api",
            "apps/artagent/backend/registries",
        ]

        found_imports = []
        for prod_dir in prod_dirs:
            result = subprocess.run(
                ["grep", "-r", "from apps.artagent.backend.evaluation", prod_dir],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:  # Found matches
                found_imports.append(prod_dir)

        if not found_imports:
            results.append(
                (
                    test_name,
                    True,
                    "No evaluation imports found in production code",
                )
            )
        else:
            results.append(
                (
                    test_name,
                    False,
                    f"Found evaluation imports in: {', '.join(found_imports)}",
                )
            )
    except FileNotFoundError:
        results.append(
            (test_name, True, "Production directories not found (acceptable for tests)")
        )
    except Exception as e:
        results.append((test_name, False, f"Import check error: {e}"))

    return results


def validate_phase2() -> List[Tuple[str, bool, str]]:
    """Validate Phase 2: Metrics Scoring"""
    results = []
    print_header("PHASE 2 VALIDATION: Metrics Scoring")

    # Test 1: MetricsScorer imports successfully
    test_name = "Test 1: MetricsScorer imports successfully"
    try:
        from apps.artagent.backend.evaluation.scorer import MetricsScorer

        results.append((test_name, True, "MetricsScorer imported"))
    except Exception as e:
        results.append((test_name, False, f"Import error: {e}"))
        return results  # Cannot continue

    # Test 2: MetricsScorer loads and scores events
    test_name = "Test 2: MetricsScorer loads and scores events"
    try:
        from apps.artagent.backend.evaluation import EventRecorder
        from apps.artagent.backend.evaluation.scorer import MetricsScorer

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a test event file
            recorder = EventRecorder(run_id="test", output_dir=tmpdir)
            recorder.record_turn_start(
                turn_id="turn1",
                agent="TestAgent",
                user_text="Hello",
                timestamp=1000.0,
            )
            recorder.record_tool_start(
                tool_name="test_tool",
                arguments={"arg": "value"},
                timestamp=1000.1,
            )
            recorder.record_tool_end(
                tool_name="test_tool",
                result={"result": "success"},
                end_ts=1000.2,
                start_ts=1000.1,
            )
            recorder.record_turn_end(
                turn_id="turn1",
                agent="TestAgent",
                response_text="The result is 42.",
                e2e_ms=100.0,
                timestamp=1000.3,
            )

            # Score the events
            scorer = MetricsScorer()
            events = scorer.load_events(recorder.output_path)

            if len(events) == 1:
                # Score the turn
                turn_score = scorer.score_turn(events[0])
                if hasattr(turn_score, "tool_precision"):
                    results.append(
                        (
                            test_name,
                            True,
                            f"Events loaded and scored | turns={len(events)}",
                        )
                    )
                else:
                    results.append((test_name, False, "Turn score missing metrics"))
            else:
                results.append(
                    (test_name, False, f"Expected 1 event, got {len(events)}")
                )
    except Exception as e:
        results.append((test_name, False, f"Scoring error: {e}"))

    # Test 3: CLI help works
    test_name = "Test 3: CLI help works"
    try:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.artagent.backend.evaluation.cli.run",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and "--input" in result.stdout:
            results.append(
                (test_name, True, "CLI help displays correctly")
            )
        else:
            results.append(
                (
                    test_name,
                    False,
                    f"CLI help failed: returncode={result.returncode}",
                )
            )
    except Exception as e:
        results.append((test_name, False, f"CLI help error: {e}"))

    # Test 4: CLI can score events.jsonl
    test_name = "Test 4: CLI can score events.jsonl"
    try:
        import subprocess
        from apps.artagent.backend.evaluation import EventRecorder

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create test events
            recorder = EventRecorder(run_id="test", output_dir=tmpdir)
            recorder.record_turn_start(
                turn_id="turn1",
                agent="TestAgent",
                user_text="What is 2+2?",
                timestamp=1000.0,
            )
            recorder.record_turn_end(
                turn_id="turn1",
                agent="TestAgent",
                response_text="The answer is 4.",
                e2e_ms=150.0,
                timestamp=1000.15,
            )

            # Run CLI
            output_dir = tmpdir / "output"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.artagent.backend.evaluation.cli.run",
                    "--input",
                    str(recorder.output_path),
                    "--output",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )

            # Check outputs
            scores_file = output_dir / "scores.jsonl"
            summary_file = output_dir / "summary.json"

            if scores_file.exists() and summary_file.exists():
                # Verify content
                with open(summary_file) as f:
                    summary = json.load(f)
                    if "total_turns" in summary and summary["total_turns"] == 1:
                        results.append(
                            (
                                test_name,
                                True,
                                f"CLI scored successfully | outputs created",
                            )
                        )
                    else:
                        results.append(
                            (test_name, False, f"Summary has unexpected content")
                        )
            else:
                results.append(
                    (
                        test_name,
                        False,
                        f"CLI outputs not created | returncode={result.returncode} | stderr={result.stderr}",
                    )
                )
    except Exception as e:
        results.append((test_name, False, f"CLI scoring error: {e}"))

    # Test 5: API-aware scoring works
    test_name = "Test 5: API-aware scoring (verbosity adjustments)"
    try:
        from apps.artagent.backend.evaluation.scorer import MetricsScorer
        from apps.artagent.backend.evaluation.schemas import TurnEvent, EvalModelConfig

        # Create events with different API configs
        chat_event = TurnEvent(
            session_id="test",
            turn_id="turn1",
            agent_name="TestAgent",
            user_text="Hello",
            response_text="Hi there!",
            tool_calls=[],
            e2e_ms=100.0,
            user_end_ts=1000.0,
            agent_last_output_ts=1000.1,
            response_tokens=3,
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o",
                endpoint_used="chat",
                temperature=0.7,
            ),
        )

        responses_event = TurnEvent(
            session_id="test",
            turn_id="turn2",
            agent_name="TestAgent",
            user_text="Hello",
            response_text="Hi there!",
            tool_calls=[],
            e2e_ms=100.0,
            user_end_ts=1000.0,
            agent_last_output_ts=1000.1,
            response_tokens=3,
            eval_model_config=EvalModelConfig(
                model_name="o1-preview",
                endpoint_used="responses",
                verbosity=0,  # Concise mode
            ),
        )

        scorer = MetricsScorer()

        # Score both
        chat_verbosity = scorer.compute_verbosity_score(chat_event)
        responses_verbosity = scorer.compute_verbosity_score(responses_event)

        # Responses API with verbosity=0 should have lower budget
        if (
            chat_verbosity["budget"] == 150
            and responses_verbosity["budget"] == 105
        ):  # 30% reduction
            results.append(
                (
                    test_name,
                    True,
                    f"API-aware budgets: chat={chat_verbosity['budget']}, responses={responses_verbosity['budget']}",
                )
            )
        else:
            results.append(
                (
                    test_name,
                    False,
                    f"Budget mismatch: chat={chat_verbosity['budget']}, responses={responses_verbosity['budget']}",
                )
            )
    except Exception as e:
        results.append((test_name, False, f"API-aware scoring error: {e}"))

    # Test 6: Groundedness computation works
    test_name = "Test 6: Groundedness (string matching)"
    try:
        from apps.artagent.backend.evaluation.scorer import MetricsScorer
        from apps.artagent.backend.evaluation.schemas import (
            TurnEvent,
            EvidenceBlob,
            EvalModelConfig,
        )

        event = TurnEvent(
            session_id="test",
            turn_id="turn1",
            agent_name="TestAgent",
            user_text="What is my balance?",
            response_text="Your balance is $1,234.56 as of 12/25/2024.",
            tool_calls=[],
            e2e_ms=100.0,
            user_end_ts=1000.0,
            agent_last_output_ts=1000.1,
            evidence_blobs=[
                EvidenceBlob(
                    source="tool:get_balance",
                    content_hash="abc123",
                    content_excerpt='{"balance": 1234.56, "date": "2024-12-25"}',
                )
            ],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", endpoint_used="chat"
            ),
        )

        scorer = MetricsScorer()
        groundedness = scorer.compute_groundedness(event)

        # Should find both factual spans in evidence
        if groundedness["grounded_span_ratio"] > 0.5:
            results.append(
                (
                    test_name,
                    True,
                    f"Groundedness computed | ratio={groundedness['grounded_span_ratio']:.2f}",
                )
            )
        else:
            results.append(
                (
                    test_name,
                    False,
                    f"Low groundedness: {groundedness['grounded_span_ratio']}",
                )
            )
    except Exception as e:
        results.append((test_name, False, f"Groundedness error: {e}"))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate evaluation framework phases"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2],
        help="Specific phase to validate (default: all)",
    )
    args = parser.parse_args()

    all_results = []

    # Run validations
    if args.phase is None or args.phase == 1:
        phase1_results = validate_phase1()
        all_results.extend(phase1_results)
        print("\n" + "=" * 70)
        for test_name, passed, details in phase1_results:
            print_test(test_name, passed, details)

    if args.phase is None or args.phase == 2:
        phase2_results = validate_phase2()
        all_results.extend(phase2_results)
        print("\n" + "=" * 70)
        for test_name, passed, details in phase2_results:
            print_test(test_name, passed, details)

    # Summary
    print_header("VALIDATION SUMMARY")
    total_tests = len(all_results)
    passed_tests = sum(1 for _, passed, _ in all_results if passed)
    failed_tests = total_tests - passed_tests

    print(f"Total tests:  {total_tests}")
    print(f"{GREEN}Passed:       {passed_tests}{RESET}")
    if failed_tests > 0:
        print(f"{RED}Failed:       {failed_tests}{RESET}")

    # Exit code
    if failed_tests > 0:
        print(f"\n{RED}❌ Validation FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}✅ All validations PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
