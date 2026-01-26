"""
Pluggable Metrics Module
========================

Provides a plugin-based system for evaluation metrics.

Usage:
    from tests.evaluation.metrics import MetricPlugin, MetricRegistry, builtin_metrics

    # Register custom metric
    @metric_plugin
    class MyMetric(MetricPlugin):
        name = "my_metric"
        def compute(self, turn, **kwargs):
            return {"score": 0.95}

    # Load built-in + custom
    registry = MetricRegistry()
    registry.load_builtins()
    registry.register(MyMetric())

    # Compute all metrics
    results = registry.compute_all(turn)
"""

from tests.evaluation.metrics.base import (
    AggregateMetricPlugin,
    MetricPlugin,
    MetricResult,
    metric_plugin,
)
from tests.evaluation.metrics.builtin import (
    BUILTIN_METRICS,
    CostMetric,
    GroundednessMetric,
    HandoffAccuracyMetric,
    LatencyMetric,
    ToolEfficiencyMetric,
    ToolPrecisionMetric,
    ToolRecallMetric,
    VerbosityMetric,
)
from tests.evaluation.metrics.registry import MetricRegistry

__all__ = [
    # Base classes
    "MetricPlugin",
    "AggregateMetricPlugin",
    "MetricResult",
    "metric_plugin",
    # Registry
    "MetricRegistry",
    # Built-in metrics
    "BUILTIN_METRICS",
    "ToolPrecisionMetric",
    "ToolRecallMetric",
    "ToolEfficiencyMetric",
    "GroundednessMetric",
    "VerbosityMetric",
    "LatencyMetric",
    "CostMetric",
    "HandoffAccuracyMetric",
]
