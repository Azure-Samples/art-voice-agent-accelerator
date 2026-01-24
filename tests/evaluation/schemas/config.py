"""
Evaluation Configuration Schemas
================================

Configuration models for model profiles and session-based scenarios.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ModelProfile(BaseModel):
    """
    Reusable model configuration template for DRY variant definitions.

    Instead of repeating model config for every agent in every variant,
    define named profiles once and reference them:

    ```yaml
    model_profiles:
      gpt4o_fast:
        deployment_id: gpt-4o
        endpoint_preference: chat
        temperature: 0.6
        max_tokens: 200

      o3_reasoning:
        deployment_id: o3-mini
        endpoint_preference: responses
        reasoning_effort: medium
        max_completion_tokens: 2000

    variants:
      - variant_id: baseline
        model_profile: gpt4o_fast  # All agents use this

      - variant_id: reasoning
        model_profile: o3_reasoning
        agent_overrides:  # Optional per-agent exceptions
          - agent: CardRecommendation
            reasoning_effort: low
    ```
    """

    deployment_id: str = Field(
        ..., description="Model deployment ID (e.g., 'gpt-4o', 'o3-mini')"
    )
    endpoint_preference: Literal["chat", "responses"] = Field(
        default="chat",
        description="API type: 'chat' (Chat Completions) or 'responses' (Responses API)",
    )

    # Chat Completions API parameters
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Temperature (Chat API)"
    )
    top_p: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Top-p sampling (Chat API)"
    )
    max_tokens: Optional[int] = Field(None, gt=0, description="Max tokens (Chat API)")

    # Responses API parameters
    max_completion_tokens: Optional[int] = Field(
        None, gt=0, description="Max completion tokens (Responses API)"
    )
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = Field(
        None, description="Reasoning effort for o-series models"
    )
    include_reasoning: Optional[bool] = Field(
        None, description="Include reasoning tokens in response"
    )

    # Advanced sampling (GPT-5+)
    min_p: Optional[float] = Field(None, description="Minimum probability threshold")
    typical_p: Optional[float] = Field(None, description="Typical sampling")

    def to_override_dict(self) -> Dict[str, Any]:
        """Convert to model_override dict for agent configuration."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class SessionHandoffConfig(BaseModel):
    """
    Handoff edge configuration for session-based scenarios.

    Mirrors the scenariostore HandoffConfig format but for evaluation scenarios.
    """

    from_agent: str = Field(
        ..., alias="from", description="Source agent initiating the handoff"
    )
    to_agent: str = Field(
        ..., alias="to", description="Target agent receiving the handoff"
    )
    tool: str = Field(default="handoff_to_agent", description="Handoff tool name")
    type: str = Field(default="announced", description="'discrete' (silent) or 'announced'")
    share_context: bool = Field(default=True, description="Pass conversation context")
    handoff_condition: str = Field(
        default="",
        description="Prompt text describing when to trigger this handoff",
    )

    model_config = {"populate_by_name": True}


class SessionAgentConfig(BaseModel):
    """
    Configuration for session-based scenarios that mirrors orchestrator.yml format.

    This allows evaluation scenarios to define:
    - Which agents to include (all discovered or filtered list)
    - Start agent for the session
    - Explicit handoff edges
    - Generic handoff configuration

    Example YAML
    ------------
    ```yaml
    session_config:
      # Use all discovered agents or specify a filter
      agents: all  # or ["BankingConcierge", "CardRecommendation"]

      # Starting agent
      start_agent: BankingConcierge

      # Explicit handoff edges (optional - like scenariostore)
      handoffs:
        - from: BankingConcierge
          to: CardRecommendation
          tool: handoff_card_recommendation
          type: discrete
          handoff_condition: |
            Transfer when customer asks about credit cards.

      # Generic handoff configuration
      generic_handoff:
        enabled: true
        allowed_targets: []  # Empty = all agents allowed
        default_type: announced
    ```
    """

    # Agent selection: "all" or list of agent names
    agents: Union[str, List[str]] = Field(
        default="all",
        description="'all' to use all discovered agents, or list of agent names to filter",
    )

    # Agent patterns for regex-based filtering (optional)
    agent_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns to filter agents (e.g., ['Banking.*', 'Card.*'])",
    )

    # Agents to exclude (applied after filtering)
    exclude_agents: List[str] = Field(
        default_factory=list,
        description="Agent names to exclude from the session",
    )

    # Starting agent
    start_agent: str = Field(..., description="Agent to start the session with")

    # Default handoff behavior
    handoff_type: str = Field(
        default="announced",
        description="Default handoff type: 'discrete' or 'announced'",
    )

    # Explicit handoff edges
    handoffs: List[SessionHandoffConfig] = Field(
        default_factory=list,
        description="Explicit handoff edges defining agent routing",
    )

    # Generic handoff configuration
    generic_handoff: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Generic handoff_to_agent configuration",
    )

    # Agent defaults (template variables, voice, etc.)
    agent_defaults: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default settings applied to all agents",
    )

    def get_agent_list(self, discovered_agents: Dict[str, Any]) -> List[str]:
        """
        Determine the final agent list based on configuration.

        Args:
            discovered_agents: Dict of agent_name -> agent from discover_agents()

        Returns:
            List of agent names to include in the session
        """
        all_agent_names = set(discovered_agents.keys())

        # Start with all or filtered list
        if isinstance(self.agents, str) and self.agents.lower() == "all":
            candidates = all_agent_names
        elif isinstance(self.agents, list):
            candidates = set(self.agents) & all_agent_names
        else:
            candidates = all_agent_names

        # Apply patterns if specified
        if self.agent_patterns:
            pattern_matches = set()
            for pattern in self.agent_patterns:
                regex = re.compile(pattern)
                pattern_matches.update(
                    name for name in all_agent_names if regex.match(name)
                )
            # If we have explicit agents list, intersect; otherwise use patterns
            if isinstance(self.agents, list):
                candidates = candidates & pattern_matches
            else:
                candidates = pattern_matches

        # Remove excluded agents
        candidates -= set(self.exclude_agents)

        return sorted(list(candidates))


__all__ = [
    "ModelProfile",
    "SessionHandoffConfig",
    "SessionAgentConfig",
]
