"""
Metric Plugin Base Classes
==========================

Defines the interface for pluggable metrics.

Design:
- MetricPlugin: Per-turn metrics (precision, recall, groundedness)
- AggregateMetricPlugin: Multi-turn metrics (latency percentiles, cost)
- MetricResult: Standardized return type with score + details
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type

if TYPE_CHECKING:
    from tests.evaluation.schemas import ScenarioExpectations, TurnEvent


@dataclass
class MetricResult:
    """
    Standardized metric computation result.

    Attributes:
        name: Metric name (e.g., "tool_precision")
        score: Primary score value (0.0 to 1.0 for most metrics)
        details: Additional computed values (counts, breakdowns, etc.)
        passed: Optional pass/fail for threshold-based checks
        threshold: Threshold used for pass/fail (if applicable)
    """

    name: str
    score: float
    details: Dict[str, Any] = field(default_factory=dict)
    passed: Optional[bool] = None
    threshold: Optional[float] = None

    def __post_init__(self):
        """Validate score is in expected range for bounded metrics."""
        # Allow unbounded metrics (e.g., latency in ms, token counts)
        # Only validate if score appears to be a ratio
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "name": self.name,
            "score": self.score,
            "details": self.details,
        }
        if self.passed is not None:
            result["passed"] = self.passed
        if self.threshold is not None:
            result["threshold"] = self.threshold
        return result


class MetricPlugin(ABC):
    """
    Base class for per-turn metric plugins.

    Subclasses must implement:
    - name: Unique identifier for the metric
    - compute(): Calculate metric for a single turn

    Optional overrides:
    - description: Human-readable description
    - higher_is_better: For comparison (default: True)
    - default_threshold: For pass/fail checks

    Example:
        class MyMetric(MetricPlugin):
            name = "my_metric"
            description = "Measures something important"
            higher_is_better = True
            default_threshold = 0.8

            def compute(self, turn, expectations=None, **kwargs):
                score = calculate_something(turn)
                return MetricResult(
                    name=self.name,
                    score=score,
                    details={"raw_value": score}
                )
    """

    # Subclasses MUST override these
    name: str = ""
    description: str = ""

    # Subclasses MAY override these
    higher_is_better: bool = True
    default_threshold: Optional[float] = None

    @abstractmethod
    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        """
        Compute metric for a single turn.

        Args:
            turn: TurnEvent to evaluate
            expectations: Optional scenario expectations
            **kwargs: Additional context (e.g., expected_tools)

        Returns:
            MetricResult with score and details
        """
        raise NotImplementedError

    def check_threshold(
        self,
        result: MetricResult,
        threshold: Optional[float] = None,
    ) -> MetricResult:
        """
        Apply threshold check to result.

        Args:
            result: MetricResult to check
            threshold: Override threshold (uses default if not provided)

        Returns:
            MetricResult with passed field set
        """
        thresh = threshold or self.default_threshold
        if thresh is None:
            return result

        if self.higher_is_better:
            passed = result.score >= thresh
        else:
            passed = result.score <= thresh

        return MetricResult(
            name=result.name,
            score=result.score,
            details=result.details,
            passed=passed,
            threshold=thresh,
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"


class AggregateMetricPlugin(ABC):
    """
    Base class for multi-turn aggregate metrics.

    Used for metrics that need all turns to compute (e.g., latency percentiles).

    Subclasses must implement:
    - name: Unique identifier
    - compute_aggregate(): Calculate metric across all turns
    """

    name: str = ""
    description: str = ""
    higher_is_better: bool = True

    @abstractmethod
    def compute_aggregate(
        self,
        turns: List["TurnEvent"],
        **kwargs: Any,
    ) -> MetricResult:
        """
        Compute aggregate metric across all turns.

        Args:
            turns: List of TurnEvents
            **kwargs: Additional context

        Returns:
            MetricResult with aggregated score and details
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"


# Registry for @metric_plugin decorator
_METRIC_REGISTRY: Dict[str, Type[MetricPlugin]] = {}


def metric_plugin(cls: Type[MetricPlugin]) -> Type[MetricPlugin]:
    """
    Decorator to register a metric plugin class.

    Usage:
        @metric_plugin
        class MyMetric(MetricPlugin):
            name = "my_metric"
            ...

    The metric will be available via get_registered_metrics().
    """
    if not cls.name:
        raise ValueError(f"Metric plugin {cls.__name__} must define 'name' attribute")

    _METRIC_REGISTRY[cls.name] = cls
    return cls


def get_registered_metrics() -> Dict[str, Type[MetricPlugin]]:
    """Get all metrics registered via @metric_plugin decorator."""
    return _METRIC_REGISTRY.copy()


def create_metric_from_function(
    name: str,
    compute_fn: Callable[["TurnEvent", Optional["ScenarioExpectations"]], MetricResult],
    description: str = "",
    higher_is_better: bool = True,
    default_threshold: Optional[float] = None,
) -> MetricPlugin:
    """
    Create a MetricPlugin from a simple function.

    Useful for quick one-off metrics without defining a class.

    Args:
        name: Metric name
        compute_fn: Function that takes (turn, expectations) and returns MetricResult
        description: Human-readable description
        higher_is_better: For comparison
        default_threshold: For pass/fail checks

    Returns:
        MetricPlugin instance

    Example:
        def my_compute(turn, expectations):
            return MetricResult(name="simple", score=0.9)

        metric = create_metric_from_function("simple", my_compute)
    """

    class FunctionMetric(MetricPlugin):
        pass

    FunctionMetric.name = name
    FunctionMetric.description = description
    FunctionMetric.higher_is_better = higher_is_better
    FunctionMetric.default_threshold = default_threshold

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        return compute_fn(turn, expectations)

    FunctionMetric.compute = compute  # type: ignore

    return FunctionMetric()


__all__ = [
    "MetricPlugin",
    "AggregateMetricPlugin",
    "MetricResult",
    "metric_plugin",
    "get_registered_metrics",
    "create_metric_from_function",
]
