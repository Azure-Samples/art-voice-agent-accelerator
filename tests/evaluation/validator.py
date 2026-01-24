"""
Expectation Validator
=====================

Validates turn results against YAML-defined expectations.

Provides detailed assertion results with clear error messages for:
- Tool calls (required, optional, forbidden)
- Handoffs (expected target, no handoff assertions)
- Response constraints (must_include, must_not_include, max_tokens)
- Grounding (minimum grounded span ratio)
- Performance (max latency)

Usage
-----
```python
from tests.evaluation.validator import ExpectationValidator

validator = ExpectationValidator()

# Validate single turn
result = validator.validate_turn(turn_event, expectations_dict)
assert result.passed, result.message

# Validate all turns in a run
results = validator.validate_run(events, scenario_yaml)
for r in results:
    if not r.passed:
        print(f"FAIL {r.turn_id}: {r.message}")
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tests.evaluation.schemas import ScenarioExpectations, TurnEvent
from utils.ml_logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single expectation."""

    turn_id: str
    check_name: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class TurnValidationResult:
    """Aggregated validation result for a turn."""

    turn_id: str
    passed: bool
    checks: List[ValidationResult] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    user_text: str = ""  # User input for debugging
    response_text: str = ""  # Agent response for debugging
    tools_called: List[str] = field(default_factory=list)  # Actual tools called

    @property
    def message(self) -> str:
        """Human-readable summary of validation."""
        if self.passed:
            return f"✅ {self.turn_id}: All {len(self.checks)} checks passed"
        failed_msgs = [c.message for c in self.checks if not c.passed]
        return f"❌ {self.turn_id}: {len(self.failed_checks)} failed - {'; '.join(failed_msgs)}"


class ExpectationValidator:
    """
    Validates turn events against YAML expectations.

    Supported Checks
    ----------------
    - tools_required: All tools in tools_called must be invoked
    - tools_forbidden: None of tools_forbidden can be called
    - handoff_expected: If handoff specified, must happen to correct agent
    - no_handoff: If no_handoff=true, no handoff can occur
    - response_must_include: All substrings in must_include present
    - response_must_not_include: No substrings in must_not_include present
    - max_tokens: Response within token budget
    - min_grounded_ratio: Groundedness above threshold
    - max_latency: E2E latency within threshold

    Compact Syntax (Phase 1 Refactor)
    ---------------------------------
    Supports shorthand expectations for common cases:

    ```yaml
    # Shorthand: just tools as array
    expect: [verify_identity, get_balance]

    # Shorthand: compact object form
    expect:
      tools: [verify_identity]
      handoff: CardAgent
      contains: ["balance", "$"]
      excludes: ["error"]
      max_latency: 5000
      no_tools: true
    ```

    These get normalized to full ScenarioExpectations format internally.
    """

    def __init__(self):
        self.logger = logger

    def _normalize_expectations(
        self,
        expectations: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Normalize compact expectation syntax to full ScenarioExpectations format.

        Supports shortcuts:
          - expect: [tools] -> tools_called: [tools]
          - expect.tools -> tools_called
          - expect.handoff -> handoff.to_agent
          - expect.contains -> response_constraints.must_include
          - expect.excludes -> response_constraints.must_not_include
          - expect.max_latency -> max_latency_ms
          - expect.no_tools -> (expects tools_called to be empty)
          - expect.no_handoff -> no_handoff: true

        Args:
            expectations: Raw expectations dict (may be compact or full format)

        Returns:
            Normalized expectations dict in full ScenarioExpectations format
        """
        # If no 'expect' key, assume already full format
        if "expect" not in expectations:
            return expectations

        expect = expectations["expect"]
        normalized: Dict[str, Any] = {}

        # Copy existing full-format fields (backward compat)
        for key in ["tools_called", "tools_optional", "tools_forbidden", "handoff",
                    "no_handoff", "response_constraints", "grounding_required",
                    "min_grounded_ratio", "max_latency_ms"]:
            if key in expectations:
                normalized[key] = expectations[key]

        # Handle shorthand: expect: [tools] (array of tool names)
        if isinstance(expect, list):
            normalized["tools_called"] = expect
            return normalized

        # Handle shorthand: expect: {...} (compact object form)
        if isinstance(expect, dict):
            # tools -> tools_called
            if "tools" in expect:
                normalized["tools_called"] = expect["tools"]

            # no_tools -> expects empty tools_called
            if expect.get("no_tools"):
                # Don't require tools, but track for potential validation
                if "tools_called" not in normalized:
                    normalized["tools_called"] = []

            # handoff -> handoff.to_agent
            if "handoff" in expect:
                handoff_target = expect["handoff"]
                if isinstance(handoff_target, str):
                    normalized["handoff"] = {"to_agent": handoff_target}
                elif isinstance(handoff_target, dict):
                    normalized["handoff"] = handoff_target

            # no_handoff
            if expect.get("no_handoff"):
                normalized["no_handoff"] = True

            # contains -> response_constraints.must_include
            if "contains" in expect:
                if "response_constraints" not in normalized:
                    normalized["response_constraints"] = {}
                normalized["response_constraints"]["must_include"] = (
                    expect["contains"] if isinstance(expect["contains"], list)
                    else [expect["contains"]]
                )

            # excludes -> response_constraints.must_not_include
            if "excludes" in expect:
                if "response_constraints" not in normalized:
                    normalized["response_constraints"] = {}
                normalized["response_constraints"]["must_not_include"] = (
                    expect["excludes"] if isinstance(expect["excludes"], list)
                    else [expect["excludes"]]
                )

            # max_latency -> max_latency_ms
            if "max_latency" in expect:
                normalized["max_latency_ms"] = expect["max_latency"]

            # min_grounded -> min_grounded_ratio
            if "min_grounded" in expect:
                normalized["min_grounded_ratio"] = expect["min_grounded"]

            # forbidden -> tools_forbidden
            if "forbidden" in expect:
                normalized["tools_forbidden"] = (
                    expect["forbidden"] if isinstance(expect["forbidden"], list)
                    else [expect["forbidden"]]
                )

        return normalized

    def validate_turn(
        self,
        turn: TurnEvent,
        expectations: Dict[str, Any] | ScenarioExpectations,
        groundedness_ratio: float = 0.0,
    ) -> TurnValidationResult:
        """
        Validate a single turn against expectations.

        Args:
            turn: TurnEvent to validate
            expectations: Expectations dict or ScenarioExpectations object
            groundedness_ratio: Pre-computed groundedness ratio for this turn

        Returns:
            TurnValidationResult with all check results
        """
        # Normalize compact syntax to full format (Phase 1 refactor)
        if isinstance(expectations, dict):
            expectations = self._normalize_expectations(expectations)
            exp = ScenarioExpectations.model_validate(expectations)
        else:
            exp = expectations

        checks: List[ValidationResult] = []
        turn_id = turn.turn_id

        # Get actual tools called
        actual_tools = [tc.name for tc in turn.tool_calls]

        # 1. Required tools (recall check)
        if exp.tools_called:
            missing_tools = set(exp.tools_called) - set(actual_tools)
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="tools_required",
                    passed=len(missing_tools) == 0,
                    message=f"Missing required tools: {sorted(missing_tools)}" if missing_tools else "All required tools called",
                    expected=exp.tools_called,
                    actual=actual_tools,
                )
            )

        # 2. Forbidden tools
        if exp.tools_forbidden:
            forbidden_called = set(exp.tools_forbidden) & set(actual_tools)
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="tools_forbidden",
                    passed=len(forbidden_called) == 0,
                    message=f"Forbidden tools called: {sorted(forbidden_called)}" if forbidden_called else "No forbidden tools called",
                    expected=f"None of {exp.tools_forbidden}",
                    actual=actual_tools,
                )
            )

        # 3. Handoff expected
        if exp.handoff:
            expected_target = exp.handoff.get("to_agent")
            actual_handoff = turn.handoff

            if actual_handoff:
                handoff_correct = actual_handoff.target_agent == expected_target
                checks.append(
                    ValidationResult(
                        turn_id=turn_id,
                        check_name="handoff_target",
                        passed=handoff_correct,
                        message=f"Handoff to wrong agent: {actual_handoff.target_agent}" if not handoff_correct else f"Correct handoff to {expected_target}",
                        expected=expected_target,
                        actual=actual_handoff.target_agent,
                    )
                )
            else:
                checks.append(
                    ValidationResult(
                        turn_id=turn_id,
                        check_name="handoff_expected",
                        passed=False,
                        message=f"Expected handoff to {expected_target}, but no handoff occurred",
                        expected=expected_target,
                        actual=None,
                    )
                )

        # 4. No handoff assertion
        if exp.no_handoff:
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="no_handoff",
                    passed=turn.handoff is None,
                    message=f"Unexpected handoff to {turn.handoff.target_agent}" if turn.handoff else "No handoff (as expected)",
                    expected="No handoff",
                    actual=turn.handoff.target_agent if turn.handoff else None,
                )
            )

        # 5. Response constraints
        constraints = exp.response_constraints

        # 5a. must_include
        must_include = constraints.get("must_include", [])
        for substring in must_include:
            found = substring.lower() in turn.response_text.lower()
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name=f"must_include:{substring}",
                    passed=found,
                    message=f"Response missing required text: '{substring}'" if not found else f"Found '{substring}'",
                    expected=substring,
                    actual="Found" if found else "Not found",
                )
            )

        # 5b. must_not_include
        must_not_include = constraints.get("must_not_include", [])
        for substring in must_not_include:
            found = substring.lower() in turn.response_text.lower()
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name=f"must_not_include:{substring}",
                    passed=not found,
                    message=f"Response contains forbidden text: '{substring}'" if found else f"Correctly excludes '{substring}'",
                    expected=f"Not '{substring}'",
                    actual="Found" if found else "Not found",
                )
            )

        # 5c. max_tokens
        max_tokens = constraints.get("max_tokens")
        if max_tokens:
            actual_tokens = turn.response_tokens or len(turn.response_text.split())
            within_budget = actual_tokens <= max_tokens
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="max_tokens",
                    passed=within_budget,
                    message=f"Response {actual_tokens} tokens exceeds budget {max_tokens}" if not within_budget else f"Response {actual_tokens} tokens within budget",
                    expected=max_tokens,
                    actual=actual_tokens,
                )
            )

        # 6. Grounding check
        if exp.min_grounded_ratio > 0:
            above_threshold = groundedness_ratio >= exp.min_grounded_ratio
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="min_grounded_ratio",
                    passed=above_threshold,
                    message=f"Groundedness {groundedness_ratio:.2%} below threshold {exp.min_grounded_ratio:.2%}" if not above_threshold else f"Groundedness {groundedness_ratio:.2%} meets threshold",
                    expected=exp.min_grounded_ratio,
                    actual=groundedness_ratio,
                )
            )

        # 7. Latency check
        if exp.max_latency_ms:
            within_latency = turn.e2e_ms <= exp.max_latency_ms
            checks.append(
                ValidationResult(
                    turn_id=turn_id,
                    check_name="max_latency_ms",
                    passed=within_latency,
                    message=f"Latency {turn.e2e_ms:.0f}ms exceeds threshold {exp.max_latency_ms}ms" if not within_latency else f"Latency {turn.e2e_ms:.0f}ms within threshold",
                    expected=exp.max_latency_ms,
                    actual=turn.e2e_ms,
                )
            )

        # Aggregate result
        failed_checks = [c.check_name for c in checks if not c.passed]

        return TurnValidationResult(
            turn_id=turn_id,
            passed=len(failed_checks) == 0,
            checks=checks,
            failed_checks=failed_checks,
            user_text=turn.user_text,
            response_text=turn.response_text,
            tools_called=actual_tools,
        )

    def validate_run(
        self,
        events: List[TurnEvent],
        scenario: Dict[str, Any],
        groundedness_scores: Optional[Dict[str, float]] = None,
    ) -> List[TurnValidationResult]:
        """
        Validate all turns in a run against scenario expectations.

        Args:
            events: List of TurnEvent objects
            scenario: Full scenario/comparison YAML as dict
            groundedness_scores: Optional map of turn_id -> groundedness ratio

        Returns:
            List of TurnValidationResult for each turn with expectations
        """
        results: List[TurnValidationResult] = []
        groundedness_scores = groundedness_scores or {}

        # Build expectations map: turn_id -> expectations dict
        turns_spec = scenario.get("turns", [])
        expectations_map: Dict[str, Dict[str, Any]] = {}

        for turn_spec in turns_spec:
            turn_id = turn_spec.get("turn_id", "")
            # Support both 'expectations' (full) and 'expect' (compact)
            exp = turn_spec.get("expectations") or turn_spec.get("expect")
            if exp:
                # Handle compact: expect at turn level
                if "expect" in turn_spec and "expectations" not in turn_spec:
                    expectations_map[turn_id] = {"expect": exp}
                else:
                    expectations_map[turn_id] = exp if isinstance(exp, dict) else {"expect": exp}

        # Validate each event
        for event in events:
            # Extract turn key from turn_id (e.g., "scenario:turn_1" -> "turn_1")
            turn_key = event.turn_id.split(":")[-1] if ":" in event.turn_id else event.turn_id

            if turn_key in expectations_map:
                groundedness = groundedness_scores.get(event.turn_id, 0.0)
                result = self.validate_turn(
                    turn=event,
                    expectations=expectations_map[turn_key],
                    groundedness_ratio=groundedness,
                )
                results.append(result)

        return results

    def format_report(
        self,
        results: List[TurnValidationResult],
        verbose: bool = False,
    ) -> str:
        """
        Format validation results as human-readable report.

        Args:
            results: List of TurnValidationResult
            verbose: Include all checks, not just failures

        Returns:
            Formatted report string
        """
        lines = ["", "=" * 70, "📋 EXPECTATION VALIDATION REPORT", "=" * 70]

        total_turns = len(results)
        passed_turns = sum(1 for r in results if r.passed)
        failed_turns = total_turns - passed_turns

        lines.append(f"\nSummary: {passed_turns}/{total_turns} turns passed")

        if failed_turns > 0:
            lines.append(f"\n❌ {failed_turns} FAILED TURNS:")
            for result in results:
                if not result.passed:
                    lines.append(f"\n  {result.turn_id}:")
                    # Show user input and response for debugging
                    lines.append(f"    📥 User: {result.user_text[:150]}{'...' if len(result.user_text) > 150 else ''}")
                    lines.append(f"    📤 Response: {result.response_text[:200]}{'...' if len(result.response_text) > 200 else ''}")
                    lines.append(f"    🔧 Tools called: {result.tools_called or '(none)'}")
                    lines.append(f"    \n    Failed checks:")
                    for check in result.checks:
                        if not check.passed:
                            lines.append(f"    - {check.check_name}: {check.message}")
                            lines.append(f"      Expected: {check.expected}")
                            lines.append(f"      Actual:   {check.actual}")

        if verbose:
            lines.append(f"\n✅ PASSED TURNS:")
            for result in results:
                if result.passed:
                    lines.append(f"  {result.turn_id}: {len(result.checks)} checks passed")

        lines.append("=" * 70 + "\n")

        return "\n".join(lines)


__all__ = ["ExpectationValidator", "ValidationResult", "TurnValidationResult"]
