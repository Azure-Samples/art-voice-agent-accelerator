"""
Hook Registry
=============

Manages registration and loading of evaluation hooks.

Supports:
- Built-in hooks via "builtin.name" syntax
- Custom hooks via module.function specification
- YAML-based hook configuration
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, TYPE_CHECKING

from utils.ml_logging import get_logger

from .base import TurnHook, ToolHook, PreScoreHook, HookResult

if TYPE_CHECKING:
    from tests.evaluation.schemas import TurnEvent

logger = get_logger(__name__)

# Built-in hook registry (populated by builtin.py)
_BUILTIN_HOOKS: dict[str, type] = {}


def register_builtin(name: str, hook_class: type) -> None:
    """Register a built-in hook class."""
    _BUILTIN_HOOKS[name] = hook_class


class HookRegistry:
    """
    Registry for evaluation hooks.

    Manages three hook types:
    - on_turn_complete: Called after each turn
    - on_tool_complete: Called after each tool execution
    - pre_score: Called before metrics scoring

    Example
    -------
    ```python
    registry = HookRegistry()

    # Register from YAML config
    registry.load_from_config({
        "on_turn_complete": [
            "builtin.log_metrics",
            {"module": "my_hooks", "function": "custom_analyzer"}
        ]
    })

    # Execute hooks
    result = await registry.dispatch_turn_complete(turn_event, context)
    ```
    """

    def __init__(self):
        self._turn_hooks: list[TurnHook] = []
        self._tool_hooks: list[ToolHook] = []
        self._pre_score_hooks: list[PreScoreHook] = []

    def load_from_config(self, config: dict[str, Any] | None) -> None:
        """
        Load hooks from YAML configuration.

        Config format:
        ```yaml
        hooks:
          on_turn_complete:
            - builtin.log_metrics
            - module: my_module
              function: my_hook
          on_tool_complete:
            - builtin.validate_result
          pre_score:
            - module: my_metrics
              function: compute_custom
        ```
        """
        if not config:
            return

        # Load turn hooks
        for hook_spec in config.get("on_turn_complete", []):
            hook = self._load_hook(hook_spec, TurnHook)
            if hook:
                self._turn_hooks.append(hook)

        # Load tool hooks
        for hook_spec in config.get("on_tool_complete", []):
            hook = self._load_hook(hook_spec, ToolHook)
            if hook:
                self._tool_hooks.append(hook)

        # Load pre-score hooks
        for hook_spec in config.get("pre_score", []):
            hook = self._load_hook(hook_spec, PreScoreHook)
            if hook:
                self._pre_score_hooks.append(hook)

        logger.info(
            "Loaded hooks | turn=%d tool=%d pre_score=%d",
            len(self._turn_hooks),
            len(self._tool_hooks),
            len(self._pre_score_hooks),
        )

    def _load_hook(self, spec: str | dict, expected_type: type) -> Any | None:
        """
        Load a single hook from specification.

        Args:
            spec: Either "builtin.name" string or {"module": ..., "function": ...}
            expected_type: Expected hook base class

        Returns:
            Instantiated hook or None if loading failed
        """
        try:
            if isinstance(spec, str):
                # Built-in hook: "builtin.log_metrics"
                if spec.startswith("builtin."):
                    hook_name = spec[8:]  # Remove "builtin." prefix
                    if hook_name not in _BUILTIN_HOOKS:
                        logger.warning("Unknown built-in hook: %s", hook_name)
                        return None
                    hook_class = _BUILTIN_HOOKS[hook_name]
                    return hook_class()
                else:
                    logger.warning("Invalid hook spec (string must start with 'builtin.'): %s", spec)
                    return None

            elif isinstance(spec, dict):
                # Custom hook: {"module": "my_module", "function": "my_func"}
                module_name = spec.get("module")
                func_name = spec.get("function")

                if not module_name or not func_name:
                    logger.warning("Hook spec missing 'module' or 'function': %s", spec)
                    return None

                # Import module and get function/class
                module = importlib.import_module(module_name)
                hook_obj = getattr(module, func_name)

                # If it's a class, instantiate it
                if isinstance(hook_obj, type):
                    return hook_obj()
                # If it's already an instance, use directly
                elif isinstance(hook_obj, expected_type):
                    return hook_obj
                else:
                    logger.warning(
                        "Hook %s.%s is not a %s",
                        module_name, func_name, expected_type.__name__
                    )
                    return None

            else:
                logger.warning("Invalid hook spec type: %s", type(spec))
                return None

        except ImportError as e:
            logger.warning("Failed to import hook module: %s", e)
            return None
        except AttributeError as e:
            logger.warning("Hook function not found: %s", e)
            return None
        except Exception as e:
            logger.warning("Failed to load hook: %s", e)
            return None

    def register_turn_hook(self, hook: TurnHook) -> None:
        """Programmatically register a turn hook."""
        self._turn_hooks.append(hook)

    def register_tool_hook(self, hook: ToolHook) -> None:
        """Programmatically register a tool hook."""
        self._tool_hooks.append(hook)

    def register_pre_score_hook(self, hook: PreScoreHook) -> None:
        """Programmatically register a pre-score hook."""
        self._pre_score_hooks.append(hook)

    async def dispatch_turn_complete(
        self,
        turn: "TurnEvent",
        context: dict[str, Any],
    ) -> HookResult:
        """
        Dispatch to all registered turn hooks.

        Hooks are executed sequentially. Errors are logged but don't stop execution.

        Args:
            turn: Completed turn event
            context: Execution context

        Returns:
            Merged HookResult from all hooks
        """
        merged = HookResult()

        for hook in self._turn_hooks:
            try:
                result = await hook.on_turn_complete(turn, context)
                if result:
                    merged = merged.merge(result)
            except Exception as e:
                logger.warning(
                    "Turn hook %s failed: %s",
                    hook.__class__.__name__, e
                )
                merged.warnings.append(f"Hook {hook.__class__.__name__} failed: {e}")

        return merged

    async def dispatch_tool_complete(
        self,
        tool_name: str,
        tool_result: Any,
        turn_context: dict[str, Any],
    ) -> HookResult:
        """
        Dispatch to all registered tool hooks.

        Args:
            tool_name: Name of completed tool
            tool_result: Tool execution result
            turn_context: Current turn context

        Returns:
            Merged HookResult from all hooks
        """
        merged = HookResult()

        for hook in self._tool_hooks:
            try:
                result = await hook.on_tool_complete(tool_name, tool_result, turn_context)
                if result:
                    merged = merged.merge(result)
            except Exception as e:
                logger.warning(
                    "Tool hook %s failed: %s",
                    hook.__class__.__name__, e
                )
                merged.warnings.append(f"Hook {hook.__class__.__name__} failed: {e}")

        return merged

    async def dispatch_pre_score(
        self,
        events: list["TurnEvent"],
        context: dict[str, Any],
    ) -> HookResult:
        """
        Dispatch to all registered pre-score hooks.

        Args:
            events: All turn events for scoring
            context: Scoring context

        Returns:
            Merged HookResult from all hooks
        """
        merged = HookResult()

        for hook in self._pre_score_hooks:
            try:
                result = await hook.pre_score(events, context)
                if result:
                    merged = merged.merge(result)
            except Exception as e:
                logger.warning(
                    "Pre-score hook %s failed: %s",
                    hook.__class__.__name__, e
                )
                merged.warnings.append(f"Hook {hook.__class__.__name__} failed: {e}")

        return merged

    @property
    def has_turn_hooks(self) -> bool:
        return len(self._turn_hooks) > 0

    @property
    def has_tool_hooks(self) -> bool:
        return len(self._tool_hooks) > 0

    @property
    def has_pre_score_hooks(self) -> bool:
        return len(self._pre_score_hooks) > 0
