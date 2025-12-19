"""
Agent Scenarios
===============

Scenario-based configurations for agent orchestration.
Allows customizing agents, tools, and templates per use case.

Example Scenarios:
- banking: Private banking with personalized greetings, customer intelligence
- healthcare: HIPAA-compliant verification flows
- retail: Order status and returns

Usage:
    from apps.artagent.backend.registries.scenariostore import load_scenario, get_scenario_agents

    # Load a scenario configuration
    scenario = load_scenario("banking")

    # Get agents with scenario overrides applied
    agents = get_scenario_agents("banking")
"""

from .loader import (
    AgentOverride,
    ScenarioConfig,
    get_scenario_agents,
    get_scenario_start_agent,
    get_scenario_template_vars,
    list_scenarios,
    load_scenario,
)

__all__ = [
    "load_scenario",
    "get_scenario_agents",
    "get_scenario_start_agent",
    "get_scenario_template_vars",
    "list_scenarios",
    "ScenarioConfig",
    "AgentOverride",
]
