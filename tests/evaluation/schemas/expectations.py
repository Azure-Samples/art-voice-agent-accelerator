"""
Scenario Expectation Schemas
============================

Models for defining expected behavior in evaluation scenarios.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScenarioExpectations(BaseModel):
    """
    Expected behavior for a scenario turn (used for validation).

    Supported Attributes
    --------------------
    Tools:
        tools_called: List[str]
            Required tools that MUST be called (recall check).
            Test fails if any are missing.

        tools_optional: List[str]
            Optional tools (won't fail if missing, but won't hurt if called).

        tools_forbidden: List[str]
            Tools that MUST NOT be called (negative test).
            Test fails if any are called.

    Handoffs:
        handoff: Dict[str, str]
            Expected handoff: {"to_agent": "AgentName"}.
            Test fails if handoff doesn't happen to correct agent.

        no_handoff: bool
            If true, asserts NO handoff should occur this turn.

    Response Constraints:
        response_constraints: Dict[str, Any]
            max_tokens: int - Max response tokens (verbosity check)
            must_include: List[str] - Substrings that MUST appear in response
            must_not_include: List[str] - Substrings that MUST NOT appear
            must_ask_for: List[str] - Questions/prompts that should appear

    Grounding:
        grounding_required: List[str]
            Human-readable descriptions of facts that must be grounded.

        min_grounded_ratio: float
            Minimum grounded span ratio (0.0-1.0, default: 0.0).

    Performance:
        max_latency_ms: int
            Maximum allowed E2E latency in milliseconds.

    Example YAML
    ------------
    ```yaml
    turns:
      - turn_id: turn_1
        user_input: "Check my account balance"
        expectations:
          tools_called:
            - verify_client_identity
            - get_account_balance
          tools_forbidden:
            - transfer_funds
          handoff:
            to_agent: AccountAgent
          response_constraints:
            max_tokens: 100
            must_include:
              - "balance"
              - "$"
            must_not_include:
              - "error"
          min_grounded_ratio: 0.7
          max_latency_ms: 5000
    ```
    """

    # Tool expectations
    tools_called: List[str] = Field(
        default_factory=list,
        description="Required tool names that MUST be called (recall check)",
    )
    tools_optional: List[str] = Field(
        default_factory=list,
        description="Optional tools (won't fail if missing)",
    )
    tools_forbidden: List[str] = Field(
        default_factory=list,
        description="Tools that MUST NOT be called",
    )

    # Handoff expectations
    handoff: Optional[Dict[str, str]] = Field(
        None,
        description="Expected handoff: {'to_agent': 'AgentName'}",
    )
    no_handoff: bool = Field(
        default=False,
        description="Assert that NO handoff occurs this turn",
    )

    # Response constraints
    response_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Response constraints: max_tokens, must_include, must_not_include, must_ask_for",
    )

    # Grounding expectations
    grounding_required: List[str] = Field(
        default_factory=list,
        description="Human-readable grounding requirements",
    )
    min_grounded_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum grounded span ratio (0.0-1.0)",
    )

    # Performance expectations
    max_latency_ms: Optional[int] = Field(
        None,
        description="Maximum allowed E2E latency in milliseconds",
    )


__all__ = [
    "ScenarioExpectations",
]
