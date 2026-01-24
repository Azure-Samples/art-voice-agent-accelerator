"""
Tests for Turn Generators (Phase 4)
===================================

Tests for template variable expansion and turn generators.
"""

from __future__ import annotations

import pytest

from tests.evaluation.generators import (
    TurnExpander,
    TurnGenerator,
    GeneratorRegistry,
    get_global_registry,
    turn_generator,
)
from tests.evaluation.generators.base import (
    GeneratedTurn,
    GeneratorConfig,
    get_registered_generator,
    list_registered_generators,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_fixtures():
    """Sample fixture data for template tests."""
    return {
        "customer": {
            "name": "Alice Brown",
            "ssn_last4": "1234",
            "account_id": "ACC-12345",
        },
        "test_amount": "500.00",
    }


@pytest.fixture
def sample_context():
    """Sample context data for template tests."""
    return {
        "scenario_name": "test_scenario",
        "institution": "Test Bank",
    }


@pytest.fixture
def expander(sample_fixtures, sample_context):
    """TurnExpander with sample data."""
    return TurnExpander(fixtures=sample_fixtures, context=sample_context)


# =============================================================================
# Template Variable Tests
# =============================================================================


class TestTemplateVariableExpansion:
    """Tests for {{variable}} expansion in user_input."""

    def test_simple_variable_substitution(self, expander, sample_fixtures):
        """Simple variable from context expands correctly."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Hello, my name is {{customer_name}}",
                "inject": {
                    "customer_name": {
                        "source": "fixture",
                        "key": "customer.name",
                    }
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert len(expanded) == 1
        assert expanded[0]["user_input"] == "Hello, my name is Alice Brown"
        assert "inject" not in expanded[0]  # inject config removed after processing

    def test_multiple_variables_in_one_turn(self, expander, sample_fixtures):
        """Multiple variables in same user_input expand correctly."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "I'm {{name}} with SSN ending {{ssn}}",
                "inject": {
                    "name": {"source": "fixture", "key": "customer.name"},
                    "ssn": {"source": "fixture", "key": "customer.ssn_last4"},
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0]["user_input"] == "I'm Alice Brown with SSN ending 1234"

    def test_context_source(self, expander, sample_context):
        """Variables from context expand correctly."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Welcome to {{institution}}",
                "inject": {
                    "institution": {"source": "context", "key": "institution"},
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0]["user_input"] == "Welcome to Test Bank"

    def test_literal_source(self, expander):
        """Literal values expand correctly."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Transfer {{amount}} dollars",
                "inject": {
                    "amount": {"source": "literal", "value": "100"},
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0]["user_input"] == "Transfer 100 dollars"

    def test_missing_variable_placeholder(self, expander):
        """Missing variable shows placeholder."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Hello {{unknown_var}}",
                "inject": {},  # No injection config
            }
        ]

        expanded = expander.expand_turns(turns)

        # Should show placeholder for unresolved variable
        assert "unknown_var" in expanded[0]["user_input"]

    def test_nested_key_access(self, expander, sample_fixtures):
        """Dot notation for nested keys works correctly."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Account {{account_id}}",
                "inject": {
                    "account_id": {"source": "fixture", "key": "customer.account_id"},
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0]["user_input"] == "Account ACC-12345"

    def test_no_templates_passthrough(self, expander):
        """Turns without templates pass through unchanged."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "What's my balance?",
                "expectations": {"tools_called": ["get_balance"]},
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0] == turns[0]

    def test_preserves_expectations(self, expander, sample_fixtures):
        """Expansion preserves expectations and other fields."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "My account is {{account_id}}",
                "inject": {
                    "account_id": {"source": "fixture", "key": "customer.account_id"},
                },
                "expectations": {
                    "tools_called": ["verify_account"],
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded[0]["expectations"]["tools_called"] == ["verify_account"]


# =============================================================================
# Turn Generator Tests
# =============================================================================


class TestTurnGenerators:
    """Tests for turn generator functionality."""

    def test_builtin_identity_verification(self):
        """Built-in identity verification generator works."""
        from tests.evaluation.generators.builtin import generate_identity_verification

        params = {"name": "Bob Smith", "ssn_last4": "5678"}
        context = {"turn_id_prefix": "verify"}

        turns = generate_identity_verification(params, context)

        assert len(turns) == 2
        assert "Bob Smith" in turns[0]["user_input"]
        assert "5678" in turns[0]["user_input"]
        assert turns[0]["expectations"]["tools_called"] == ["verify_client_identity"]

    def test_builtin_balance_inquiry(self):
        """Built-in balance inquiry generator works."""
        from tests.evaluation.generators.builtin import generate_balance_inquiry

        params = {"account_type": "savings"}
        context = {"turn_id_prefix": "bal"}

        turns = generate_balance_inquiry(params, context)

        assert len(turns) == 1
        assert "savings" in turns[0]["user_input"]

    def test_builtin_handoff_request(self):
        """Built-in handoff request generator works."""
        from tests.evaluation.generators.builtin import generate_handoff_request

        params = {"target_agent": "CardAgent", "topic": "credit cards"}
        context = {"turn_id_prefix": "handoff"}

        turns = generate_handoff_request(params, context)

        assert len(turns) == 1
        assert "credit cards" in turns[0]["user_input"]
        assert turns[0]["expectations"]["handoff"]["to_agent"] == "CardAgent"

    def test_builtin_variation_set(self):
        """Built-in variation set generator creates multiple turns."""
        from tests.evaluation.generators.builtin import generate_variation_set

        params = {
            "base_input": "What's my {account_type} balance?",
            "variations": {"account_type": ["checking", "savings", "investment"]},
            "expectations": {"tools_called": ["get_balance"]},
        }
        context = {"turn_id_prefix": "var"}

        turns = generate_variation_set(params, context)

        assert len(turns) == 3
        assert "checking" in turns[0]["user_input"]
        assert "savings" in turns[1]["user_input"]
        assert "investment" in turns[2]["user_input"]

    def test_builtin_edge_cases(self):
        """Built-in edge cases generator creates test cases."""
        from tests.evaluation.generators.builtin import generate_edge_cases

        params = {"category": "general"}
        context = {"turn_id_prefix": "edge"}

        turns = generate_edge_cases(params, context)

        assert len(turns) >= 3
        assert all("edge_case_name" in t.get("metadata", {}) for t in turns)

    def test_generator_in_expander(self, expander):
        """Generator referenced in turn is executed by expander."""
        turns = [
            {
                "turn_id": "gen_1",
                "generator": "builtin.balance_inquiry",
                "params": {"account_type": "checking"},
            }
        ]

        expanded = expander.expand_turns(turns)

        assert len(expanded) == 1
        assert "checking" in expanded[0]["user_input"]

    def test_mixed_static_and_generated_turns(self, expander):
        """Mix of static turns and generators works."""
        turns = [
            {
                "turn_id": "turn_1",
                "user_input": "Hello",
            },
            {
                "turn_id": "gen_1",
                "generator": "builtin.balance_inquiry",
            },
            {
                "turn_id": "turn_2",
                "user_input": "Goodbye",
            },
        ]

        expanded = expander.expand_turns(turns)

        assert len(expanded) == 3
        assert expanded[0]["user_input"] == "Hello"
        assert "balance" in expanded[1]["user_input"].lower()
        assert expanded[2]["user_input"] == "Goodbye"


# =============================================================================
# Generator Registry Tests
# =============================================================================


class TestGeneratorRegistry:
    """Tests for GeneratorRegistry."""

    def test_register_and_get_function(self):
        """Function registration and retrieval works."""
        registry = GeneratorRegistry()

        def my_generator(params, context):
            return [{"turn_id": "test", "user_input": "test"}]

        registry.register_func("test.generator", my_generator)

        assert registry.get("test.generator") == my_generator

    def test_register_class_generator(self):
        """Class-based generator registration works."""

        class MyGenerator(TurnGenerator):
            def generate(self, params, context):
                return [GeneratedTurn(turn_id="test", user_input="test")]

        registry = GeneratorRegistry()
        registry.register_class("test.class_gen", MyGenerator)

        assert registry.get("test.class_gen") == MyGenerator

    def test_execute_function_generator(self):
        """Execute function generator returns turns."""
        registry = GeneratorRegistry()

        def my_gen(params, context):
            count = params.get("count", 1)
            return [
                {"turn_id": f"t_{i}", "user_input": f"Turn {i}"}
                for i in range(count)
            ]

        registry.register_func("test.gen", my_gen)
        turns = registry.execute("test.gen", {"count": 3}, {})

        assert len(turns) == 3

    def test_list_generators(self):
        """List generators returns registered names."""
        registry = GeneratorRegistry()
        registry.register_func("a.gen", lambda p, c: [])
        registry.register_func("b.gen", lambda p, c: [])

        names = registry.list_generators()

        assert "a.gen" in names
        assert "b.gen" in names

    def test_clear_registry(self):
        """Clear removes all registered generators."""
        registry = GeneratorRegistry()
        registry.register_func("test.gen", lambda p, c: [])

        registry.clear()

        assert registry.list_generators() == []


# =============================================================================
# Decorator Tests
# =============================================================================


class TestTurnGeneratorDecorator:
    """Tests for @turn_generator decorator."""

    def test_decorator_registers_function(self):
        """Decorated function is registered globally."""
        # Note: Built-in generators are already registered

        func = get_registered_generator("builtin.identity_verification")
        assert func is not None
        assert callable(func)

    def test_list_registered_includes_decorators(self):
        """list_registered_generators includes decorated functions."""
        names = list_registered_generators()

        assert "builtin.identity_verification" in names
        assert "builtin.balance_inquiry" in names


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in generators module."""

    def test_invalid_generator_config(self, expander):
        """Invalid generator config is handled gracefully."""
        turns = [
            {
                "turn_id": "bad_gen",
                "generator": {
                    "module": "nonexistent.module",
                    "function": "nonexistent_func",
                },
            }
        ]

        expanded = expander.expand_turns(turns)

        # Should return empty list for failed generator
        assert expanded == []

    def test_unknown_generator_name(self, expander):
        """Unknown generator name is handled gracefully."""
        turns = [
            {
                "turn_id": "bad_gen",
                "generator": "nonexistent.generator",
            }
        ]

        expanded = expander.expand_turns(turns)

        assert expanded == []

    def test_empty_turns_list(self, expander):
        """Empty turns list returns empty."""
        expanded = expander.expand_turns([])
        assert expanded == []

    def test_generator_exception_handled(self):
        """Generator exception doesn't crash expansion."""
        registry = GeneratorRegistry()

        def bad_generator(params, context):
            raise ValueError("Generator error")

        registry.register_func("test.bad", bad_generator)
        result = registry.execute("test.bad", {}, {})

        # Should return empty list on error
        assert result == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for generators with scenario YAML structure."""

    def test_full_scenario_expansion(self):
        """Full scenario with generators expands correctly."""
        fixtures = {
            "user": {"name": "John Doe", "ssn": "9999"},
        }
        context = {"scenario_name": "integration_test"}

        expander = TurnExpander(fixtures=fixtures, context=context)

        turns = [
            # Static turn
            {"turn_id": "turn_1", "user_input": "Hi there"},
            # Template variable turn
            {
                "turn_id": "turn_2",
                "user_input": "My name is {{name}}",
                "inject": {"name": {"source": "fixture", "key": "user.name"}},
            },
            # Generator turn
            {
                "turn_id": "gen_1",
                "generator": "builtin.balance_inquiry",
                "params": {"account_type": "checking"},
            },
        ]

        expanded = expander.expand_turns(turns)

        assert len(expanded) == 3
        assert expanded[0]["user_input"] == "Hi there"
        assert expanded[1]["user_input"] == "My name is John Doe"
        assert "checking" in expanded[2]["user_input"]
