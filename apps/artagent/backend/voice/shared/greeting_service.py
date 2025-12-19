"""
Greeting Service
================

Centralized greeting resolution for voice orchestrators.

Consolidates greeting logic from:
- HandoffService.select_greeting()
- MediaHandler._derive_default_greeting()
- UnifiedAgent.render_greeting()

Provides a single API for determining what greeting to play.

Usage:
    from apps.artagent.backend.voice.shared.greeting_service import (
        GreetingService,
        resolve_greeting,
    )

    # Quick resolution
    greeting = resolve_greeting(
        agent=my_agent,
        context={"caller_name": "John"},
        is_first_visit=True,
    )

    # Or use service for more control
    service = GreetingService()
    greeting = service.select_greeting(
        agent=my_agent,
        context=context,
        greet_on_switch=True,
        is_first_visit=True,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
    from src.stateful.state_managment import MemoManager

try:
    from utils.ml_logging import get_logger
    logger = get_logger("voice.shared.greeting_service")
except ImportError:
    import logging
    logger = logging.getLogger("voice.shared.greeting_service")


@dataclass
class GreetingContext:
    """
    Context for greeting template rendering.

    Contains all variables that can be used in Jinja greeting templates.
    """

    caller_name: str | None = None
    client_id: str | None = None
    institution_name: str | None = None
    customer_intelligence: dict[str, Any] = field(default_factory=dict)
    session_profile: dict[str, Any] | None = None
    active_agent: str | None = None
    previous_agent: str | None = None
    agent_name: str | None = None
    handoff_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_system_vars(cls, system_vars: dict[str, Any]) -> GreetingContext:
        """
        Create GreetingContext from system_vars dictionary.

        Extracts relevant fields from various nested structures.
        """
        ctx = cls()

        # Direct fields
        ctx.caller_name = system_vars.get("caller_name")
        ctx.client_id = system_vars.get("client_id")
        ctx.institution_name = system_vars.get("institution_name")
        ctx.customer_intelligence = system_vars.get("customer_intelligence") or {}
        ctx.session_profile = system_vars.get("session_profile")
        ctx.active_agent = system_vars.get("active_agent")
        ctx.previous_agent = system_vars.get("previous_agent")
        ctx.agent_name = system_vars.get("agent_name")

        # Extract from handoff_context
        handoff_ctx = system_vars.get("handoff_context")
        if handoff_ctx and isinstance(handoff_ctx, dict):
            ctx.handoff_context = handoff_ctx
            # Backfill from handoff_context if missing
            if not ctx.caller_name:
                ctx.caller_name = handoff_ctx.get("caller_name")
            if not ctx.client_id:
                ctx.client_id = handoff_ctx.get("client_id")
            if not ctx.institution_name:
                ctx.institution_name = handoff_ctx.get("institution_name")
            if not ctx.customer_intelligence:
                ctx.customer_intelligence = handoff_ctx.get("customer_intelligence") or {}

        # Extract from session_profile if missing
        if ctx.session_profile and isinstance(ctx.session_profile, dict):
            if not ctx.caller_name:
                ctx.caller_name = ctx.session_profile.get("full_name")
            if not ctx.client_id:
                ctx.client_id = ctx.session_profile.get("client_id")
            if not ctx.customer_intelligence:
                ctx.customer_intelligence = ctx.session_profile.get("customer_intelligence") or {}
            if not ctx.institution_name:
                ctx.institution_name = ctx.session_profile.get("institution_name")

        return ctx

    @classmethod
    def from_memo_manager(cls, mm: MemoManager) -> GreetingContext:
        """
        Create GreetingContext from MemoManager.

        Extracts all relevant values from core memory.
        """
        ctx = cls()

        try:
            ctx.session_profile = mm.get_value_from_corememory("session_profile")
            ctx.caller_name = mm.get_value_from_corememory("caller_name")
            ctx.client_id = mm.get_value_from_corememory("client_id")
            ctx.customer_intelligence = mm.get_value_from_corememory("customer_intelligence") or {}
            ctx.institution_name = mm.get_value_from_corememory("institution_name")
            ctx.active_agent = mm.get_value_from_corememory("active_agent")
            ctx.previous_agent = mm.get_value_from_corememory("previous_agent")

            # Extract from session_profile if direct values are missing
            if ctx.session_profile and isinstance(ctx.session_profile, dict):
                if not ctx.caller_name:
                    ctx.caller_name = ctx.session_profile.get("full_name")
                if not ctx.client_id:
                    ctx.client_id = ctx.session_profile.get("client_id")
                if not ctx.customer_intelligence:
                    ctx.customer_intelligence = ctx.session_profile.get("customer_intelligence") or {}

        except Exception:
            logger.debug("Error extracting greeting context from MemoManager", exc_info=True)

        return ctx

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for template rendering."""
        result: dict[str, Any] = {}

        if self.caller_name:
            result["caller_name"] = self.caller_name
        if self.client_id:
            result["client_id"] = self.client_id
        if self.institution_name:
            result["institution_name"] = self.institution_name
        if self.customer_intelligence:
            result["customer_intelligence"] = self.customer_intelligence
        if self.session_profile:
            result["session_profile"] = self.session_profile
        if self.active_agent:
            result["active_agent"] = self.active_agent
        if self.previous_agent:
            result["previous_agent"] = self.previous_agent
        if self.agent_name:
            result["agent_name"] = self.agent_name
        if self.handoff_context:
            result["handoff_context"] = self.handoff_context

        return result


class GreetingService:
    """
    Centralized greeting resolution service.

    Provides consistent greeting logic across all orchestrators:
    - Respects explicit greeting overrides
    - Handles discrete vs announced handoffs
    - Renders agent greeting templates with context
    """

    def select_greeting(
        self,
        agent: UnifiedAgent,
        context: dict[str, Any] | GreetingContext,
        *,
        is_first_visit: bool = True,
        greet_on_switch: bool = True,
        explicit_greeting: str | None = None,
    ) -> str | None:
        """
        Select appropriate greeting for agent activation.

        Resolution order:
        1. Explicit greeting override (from system_vars or parameter)
        2. Skip if discrete handoff (greet_on_switch=False)
        3. Render agent's greeting/return_greeting template

        Args:
            agent: The agent being activated
            context: Context for template rendering (dict or GreetingContext)
            is_first_visit: Whether this is first visit to this agent
            greet_on_switch: Whether handoff mode allows greeting
            explicit_greeting: Direct greeting override

        Returns:
            Rendered greeting string, or None if no greeting
        """
        # Convert context to dict if needed
        if isinstance(context, GreetingContext):
            context_dict = context.to_dict()
        else:
            context_dict = dict(context)

        # Priority 1: Explicit greeting override
        if explicit_greeting:
            return explicit_greeting.strip() or None

        # Check system_vars for override
        override = context_dict.get("greeting")
        if not override:
            session_overrides = context_dict.get("session_overrides")
            if isinstance(session_overrides, dict):
                override = session_overrides.get("greeting")

        if override:
            return str(override).strip() or None

        # Priority 2: Discrete handoff = no greeting
        if not greet_on_switch:
            logger.debug(
                "Discrete handoff - skipping greeting for %s",
                getattr(agent, "name", "unknown"),
            )
            return None

        # Priority 3: Render from agent config
        try:
            if is_first_visit:
                rendered = agent.render_greeting(context_dict)
                return (rendered or "").strip() or None
            else:
                rendered = agent.render_return_greeting(context_dict)
                return (rendered or "Welcome back!").strip()
        except Exception as e:
            logger.warning("Failed to render greeting for %s: %s", agent.name, e)
            return None

    def get_initial_greeting(
        self,
        agent: UnifiedAgent,
        context: dict[str, Any] | GreetingContext | None = None,
    ) -> str:
        """
        Get initial greeting for session start.

        This is used when a session first begins, before any handoffs.

        Args:
            agent: The starting agent
            context: Optional context for personalization

        Returns:
            Greeting string (never None - returns default if needed)
        """
        context_dict = {}
        if isinstance(context, GreetingContext):
            context_dict = context.to_dict()
        elif context:
            context_dict = dict(context)

        greeting = self.select_greeting(
            agent=agent,
            context=context_dict,
            is_first_visit=True,
            greet_on_switch=True,
        )

        if greeting:
            return greeting

        # Fallback to default
        return "Hello! How can I help you today?"


# ─────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────

# Module-level service instance for convenience
_greeting_service = GreetingService()


def resolve_greeting(
    agent: UnifiedAgent,
    context: dict[str, Any] | GreetingContext | None = None,
    *,
    is_first_visit: bool = True,
    greet_on_switch: bool = True,
) -> str | None:
    """
    Quick greeting resolution.

    Convenience function that uses the module-level service.

    Args:
        agent: The agent to get greeting for
        context: Optional context for template rendering
        is_first_visit: Whether first visit to agent
        greet_on_switch: Whether to greet (from scenario config)

    Returns:
        Greeting text or None
    """
    return _greeting_service.select_greeting(
        agent=agent,
        context=context or {},
        is_first_visit=is_first_visit,
        greet_on_switch=greet_on_switch,
    )


def build_greeting_context(
    system_vars: dict[str, Any] | None = None,
    memo_manager: MemoManager | None = None,
) -> GreetingContext:
    """
    Build GreetingContext from available sources.

    Prefers system_vars if provided, falls back to MemoManager.

    Args:
        system_vars: System variables dictionary
        memo_manager: MemoManager instance

    Returns:
        GreetingContext with extracted values
    """
    if system_vars:
        return GreetingContext.from_system_vars(system_vars)
    if memo_manager:
        return GreetingContext.from_memo_manager(memo_manager)
    return GreetingContext()


__all__ = [
    "GreetingService",
    "GreetingContext",
    "resolve_greeting",
    "build_greeting_context",
]
