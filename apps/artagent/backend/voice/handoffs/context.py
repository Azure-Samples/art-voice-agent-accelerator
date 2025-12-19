"""
Handoff Context, Result, and Helper Functions
==============================================

This module provides the core handoff data structures and helper functions
used by all orchestrators (LiveOrchestrator, CascadeAdapter) to build
consistent handoff context during agent transitions.

Dataclasses:
- **HandoffContext**: Built when a handoff is detected, contains all
  information needed to switch agents (source, target, reason, user context).
- **HandoffResult**: Returned by execute_handoff(), signals success/failure
  and provides data for the orchestrator to complete the switch.

Helper Functions:
- **sanitize_handoff_context**: Removes control flags from handoff context
- **build_handoff_system_vars**: Builds system_vars dict for agent switches
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Control flags that should never appear in handoff_context passed to agents
_HANDOFF_CONTROL_FLAGS = frozenset(
    {
        "success",
        "handoff",
        "target_agent",
        "message",
        "handoff_summary",
        "should_interrupt_playback",
        "session_overrides",
    }
)


def sanitize_handoff_context(raw: Any) -> dict[str, Any]:
    """
    Remove control flags from raw handoff context so prompt variables stay clean.

    Control flags like 'success', 'target_agent', 'handoff_summary' are internal
    signaling mechanisms and should not be passed to agent prompts.

    Args:
        raw: Raw handoff context dict (or non-dict value which returns empty dict)

    Returns:
        Cleaned dict with control flags and empty values removed.

    Example:
        raw = {"reason": "fraud inquiry", "success": True, "target_agent": "FraudAgent"}
        clean = sanitize_handoff_context(raw)
        # clean = {"reason": "fraud inquiry"}
    """
    if not isinstance(raw, dict):
        return {}

    return {
        key: value
        for key, value in raw.items()
        if key not in _HANDOFF_CONTROL_FLAGS and value not in (None, "", [], {})
    }


def build_handoff_system_vars(
    *,
    source_agent: str,
    target_agent: str,
    tool_result: dict[str, Any],
    tool_args: dict[str, Any],
    current_system_vars: dict[str, Any],
    user_last_utterance: str | None = None,
    share_context: bool = True,
    greet_on_switch: bool = True,
) -> dict[str, Any]:
    """
    Build system_vars dict for agent handoff from tool result and session state.

    This is the shared logic used by all orchestrators to build consistent
    handoff context. It:
    1. Extracts and sanitizes handoff_context from tool result
    2. Builds handoff_reason from multiple fallback sources
    3. Carries forward key session variables (profile, client_id, etc.)
    4. Applies session_overrides if present
    5. Adds handoff template vars for Jinja prompts (is_handoff, share_context, greet_on_switch)

    Args:
        source_agent: Name of the agent initiating the handoff
        target_agent: Name of the agent receiving the handoff
        tool_result: Result dict from the handoff tool execution
        tool_args: Arguments passed to the handoff tool
        current_system_vars: Current session's system_vars dict
        user_last_utterance: User's most recent speech (for context)
        share_context: Whether to pass full context to target agent (default True)
        greet_on_switch: Whether target agent should announce the handoff (default True)

    Returns:
        system_vars dict ready for agent.apply_session()

    Example:
        ctx = build_handoff_system_vars(
            source_agent="Concierge",
            target_agent="FraudAgent",
            tool_result={"handoff_summary": "User suspects fraud", "handoff_context": {...}},
            tool_args={"reason": "fraud inquiry"},
            current_system_vars={"session_profile": {...}, "client_id": "123"},
            user_last_utterance="I think someone stole my card",
            share_context=True,
            greet_on_switch=False,  # Discrete handoff
        )
    """
    # Extract and sanitize handoff_context from tool result
    raw_handoff_context = (
        tool_result.get("handoff_context") if isinstance(tool_result, dict) else {}
    )
    handoff_context: dict[str, Any] = {}
    if isinstance(raw_handoff_context, dict):
        handoff_context = dict(raw_handoff_context)

    # Add user utterance to handoff_context if available
    if user_last_utterance:
        handoff_context.setdefault("user_last_utterance", user_last_utterance)
        handoff_context.setdefault("details", user_last_utterance)

    # Clean control flags from handoff_context
    handoff_context = sanitize_handoff_context(handoff_context)

    # Extract session_overrides if present and valid
    session_overrides = tool_result.get("session_overrides")
    if not isinstance(session_overrides, dict) or not session_overrides:
        session_overrides = None

    # Build reason from multiple fallback sources
    handoff_reason = (
        tool_result.get("handoff_summary")
        or handoff_context.get("reason")
        or tool_args.get("reason", "unspecified")
    )

    # Build details from multiple fallback sources
    details = (
        handoff_context.get("details")
        or tool_result.get("details")
        or tool_args.get("details")
        or user_last_utterance
    )

    # Build the system_vars dict
    ctx: dict[str, Any] = {
        "handoff_reason": handoff_reason,
        "previous_agent": source_agent,
        "active_agent": target_agent,
        "handoff_context": handoff_context if share_context else {},
        "handoff_message": tool_result.get("message"),
        # Template variables for Jinja prompts
        "is_handoff": True,
        "share_context": share_context,
        "greet_on_switch": greet_on_switch,
    }

    if details and share_context:
        ctx["details"] = details

    if user_last_utterance and share_context:
        ctx["user_last_utterance"] = user_last_utterance

    if session_overrides:
        ctx["session_overrides"] = session_overrides

    # Carry forward key session variables from current session (if sharing context)
    if share_context:
        for key in ("session_profile", "client_id", "customer_intelligence", "institution_name"):
            if key in current_system_vars:
                ctx[key] = current_system_vars[key]

    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class HandoffContext:
    """
    Context passed during agent handoffs.

    Captures all relevant information for smooth agent transitions:
    - Source and target agent identifiers
    - User's last utterance for context continuity
    - Session variables and overrides
    - Custom handoff metadata

    Attributes:
        source_agent: Name of the agent initiating the handoff
        target_agent: Name of the agent receiving the handoff
        reason: Why the handoff is occurring
        user_last_utterance: User's most recent speech (for context)
        context_data: Additional structured context (caller info, etc.)
        session_overrides: Configuration to apply to the new agent
        greeting: Optional greeting for the new agent to speak

    Example:
        context = HandoffContext(
            source_agent="Concierge",
            target_agent="FraudAgent",
            reason="User reported suspicious card activity",
            user_last_utterance="I think my card was stolen",
            context_data={"caller_name": "John", "account_type": "Premium"},
        )

        # Convert to system_vars for agent.apply_session()
        vars = context.to_system_vars()
    """

    source_agent: str
    target_agent: str
    reason: str = ""
    user_last_utterance: str = ""
    context_data: dict[str, Any] = field(default_factory=dict)
    session_overrides: dict[str, Any] = field(default_factory=dict)
    greeting: str | None = None

    def to_system_vars(self) -> dict[str, Any]:
        """
        Convert to system_vars dict for agent session application.

        The resulting dict is passed to agent.apply_session() which uses
        these values to render the system prompt (via Handlebars) and
        configure the session.

        Returns:
            Dict with keys like 'previous_agent', 'active_agent',
            'handoff_reason', 'handoff_context', etc.
        """
        vars_dict: dict[str, Any] = {
            "previous_agent": self.source_agent,
            "active_agent": self.target_agent,
            "handoff_reason": self.reason,
        }
        if self.user_last_utterance:
            vars_dict["user_last_utterance"] = self.user_last_utterance
            vars_dict["details"] = self.user_last_utterance
        if self.context_data:
            vars_dict["handoff_context"] = self.context_data
        if self.session_overrides:
            vars_dict["session_overrides"] = self.session_overrides
        if self.greeting:
            vars_dict["greeting"] = self.greeting
        return vars_dict


@dataclass
class HandoffResult:
    """
    Result from a handoff operation.

    This is a **signal** returned by execute_handoff() that tells the
    orchestrator what to do next. The actual agent switch (session.update)
    happens in the orchestrator based on this result.

    Attributes:
        success: Whether the handoff completed successfully
        target_agent: The agent to switch to (if success=True)
        message: Optional message to speak after handoff
        error: Error message if handoff failed
        should_interrupt: Whether to cancel current TTS playback

    Flow:
        HandoffResult(success=True, target="FraudAgent")
               ↓
        Orchestrator._switch_to_agent("FraudAgent", system_vars)
               ↓
        Agent.apply_session(conn, system_vars)
               ↓
        conn.session.update(session=RequestSession(...))

    Example:
        result = await strategy.execute_handoff(tool_name, args, context)
        if result.success and result.target_agent:
            await self._switch_to_agent(result.target_agent, context.to_system_vars())
        else:
            logger.warning("Handoff failed: %s", result.error)
    """

    success: bool
    target_agent: str | None = None
    message: str | None = None
    error: str | None = None
    should_interrupt: bool = True


__all__ = [
    "HandoffContext",
    "HandoffResult",
    "sanitize_handoff_context",
    "build_handoff_system_vars",
]
