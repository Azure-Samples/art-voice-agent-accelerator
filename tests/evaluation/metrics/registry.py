"""
Metric Registry
===============

Manages registration and loading of metric plugins.

Features:
- Load built-in metrics
- Register custom metrics
- Load metrics from YAML config
- Load metrics from Python modules
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, Union

from tests.evaluation.metrics.base import (
    AggregateMetricPlugin,
    MetricPlugin,
    MetricResult,
)
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from tests.evaluation.schemas import ScenarioExpectations, TurnEvent

logger = get_logger(__name__)


class MetricRegistry:
    """
    Registry for metric plugins.

    Manages metric loading, registration, and computation.

    Usage:
        registry = MetricRegistry()
        registry.load_builtins()
        registry.register(MyCustomMetric())

        # Compute specific metrics
        results = registry.compute(turns, ["tool_precision", "tool_recall"])

        # Compute all registered metrics
        results = registry.compute_all(turns)
    """

    def __init__(self):
        """Initialize empty registry."""
        self._plugins: Dict[str, MetricPlugin] = {}
        self._aggregate_plugins: Dict[str, AggregateMetricPlugin] = {}

    def load_builtins(self) -> "MetricRegistry":
        """
        Load all built-in metrics.

        Returns:
            Self for method chaining
        """
        from tests.evaluation.metrics.builtin import BUILTIN_METRICS

        for name, plugin in BUILTIN_METRICS.items():
            self.register(plugin)

        logger.debug(f"Loaded {len(BUILTIN_METRICS)} built-in metrics")
        return self

    def register(
        self,
        plugin: Union[MetricPlugin, AggregateMetricPlugin],
        override: bool = False,
    ) -> "MetricRegistry":
        """
        Register a metric plugin.

        Args:
            plugin: MetricPlugin or AggregateMetricPlugin instance
            override: If True, replace existing plugin with same name

        Returns:
            Self for method chaining

        Raises:
            ValueError: If plugin with same name exists and override=False
        """
        name = plugin.name

        if not name:
            raise ValueError(f"Plugin {plugin.__class__.__name__} must have a name")

        # Check for duplicates
        if name in self._plugins or name in self._aggregate_plugins:
            if not override:
                raise ValueError(
                    f"Metric '{name}' already registered. Use override=True to replace."
                )
            logger.warning(f"Overriding existing metric: {name}")

        # Register based on type
        if isinstance(plugin, AggregateMetricPlugin):
            self._aggregate_plugins[name] = plugin
        else:
            self._plugins[name] = plugin

        logger.debug(f"Registered metric: {name}")
        return self

    def unregister(self, name: str) -> bool:
        """
        Unregister a metric by name.

        Args:
            name: Metric name to remove

        Returns:
            True if metric was removed, False if not found
        """
        if name in self._plugins:
            del self._plugins[name]
            return True
        if name in self._aggregate_plugins:
            del self._aggregate_plugins[name]
            return True
        return False

    def get(self, name: str) -> Optional[Union[MetricPlugin, AggregateMetricPlugin]]:
        """
        Get a metric plugin by name.

        Args:
            name: Metric name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name) or self._aggregate_plugins.get(name)

    def list_metrics(self) -> List[str]:
        """Get list of all registered metric names."""
        return list(self._plugins.keys()) + list(self._aggregate_plugins.keys())

    def list_per_turn_metrics(self) -> List[str]:
        """Get list of per-turn metric names."""
        return list(self._plugins.keys())

    def list_aggregate_metrics(self) -> List[str]:
        """Get list of aggregate metric names."""
        return list(self._aggregate_plugins.keys())

    # =========================================================================
    # LOADING FROM CONFIG/MODULES
    # =========================================================================

    def load_from_yaml(self, config: Dict[str, Any]) -> "MetricRegistry":
        """
        Load metrics from YAML configuration.

        YAML format:
        ```yaml
        metrics:
          - builtin.tool_precision
          - builtin.groundedness
          - type: custom
            module: my_metrics.domain
            metrics:
              - name: banking_accuracy
                function: compute_banking_accuracy
        ```

        Args:
            config: Parsed YAML config dict

        Returns:
            Self for method chaining
        """
        metrics_config = config.get("metrics", [])

        for entry in metrics_config:
            if isinstance(entry, str):
                # Simple built-in reference: "builtin.tool_precision"
                if entry.startswith("builtin."):
                    metric_name = entry.replace("builtin.", "")
                    self._ensure_builtin(metric_name)
                else:
                    # Just a name, assume built-in
                    self._ensure_builtin(entry)

            elif isinstance(entry, dict):
                if entry.get("type") == "custom":
                    # Load custom metrics from module
                    self._load_custom_from_config(entry)
                elif "name" in entry:
                    # Inline metric definition (future)
                    logger.warning(f"Inline metric definitions not yet supported: {entry}")

        return self

    def _ensure_builtin(self, name: str) -> None:
        """Ensure a built-in metric is loaded."""
        if name not in self._plugins and name not in self._aggregate_plugins:
            from tests.evaluation.metrics.builtin import BUILTIN_METRICS

            if name in BUILTIN_METRICS:
                self.register(BUILTIN_METRICS[name])
            else:
                logger.warning(f"Unknown built-in metric: {name}")

    def _load_custom_from_config(self, config: Dict[str, Any]) -> None:
        """Load custom metrics from config entry."""
        module_path = config.get("module")
        if not module_path:
            logger.warning("Custom metric config missing 'module' field")
            return

        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.error(f"Failed to import custom metric module '{module_path}': {e}")
            return

        for metric_def in config.get("metrics", []):
            name = metric_def.get("name")
            func_name = metric_def.get("function")

            if not name or not func_name:
                logger.warning(f"Custom metric missing name or function: {metric_def}")
                continue

            if hasattr(module, func_name):
                func = getattr(module, func_name)
                # Check if it's a MetricPlugin class or instance
                if isinstance(func, type) and issubclass(func, MetricPlugin):
                    self.register(func())
                elif isinstance(func, MetricPlugin):
                    self.register(func)
                elif callable(func):
                    # Create plugin from function
                    from tests.evaluation.metrics.base import create_metric_from_function

                    plugin = create_metric_from_function(
                        name=name,
                        compute_fn=func,
                        description=metric_def.get("description", ""),
                        higher_is_better=metric_def.get("higher_is_better", True),
                    )
                    self.register(plugin)
            else:
                logger.warning(f"Function '{func_name}' not found in module '{module_path}'")

    def load_from_module(self, module_path: str) -> "MetricRegistry":
        """
        Load all MetricPlugin classes from a Python module.

        Args:
            module_path: Dotted module path (e.g., "my_project.metrics")

        Returns:
            Self for method chaining
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.error(f"Failed to import module '{module_path}': {e}")
            return self

        loaded = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if it's a MetricPlugin class (not base classes)
            if (
                isinstance(attr, type)
                and issubclass(attr, (MetricPlugin, AggregateMetricPlugin))
                and attr not in (MetricPlugin, AggregateMetricPlugin)
                and hasattr(attr, "name")
                and attr.name
            ):
                self.register(attr())
                loaded += 1

        logger.info(f"Loaded {loaded} metrics from module: {module_path}")
        return self

    # =========================================================================
    # COMPUTATION
    # =========================================================================

    def compute_turn(
        self,
        turn: "TurnEvent",
        metrics: Optional[List[str]] = None,
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> Dict[str, MetricResult]:
        """
        Compute per-turn metrics for a single turn.

        Args:
            turn: TurnEvent to evaluate
            metrics: List of metric names (default: all per-turn metrics)
            expectations: Optional scenario expectations
            **kwargs: Additional context passed to metrics

        Returns:
            Dict mapping metric name -> MetricResult
        """
        if metrics is None:
            metrics = self.list_per_turn_metrics()

        results: Dict[str, MetricResult] = {}

        for name in metrics:
            plugin = self._plugins.get(name)
            if plugin:
                try:
                    results[name] = plugin.compute(turn, expectations=expectations, **kwargs)
                except Exception as e:
                    logger.error(f"Metric '{name}' failed: {e}")
                    results[name] = MetricResult(
                        name=name,
                        score=0.0,
                        details={"error": str(e)},
                    )
            else:
                logger.warning(f"Metric '{name}' not found in registry")

        return results

    def compute_aggregate(
        self,
        turns: List["TurnEvent"],
        metrics: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, MetricResult]:
        """
        Compute aggregate metrics across all turns.

        Args:
            turns: List of TurnEvents
            metrics: List of metric names (default: all aggregate metrics)
            **kwargs: Additional context passed to metrics

        Returns:
            Dict mapping metric name -> MetricResult
        """
        if metrics is None:
            metrics = self.list_aggregate_metrics()

        results: Dict[str, MetricResult] = {}

        for name in metrics:
            plugin = self._aggregate_plugins.get(name)
            if plugin:
                try:
                    results[name] = plugin.compute_aggregate(turns, **kwargs)
                except Exception as e:
                    logger.error(f"Aggregate metric '{name}' failed: {e}")
                    results[name] = MetricResult(
                        name=name,
                        score=0.0,
                        details={"error": str(e)},
                    )
            else:
                logger.warning(f"Aggregate metric '{name}' not found in registry")

        return results

    def compute_all(
        self,
        turns: List["TurnEvent"],
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Compute all metrics (per-turn and aggregate).

        Args:
            turns: List of TurnEvents
            expectations: Optional scenario expectations
            **kwargs: Additional context

        Returns:
            Dict with:
            - per_turn: List of per-turn metric results
            - aggregate: Dict of aggregate metric results
        """
        # Per-turn metrics
        per_turn_results: List[Dict[str, MetricResult]] = []
        for turn in turns:
            per_turn_results.append(
                self.compute_turn(turn, expectations=expectations, **kwargs)
            )

        # Aggregate metrics
        aggregate_results = self.compute_aggregate(turns, **kwargs)

        return {
            "per_turn": per_turn_results,
            "aggregate": aggregate_results,
        }

    def __len__(self) -> int:
        """Get total number of registered metrics."""
        return len(self._plugins) + len(self._aggregate_plugins)

    def __repr__(self) -> str:
        return (
            f"<MetricRegistry("
            f"per_turn={len(self._plugins)}, "
            f"aggregate={len(self._aggregate_plugins)})>"
        )


# Singleton default registry
_DEFAULT_REGISTRY: Optional[MetricRegistry] = None


def get_default_registry() -> MetricRegistry:
    """
    Get the default metric registry with built-ins loaded.

    Thread-safe singleton pattern.
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = MetricRegistry()
        _DEFAULT_REGISTRY.load_builtins()
    return _DEFAULT_REGISTRY


__all__ = [
    "MetricRegistry",
    "get_default_registry",
]
