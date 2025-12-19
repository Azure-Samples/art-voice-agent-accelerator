"""
Session State Synchronization
==============================

Shared utilities for synchronizing orchestrator state with MemoManager.
This module extracts common patterns from CascadeOrchestratorAdapter and
LiveOrchestrator to provide a single, tested, documented source of truth.

Why this exists:
- Both orchestrators need to sync active_agent, visited_agents, session_profile
- Duplicating this logic leads to subtle bugs when one is updated and not the other
- Junior developers can understand session flow from one well-documented file

Usage:
    from apps.artagent.backend.voice.shared.session_state import (
        sync_state_from_memo,
        sync_state_to_memo,
        SessionStateKeys,
    )

    # In orchestrator __init__:
    state = sync_state_from_memo(self._memo_manager)
    self.active = state.active_agent or self.active
    self.visited_agents = state.visited_agents
    self._system_vars = state.system_vars

    # At turn boundaries:
    sync_state_to_memo(
        memo_manager=self._memo_manager,
        active_agent=self.active,
        visited_agents=self.visited_agents,
        system_vars=self._system_vars,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.stateful.state_managment import MemoManager

try:
    from utils.ml_logging import get_logger

    logger = get_logger("voice.shared.session_state")
except ImportError:
    import logging

    logger = logging.getLogger("voice.shared.session_state")


# ─────────────────────────────────────────────────────────────────────────────
# Constants: Session State Keys
# ─────────────────────────────────────────────────────────────────────────────


class SessionStateKeys:
    """
    Standard keys used in MemoManager for session state.

    Using constants instead of magic strings:
    - Prevents typos (IDE catches undefined references)
    - Single place to document what each key means
    - Easy to find all usages via "Find References"
    """

    # Core orchestration state
    ACTIVE_AGENT = "active_agent"
    """Name of the currently active agent (e.g., "Concierge")"""

    VISITED_AGENTS = "visited_agents"
    """List of agent names visited in this session (for return_greeting logic)"""

    # User identity and context
    SESSION_PROFILE = "session_profile"
    """User profile dict with name, email, client_id, etc."""

    CLIENT_ID = "client_id"
    """Unique client identifier (e.g., phone number hash, AAD OID)"""

    CALLER_NAME = "caller_name"
    """Display name for the caller (for personalization)"""

    INSTITUTION_NAME = "institution_name"
    """Tenant/institution name (for white-label scenarios)"""

    CUSTOMER_INTELLIGENCE = "customer_intelligence"
    """CRM/personalization data for the customer"""

    # Handoff context
    PENDING_HANDOFF = "pending_handoff"
    """Dict with target_agent, reason, context when handoff is queued"""

    HANDOFF_CONTEXT = "handoff_context"
    """Context passed from previous agent during handoff"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SessionState:
    """
    Snapshot of session state from MemoManager.

    This is what gets passed to orchestrators after sync.
    All fields are Optional because MemoManager might not have them.
    """

    active_agent: str | None = None
    """Currently active agent name"""

    visited_agents: set[str] = field(default_factory=set)
    """Set of previously visited agents"""

    system_vars: dict[str, Any] = field(default_factory=dict)
    """Template variables for prompt rendering (session_profile, client_id, etc.)"""

    pending_handoff: dict[str, Any] | None = None
    """Queued handoff if state-based handoff is triggered"""


# ─────────────────────────────────────────────────────────────────────────────
# Sync Functions
# ─────────────────────────────────────────────────────────────────────────────


def sync_state_from_memo(
    memo_manager: MemoManager | None,
    *,
    available_agents: set[str] | None = None,
) -> SessionState:
    """
    Load session state from MemoManager.

    This is the READ side of state sync - called at:
    - Orchestrator initialization
    - Start of a new turn (optional, for cross-request consistency)

    Args:
        memo_manager: The session's MemoManager instance (can be None)
        available_agents: Set of valid agent names (for validation)

    Returns:
        SessionState with values from MemoManager (or defaults if not found)

    Example:
        state = sync_state_from_memo(self._memo_manager, available_agents=set(self.agents.keys()))
        if state.active_agent:
            self.active = state.active_agent
    """
    state = SessionState()

    if not memo_manager:
        return state

    mm = memo_manager
    K = SessionStateKeys

    # ─── Active Agent ───
    active = _get_from_memo(mm, K.ACTIVE_AGENT)
    if active and (available_agents is None or active in available_agents):
        state.active_agent = active
        logger.debug("Synced active_agent from MemoManager: %s", active)
    elif active and available_agents:
        logger.warning(
            "Active agent '%s' not in available agents, ignoring",
            active,
        )

    # ─── Visited Agents ───
    visited = _get_from_memo(mm, K.VISITED_AGENTS)
    if visited:
        state.visited_agents = set(visited) if isinstance(visited, (list, set)) else set()
        logger.debug("Synced visited_agents: %s", state.visited_agents)

    # ─── Session Profile (primary user context) ───
    session_profile = _get_from_memo(mm, K.SESSION_PROFILE)
    if session_profile and isinstance(session_profile, dict):
        state.system_vars[K.SESSION_PROFILE] = session_profile
        # Extract commonly-used fields to top level for prompt templates
        state.system_vars[K.CLIENT_ID] = session_profile.get("client_id")
        state.system_vars[K.CALLER_NAME] = session_profile.get("full_name")
        state.system_vars[K.CUSTOMER_INTELLIGENCE] = session_profile.get(
            "customer_intelligence", {}
        )
        if session_profile.get("institution_name"):
            state.system_vars[K.INSTITUTION_NAME] = session_profile["institution_name"]

        logger.info(
            "🔄 Restored session context | client_id=%s name=%s",
            session_profile.get("client_id"),
            session_profile.get("full_name"),
        )
    else:
        # Fallback: Load individual fields if session_profile not available
        for key in (K.CLIENT_ID, K.CALLER_NAME, K.CUSTOMER_INTELLIGENCE, K.INSTITUTION_NAME):
            val = _get_from_memo(mm, key)
            if val:
                state.system_vars[key] = val

    # ─── Pending Handoff (for state-based handoffs) ───
    pending = _get_from_memo(mm, K.PENDING_HANDOFF)
    if pending and isinstance(pending, dict):
        state.pending_handoff = pending
        logger.debug("Found pending handoff: %s", pending.get("target_agent"))

    return state


def sync_state_to_memo(
    memo_manager: MemoManager | None,
    *,
    active_agent: str | None = None,
    visited_agents: set[str] | None = None,
    system_vars: dict[str, Any] | None = None,
    clear_pending_handoff: bool = False,
) -> None:
    """
    Persist session state to MemoManager.

    This is the WRITE side of state sync - called at:
    - End of each turn
    - After agent handoffs
    - Before session ends (for next-session restore)

    Args:
        memo_manager: The session's MemoManager instance
        active_agent: Current agent name to persist
        visited_agents: Set of visited agents
        system_vars: Template variables to persist
        clear_pending_handoff: If True, clear the pending_handoff key

    Example:
        sync_state_to_memo(
            self._memo_manager,
            active_agent=self.active,
            visited_agents=self.visited_agents,
            system_vars=self._system_vars,
        )
    """
    if not memo_manager:
        return

    mm = memo_manager
    K = SessionStateKeys

    # ─── Active Agent ───
    if active_agent is not None:
        _set_to_memo(mm, K.ACTIVE_AGENT, active_agent)

    # ─── Visited Agents ───
    if visited_agents is not None:
        _set_to_memo(mm, K.VISITED_AGENTS, list(visited_agents))

    # ─── System Vars ───
    if system_vars:
        # Persist session_profile for next-session restore
        session_profile = system_vars.get(K.SESSION_PROFILE)
        if session_profile:
            _set_to_memo(mm, K.SESSION_PROFILE, session_profile)

        # Persist individual fields for backward compatibility
        for key in (K.CLIENT_ID, K.CALLER_NAME, K.CUSTOMER_INTELLIGENCE, K.INSTITUTION_NAME):
            if key in system_vars and system_vars[key]:
                _set_to_memo(mm, key, system_vars[key])

    # ─── Clear Pending Handoff ───
    if clear_pending_handoff:
        _set_to_memo(mm, K.PENDING_HANDOFF, None)

    logger.debug("Synced state to MemoManager | agent=%s", active_agent)


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_from_memo(mm: MemoManager, key: str) -> Any:
    """
    Get a value from MemoManager.

    Tries corememory first (persistent), then context (session-level).
    MemoManager always has these methods - no hasattr checks needed.
    """
    val = mm.get_value_from_corememory(key)
    if val is not None:
        return val
    return mm.get_context(key)


def _set_to_memo(mm: MemoManager, key: str, value: Any) -> None:
    """
    Set a value in MemoManager's corememory (persistent storage).

    MemoManager always has set_corememory - no hasattr checks needed.
    """
    mm.set_corememory(key, value)


__all__ = [
    "SessionStateKeys",
    "SessionState",
    "sync_state_from_memo",
    "sync_state_to_memo",
]
