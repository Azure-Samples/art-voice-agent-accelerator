"""
Naming Utilities for Agent and Scenario Identifiers
====================================================

Centralized utilities for normalizing, comparing, and managing agent/scenario names.
This ensures consistent naming across all modules and prevents case-sensitivity issues.

Key Principle:
- **Store with original casing** (preserves display names like "AuthAgent")
- **Lookup with case-insensitive matching** via find_agent_by_name()

Key Functions:
- normalize_agent_name: Canonical form for agent names (preserves original casing)
- find_agent_by_name: Case-insensitive lookup returning (actual_key, agent)
- names_equal: Case-insensitive comparison

Usage:
    from apps.artagent.backend.src.orchestration.naming import (
        normalize_agent_name,
        find_agent_by_name,
        names_equal,
    )

    # Store agents with original name (preserves casing)
    agents[config.name] = agent

    # Lookup agents case-insensitively
    actual_key, agent = find_agent_by_name(agents, "authagent")  # finds "AuthAgent"

    # Compare names case-insensitively
    if names_equal(user_input, "BankingConcierge"):
        ...
"""

from __future__ import annotations

import re

# Suffix added by UI for session-scoped agents
_SESSION_SUFFIX = " (session)"

# Core memory keys for scenario state (standardized)
SCENARIO_KEY_ACTIVE = "active_scenario_name"
SCENARIO_KEY_ALL = "session_scenarios_all"
SCENARIO_KEY_CONFIG = "session_scenario_config"
# Legacy key for backwards compatibility
SCENARIO_KEY_LEGACY = "scenario_name"


def normalize_agent_name(name: str | None) -> str | None:
    """
    Normalize an agent name for storage and display.

    - Strips whitespace
    - Removes session suffix if present
    - Preserves original casing (for display purposes)

    Args:
        name: Raw agent name (may have suffix, extra whitespace)

    Returns:
        Normalized name or None if input was None/empty
    """
    if not name:
        return None

    normalized = name.strip()

    # Remove session suffix (e.g., "MyAgent (session)" → "MyAgent")
    if normalized.endswith(_SESSION_SUFFIX):
        normalized = normalized[: -len(_SESSION_SUFFIX)].strip()

    return normalized if normalized else None


def agent_key(name: str | None) -> str | None:
    """
    Get the canonical key for agent dict lookups (case-insensitive).

    This should be used for all dict keys when storing/retrieving agents
    to ensure case-insensitive matching.

    Args:
        name: Agent name

    Returns:
        Lowercase key for dict operations, or None if input was None/empty
    """
    normalized = normalize_agent_name(name)
    return normalized.lower() if normalized else None


def normalize_scenario_name(name: str | None) -> str | None:
    """
    Normalize a scenario name for storage and display.

    - Strips whitespace
    - Preserves original casing (for display purposes)

    Args:
        name: Raw scenario name

    Returns:
        Normalized name or None if input was None/empty
    """
    if not name:
        return None

    normalized = name.strip()
    return normalized if normalized else None


def scenario_key(name: str | None) -> str | None:
    """
    Get the canonical key for scenario dict lookups (case-insensitive).

    This should be used for all dict keys when storing/retrieving scenarios
    to ensure case-insensitive matching.

    Args:
        name: Scenario name

    Returns:
        Lowercase key for dict operations, or None if input was None/empty
    """
    normalized = normalize_scenario_name(name)
    return normalized.lower() if normalized else None


def names_equal(name1: str | None, name2: str | None) -> bool:
    """
    Compare two names case-insensitively.

    Args:
        name1: First name
        name2: Second name

    Returns:
        True if names match (case-insensitive), False otherwise
    """
    key1 = agent_key(name1)
    key2 = agent_key(name2)

    if key1 is None or key2 is None:
        return key1 is None and key2 is None

    return key1 == key2


def normalize_agent_names(names: list[str]) -> list[str]:
    """
    Normalize a list of agent names, removing duplicates (case-insensitive).

    Preserves the original casing of the first occurrence of each name.

    Args:
        names: List of raw agent names

    Returns:
        Deduplicated list with normalized names
    """
    normalized: list[str] = []
    seen_keys: set[str] = set()

    for name in names:
        canonical = normalize_agent_name(name)
        if canonical:
            key = canonical.lower()
            if key not in seen_keys:
                normalized.append(canonical)
                seen_keys.add(key)

    return normalized


def find_agent_by_name(
    agents: dict[str, any],
    name: str | None,
) -> tuple[str | None, any]:
    """
    Find an agent in a dict by name (case-insensitive).

    Args:
        agents: Dict of agent_name → agent (may have mixed-case keys)
        name: Name to search for

    Returns:
        Tuple of (actual_key, agent) or (None, None) if not found
    """
    if not name:
        return None, None

    target_key = agent_key(name)
    if not target_key:
        return None, None

    # First try exact match (fastest)
    if name in agents:
        return name, agents[name]

    # Then try case-insensitive match
    for actual_key, agent in agents.items():
        if actual_key.lower() == target_key:
            return actual_key, agent

    return None, None


def find_scenario_by_name(
    scenarios: dict[str, any],
    name: str | None,
) -> tuple[str | None, any]:
    """
    Find a scenario in a dict by name (case-insensitive).

    Args:
        scenarios: Dict of scenario_name → scenario (may have mixed-case keys)
        name: Name to search for

    Returns:
        Tuple of (actual_key, scenario) or (None, None) if not found
    """
    if not name:
        return None, None

    target_key = scenario_key(name)
    if not target_key:
        return None, None

    # First try exact match (fastest)
    if name in scenarios:
        return name, scenarios[name]

    # Then try case-insensitive match
    for actual_key, scenario in scenarios.items():
        if actual_key.lower() == target_key:
            return actual_key, scenario

    return None, None


def get_scenario_from_corememory(memo_manager: any, default: str | None = None) -> str | None:
    """
    Get the active scenario name from MemoManager core memory.

    Checks keys in priority order:
    1. active_scenario_name (set by ScenarioBuilder)
    2. scenario_name (legacy, set by initial connection)

    Args:
        memo_manager: MemoManager instance with get_value_from_corememory method
        default: Default value if no scenario is set

    Returns:
        Active scenario name or default
    """
    if not memo_manager or not hasattr(memo_manager, "get_value_from_corememory"):
        return default

    # Try new key first
    scenario = memo_manager.get_value_from_corememory(SCENARIO_KEY_ACTIVE, None)
    if scenario:
        return scenario

    # Fall back to legacy key
    scenario = memo_manager.get_value_from_corememory(SCENARIO_KEY_LEGACY, None)
    if scenario:
        return scenario

    return default


def set_scenario_in_corememory(memo_manager: any, scenario_name: str | None) -> None:
    """
    Set the active scenario name in MemoManager core memory.

    Sets both the new key and legacy key for compatibility.

    Args:
        memo_manager: MemoManager instance with set_corememory method
        scenario_name: Scenario name to set (or None to clear)
    """
    if not memo_manager or not hasattr(memo_manager, "set_corememory"):
        return

    memo_manager.set_corememory(SCENARIO_KEY_ACTIVE, scenario_name)
    # Also set legacy key for backwards compatibility
    memo_manager.set_corememory(SCENARIO_KEY_LEGACY, scenario_name)
