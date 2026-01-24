"""
Turn Generator Base Classes (Phase 4)
=====================================

Abstract interfaces and decorators for creating turn generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, TypeVar

from pydantic import BaseModel, Field


class GeneratorConfig(BaseModel):
    """Configuration for a turn generator."""

    module: str = Field(..., description="Module path for custom generator")
    function: str = Field(..., description="Function name in the module")
    params: Dict[str, Any] = Field(
        default_factory=dict, description="Parameters to pass to the generator"
    )


class GeneratedTurn(BaseModel):
    """A turn produced by a generator."""

    turn_id: str
    user_input: str
    expectations: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TurnGenerator(ABC):
    """
    Abstract base class for turn generators.

    Generators create turns dynamically at scenario load time based on
    configuration parameters and runtime context.

    Example
    -------
    ```python
    class FraudScenarioGenerator(TurnGenerator):
        def generate(
            self,
            params: dict[str, Any],
            context: dict[str, Any],
        ) -> list[GeneratedTurn]:
            count = params.get("count", 3)
            return [
                GeneratedTurn(
                    turn_id=f"fraud_{i}",
                    user_input=f"I think someone hacked my account...",
                    expectations={"tools_called": ["flag_fraud"]},
                )
                for i in range(count)
            ]
    ```
    """

    @abstractmethod
    def generate(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[GeneratedTurn]:
        """
        Generate turns based on parameters and context.

        Args:
            params: Generator-specific parameters from YAML config
            context: Runtime context including:
                - fixtures: Test fixture data
                - previous_turns: Results from prior turns
                - scenario_config: Full scenario configuration

        Returns:
            List of GeneratedTurn objects to inject into the scenario
        """
        pass

    @property
    def name(self) -> str:
        """Generator name for registry."""
        return self.__class__.__name__


# Type for generator functions (non-class-based generators)
GeneratorFunc = Callable[[Dict[str, Any], Dict[str, Any]], List[Dict[str, Any]]]

# Registry for decorator-based generators
_generator_registry: Dict[str, GeneratorFunc] = {}


def turn_generator(name: str) -> Callable[[GeneratorFunc], GeneratorFunc]:
    """
    Decorator to register a function as a turn generator.

    Example
    -------
    ```python
    @turn_generator("banking.verify_identity")
    def generate_identity_verification(params: dict, context: dict) -> list[dict]:
        return [
            {
                "turn_id": "verify_1",
                "user_input": f"Hi, my name is {params['name']} and SSN ends in {params['ssn']}",
                "expectations": {"tools_called": ["verify_client_identity"]},
            }
        ]
    ```
    """

    def decorator(func: GeneratorFunc) -> GeneratorFunc:
        _generator_registry[name] = func
        return func

    return decorator


def get_registered_generator(name: str) -> GeneratorFunc | None:
    """Get a registered generator function by name."""
    return _generator_registry.get(name)


def list_registered_generators() -> List[str]:
    """List all registered generator names."""
    return list(_generator_registry.keys())


__all__ = [
    "GeneratorConfig",
    "GeneratedTurn",
    "TurnGenerator",
    "turn_generator",
    "get_registered_generator",
    "list_registered_generators",
]
