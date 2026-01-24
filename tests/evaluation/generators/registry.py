"""
Generator Registry (Phase 4)
============================

Central registry for turn generators, supporting both class-based
and function-based generators.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Type

from utils.ml_logging import get_logger

from .base import (
    GeneratedTurn,
    GeneratorConfig,
    GeneratorFunc,
    TurnGenerator,
    get_registered_generator,
)

logger = get_logger(__name__)


class GeneratorRegistry:
    """
    Registry for turn generators.

    Supports:
        - Decorator-registered functions via @turn_generator
        - Class-based generators implementing TurnGenerator
        - Dynamic module loading from YAML config
    """

    def __init__(self):
        self._class_generators: Dict[str, Type[TurnGenerator]] = {}
        self._func_generators: Dict[str, GeneratorFunc] = {}

    def register_class(
        self,
        name: str,
        generator_class: Type[TurnGenerator],
    ) -> None:
        """
        Register a class-based generator.

        Args:
            name: Unique name for the generator
            generator_class: Class implementing TurnGenerator

        Example
        -------
        ```python
        registry.register_class("banking.fraud", FraudScenarioGenerator)
        ```
        """
        if name in self._class_generators or name in self._func_generators:
            logger.warning(f"Overwriting existing generator: {name}")

        self._class_generators[name] = generator_class
        logger.debug(f"Registered class generator: {name}")

    def register_func(
        self,
        name: str,
        func: GeneratorFunc,
    ) -> None:
        """
        Register a function-based generator.

        Args:
            name: Unique name for the generator
            func: Function with signature (params: dict, context: dict) -> list[dict]

        Example
        -------
        ```python
        registry.register_func("banking.balance_check", generate_balance_checks)
        ```
        """
        if name in self._class_generators or name in self._func_generators:
            logger.warning(f"Overwriting existing generator: {name}")

        self._func_generators[name] = func
        logger.debug(f"Registered function generator: {name}")

    def get(self, name: str) -> GeneratorFunc | Type[TurnGenerator] | None:
        """
        Get a generator by name.

        Checks in order:
            1. Function registry
            2. Class registry
            3. Decorator-registered functions (@turn_generator)

        Args:
            name: Generator name

        Returns:
            Generator function/class or None if not found
        """
        # Check local registries first
        if name in self._func_generators:
            return self._func_generators[name]

        if name in self._class_generators:
            return self._class_generators[name]

        # Check decorator registry
        decorator_func = get_registered_generator(name)
        if decorator_func:
            return decorator_func

        return None

    def execute(
        self,
        name: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Execute a generator and return turns.

        Args:
            name: Generator name
            params: Parameters from YAML config
            context: Runtime context

        Returns:
            List of generated turn dictionaries
        """
        generator = self.get(name)

        if generator is None:
            logger.error(f"Generator not found: {name}")
            return []

        try:
            # Handle class-based generator
            if isinstance(generator, type) and issubclass(generator, TurnGenerator):
                instance = generator()
                generated_turns = instance.generate(params, context)
                return [t.model_dump() for t in generated_turns]

            # Handle function-based generator
            if callable(generator):
                result = generator(params, context)
                # Normalize to list of dicts
                if result and isinstance(result[0], GeneratedTurn):
                    return [t.model_dump() for t in result]
                return result

        except Exception as e:
            logger.error(f"Generator {name} failed: {e}")
            return []

        return []

    def execute_from_config(
        self,
        config: GeneratorConfig | Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Execute a generator from YAML configuration.

        Args:
            config: Generator config (GeneratorConfig or dict)
            context: Runtime context

        Returns:
            List of generated turn dictionaries
        """
        if isinstance(config, dict):
            config = GeneratorConfig.model_validate(config)

        # Try loading from module
        try:
            module = importlib.import_module(config.module)
            func = getattr(module, config.function, None)

            if func:
                result = func(config.params, context)
                return result if isinstance(result, list) else []

        except ImportError:
            # Not a loadable module - might be a registered name
            pass

        # Fall back to registry lookup (module.function as name)
        name = f"{config.module}.{config.function}"
        return self.execute(name, config.params, context)

    def list_generators(self) -> List[str]:
        """List all registered generator names."""
        names = set(self._func_generators.keys())
        names.update(self._class_generators.keys())
        return sorted(names)

    def clear(self) -> None:
        """Clear all registered generators (useful for testing)."""
        self._class_generators.clear()
        self._func_generators.clear()


# Global registry instance
_global_registry = GeneratorRegistry()


def get_global_registry() -> GeneratorRegistry:
    """Get the global generator registry."""
    return _global_registry


__all__ = ["GeneratorRegistry", "get_global_registry"]
