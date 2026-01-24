"""
Turn Expander (Phase 4)
=======================

Expands template variables and generators in scenario turns.

Template Variable Syntax
------------------------
Use double curly braces: `{{variable_name}}`

Sources for variable values:
    - fixture: From test fixtures file
    - context: From runtime context
    - previous_turn: Extract from previous turn's response
    - env: From environment variables (for non-secret config)

Example YAML
------------
```yaml
turns:
  - turn_id: turn_1
    user_input: "My name is {{customer_name}} and SSN ends in {{ssn_last4}}"
    inject:
      customer_name:
        source: fixture
        key: test_customer.name
      ssn_last4:
        source: fixture
        key: test_customer.ssn_last4

  - turn_id: turn_2
    user_input: "Transfer {{amount}} to savings"
    inject:
      amount:
        source: previous_turn
        extract: "account_balance"  # JSONPath-like extraction
```
"""

from __future__ import annotations

import importlib
import re
from typing import Any, Dict, List

from utils.ml_logging import get_logger

from .base import GeneratorConfig, GeneratorFunc, get_registered_generator

logger = get_logger(__name__)


class VariableSource:
    """Source types for template variables."""

    FIXTURE = "fixture"
    CONTEXT = "context"
    PREVIOUS_TURN = "previous_turn"
    ENV = "env"
    LITERAL = "literal"


class TurnExpander:
    """
    Expands template variables and generators in scenario turns.

    Responsibilities:
        1. Resolve `{{variable}}` placeholders in user_input
        2. Execute generators to create dynamic turns
        3. Support nested key access (e.g., `customer.address.city`)
    """

    # Pattern to match {{variable_name}}
    TEMPLATE_PATTERN = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")

    def __init__(
        self,
        fixtures: Dict[str, Any] | None = None,
        context: Dict[str, Any] | None = None,
    ):
        """
        Initialize the expander.

        Args:
            fixtures: Test fixture data (loaded from YAML/JSON)
            context: Runtime context (scenario config, metadata)
        """
        self.fixtures = fixtures or {}
        self.context = context or {}
        self._previous_turns: List[Dict[str, Any]] = []

    def expand_turns(
        self,
        turns: List[Dict[str, Any]],
        fixtures: Dict[str, Any] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Expand all turns, resolving templates and generators.

        Args:
            turns: List of turn dictionaries from scenario YAML
            fixtures: Optional fixtures override
            context: Optional context override

        Returns:
            List of expanded turn dictionaries ready for execution
        """
        if fixtures:
            self.fixtures = fixtures
        if context:
            self.context = context

        expanded: List[Dict[str, Any]] = []

        for turn in turns:
            # Check if this turn has a generator
            if "generator" in turn:
                generated = self._execute_generator(turn)
                expanded.extend(generated)
            else:
                # Expand template variables in user_input
                expanded_turn = self._expand_turn(turn)
                expanded.append(expanded_turn)

                # Track for previous_turn references
                self._previous_turns.append(expanded_turn)

        return expanded

    def _expand_turn(self, turn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expand template variables in a single turn.

        Args:
            turn: Turn dictionary with potential {{variables}}

        Returns:
            Turn with all variables resolved
        """
        result = turn.copy()
        user_input = turn.get("user_input", "")
        inject_config = turn.get("inject", {})

        if not user_input:
            return result

        # Find all template variables
        matches = self.TEMPLATE_PATTERN.findall(user_input)

        for var_name in matches:
            # Get injection config for this variable
            var_config = inject_config.get(var_name.split(".")[0], {})

            # Resolve the value
            value = self._resolve_variable(var_name, var_config)

            # Replace in user_input
            placeholder = f"{{{{{var_name}}}}}"
            user_input = user_input.replace(placeholder, str(value))

        result["user_input"] = user_input

        # Remove inject config from output (it's processed)
        if "inject" in result:
            del result["inject"]

        return result

    def _resolve_variable(
        self,
        var_name: str,
        config: Dict[str, Any],
    ) -> Any:
        """
        Resolve a template variable to its value.

        Args:
            var_name: Variable name (may contain dots for nested access)
            config: Injection configuration for this variable

        Returns:
            Resolved value
        """
        source = config.get("source", VariableSource.CONTEXT)

        if source == VariableSource.FIXTURE:
            key = config.get("key", var_name)
            return self._get_nested_value(self.fixtures, key)

        elif source == VariableSource.CONTEXT:
            key = config.get("key", var_name)
            return self._get_nested_value(self.context, key)

        elif source == VariableSource.PREVIOUS_TURN:
            extract_key = config.get("extract", "response_text")
            if self._previous_turns:
                last_turn = self._previous_turns[-1]
                return self._get_nested_value(last_turn, extract_key)
            logger.warning(f"No previous turn for variable: {var_name}")
            return f"<{var_name}>"

        elif source == VariableSource.LITERAL:
            return config.get("value", "")

        elif source == VariableSource.ENV:
            import os

            key = config.get("key", var_name)
            return os.environ.get(key, f"<{var_name}>")

        else:
            # Try context first, then fixtures
            if var_name in self.context:
                return self.context[var_name]
            if var_name in self.fixtures:
                return self.fixtures[var_name]

            logger.warning(f"Unresolved variable: {var_name}")
            return f"<{var_name}>"

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """
        Get a nested value using dot notation.

        Args:
            data: Dictionary to search
            key: Dot-separated key path (e.g., "customer.address.city")

        Returns:
            Value at the key path, or placeholder if not found
        """
        parts = key.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                logger.warning(f"Key path not found: {key} (failed at '{part}')")
                return f"<{key}>"

        return current

    def _execute_generator(self, turn: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute a turn generator and return generated turns.

        Args:
            turn: Turn dict with "generator" configuration

        Returns:
            List of generated turn dictionaries
        """
        gen_config = turn["generator"]
        turn_id_prefix = turn.get("turn_id", "gen")

        # Handle string reference to registered generator
        if isinstance(gen_config, str):
            generator_func = get_registered_generator(gen_config)
            if generator_func:
                params = turn.get("params", {})
                context = {
                    "fixtures": self.fixtures,
                    "context": self.context,
                    "previous_turns": self._previous_turns,
                    "turn_id_prefix": turn_id_prefix,
                }
                return generator_func(params, context)
            else:
                logger.error(f"Generator not found: {gen_config}")
                return []

        # Handle config object
        try:
            config = GeneratorConfig.model_validate(gen_config)
        except Exception as e:
            logger.error(f"Invalid generator config: {e}")
            return []

        # Load and execute the generator
        generator_func = self._load_generator_func(config)
        if not generator_func:
            return []

        context = {
            "fixtures": self.fixtures,
            "context": self.context,
            "previous_turns": self._previous_turns,
            "turn_id_prefix": turn_id_prefix,
        }

        try:
            generated = generator_func(config.params, context)

            # Ensure turn_ids are unique
            for i, gen_turn in enumerate(generated):
                if "turn_id" not in gen_turn:
                    gen_turn["turn_id"] = f"{turn_id_prefix}_{i}"

            logger.info(
                f"Generator {config.module}.{config.function} produced {len(generated)} turns"
            )
            return generated

        except Exception as e:
            logger.error(f"Generator execution failed: {e}")
            return []

    def _load_generator_func(self, config: GeneratorConfig) -> GeneratorFunc | None:
        """
        Dynamically load a generator function from a module.

        Args:
            config: Generator configuration with module and function names

        Returns:
            Generator function or None if not found
        """
        try:
            module = importlib.import_module(config.module)
            func = getattr(module, config.function, None)

            if func is None:
                logger.error(
                    f"Function {config.function} not found in {config.module}"
                )
                return None

            return func

        except ImportError as e:
            logger.error(f"Failed to import generator module {config.module}: {e}")
            return None


__all__ = ["TurnExpander", "VariableSource"]
