"""
Built-in Turn Generators (Phase 4)
==================================

Pre-built generators for common evaluation patterns.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base import GeneratedTurn, turn_generator


@turn_generator("builtin.identity_verification")
def generate_identity_verification(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate identity verification turns.

    Params:
        name: Customer name (default: "Alice Brown")
        ssn_last4: Last 4 of SSN (default: "1234")
        include_confirmation: Include confirmation turn (default: True)
    """
    name = params.get("name", "Alice Brown")
    ssn_last4 = params.get("ssn_last4", "1234")
    include_confirmation = params.get("include_confirmation", True)
    prefix = context.get("turn_id_prefix", "verify")

    turns = [
        {
            "turn_id": f"{prefix}_1",
            "user_input": f"Hi, my name is {name} and my last four SSN digits are {ssn_last4}.",
            "expectations": {
                "tools_called": ["verify_client_identity"],
            },
        }
    ]

    if include_confirmation:
        turns.append(
            {
                "turn_id": f"{prefix}_2",
                "user_input": "Yes, that's correct.",
                "expectations": {
                    "tools_called": [],  # May call get_user_profile
                },
            }
        )

    return turns


@turn_generator("builtin.balance_inquiry")
def generate_balance_inquiry(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate account balance inquiry turns.

    Params:
        account_type: Type of account (default: "checking")
        expect_tool: Expected tool call (default: "get_account_balance")
    """
    account_type = params.get("account_type", "checking")
    expect_tool = params.get("expect_tool", "get_account_balance")
    prefix = context.get("turn_id_prefix", "balance")

    return [
        {
            "turn_id": f"{prefix}_1",
            "user_input": f"What's my {account_type} account balance?",
            "expectations": {
                "tools_called": [expect_tool],
            },
        }
    ]


@turn_generator("builtin.handoff_request")
def generate_handoff_request(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate a handoff request turn.

    Params:
        target_agent: Agent to hand off to (required)
        topic: Topic to mention in request (e.g., "credit cards", "investments")
    """
    target_agent = params.get("target_agent", "specialist")
    topic = params.get("topic", "that topic")
    prefix = context.get("turn_id_prefix", "handoff")

    return [
        {
            "turn_id": f"{prefix}_1",
            "user_input": f"Can you transfer me to someone who can help with {topic}?",
            "expectations": {
                "tools_called": ["handoff_to_agent"],
                "handoff": {"to_agent": target_agent},
            },
        }
    ]


@turn_generator("builtin.multi_turn_conversation")
def generate_multi_turn_conversation(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate a multi-turn conversation sequence.

    Params:
        messages: List of user messages to convert to turns
        base_expectations: Default expectations for all turns
    """
    messages = params.get("messages", [])
    base_expectations = params.get("base_expectations", {})
    prefix = context.get("turn_id_prefix", "conv")

    turns = []
    for i, message in enumerate(messages):
        if isinstance(message, str):
            turns.append(
                {
                    "turn_id": f"{prefix}_{i + 1}",
                    "user_input": message,
                    "expectations": base_expectations.copy(),
                }
            )
        elif isinstance(message, dict):
            turn = {
                "turn_id": message.get("turn_id", f"{prefix}_{i + 1}"),
                "user_input": message.get("input", message.get("user_input", "")),
                "expectations": {**base_expectations, **message.get("expectations", {})},
            }
            turns.append(turn)

    return turns


@turn_generator("builtin.variation_set")
def generate_variation_set(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate multiple variations of the same turn for testing robustness.

    Params:
        base_input: Base user input with {placeholder} markers
        variations: Dict mapping placeholder to list of values
        expectations: Expected outcomes (same for all variations)

    Example:
        params:
          base_input: "What's my {account_type} balance?"
          variations:
            account_type: ["checking", "savings", "investment"]
          expectations:
            tools_called: [get_account_balance]
    """
    base_input = params.get("base_input", "")
    variations = params.get("variations", {})
    expectations = params.get("expectations", {})
    prefix = context.get("turn_id_prefix", "var")

    # If no variations, return single turn
    if not variations:
        return [
            {
                "turn_id": f"{prefix}_1",
                "user_input": base_input,
                "expectations": expectations,
            }
        ]

    # Generate cartesian product of all variations
    turns = []
    variation_key = list(variations.keys())[0]  # Start with first key
    variation_values = variations[variation_key]

    for i, value in enumerate(variation_values):
        user_input = base_input.replace(f"{{{variation_key}}}", str(value))
        turns.append(
            {
                "turn_id": f"{prefix}_{i + 1}",
                "user_input": user_input,
                "expectations": expectations.copy(),
                "metadata": {
                    "variation": {variation_key: value},
                },
            }
        )

    return turns


@turn_generator("builtin.edge_cases")
def generate_edge_cases(
    params: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate edge case turns for robustness testing.

    Params:
        category: Edge case category (default: "general")
            - "general": Generic edge cases
            - "banking": Banking-specific edge cases
            - "empty": Empty/minimal inputs
    """
    category = params.get("category", "general")
    prefix = context.get("turn_id_prefix", "edge")

    edge_cases = {
        "general": [
            ("Very short input", "Hi"),
            ("Numbers only", "12345"),
            ("Special characters", "Hello! How are you? :)"),
            ("Long input", "I have a question about " + "my account " * 20 + "balance"),
        ],
        "banking": [
            ("Large amount", "Transfer $999,999,999 to my savings"),
            ("Negative amount", "Transfer -$100 to checking"),
            ("Multiple accounts", "Show balances for all my accounts"),
            ("Sensitive info", "My SSN is 123-45-6789"),
        ],
        "empty": [
            ("Whitespace", "   "),
            ("Single char", "?"),
            ("Just emoji", "👋"),
        ],
    }

    cases = edge_cases.get(category, edge_cases["general"])

    return [
        {
            "turn_id": f"{prefix}_{i + 1}",
            "user_input": user_input,
            "expectations": {},
            "metadata": {
                "edge_case_name": name,
                "category": category,
            },
        }
        for i, (name, user_input) in enumerate(cases)
    ]


__all__ = [
    "generate_identity_verification",
    "generate_balance_inquiry",
    "generate_handoff_request",
    "generate_multi_turn_conversation",
    "generate_variation_set",
    "generate_edge_cases",
]
