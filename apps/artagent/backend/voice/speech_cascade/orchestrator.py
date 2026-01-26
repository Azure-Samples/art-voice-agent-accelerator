"""
Cascade Orchestrator Adapter
==============================

Adapter that integrates the unified agent structure (apps/artagent/agents/)
with the SpeechCascade handler for multi-agent voice orchestration.

This adapter:
- Uses UnifiedAgent from the new modular agent structure
- Provides multi-agent handoffs via state-based transitions
- Integrates with the shared tool registry
- Processes turns synchronously via process_gpt_response pattern

Architecture:
    SpeechCascadeHandler
           │
           ▼
    CascadeOrchestratorAdapter ─► UnifiedAgent registry
           │                           │
           ├─► process_turn()          └─► get_tools()
           │                               render_prompt()
           └─► HandoffManager ─────────► build_handoff_map()

Usage:
    from apps.artagent.backend.voice.speech_cascade import CascadeOrchestratorAdapter

    # Create with unified agents
    adapter = CascadeOrchestratorAdapter.create(
        start_agent="Concierge",
        call_connection_id="call_123",
        session_id="session_456",
    )

    # Use as orchestrator_func in SpeechCascadeHandler
    async def orchestrator_func(cm, transcript):
        await adapter.process_user_input(transcript, cm)

    # Or wrap for legacy gpt_flow interface
    func = adapter.as_orchestrator_func()
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.voice.shared.base import (
    OrchestratorContext,
    OrchestratorResult,
)
from apps.artagent.backend.voice.shared.config_resolver import (
    DEFAULT_START_AGENT,
    resolve_from_app_state,
    resolve_orchestrator_config,
)
from apps.artagent.backend.voice.shared.handoff_service import HandoffService
from apps.artagent.backend.voice.shared.metrics import OrchestratorMetrics
from apps.artagent.backend.voice.shared.session_state import (
    SessionStateKeys,
    sync_state_from_memo,
    sync_state_to_memo,
)
from apps.artagent.backend.voice.speech_cascade.tts_processor import TTSTextProcessor
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.monitoring import GenAIOperation, GenAIProvider, SpanAttr


@dataclass
class HandoffResult:
    """Result from executing a handoff."""
    success: bool
    target_agent: str = ""
    handoff_type: str = "announced"  # "discrete" or "announced"
    greeting: str | None = None
    error: str | None = None


if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
    from src.stateful.state_managment import MemoManager

try:
    from utils.ml_logging import get_logger

    logger = get_logger("cascade.adapter")
except ImportError:
    import logging

    logger = logging.getLogger("cascade.adapter")

from apps.artagent.backend.src.orchestration.naming import find_agent_by_name

tracer = trace.get_tracer(__name__)


# ─────────────────────────────────────────────────────────────────────
# State Keys (use shared SessionStateKeys for consistency)
# ─────────────────────────────────────────────────────────────────────

# Re-export for backward compatibility
StateKeys = SessionStateKeys


# ─────────────────────────────────────────────────────────────────────
# Session Context (for cross-thread preservation)
# ─────────────────────────────────────────────────────────────────────

# Context variable to preserve session state across thread boundaries
_cascade_session_ctx: contextvars.ContextVar[CascadeSessionScope | None] = contextvars.ContextVar(
    "cascade_session", default=None
)


@dataclass
class CascadeSessionScope:
    """
    Session scope for preserving context across thread boundaries.

    This dataclass holds session-specific state that must be preserved
    when crossing async/thread boundaries (e.g., during LLM streaming).
    """

    session_id: str
    call_connection_id: str
    memo_manager: MemoManager | None = None
    active_agent: str = ""
    turn_id: str = ""

    @classmethod
    def get_current(cls) -> CascadeSessionScope | None:
        """Get the current session scope from context variable."""
        return _cascade_session_ctx.get()

    @classmethod
    @contextmanager
    def activate(
        cls,
        session_id: str,
        call_connection_id: str,
        memo_manager: MemoManager | None = None,
        active_agent: str = "",
        turn_id: str = "",
    ):
        """
        Context manager that activates a session scope.

        Usage:
            with CascadeSessionScope.activate(session_id, call_id, cm):
                # Session context is preserved here
                await process_llm(...)
        """
        scope = cls(
            session_id=session_id,
            call_connection_id=call_connection_id,
            memo_manager=memo_manager,
            active_agent=active_agent,
            turn_id=turn_id,
        )
        token = _cascade_session_ctx.set(scope)
        try:
            yield scope
        finally:
            _cascade_session_ctx.reset(token)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

# Get deployment name from environment, with fallback
DEFAULT_MODEL_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


@dataclass
class CascadeConfig:
    """
    Configuration for CascadeOrchestratorAdapter.

    Attributes:
        start_agent: Name of the initial agent
        model_name: LLM deployment name (from AZURE_OPENAI_DEPLOYMENT)
        call_connection_id: ACS call connection for tracing
        session_id: Session identifier for tracing
        enable_rag: Whether to enable RAG search for responses
        streaming: Whether to stream responses (default False for sentence-level TTS)
    """

    start_agent: str = DEFAULT_START_AGENT
    model_name: str = field(default_factory=lambda: DEFAULT_MODEL_NAME)
    call_connection_id: str | None = None
    session_id: str | None = None
    enable_rag: bool = True
    streaming: bool = False  # Non-streaming matches legacy gpt_flow behavior


# ─────────────────────────────────────────────────────────────────────
# Main Adapter
# ─────────────────────────────────────────────────────────────────────


@dataclass
class CascadeOrchestratorAdapter:
    """
    Adapter for SpeechCascade multi-agent orchestration using unified agents.

    This adapter integrates the modular agent structure (apps/artagent/agents/)
    with the SpeechCascadeHandler, providing:

    - State-based handoffs via MemoManager
    - Tool execution via shared registry
    - Prompt rendering with runtime context
    - OpenTelemetry instrumentation

    Design:
    - Synchronous turn processing (not event-driven)
    - State-based handoffs (not tool-based)
    - Uses gpt_flow pattern for LLM streaming

    Attributes:
        config: Orchestrator configuration
        agents: Registry of UnifiedAgent instances
        handoff_map: Tool name → agent name mapping
    """

    config: CascadeConfig = field(default_factory=CascadeConfig)
    agents: dict[str, UnifiedAgent] = field(default_factory=dict)
    handoff_map: dict[str, str] = field(default_factory=dict)

    # Runtime state
    _active_agent: str = field(default="", init=False)
    _visited_agents: set = field(default_factory=set, init=False)
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _last_user_message: str | None = field(default=None, init=False)

    # Session context - preserves MemoManager reference for turn duration
    _current_memo_manager: MemoManager | None = field(default=None, init=False)
    _session_vars: dict[str, Any] = field(default_factory=dict, init=False)

    # Unified metrics tracking (replaces individual token/timing fields)
    _metrics: OrchestratorMetrics = field(default=None, init=False)  # type: ignore

    # Callbacks for integration with SpeechCascadeHandler
    _on_tts_chunk: Callable[[str], Awaitable[None]] | None = field(default=None, init=False)
    _on_agent_switch: Callable[[str, str], Awaitable[None]] | None = field(default=None, init=False)

    def __post_init__(self):
        """Initialize agent registry if not provided."""
        # Initialize metrics tracker
        self._metrics = OrchestratorMetrics(
            agent_name=self.config.start_agent or "",
            call_connection_id=self.config.call_connection_id,
            session_id=self.config.session_id,
        )
        
        if not self.agents:
            self._load_agents()

        if not self.handoff_map:
            self._build_handoff_map()

        if not self._active_agent:
            self._active_agent = self.config.start_agent

        # Validate start agent exists (case-insensitive)
        if self._active_agent:
            actual_key, _ = find_agent_by_name(self.agents, self._active_agent)
            if actual_key is None:
                available = list(self.agents.keys())
                if available:
                    logger.warning(
                        "Start agent '%s' not found, using '%s'",
                        self._active_agent,
                        available[0],
                    )
                    self._active_agent = available[0]
            else:
                # Normalize to actual key
                self._active_agent = actual_key

    def _load_agents(self) -> None:
        """Load agents from the unified agent registry with scenario support."""
        # Use cached orchestrator config (this also populates the cache for future use)
        config = self._orchestrator_config
        self.agents = config.agents
        self.handoff_map = config.handoff_map

        # Update start agent if scenario specifies one
        if config.has_scenario and config.start_agent:
            self.config.start_agent = config.start_agent
            self._active_agent = config.start_agent

        logger.info(
            "Loaded %d agents for cascade adapter (session_id=%s)",
            len(self.agents),
            self.config.session_id or "(none)",
            extra={
                "scenario": config.scenario_name or "(none)",
                "start_agent": config.start_agent,
            },
        )

    def _build_handoff_map(self) -> None:
        """Build handoff map from agent declarations."""
        # Already built by _load_agents via resolver
        if self.handoff_map:
            return

        try:
            from apps.artagent.backend.registries.agentstore.loader import build_handoff_map

            self.handoff_map = build_handoff_map(self.agents)
            logger.debug("Built handoff map: %s", self.handoff_map)
        except ImportError as e:
            logger.error("Failed to import build_handoff_map: %s", e)
            self.handoff_map = {}

    @classmethod
    def create(
        cls,
        *,
        start_agent: str = "Concierge",
        model_name: str | None = None,
        call_connection_id: str | None = None,
        session_id: str | None = None,
        agents: dict[str, UnifiedAgent] | None = None,
        handoff_map: dict[str, str] | None = None,
        enable_rag: bool = True,
        streaming: bool = False,  # Non-streaming for sentence-level TTS
    ) -> CascadeOrchestratorAdapter:
        """
        Factory method to create a fully configured adapter.

        Args:
            start_agent: Initial agent name
            model_name: LLM deployment name (defaults to AZURE_OPENAI_DEPLOYMENT)
            call_connection_id: ACS call ID for tracing
            session_id: Session ID for tracing
            agents: Optional pre-loaded agent registry
            handoff_map: Optional pre-built handoff map
            enable_rag: Whether to enable RAG search
            streaming: Whether to stream responses

        Returns:
            Configured CascadeOrchestratorAdapter instance
        """
        config = CascadeConfig(
            start_agent=start_agent,
            model_name=model_name or DEFAULT_MODEL_NAME,
            call_connection_id=call_connection_id,
            session_id=session_id,
            enable_rag=enable_rag,
            streaming=streaming,
        )

        adapter = cls(
            config=config,
            agents=agents or {},
            handoff_map=handoff_map or {},
        )

        return adapter

    # ─────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "cascade_orchestrator"

    @property
    def current_agent(self) -> str | None:
        """Get the currently active agent name."""
        return self._active_agent

    @property
    def current_agent_config(self) -> UnifiedAgent | None:
        """Get the currently active agent configuration."""
        return self.agents.get(self._active_agent)

    @property
    def available_agents(self) -> list[str]:
        """Get list of available agent names."""
        return list(self.agents.keys())

    @property
    def memo_manager(self) -> MemoManager | None:
        """
        Get the current MemoManager reference.

        This is available during turn processing and allows
        tools and callbacks to access session state.
        """
        # Try session scope first (for cross-thread access)
        scope = CascadeSessionScope.get_current()
        if scope and scope.memo_manager:
            return scope.memo_manager
        # Fall back to instance reference
        return self._current_memo_manager

    @property
    def _orchestrator_config(self):
        """
        Get cached orchestrator config for scenario resolution.

        Lazily resolves and caches the config on first access to avoid
        repeated calls to resolve_orchestrator_config() during the session.

        The config is cached per-instance (session lifetime), which is appropriate
        because scenario changes during a call would be disruptive anyway.
        """
        if not hasattr(self, "_cached_orchestrator_config"):
            # Get scenario_name from session memo_manager using centralized utility
            scenario_name = None
            if self._current_memo_manager:
                from apps.artagent.backend.src.orchestration.naming import get_scenario_from_corememory
                scenario_name = get_scenario_from_corememory(self._current_memo_manager)
            self._cached_orchestrator_config = resolve_orchestrator_config(
                session_id=self.config.session_id,
                scenario_name=scenario_name,
            )
            logger.debug(
                "Cached orchestrator config | scenario=%s session=%s",
                self._cached_orchestrator_config.scenario_name,
                self.config.session_id,
            )
        return self._cached_orchestrator_config

    @property
    def handoff_service(self) -> HandoffService:
        """
        Get the HandoffService for consistent handoff resolution.

        Lazily initialized on first access using current orchestrator state.
        Uses cached scenario config for handoff behavior (discrete/announced).

        For session-scoped scenarios (from Scenario Builder), passes the
        ScenarioConfig object directly so HandoffService can use it without
        trying to load from YAML files.
        """
        if not hasattr(self, "_handoff_service") or self._handoff_service is None:
            # Use cached orchestrator config for scenario resolution
            config = self._orchestrator_config
            self._handoff_service = HandoffService(
                scenario_name=config.scenario_name,
                handoff_map=self.handoff_map,
                agents=self.agents,
                memo_manager=self._current_memo_manager,
                scenario=config.scenario,  # Pass scenario object for session-scoped scenarios
            )
        return self._handoff_service

    def get_handoff_target(self, tool_name: str) -> str | None:
        """
        Get the target agent for a handoff tool.

        Uses HandoffService for consistent resolution.
        """
        return self.handoff_service.get_handoff_target(tool_name)

    def _get_tools_with_handoffs(self, agent: UnifiedAgent) -> list[dict[str, Any]]:
        """
        Get agent tools with centralized handoff tool injection.

        This method:
        1. Filters OUT explicit handoff tools (e.g., handoff_concierge)
        2. Auto-injects the generic `handoff_to_agent` tool when needed

        The scenario edges define handoff routing and conditions, so we only
        need the single centralized `handoff_to_agent` tool. Agents call it
        with `target_agent` parameter based on system prompt instructions.

        Args:
            agent: The agent to get tools for

        Returns:
            List of tool schemas with only the generic handoff_to_agent tool
        """
        tools = agent.get_tools()

        # Filter out explicit handoff tools - we use handoff_to_agent exclusively
        filtered_tools = []
        for tool in tools:
            func_name = tool.get("function", {}).get("name", "")
            # Keep handoff_to_agent, filter out other handoff_* patterns
            if func_name == "handoff_to_agent":
                filtered_tools.append(tool)
            elif self.handoff_service.is_handoff(func_name):
                logger.debug(
                    "Filtering explicit handoff tool | tool=%s agent=%s reason=using_centralized_handoff",
                    func_name,
                    agent.name,
                )
            else:
                filtered_tools.append(tool)

        tools = filtered_tools
        tool_names = {t.get("function", {}).get("name") for t in tools}

        # Check if handoff_to_agent is already present
        if "handoff_to_agent" in tool_names:
            return tools

        # Check scenario configuration for automatic handoff tool injection
        # Use cached orchestrator config (supports both file-based and session-scoped)
        config = self._orchestrator_config
        scenario = config.scenario
        if not scenario:
            logger.warning(
                "No scenario loaded for handoff tool injection | agent=%s scenario_name=%s",
                agent.name,
                config.scenario_name,
            )
            # Fallback: still add handoff_to_agent if agent has explicit handoff tools defined
            # This ensures basic handoff capability even without scenario config
            agent_tools = agent.get_tools()
            has_handoff_tools = any(
                self.handoff_service.is_handoff(t.get("function", {}).get("name", ""))
                for t in agent_tools
            )
            if has_handoff_tools:
                from apps.artagent.backend.registries.toolstore import get_tools_for_agent, initialize_tools
                initialize_tools()
                handoff_tools = get_tools_for_agent(["handoff_to_agent"])
                if handoff_tools:
                    # Enhance with available agent names
                    handoff_tools = self._enhance_handoff_tool_with_agents(handoff_tools, agent.name)
                    tools = list(tools) + handoff_tools
                    logger.info(
                        "Added handoff_to_agent (fallback) | agent=%s reason=agent_has_handoff_tools",
                        agent.name,
                    )
            return tools

        # Add handoff_to_agent if generic handoffs enabled or agent has outgoing edges
        should_add_handoff_tool = False

        if scenario.generic_handoff.enabled:
            should_add_handoff_tool = True
            logger.debug(
                "Auto-adding handoff_to_agent | agent=%s reason=generic_handoff_enabled",
                agent.name,
            )
        else:
            # Check if agent has outgoing handoffs in the scenario
            outgoing = scenario.get_outgoing_handoffs(agent.name)
            if outgoing:
                should_add_handoff_tool = True
                logger.debug(
                    "Auto-adding handoff_to_agent | agent=%s reason=has_outgoing_handoffs count=%d targets=%s",
                    agent.name,
                    len(outgoing),
                    [h.to_agent for h in outgoing],
                )

        if should_add_handoff_tool:
            from apps.artagent.backend.registries.toolstore import get_tools_for_agent, initialize_tools
            initialize_tools()
            handoff_tools = get_tools_for_agent(["handoff_to_agent"])
            if handoff_tools:
                # Enhance with available agent names
                handoff_tools = self._enhance_handoff_tool_with_agents(handoff_tools, agent.name)
                tools = list(tools) + handoff_tools
                logger.info(
                    "Added handoff_to_agent tool | agent=%s scenario=%s",
                    agent.name,
                    config.scenario_name,
                )

        return tools

    def _enhance_handoff_tool_with_agents(
        self, handoff_tools: list[dict[str, Any]], current_agent: str
    ) -> list[dict[str, Any]]:
        """
        Enhance handoff_to_agent tool description with available agent names.

        This helps the LLM know exactly which agents it can hand off to,
        preventing hallucinated agent names like "CardSpecialist" instead
        of the correct "CardRecommendation".

        Args:
            handoff_tools: List of handoff tool schemas
            current_agent: The current agent name (to exclude from targets)

        Returns:
            Modified tool schemas with agent names in description
        """
        import copy

        # Get available agents (excluding current agent)
        available_agents = [name for name in self.agents.keys() if name != current_agent]

        if not available_agents:
            return handoff_tools

        enhanced_tools = []
        for tool in handoff_tools:
            tool_copy = copy.deepcopy(tool)
            func = tool_copy.get("function", {})
            if func.get("name") == "handoff_to_agent":
                # Update description to include available agents
                original_desc = func.get("description", "")
                agent_list = ", ".join(sorted(available_agents))
                enhanced_desc = (
                    f"{original_desc}\n\n"
                    f"AVAILABLE AGENTS: {agent_list}\n"
                    f"You MUST use one of these exact agent names as the target_agent parameter."
                )
                func["description"] = enhanced_desc

                # Also update the target_agent parameter with enum
                params = func.get("parameters", {})
                props = params.get("properties", {})
                if "target_agent" in props:
                    props["target_agent"]["enum"] = sorted(available_agents)
                    props["target_agent"]["description"] = (
                        f"The name of the agent to transfer to. Must be one of: {agent_list}"
                    )

            enhanced_tools.append(tool_copy)

        return enhanced_tools

    def set_on_agent_switch(self, callback: Callable[[str, str], Awaitable[None]] | None) -> None:
        """
        Set callback for agent switch notifications.

        The callback receives (previous_agent, new_agent) when a handoff occurs.
        Use this to emit agent_change envelopes or update voice configuration.

        Args:
            callback: Async function(previous_agent, new_agent) -> None
        """
        self._on_agent_switch = callback

    def update_scenario(
        self,
        agents: dict[str, UnifiedAgent],
        handoff_map: dict[str, str],
        start_agent: str | None = None,
        scenario_name: str | None = None,
    ) -> None:
        """
        Update the adapter with a new scenario configuration.

        This is called when the user changes scenarios mid-session via the UI.
        All agent-related attributes are updated to reflect the new scenario.

        Args:
            agents: New agents registry
            handoff_map: New handoff routing map
            start_agent: Optional new start agent to switch to
            scenario_name: Optional scenario name for logging
        """
        old_agents = list(self.agents.keys())
        old_active = self._active_agent

        # Update agents registry
        self.agents = agents

        # Update handoff map
        self.handoff_map = handoff_map

        # Clear cached HandoffService so it's recreated with new values
        if hasattr(self, "_handoff_service"):
            self._handoff_service = None

        # Clear visited agents for fresh scenario experience
        self._visited_agents.clear()

        # Update config start_agent
        if start_agent:
            self.config.start_agent = start_agent

        # Switch to start_agent if provided (always switch for explicit scenario change)
        if start_agent:
            # Normalize to actual key
            actual_key, _ = find_agent_by_name(agents, start_agent)
            self._active_agent = actual_key or start_agent
            logger.info(
                "🔄 Cascade switching to scenario start_agent | from=%s to=%s scenario=%s",
                old_active,
                self._active_agent,
                scenario_name or "(unknown)",
            )
        else:
            # Check if current agent in new scenario (case-insensitive)
            actual_key, _ = find_agent_by_name(agents, self._active_agent)
            if actual_key is None:
                # Current agent not in new scenario - switch to first available
                available = list(agents.keys())
                if available:
                    self._active_agent = available[0]
                    logger.warning(
                        "🔄 Cascade current agent not in scenario, switching | from=%s to=%s",
                        old_active,
                        self._active_agent,
                    )
            else:
                # Normalize to actual key
                self._active_agent = actual_key

        logger.info(
            "🔄 Cascade scenario updated | old_agents=%s new_agents=%s active=%s scenario=%s",
            old_agents,
            list(agents.keys()),
            self._active_agent,
            scenario_name or "(unknown)",
        )

    # ─────────────────────────────────────────────────────────────────
    # History Management (Consolidated)
    # ─────────────────────────────────────────────────────────────────

    def _record_turn(
        self,
        agent: str,
        user_text: str | None,
        assistant_text: str | None,
    ) -> tuple[bool, bool]:
        """
        Record a conversation turn to history.

        This is the SINGLE place where conversation history is written.
        All in-memory, no I/O - safe for hot path.

        Args:
            agent: Agent name for the history thread
            user_text: User's message (or None to skip)
            assistant_text: Assistant's response (or None to skip)

        Returns:
            Tuple of (user_recorded, assistant_recorded)
        """
        cm = self._current_memo_manager
        if not cm:
            return (False, False)

        user_recorded = False
        assistant_recorded = False

        if user_text and user_text.strip():
            cm.append_to_history(agent, "user", user_text)
            user_recorded = True

        if assistant_text:
            cm.append_to_history(agent, "assistant", assistant_text)
            assistant_recorded = True

        return (user_recorded, assistant_recorded)

    def _get_conversation_history(self, cm: MemoManager) -> list[dict[str, str]]:
        """
        Build conversation history for the current agent.

        Includes context from other agents to preserve cross-agent continuity.
        Makes a COPY to avoid mutation issues.

        Args:
            cm: MemoManager instance

        Returns:
            List of message dicts for conversation history
        """
        # Get current agent's history (copy to avoid reference issues)
        agent_history = list(cm.get_history(self._active_agent) or [])

        # Collect substantive user messages from other agents
        all_histories = cm.history.get_all()
        seen_content: set[str] = set()
        cross_agent_context: list[dict[str, str]] = []

        for agent_name, msgs in all_histories.items():
            if agent_name == self._active_agent:
                continue
            for msg in msgs:
                if msg.get("role") != "user":
                    continue
                content = msg.get("content", "").strip()
                # Skip short or greeting-like messages
                if len(content) <= 10 or content.lower().startswith("welcome"):
                    continue
                # Deduplicate
                key = content.lower()
                if key not in seen_content:
                    seen_content.add(key)
                    cross_agent_context.append(msg)

        # Cross-agent context first, then current agent's history
        return cross_agent_context + agent_history

    def _build_session_context(self, cm: MemoManager) -> dict[str, Any]:
        """
        Build session context dict for prompt rendering.

        Args:
            cm: MemoManager instance

        Returns:
            Dict with session variables for Jinja templates
        """
        return {
            "memo_manager": cm,
            "session_profile": cm.get_value_from_corememory("session_profile"),
            "caller_name": cm.get_value_from_corememory("caller_name"),
            "client_id": cm.get_value_from_corememory("client_id"),
            "customer_intelligence": cm.get_value_from_corememory("customer_intelligence"),
            "institution_name": cm.get_value_from_corememory("institution_name"),
            "active_agent": cm.get_value_from_corememory("active_agent"),
            "previous_agent": cm.get_value_from_corememory("previous_agent"),
            "visited_agents": cm.get_value_from_corememory("visited_agents"),
            "handoff_context": cm.get_value_from_corememory("handoff_context"),
        }

    # ─────────────────────────────────────────────────────────────────
    # Turn Processing
    # ─────────────────────────────────────────────────────────────────

    async def process_turn(
        self,
        context: OrchestratorContext | None = None,
        *,
        user_text: str | None = None,
        memo_manager: MemoManager | None = None,
        on_tts_chunk: Callable[[str], Awaitable[None]] | None = None,
        on_tool_start: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_end: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> OrchestratorResult:
        """
        Process a conversation turn - UNIFIED ENTRY POINT.

        This is the single entry point for turn processing. Supports two calling patterns:

        Pattern 1 (Full context):
            result = await adapter.process_turn(context=orchestrator_context)

        Pattern 2 (Direct MemoManager - simplified):
            result = await adapter.process_turn(
                user_text="Hello",
                memo_manager=cm,
                on_tts_chunk=my_callback
            )

        Flow:
        1. Build/extract context and MemoManager
        2. Sync state from MemoManager (if provided)
        3. Build messages from history + user input
        4. Call LLM with streaming
        5. Handle tool calls / handoffs
        6. Record conversation to history
        7. Sync state to MemoManager

        Args:
            context: OrchestratorContext with user input and state (Pattern 1)
            user_text: User's input text (Pattern 2)
            memo_manager: MemoManager for state management (Pattern 2)
            on_tts_chunk: Callback for streaming TTS chunks
            on_tool_start: Callback when tool execution starts
            on_tool_end: Callback when tool execution completes

        Returns:
            OrchestratorResult with response and metadata
        """
        self._cancel_event.clear()
        self._metrics.start_turn()  # Increments turn count and resets TTFT tracking

        # Support both calling patterns: context OR direct parameters
        if context is None:
            # Pattern 2: Build context from parameters
            if memo_manager:
                self.sync_from_memo_manager(memo_manager)
                self._current_memo_manager = memo_manager

                # Get history and append current user message
                history = list(memo_manager.get_history(self._active_agent) or [])
                if user_text:
                    memo_manager.append_to_history(self._active_agent, "user", user_text)

                # Build context using helper (eliminates duplication)
                session_context = self._build_session_context(memo_manager)
            else:
                history = []
                session_context = {}

            context = OrchestratorContext(
                session_id=self.config.session_id or "",
                websocket=None,
                call_connection_id=self.config.call_connection_id,
                user_text=user_text or "",
                conversation_history=history,
                metadata=session_context,
            )
        else:
            # Pattern 1: Extract from provided context
            self._current_memo_manager = (
                context.metadata.get("memo_manager") if context.metadata else None
            )

        self._last_user_message = context.user_text
        turn_id = context.metadata.get("run_id", "") if context.metadata else ""

        agent = self.current_agent_config
        if not agent:
            return OrchestratorResult(
                response_text="",
                agent_name=self._active_agent,
                error=f"Agent '{self._active_agent}' not found",
            )

        # Activate session scope for cross-thread context preservation
        with CascadeSessionScope.activate(
            session_id=self.config.session_id or "",
            call_connection_id=self.config.call_connection_id or "",
            memo_manager=self._current_memo_manager,
            active_agent=self._active_agent,
            turn_id=turn_id,
        ):
            with tracer.start_as_current_span(
                "cascade.process_turn",
                kind=SpanKind.INTERNAL,
                attributes={
                    "cascade.agent": self._active_agent,
                    "cascade.turn": self._metrics.turn_count,
                    "session.id": self.config.session_id or "",
                    "call.connection.id": self.config.call_connection_id or "",
                    "cascade.has_memo_manager": self._current_memo_manager is not None,
                },
            ) as span:
                try:
                    # Build messages
                    messages = self._build_messages(context, agent)

                    # Get tools for current agent with automatic handoff tool injection
                    tools = self._get_tools_with_handoffs(agent)
                    logger.info(
                        "🔧 Agent tools loaded | agent=%s tool_count=%d tool_names=%s",
                        self._active_agent,
                        len(tools) if tools else 0,
                        [t.get("function", {}).get("name") for t in tools] if tools else [],
                    )

                    # Process with LLM (streaming) - session scope is preserved
                    response_text, tool_calls = await self._process_llm(
                        messages=messages,
                        tools=tools,
                        on_tts_chunk=on_tts_chunk,
                        on_tool_start=on_tool_start,
                        on_tool_end=on_tool_end,
                    )

                    # Check for handoff tool calls
                    handoff_executed = False
                    handoff_target = None
                    handoff_greeting = None  # Store greeting for fallback
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "")
                        if self.handoff_service.is_handoff(tool_name):
                            # Parse arguments first - they come as JSON string from streaming
                            raw_args = tool_call.get("arguments", "{}")
                            if isinstance(raw_args, str):
                                try:
                                    parsed_args = json.loads(raw_args) if raw_args else {}
                                except json.JSONDecodeError:
                                    parsed_args = {}
                            else:
                                parsed_args = raw_args if isinstance(raw_args, dict) else {}

                            # For handoff_to_agent, get target from arguments
                            # For other handoff tools (legacy), use handoff_map
                            if tool_name == "handoff_to_agent":
                                target_agent = parsed_args.get("target_agent", "")
                                if not target_agent:
                                    logger.warning(
                                        "handoff_to_agent called without target_agent | args=%s",
                                        parsed_args,
                                    )
                                    continue
                                # Validate target exists
                                if target_agent not in self.agents:
                                    logger.warning(
                                        "handoff_to_agent target not found | target=%s available=%s",
                                        target_agent,
                                        list(self.agents.keys()),
                                    )
                                    continue
                            else:
                                target_agent = self.get_handoff_target(tool_name)
                                if not target_agent:
                                    logger.warning("Handoff tool '%s' not in handoff_map", tool_name)
                                    continue

                            # Emit tool_start for handoff tool (before execution)
                            if on_tool_start:
                                try:
                                    await on_tool_start(tool_name, raw_args)
                                except Exception:
                                    logger.debug("Failed to emit handoff tool_start", exc_info=True)

                            handoff_result = await self._execute_handoff(
                                target_agent=target_agent,
                                tool_name=tool_name,
                                args=parsed_args,
                            )

                            # Emit tool_end for handoff tool (after execution)
                            if on_tool_end:
                                try:
                                    await on_tool_end(
                                        tool_name,
                                        {
                                            "handoff": True,
                                            "target_agent": target_agent,
                                            "handoff_type": handoff_result.handoff_type,
                                            "success": handoff_result.success,
                                        },
                                    )
                                except Exception:
                                    logger.debug("Failed to emit handoff tool_end", exc_info=True)

                            if not handoff_result.success:
                                logger.warning("Handoff to %s failed: %s", target_agent, handoff_result.error)
                                continue

                            handoff_executed = True
                            handoff_target = target_agent
                            handoff_greeting = handoff_result.greeting
                            break

                    # If handoff occurred, let the NEW agent respond immediately
                    # This eliminates the awkward "handoff confirmation" message
                    if handoff_executed and handoff_target:
                        span.set_attribute("cascade.handoff_executed", True)
                        span.set_attribute("cascade.handoff_target", handoff_target)

                        # Get the new agent
                        new_agent = self.agents.get(handoff_target)
                        if new_agent:
                            logger.info(
                                "Handoff complete, new agent responding | from=%s to=%s",
                                context.metadata.get("agent_name", "unknown"),
                                handoff_target,
                            )

                            # Update context metadata for new agent
                            updated_metadata = dict(context.metadata) if context.metadata else {}
                            updated_metadata["agent_name"] = handoff_target
                            updated_metadata["previous_agent"] = (
                                context.metadata.get("agent_name") if context.metadata else None
                            )
                            # Ensure handoff_context is always a dict
                            raw_context = parsed_args.get("context") or parsed_args.get("reason")
                            if isinstance(raw_context, dict):
                                updated_metadata["handoff_context"] = raw_context
                            elif raw_context:
                                # Convert string reason to dict format
                                updated_metadata["handoff_context"] = {
                                    "reason": raw_context,
                                    "details": raw_context,
                                }
                            else:
                                updated_metadata["handoff_context"] = {}

                            # Get the new agent's existing history (if returning to this agent)
                            # Plus add user's current message for context about why handoff happened
                            new_agent_history = []
                            if self._current_memo_manager:
                                try:
                                    new_agent_history = list(
                                        self._current_memo_manager.get_history(handoff_target) or []
                                    )
                                except Exception:
                                    pass

                            # If this is first visit to agent, add context about user's request
                            if not new_agent_history and context.user_text:
                                new_agent_history.append(
                                    {
                                        "role": "user",
                                        "content": context.user_text,
                                    }
                                )

                            # Build messages for new agent with its own history
                            new_context = OrchestratorContext(
                                session_id=context.session_id,
                                websocket=context.websocket,
                                call_connection_id=context.call_connection_id,
                                user_text=(
                                    "" if new_agent_history else context.user_text
                                ),  # Avoid duplicate if added above
                                conversation_history=new_agent_history,
                                metadata=updated_metadata,
                            )

                            new_messages = self._build_messages(new_context, new_agent)
                            new_tools = new_agent.get_tools()

                            try:
                                # Get response from new agent
                                new_response_text, new_tool_calls = await self._process_llm(
                                    messages=new_messages,
                                    tools=new_tools,
                                    on_tts_chunk=on_tts_chunk,
                                    on_tool_start=on_tool_start,
                                    on_tool_end=on_tool_end,
                                )

                                # Check if LLM produced meaningful response
                                if not new_response_text or len(new_response_text.strip()) < 10:
                                    # LLM response too short or empty - use greeting as fallback
                                    if handoff_greeting:
                                        logger.warning(
                                            "New agent LLM response too short (%d chars), using greeting fallback",
                                            len(new_response_text) if new_response_text else 0,
                                        )
                                        new_response_text = handoff_greeting
                                        # Stream greeting to TTS
                                        if on_tts_chunk and handoff_greeting:
                                            await on_tts_chunk(handoff_greeting)

                                logger.info(
                                    "New agent responded | agent=%s text_len=%d tool_calls=%d",
                                    handoff_target,
                                    len(new_response_text),
                                    len(new_tool_calls),
                                )

                                # Record handoff turn using consolidated helper
                                user_for_handoff = context.user_text if not new_agent_history else None
                                self._record_turn(handoff_target, user_for_handoff, new_response_text)
                                
                                # Sync state
                                if self._current_memo_manager:
                                    self.sync_to_memo_manager(self._current_memo_manager)

                                span.set_status(Status(StatusCode.OK))

                                return OrchestratorResult(
                                    response_text=new_response_text,
                                    tool_calls=tool_calls + new_tool_calls,
                                    agent_name=self._active_agent,
                                    interrupted=self._cancel_event.is_set(),
                                    input_tokens=self._metrics.input_tokens,
                                    output_tokens=self._metrics.output_tokens,
                                )
                            except Exception as handoff_err:
                                logger.error(
                                    "New agent failed to respond after handoff: %s",
                                    handoff_err,
                                    exc_info=True,
                                )
                                # Use greeting as fallback response
                                if handoff_greeting:
                                    logger.info(
                                        "Using greeting as fallback after LLM error | agent=%s",
                                        handoff_target,
                                    )
                                    # Stream greeting to TTS
                                    if on_tts_chunk:
                                        await on_tts_chunk(handoff_greeting)
                                    
                                    # Record the greeting as agent response
                                    self._record_turn(handoff_target, context.user_text, handoff_greeting)
                                    
                                    if self._current_memo_manager:
                                        self.sync_to_memo_manager(self._current_memo_manager)
                                    
                                    span.set_status(Status(StatusCode.OK))
                                    return OrchestratorResult(
                                        response_text=handoff_greeting,
                                        tool_calls=tool_calls,
                                        agent_name=self._active_agent,
                                        interrupted=self._cancel_event.is_set(),
                                        input_tokens=self._metrics.input_tokens,
                                        output_tokens=self._metrics.output_tokens,
                                    )
                                # No greeting fallback - fall through to return original response
                        else:
                            logger.warning(
                                "Handoff target agent not found: %s",
                                handoff_target,
                            )

                    # ─── RECORD & FINALIZE ───
                    # Record turn using consolidated helper (in-memory, no I/O)
                    user_recorded, assistant_recorded = self._record_turn(
                        self._active_agent, context.user_text, response_text
                    )

                    # Sync orchestrator state to MemoManager (in-memory)
                    if self._current_memo_manager:
                        self.sync_to_memo_manager(self._current_memo_manager)

                    # Set span attributes for observability
                    span.set_attributes({
                        "cascade.user_recorded": user_recorded,
                        "cascade.assistant_recorded": assistant_recorded,
                        "cascade.user_text_len": len(context.user_text or ""),
                        "cascade.response_text_len": len(response_text or ""),
                        "cascade.handoff_executed": handoff_executed,
                    })
                    span.set_status(Status(StatusCode.OK))

                    return OrchestratorResult(
                        response_text=response_text,
                        tool_calls=tool_calls,
                        agent_name=self._active_agent,
                        interrupted=self._cancel_event.is_set(),
                        input_tokens=self._metrics.input_tokens,
                        output_tokens=self._metrics.output_tokens,
                    )

                except asyncio.CancelledError:
                    span.set_status(Status(StatusCode.ERROR, "Cancelled"))
                    return OrchestratorResult(
                        response_text="",
                        agent_name=self._active_agent,
                        interrupted=True,
                    )
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    logger.exception("Turn processing failed: %s", e)

                    # Extract user-friendly error message
                    error_details = self._extract_error_details(e)

                    return OrchestratorResult(
                        response_text="",
                        agent_name=self._active_agent,
                        error=error_details,
                    )

    def _build_messages(
        self,
        context: OrchestratorContext,
        agent: UnifiedAgent,
    ) -> list[dict[str, Any]]:
        """Build messages for LLM request.

        Handles both simple messages (role + content) and complex messages
        (tool calls, tool results) which are stored as JSON in the content field.
        
        Also injects scenario-based handoff instructions if defined.
        """
        messages = []

        # System prompt from agent
        system_content = agent.render_prompt(context.metadata)
        
        # Inject handoff instructions from scenario configuration
        # Use cached orchestrator config (supports both file-based and session-scoped)
        config = self._orchestrator_config
        if config.scenario and agent.name:
            # Use scenario.build_handoff_instructions directly (works for session scenarios)
            handoff_instructions = config.scenario.build_handoff_instructions(agent.name)
            if handoff_instructions:
                system_content = f"{system_content}\n\n{handoff_instructions}" if system_content else handoff_instructions
                logger.info(
                    "Injected handoff instructions into system prompt | agent=%s scenario=%s len=%d",
                    agent.name,
                    config.scenario_name,
                    len(handoff_instructions),
                )
        else:
            logger.debug(
                "_build_messages: no scenario or agent name | scenario=%s agent_name=%s",
                config.scenario_name if config.scenario else None,
                agent.name if agent else None,
            )

        if system_content:
            messages.append({"role": "system", "content": system_content})

        # Conversation history - expand any JSON-encoded tool messages
        for msg in context.conversation_history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Check if this is a JSON-encoded complex message (tool call or tool result)
            if role in ("assistant", "tool") and content and content.startswith("{"):
                try:
                    decoded = json.loads(content)
                    # If it has the expected structure, use it directly
                    if isinstance(decoded, dict) and "role" in decoded:
                        messages.append(decoded)
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass  # Not JSON, use as-is

            # Regular message
            messages.append(msg)

        # Current user message
        if context.user_text:
            messages.append({"role": "user", "content": context.user_text})

        return messages

    def _sanitize_tts_text(self, text: str) -> str:
        """Remove markdown so TTS only speaks plain text. DEPRECATED: Use TTSTextProcessor."""
        return TTSTextProcessor.sanitize_tts_text(text)

    def _find_tts_boundary(self, text: str, terms: str, min_index: int) -> int:
        """Return first punctuation boundary that is safe to split on. DEPRECATED: Use TTSTextProcessor."""
        return TTSTextProcessor.find_tts_boundary(text, terms, min_index)

    def _split_tts_buffer(self, text: str, end_index: int) -> tuple[str, str]:
        """Split text at end_index, keeping trailing whitespace with the left chunk. DEPRECATED: Use TTSTextProcessor."""
        return TTSTextProcessor.split_tts_buffer(text, end_index)

    async def _process_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_tts_chunk: Callable[[str], Awaitable[None]] | None = None,
        on_tool_start: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_end: Callable[[str, Any], Awaitable[None]] | None = None,
        *,
        _iteration: int = 0,
        _max_iterations: int = 5,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Process messages through LLM with streaming TTS and tool-call loop.

        Uses STREAMING with async queue for low-latency TTS dispatch:
        - OpenAI stream runs in thread, puts chunks to asyncio.Queue
        - Main coroutine consumes queue and dispatches to TTS immediately
        - Tool calls are aggregated during streaming
        - After stream completes, tools are executed and we recurse

        Uses the current agent's model configuration (deployment_id, temperature, etc.)
        to allow session agents to specify their own LLM settings.

        Args:
            messages: Conversation messages including system prompt
            tools: OpenAI-format tool definitions
            on_tts_chunk: Callback for streaming TTS chunks
            on_tool_start: Callback when tool execution starts
            on_tool_end: Callback when tool execution completes
            _iteration: Internal recursion counter
            _max_iterations: Maximum tool-loop iterations

        Returns:
            Tuple of (response_text, all_tool_calls)
        """
        import json

        # Get model configuration from current agent (prefers cascade_model over generic model)
        agent = self.current_agent_config
        model_name = self.config.model_name  # Default from adapter config
        model_config = None

        if agent:
            # Use get_model_for_mode to pick cascade_model if available, else fallback to model
            model_config = agent.get_model_for_mode("cascade")
            model_name = model_config.deployment_id or model_name

        # Safety: prevent infinite tool loops
        if _iteration >= _max_iterations:
            logger.warning(
                "Tool loop reached max iterations (%d); returning current state",
                _max_iterations,
            )
            return ("", [])

        # Use AzureOpenAIManager for dual-endpoint support (chat vs responses)
        # This enables proper routing based on model_config.endpoint_preference
        try:
            from src.aoai.manager import AzureOpenAIManager
            from src.aoai.client import get_client as get_aoai_client

            # Get the raw client for streaming (manager doesn't support streaming yet)
            client = get_aoai_client()
            if client is None:
                logger.error("AOAI client is None - not initialized")
                return ("I'm having trouble connecting to the AI service.", [])

            # Also get manager instance for future non-streaming support
            # Initialize manager with session context for tracing
            manager = AzureOpenAIManager(
                call_connection_id=self.config.call_connection_id,
                session_id=self.config.session_id,
                enable_tracing=True,
            )
        except ImportError as e:
            logger.error("Failed to import AOAI client/manager: %s", e)
            return ("I'm having trouble connecting to the AI service.", [])

        response_text = ""
        tool_calls: list[dict[str, Any]] = []
        all_tool_calls: list[dict[str, Any]] = []
        output_tokens = 0

        # Prepare streaming parameters early for telemetry
        streaming_params = self._prepare_streaming_params(model_config, model_name, messages, tools)
        temp_attr = streaming_params.get("temperature")
        top_p_attr = streaming_params.get("top_p")
        max_tokens_attr = streaming_params.get("max_tokens") or streaming_params.get("max_completion_tokens")

        # Extract endpoint preference and reasoning params from model_config for logging
        endpoint_pref = getattr(model_config, "endpoint_preference", "auto") if model_config else "auto"
        reasoning_effort = getattr(model_config, "reasoning_effort", None) if model_config else None
        verbosity = getattr(model_config, "verbosity", None) if model_config else None

        # Create span with GenAI semantic conventions
        span_attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": self._active_agent,
            "gen_ai.agent.description": f"Voice agent: {self._active_agent}",
            "gen_ai.provider.name": "azure.ai.openai",
            "gen_ai.request.model": model_name,
            "gen_ai.request.max_tokens": max_tokens_attr,
            "gen_ai.request.endpoint_preference": endpoint_pref,
            "session.id": self.config.session_id or "",
            "rt.session.id": self.config.session_id or "",
            "rt.call.connection_id": self.config.call_connection_id or "",
            # Azure Monitor semantic conventions
            "dependency.type": "Azure OpenAI",
            "peer.service": "azure.ai.openai",
            "component": "cascade_adapter",
            "cascade.streaming": True,
            "cascade.tool_loop_iteration": _iteration,
        }
        # Add chat completions params (always used for streaming)
        span_attributes["gen_ai.request.temperature"] = temp_attr
        span_attributes["gen_ai.request.top_p"] = top_p_attr
        # Add responses API params if configured
        if reasoning_effort:
            span_attributes["gen_ai.request.reasoning_effort"] = reasoning_effort
        if verbosity is not None:
            span_attributes["gen_ai.request.verbosity"] = verbosity

        with tracer.start_as_current_span(
            f"invoke_agent {self._active_agent}",
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            try:
                # Build log message based on endpoint preference
                # Streaming always uses chat.completions, but show configured params appropriately
                if endpoint_pref == "responses":
                    # Responses API config: show reasoning-specific parameters
                    params_str = f"reasoning_effort={reasoning_effort or 'N/A'} verbosity={verbosity if verbosity is not None else 'N/A'} max_tokens={max_tokens_attr or 'N/A'}"
                else:
                    # Chat Completions config: show traditional parameters
                    params_str = f"temp={temp_attr if temp_attr is not None else 'N/A'} top_p={top_p_attr if top_p_attr is not None else 'N/A'} max_tokens={max_tokens_attr or 'N/A'}"

                logger.info(
                    "Starting LLM request (streaming) | agent=%s model=%s endpoint=%s %s iteration=%d tools=%d",
                    self._active_agent,
                    model_name,
                    endpoint_pref,
                    params_str,
                    _iteration,
                    len(tools) if tools else 0,
                )

                # Use asyncio.Queue for thread-safe async communication
                # Special markers: None = stream end, "__HANDOFF_DETECTED__" = discard prior text
                tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
                tool_buffers: dict[str, dict[str, Any]] = {}
                collected_text: list[str] = []
                stream_error: list[Exception] = []
                stream_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
                loop = asyncio.get_running_loop()
                tool_call_detected = False  # Track if tool calls are streaming
                handoff_tool_detected = False  # Track if specifically a handoff tool

                # Sentence buffer state for sentence-based TTS streaming
                sentence_buffer = ""
                # Primary breaks: sentence endings
                primary_terms = ".!?"

                def _put_chunk(text: str) -> None:
                    """Thread-safe put to async queue."""
                    # Don't send text to TTS if tool calls are being made
                    # The LLM sometimes outputs explanatory text alongside tool calls
                    if tool_call_detected:
                        return
                    if text and text.strip():
                        loop.call_soon_threadsafe(tts_queue.put_nowait, text)
                
                def _signal_handoff_detected() -> None:
                    """Signal consumer to discard any queued text (for discrete handoffs)."""
                    loop.call_soon_threadsafe(tts_queue.put_nowait, "__HANDOFF_DETECTED__")

                # Capture current OpenTelemetry context to propagate into thread
                from opentelemetry import context as otel_context
                current_context = otel_context.get_current()

                def _streaming_completion():
                    """Run in thread - consumes OpenAI stream."""
                    nonlocal sentence_buffer, tool_call_detected, handoff_tool_detected
                    # Attach the parent span context in the thread
                    token = otel_context.attach(current_context)
                    try:
                        # Use pre-prepared streaming parameters
                        api_params = streaming_params

                        logger.debug(
                            "Starting OpenAI stream | model=%s messages=%d tools=%d params=%s",
                            model_name,
                            len(messages),
                            len(tools) if tools else 0,
                            {k: v for k, v in api_params.items() if k not in ["messages", "tools"]},
                        )
                        chunk_count = 0

                        # Extract telemetry values for span attributes
                        temp_value = api_params.get("temperature")
                        top_p_value = api_params.get("top_p")
                        max_tokens_value = api_params.get("max_tokens") or api_params.get("max_completion_tokens")

                        # SIMPLIFIED: Always use chat.completions for streaming
                        # Params are built by _prepare_streaming_params for chat API
                        endpoint_name = "chat.completions"

                        # Create a span for the OpenAI streaming call
                        with tracer.start_as_current_span(
                            f"openai.{endpoint_name}.create (streaming)",
                            kind=SpanKind.CLIENT,
                            attributes={
                                "dependency.type": "Azure OpenAI",
                                "peer.service": "azure.ai.openai",
                                "gen_ai.operation.name": "chat",
                                "gen_ai.request.model": model_name,
                                "gen_ai.request.temperature": temp_value,
                                "gen_ai.request.top_p": top_p_value,
                                "gen_ai.request.max_tokens": max_tokens_value,
                                "gen_ai.streaming": True,
                                "gen_ai.endpoint_type": "chat",
                            },
                        ) as openai_span:
                            # Always use chat completions API for streaming
                            stream = client.chat.completions.create(**api_params)

                            for chunk in stream:
                                chunk_count += 1

                                # Capture usage data from final chunk (stream_options.include_usage)
                                # Usage comes in a separate chunk at the end of the stream
                                usage = getattr(chunk, "usage", None)
                                if usage:
                                    # Handle both OpenAI and Azure naming conventions
                                    input_tok = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0
                                    output_tok = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0
                                    stream_usage["input_tokens"] = input_tok
                                    stream_usage["output_tokens"] = output_tok
                                    logger.debug(
                                        "Stream usage captured | input=%d output=%d",
                                        input_tok, output_tok
                                    )

                                if not getattr(chunk, "choices", None):
                                    continue
                                choice = chunk.choices[0]
                                delta = getattr(choice, "delta", None)
                                if not delta:
                                    continue

                                # Tool calls - aggregate streamed chunks by index
                                # Check tool calls FIRST to detect before dispatching text
                                if getattr(delta, "tool_calls", None):
                                    if not tool_call_detected:
                                        tool_call_detected = True
                                        logger.debug("Tool call detected - suppressing TTS output")
                                    for tc in delta.tool_calls:
                                        # Use explicit None check - index=0 is valid!
                                        tc_idx = getattr(tc, "index", None)
                                        if tc_idx is None:
                                            tc_idx = len(tool_buffers)
                                        tc_key = f"tool_{tc_idx}"

                                        if tc_key not in tool_buffers:
                                            tool_buffers[tc_key] = {
                                                "id": getattr(tc, "id", None) or tc_key,
                                                "name": "",
                                                "arguments": "",
                                            }

                                        buf = tool_buffers[tc_key]
                                        tc_id = getattr(tc, "id", None)
                                        if tc_id:
                                            buf["id"] = tc_id
                                        fn = getattr(tc, "function", None)
                                        if fn:
                                            fn_name = getattr(fn, "name", None)
                                            if fn_name:
                                                buf["name"] = fn_name
                                                # Check if this is a handoff tool - signal to discard queued text
                                                # This ensures discrete handoffs are seamless (no old agent speech)
                                                if not handoff_tool_detected and self.handoff_service.is_handoff(fn_name):
                                                    handoff_tool_detected = True
                                                    logger.debug(
                                                        "Handoff tool detected: %s - signaling to discard queued TTS",
                                                        fn_name,
                                                    )
                                                    _signal_handoff_detected()
                                            fn_args = getattr(fn, "arguments", None)
                                            if fn_args:
                                                buf["arguments"] += fn_args

                                # Text content - collect but only TTS if no tool calls
                                if getattr(delta, "content", None):
                                    text = delta.content
                                    collected_text.append(text)
                                    sentence_buffer += self._sanitize_tts_text(text)

                                    # Dispatch only on sentence boundaries.
                                    while True:
                                        term_idx = self._find_tts_boundary(
                                            sentence_buffer, primary_terms, 0
                                        )
                                        if term_idx < 0:
                                            break
                                        dispatch, sentence_buffer = self._split_tts_buffer(
                                            sentence_buffer, term_idx + 1
                                        )
                                        _put_chunk(dispatch)

                            logger.debug("OpenAI stream completed | chunks=%d", chunk_count)
                            # Flush remaining buffer (only if no tool calls)
                            if sentence_buffer.strip():
                                _put_chunk(sentence_buffer)
                    except Exception as e:
                        logger.error("OpenAI stream error: %s", e)
                        stream_error.append(e)
                    finally:
                        # Detach the context
                        otel_context.detach(token)
                        # Signal end
                        loop.call_soon_threadsafe(tts_queue.put_nowait, None)

                # Start stream in thread
                stream_future = asyncio.get_running_loop().run_in_executor(
                    None, _streaming_completion
                )

                # Consume queue with timeout - don't hang forever
                llm_timeout = 90.0  # seconds
                queue_timeout = 5.0  # per-chunk timeout
                start_time = time.perf_counter()
                suppress_tts_output = False  # Set to True when handoff detected

                while True:
                    elapsed = time.perf_counter() - start_time
                    if elapsed > llm_timeout:
                        logger.error("LLM response timeout after %.1fs", elapsed)
                        break

                    try:
                        chunk = await asyncio.wait_for(tts_queue.get(), timeout=queue_timeout)
                    except TimeoutError:
                        # Check if stream is still running
                        if stream_future.done():
                            # Stream finished but didn't signal - break out
                            logger.warning("Stream finished without signaling queue end")
                            break
                        # Otherwise keep waiting
                        continue

                    if chunk is None:
                        break
                    
                    # Handle handoff detection signal - suppress all TTS output for seamless handoff
                    if chunk == "__HANDOFF_DETECTED__":
                        suppress_tts_output = True
                        logger.debug("Handoff detected - suppressing all TTS output for seamless transfer")
                        continue
                    
                    # Skip TTS if handoff is pending (for discrete/seamless handoffs)
                    if suppress_tts_output:
                        logger.debug("Suppressing TTS chunk due to pending handoff: %s...", chunk[:30] if len(chunk) > 30 else chunk)
                        continue
                        
                    if on_tts_chunk:
                        try:
                            await on_tts_chunk(chunk)
                        except Exception as e:
                            logger.debug("TTS callback error: %s", e)

                # Wait for stream to finish with timeout
                try:
                    await asyncio.wait_for(stream_future, timeout=10.0)
                except TimeoutError:
                    logger.error("Stream thread did not complete in time")

                if stream_error:
                    raise stream_error[0]

                response_text = "".join(collected_text).strip()

                # Filter out incomplete tool calls (empty name or malformed)
                raw_tool_calls = list(tool_buffers.values())
                tool_calls = []
                for tc in raw_tool_calls:
                    name = tc.get("name", "").strip()
                    if not name:
                        logger.debug("Skipping tool call with empty name: %s", tc)
                        continue
                    # Validate arguments are parseable JSON
                    args_str = tc.get("arguments", "")
                    if args_str:
                        try:
                            json.loads(args_str)
                        except json.JSONDecodeError as e:
                            logger.warning(
                                "Skipping tool call with invalid JSON args: name=%s error=%s",
                                name,
                                e,
                            )
                            continue
                    tool_calls.append(tc)

                # Use actual token usage from stream if available, fallback to estimate
                input_tokens = stream_usage.get("input_tokens", 0)
                output_tokens = stream_usage.get("output_tokens", 0)
                
                # Fallback to estimate if stream didn't provide usage
                if output_tokens == 0 and response_text:
                    output_tokens = len(response_text) // 4
                    logger.debug("Using estimated output_tokens=%d (stream usage not available)", output_tokens)
                
                # Track tokens via metrics - now includes input tokens
                self._metrics.add_tokens(input_tokens=input_tokens, output_tokens=output_tokens)
                self._metrics.record_response()

                logger.info(
                    "LLM response (streamed) | agent=%s text_len=%d tool_calls=%d (filtered from %d) iteration=%d tokens=%d/%d",
                    self._active_agent,
                    len(response_text),
                    len(tool_calls),
                    len(raw_tool_calls),
                    _iteration,
                    input_tokens,
                    output_tokens,
                )

                # Set GenAI semantic convention attributes for App Insights
                span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                span.set_attribute("gen_ai.response.length", len(response_text))

                if tool_calls:
                    span.set_attribute("tool_call_detected", True)
                    span.set_attribute("tool_names", [tc.get("name", "") for tc in tool_calls])

                # Process tool calls if any
                non_handoff_tools = [
                    tc for tc in tool_calls if not self.handoff_service.is_handoff(tc.get("name", ""))
                ]
                handoff_tools = [tc for tc in tool_calls if self.handoff_service.is_handoff(tc.get("name", ""))]

                all_tool_calls.extend(tool_calls)

                # If we have handoff tools, return immediately (handoffs handled by caller)
                if handoff_tools:
                    span.set_attribute("cascade.handoff_detected", True)
                    span.set_status(Status(StatusCode.OK))
                    return response_text, all_tool_calls

                # Execute non-handoff tools and loop back to LLM
                if non_handoff_tools:
                    # Append assistant message with tool calls to history
                    assistant_msg: dict[str, Any] = {"role": "assistant"}
                    if response_text:
                        assistant_msg["content"] = response_text
                    else:
                        assistant_msg["content"] = None
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": tc.get("arguments", "{}"),
                            },
                        }
                        for tc in non_handoff_tools
                    ]
                    messages.append(assistant_msg)

                    # Execute each tool and collect results
                    agent = self.current_agent_config

                    # Get session scope for context preservation
                    session_scope = CascadeSessionScope.get_current()
                    cm = session_scope.memo_manager if session_scope else self._current_memo_manager

                    # Persist assistant message with tool calls to MemoManager
                    # This ensures the tool call is in history for subsequent turns
                    if cm:
                        try:
                            # Store the assistant message as JSON to preserve tool_calls structure
                            cm.append_to_history(
                                self._active_agent,
                                "assistant",
                                (
                                    json.dumps(assistant_msg)
                                    if assistant_msg.get("tool_calls")
                                    else (response_text or "")
                                ),
                            )
                        except Exception:
                            logger.debug(
                                "Failed to persist assistant tool_call message to history",
                                exc_info=True,
                            )

                    tool_results_for_history: list[dict[str, Any]] = []

                    for tool_call in non_handoff_tools:
                        tool_name = tool_call.get("name", "")
                        tool_id = tool_call.get("id", "")
                        raw_args = tool_call.get("arguments", "{}")

                        # Create tool execution span for App Insights tracing
                        tool_span_attrs = {
                            SpanAttr.GENAI_OPERATION_NAME.value: GenAIOperation.EXECUTE_TOOL,
                            SpanAttr.GENAI_TOOL_NAME.value: tool_name,
                            SpanAttr.GENAI_TOOL_CALL_ID.value: tool_id,
                            SpanAttr.GENAI_TOOL_TYPE.value: "function",
                            SpanAttr.PEER_SERVICE.value: "agent.tools",
                        }

                        with tracer.start_as_current_span(
                            f"execute_tool {tool_name}",
                            kind=trace.SpanKind.INTERNAL,
                            attributes=tool_span_attrs,
                        ) as tool_span:
                            if on_tool_start:
                                await on_tool_start(tool_name, raw_args)

                            result: dict[str, Any] = {"error": "Tool execution failed"}
                            if agent:
                                try:
                                    args = (
                                        json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                    )
                                    # Inject session context into tool args for profile-aware tools
                                    # This allows tools to use already-loaded session data
                                    if cm:
                                        session_profile = cm.get_value_from_corememory("session_profile")
                                        if session_profile:
                                            args["_session_profile"] = session_profile
                                    result = await agent.execute_tool(tool_name, args)
                                    logger.info(
                                        "Tool executed | name=%s result_keys=%s",
                                        tool_name,
                                        (
                                            list(result.keys())
                                            if isinstance(result, dict)
                                            else type(result).__name__
                                        ),
                                    )

                                    # Persist tool output to MemoManager for context continuity
                                    if cm:
                                        try:
                                            cm.persist_tool_output(tool_name, result)
                                            # Update any slots returned by the tool
                                            if isinstance(result, dict) and "slots" in result:
                                                cm.update_slots(result["slots"])
                                        except Exception as persist_err:
                                            logger.debug(
                                                "Failed to persist tool output: %s", persist_err
                                            )

                                    # Mark tool span as successful
                                    tool_span.set_status(Status(StatusCode.OK))

                                except Exception as e:
                                    logger.error("Tool execution failed for %s: %s", tool_name, e)
                                    result = {"error": str(e), "tool_name": tool_name}
                                    # Record GenAI error for failed tool execution
                                    tool_span.set_status(Status(StatusCode.ERROR, str(e)))
                                    tool_span.record_exception(e)
                                    tool_span.add_event(
                                        "gen_ai.tool.execution_error",
                                        {
                                            "error.type": type(e).__name__,
                                            "error.message": str(e),
                                            "gen_ai.tool.name": tool_name,
                                        },
                                    )

                            if on_tool_end:
                                await on_tool_end(tool_name, result)

                            # Append tool result message
                            tool_result_msg = {
                                "tool_call_id": tool_id,
                                "role": "tool",
                                "name": tool_name,
                                "content": (
                                    json.dumps(result) if isinstance(result, dict) else str(result)
                                ),
                            }
                            messages.append(tool_result_msg)
                            tool_results_for_history.append(tool_result_msg)

                    # Persist tool results to MemoManager for history continuity
                    if cm and tool_results_for_history:
                        try:
                            for tool_msg in tool_results_for_history:
                                cm.append_to_history(
                                    self._active_agent, "tool", json.dumps(tool_msg)
                                )
                        except Exception:
                            logger.debug("Failed to persist tool results to history", exc_info=True)

                    # Recurse to get LLM follow-up response
                    span.add_event(
                        "tool_followup_starting", {"tools_executed": len(non_handoff_tools)}
                    )
                    followup_text, followup_tools = await self._process_llm(
                        messages=messages,
                        tools=tools,
                        on_tts_chunk=on_tts_chunk,
                        on_tool_start=on_tool_start,
                        on_tool_end=on_tool_end,
                        _iteration=_iteration + 1,
                        _max_iterations=_max_iterations,
                    )

                    # Combine results
                    all_tool_calls.extend(followup_tools)
                    span.set_status(Status(StatusCode.OK))
                    return followup_text, all_tool_calls

                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.exception("LLM processing failed: %s", e)
                response_text = "I apologize, I encountered an error processing your request. Please ensure the selected agent model is available in your Azure AI Foundry resource."
                

        return response_text, all_tool_calls

    async def _dispatch_tts_chunks(
        self,
        text: str,
        on_tts_chunk: Callable[[str], Awaitable[None]],
        *,
        min_chunk: int = 40,
    ) -> None:
        """
        Emit TTS chunks based on sentence boundaries.

        Splits by sentence boundaries and flushes any remaining text at end.
        """
        try:
            sanitized = self._sanitize_tts_text(text).strip()
            if not sanitized:
                return

            segments: list[str] = []
            buffer = sanitized
            primary_terms = ".!?"
            while True:
                term_idx = self._find_tts_boundary(buffer, primary_terms, 0)
                if term_idx < 0:
                    break
                segment, buffer = self._split_tts_buffer(buffer, term_idx + 1)
                if segment.strip():
                    segments.append(segment)

            if buffer.strip():
                segments.append(buffer)

            for segment in segments:
                result = on_tts_chunk(segment)
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("TTS chunk dispatch failed: %s", exc)

    def _prepare_streaming_params(
        self,
        model_config: Any,
        model_name: str,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> dict[str, Any]:
        """
        Prepare API parameters for streaming LLM calls.

        SIMPLIFIED: Always builds chat.completions compatible params for streaming.
        This avoids endpoint/param mismatches that cause runtime errors.

        Parameter rules by model type:
        - Legacy models (gpt-4o, gpt-4): temperature, top_p, max_tokens
        - New-gen models (o1, o3, o4, gpt-5, gpt-5.1, gpt-4.1): max_completion_tokens

        Args:
            model_config: ModelConfig instance (or None for defaults)
            model_name: Deployment ID
            messages: Conversation messages
            tools: Tool definitions

        Returns:
            Dict of parameters for chat.completions.create()
        """
        # Detect if this is a new-generation model that uses max_completion_tokens
        # This includes: reasoning models (o1/o3/o4) AND new GPT models (gpt-5.x, gpt-4.1)
        deployment_lower = model_name.lower() if model_name else ""
        
        # Patterns for new-gen models requiring max_completion_tokens
        new_gen_patterns = ["o1", "o3-", "o4-", "gpt-5", "gpt5", "gpt-4.1", "gpt4.1"]
        uses_max_completion_tokens = any(p in deployment_lower for p in new_gen_patterns)
        
        # Also check model_config for explicit settings
        if model_config:
            uses_max_completion_tokens = uses_max_completion_tokens or \
                getattr(model_config, "is_reasoning_model", False)
            model_family = getattr(model_config, "model_family", None)
            if model_family in ["o1", "o3", "o4", "gpt-5", "gpt-4.1"]:
                uses_max_completion_tokens = True
        
        # Models that don't support custom temperature (reasoning models only)
        no_custom_temp = any(p in deployment_lower for p in ["o1", "o3-", "o4-"])
        if model_config:
            model_family = getattr(model_config, "model_family", None)
            if model_family in ["o1", "o3", "o4"]:
                no_custom_temp = True

        # Base params - always required
        params: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "timeout": 60,
        }

        # Add tools if provided
        if tools:
            params["tools"] = tools

        # Token limit parameter
        max_tokens = 4096  # default
        if model_config:
            max_tokens = getattr(model_config, "max_completion_tokens", None) or \
                         getattr(model_config, "max_tokens", None) or 4096

        if uses_max_completion_tokens:
            params["max_completion_tokens"] = max_tokens
        else:
            params["max_tokens"] = max_tokens

        # Temperature/top_p - only for models that support them
        if not no_custom_temp:
            temp = 0.7  # default
            if model_config:
                temp = getattr(model_config, "temperature", None)
                if temp is None:
                    temp = 0.7
            params["temperature"] = temp

            top_p = None
            if model_config:
                top_p = getattr(model_config, "top_p", None)
            if top_p is not None:
                params["top_p"] = top_p

        logger.debug(
            "Prepared streaming params | model=%s uses_max_completion_tokens=%s no_custom_temp=%s",
            model_name, uses_max_completion_tokens, no_custom_temp
        )

        return params

    def _extract_error_details(self, exception: Exception) -> str:
        """
        Extract user-friendly error details from various exception types.

        Returns a JSON string with error code and message for frontend display.
        """
        import json

        error_str = str(exception)

        # OpenAI API errors - extract code and message
        if "Error code:" in error_str:
            try:
                # Parse OpenAI error format: "Error code: 404 - {'error': {'code': 'DeploymentNotFound', ...}}"
                if "DeploymentNotFound" in error_str:
                    return json.dumps({
                        "code": "DeploymentNotFound",
                        "message": "The specified model deployment was not found. Please check your model configuration.",
                        "details": "Verify that the deployment ID matches your Azure OpenAI deployment name."
                    })
                elif "RateLimitError" in error_str or "429" in error_str:
                    return json.dumps({
                        "code": "RateLimitExceeded",
                        "message": "Too many requests. Please wait a moment and try again.",
                        "details": "You've exceeded the rate limit for this deployment."
                    })
                elif "InvalidApiKey" in error_str or "401" in error_str:
                    return json.dumps({
                        "code": "AuthenticationError",
                        "message": "Authentication failed. Please check your API configuration.",
                        "details": "The API key or authentication token is invalid or expired."
                    })
                elif "ContentFilter" in error_str:
                    return json.dumps({
                        "code": "ContentFiltered",
                        "message": "Your request was flagged by content filters.",
                        "details": "Please rephrase your request to comply with usage policies."
                    })
                elif "ContextLengthExceeded" in error_str or "maximum context length" in error_str:
                    return json.dumps({
                        "code": "ContextLengthExceeded",
                        "message": "The conversation is too long for the model's context window.",
                        "details": "Try starting a new conversation or shortening your message."
                    })
                elif "unsupported_parameter" in error_str.lower() or "UnsupportedParameter" in error_str:
                    # Extract which parameter is unsupported
                    param_match = None
                    if "'max_tokens'" in error_str:
                        param_match = "max_tokens"
                    elif "param" in error_str:
                        import re
                        match = re.search(r"'param':\s*'([^']+)'", error_str)
                        if match:
                            param_match = match.group(1)

                    return json.dumps({
                        "code": "UnsupportedParameter",
                        "message": f"The parameter '{param_match or 'provided'}' is not supported by this model.",
                        "details": "This model may require the responses API endpoint. Try setting endpoint_preference to 'responses' in your agent configuration, or check that you're using compatible parameters for your model."
                    })
                else:
                    # Generic OpenAI error
                    return json.dumps({
                        "code": "APIError",
                        "message": "An error occurred while processing your request.",
                        "details": error_str[:200]  # Truncate long error messages
                    })
            except Exception:
                pass

        # Connection errors
        if "connection" in error_str.lower() or "timeout" in error_str.lower():
            return json.dumps({
                "code": "ConnectionError",
                "message": "Unable to connect to the AI service.",
                "details": "Please check your network connection and try again."
            })

        # Generic fallback
        return json.dumps({
            "code": "UnknownError",
            "message": "An unexpected error occurred.",
            "details": error_str[:200]  # Truncate long error messages
        })

    async def cancel_current(self) -> None:
        """Signal cancellation for barge-in."""
        self._cancel_event.set()

    # ─────────────────────────────────────────────────────────────────
    # Handoff Management
    # ─────────────────────────────────────────────────────────────────

    async def _execute_handoff(
        self,
        target_agent: str,
        tool_name: str,
        args: dict[str, Any],
        system_vars: dict[str, Any] | None = None,
    ) -> HandoffResult:
        """
        Execute a handoff to another agent.

        Uses HandoffService for consistent resolution and greeting selection
        across both Cascade and VoiceLive orchestrators.

        Args:
            target_agent: Target agent name
            tool_name: Handoff tool that triggered the switch
            args: Tool arguments (may contain context)
            system_vars: Optional system variables for greeting selection

        Returns:
            HandoffResult with success status, handoff_type, greeting, etc.
        """
        previous_agent = self._active_agent
        is_first_visit = target_agent not in self._visited_agents

        with tracer.start_as_current_span(
            "cascade.handoff",
            kind=SpanKind.INTERNAL,
            attributes={
                "cascade.source_agent": previous_agent,
                "cascade.target_agent": target_agent,
                "cascade.tool_name": tool_name,
                "cascade.is_first_visit": is_first_visit,
            },
        ) as span:
            # Use HandoffService for consistent resolution
            resolution = self.handoff_service.resolve_handoff(
                tool_name=tool_name,
                tool_args=args,
                source_agent=previous_agent,
                current_system_vars=system_vars or self._session_vars,
                user_last_utterance=self._last_user_message,
            )

            if not resolution.success:
                logger.warning(
                    "Handoff resolution failed | tool=%s error=%s",
                    tool_name,
                    resolution.error,
                )
                span.set_status(Status(StatusCode.ERROR, resolution.error or "Handoff failed"))
                return HandoffResult(
                    success=False,
                    target_agent=target_agent,
                    handoff_type=resolution.handoff_type,
                    error=resolution.error,
                )

            # Update state
            self._visited_agents.add(target_agent)
            self._active_agent = target_agent

            # Reset metrics for new agent (captures summary of previous)
            self._metrics.reset_for_agent_switch(target_agent)

            # Select greeting using HandoffService for consistent behavior
            new_agent = self.agents[target_agent]
            greeting = self.handoff_service.select_greeting(
                agent=new_agent,
                is_first_visit=is_first_visit,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )

            # Notify callback
            if self._on_agent_switch:
                await self._on_agent_switch(previous_agent, target_agent)

            span.set_attribute("cascade.greeting", greeting or "(none)")
            span.set_attribute("cascade.handoff_type", resolution.handoff_type)
            span.set_attribute("cascade.share_context", resolution.share_context)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "Handoff: %s → %s (trigger=%s type=%s greeting=%s)",
                previous_agent,
                target_agent,
                tool_name,
                resolution.handoff_type,
                "yes" if greeting else "no",
            )

            return HandoffResult(
                success=True,
                target_agent=target_agent,
                handoff_type=resolution.handoff_type,
                greeting=greeting,
            )

    # ─────────────────────────────────────────────────────────────────
    # Greeting Selection (delegates to HandoffService)
    # ─────────────────────────────────────────────────────────────────

    def _select_greeting(
        self,
        agent: UnifiedAgent,
        agent_name: str,
        system_vars: dict[str, Any],
        is_first_visit: bool,
        greet_on_switch: bool = True,
    ) -> str | None:
        """
        Select appropriate greeting for agent activation.

        Delegates to HandoffService for consistent behavior across orchestrators.

        Args:
            agent: The agent to get greeting for
            agent_name: Name of the agent (unused, kept for backward compat)
            system_vars: System variables for template rendering
            is_first_visit: Whether this is first visit to agent
            greet_on_switch: Whether to greet (from scenario config)

        Returns:
            Greeting text or None
        """
        return self.handoff_service.select_greeting(
            agent=agent,
            is_first_visit=is_first_visit,
            greet_on_switch=greet_on_switch,
            system_vars=system_vars,
        )

    async def switch_agent(
        self,
        agent_name: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Programmatically switch to a different agent.

        Args:
            agent_name: Target agent name
            context: Optional handoff context

        Returns:
            True if switch succeeded
        """
        result = await self._execute_handoff(
            target_agent=agent_name,
            tool_name=f"manual_switch_{agent_name}",
            args=context or {},
        )
        return result.success

    # ─────────────────────────────────────────────────────────────────
    # MemoManager Integration
    # ─────────────────────────────────────────────────────────────────

    def sync_from_memo_manager(self, cm: MemoManager) -> None:
        """
        Sync adapter state from MemoManager.

        Call this at the start of each turn to pick up any
        state changes (e.g., handoffs set by tools), ensuring
        session context continuity.

        Args:
            cm: MemoManager instance
        """
        # Use shared sync utility
        state = sync_state_from_memo(cm, available_agents=set(self.agents.keys()))

        # Handle pending handoff (clears the pending key)
        if state.pending_handoff:
            target = state.pending_handoff.get("target_agent")
            if target and target in self.agents:
                logger.info("Pending handoff detected: %s", target)
                self._active_agent = target
                sync_state_to_memo(cm, active_agent=self._active_agent, clear_pending_handoff=True)

        # Apply synced state
        if state.active_agent:
            self._active_agent = state.active_agent
        if state.visited_agents:
            self._visited_agents = state.visited_agents
        if state.system_vars:
            self._session_vars.update(state.system_vars)

        # Restore cascade-specific state (turn count via metrics)
        turn_count = (
            cm.get_value_from_corememory("cascade_turn_count")
            if hasattr(cm, "get_value_from_corememory")
            else None
        )
        if turn_count and isinstance(turn_count, int):
            self._metrics._turn_count = turn_count

        # Restore token counts via metrics
        tokens = (
            cm.get_value_from_corememory("cascade_tokens")
            if hasattr(cm, "get_value_from_corememory")
            else None
        )
        if tokens and isinstance(tokens, dict):
            self._metrics.restore_from_memo(tokens)

    def sync_to_memo_manager(self, cm: MemoManager) -> None:
        """
        Sync adapter state to MemoManager.

        Call this after processing to persist state, ensuring
        session context continuity across turns.

        Args:
            cm: MemoManager instance
        """
        # Use shared sync utility for common state
        sync_state_to_memo(
            cm,
            active_agent=self._active_agent,
            visited_agents=self._visited_agents,
            system_vars=self._session_vars,
        )

        # Persist cascade-specific state (turn count, tokens) via metrics
        if hasattr(cm, "set_corememory"):
            cm.set_corememory("cascade_turn_count", self._metrics.turn_count)
            cm.set_corememory("cascade_tokens", self._metrics.to_memo_state())

    # ─────────────────────────────────────────────────────────────────
    # Legacy Interface for SpeechCascadeHandler
    # ─────────────────────────────────────────────────────────────────

    async def process_user_input(
        self,
        transcript: str,
        cm: MemoManager,
        *,
        on_tts_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> str | None:
        """
        DEPRECATED: Process user input in cascade pattern.

        This method is deprecated and will be removed in a future version.
        Use process_turn() directly instead:

            result = await adapter.process_turn(
                user_text=transcript,
                memo_manager=cm,
                on_tts_chunk=on_tts_chunk
            )
            return result.response_text

        This is now a thin compatibility shim that calls process_turn().

        Args:
            transcript: User's transcribed speech
            cm: MemoManager for conversation state
            on_tts_chunk: Optional callback for streaming TTS

        Returns:
            Full response text (or None if cancelled/error)
        """
        # Call unified process_turn with Pattern 2 (direct MemoManager)
        result = await self.process_turn(
            user_text=transcript,
            memo_manager=cm,
            on_tts_chunk=on_tts_chunk,
        )

        # Return text response (or None for errors/interrupts)
        if result.error or result.interrupted:
            return None
        return result.response_text

    async def _persist_to_redis_background(self, cm: MemoManager) -> None:
        """Background task to persist session state to Redis."""
        try:
            await cm.persist_to_redis_async(cm._redis_manager)
        except Exception as e:
            logger.warning("Redis persist failed: %s", e)

    def as_orchestrator_func(
        self,
    ) -> Callable[[MemoManager, str], Awaitable[str | None]]:
        """
        DEPRECATED: Return a function compatible with SpeechCascadeHandler.

        This method is deprecated and will be removed in a future version.
        Use the adapter instance directly with process_turn():

            # Instead of:
            handler = SpeechCascadeHandler(
                orchestrator_func=adapter.as_orchestrator_func(),
            )

            # Use:
            async def orchestrator_func(cm, transcript):
                result = await adapter.process_turn(
                    user_text=transcript,
                    memo_manager=cm
                )
                return result.response_text

        Returns:
            Callable matching the legacy orchestrator signature
        """

        async def orchestrator_func(
            cm: MemoManager,
            transcript: str,
        ) -> str | None:
            return await self.process_user_input(transcript, cm)

        return orchestrator_func


# ─────────────────────────────────────────────────────────────────────
# Factory Functions (DEPRECATED - Use CascadeOrchestratorAdapter.create())
# ─────────────────────────────────────────────────────────────────────


def get_cascade_orchestrator(
    *,
    start_agent: str | None = None,
    model_name: str | None = None,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    scenario_name: str | None = None,
    app_state: Any | None = None,
    **kwargs,
) -> CascadeOrchestratorAdapter:
    """
    DEPRECATED: Create a CascadeOrchestratorAdapter instance with scenario support.

    This function is deprecated. Use CascadeOrchestratorAdapter.create() directly:

        adapter = CascadeOrchestratorAdapter.create(
            start_agent="MyAgent",
            session_id="session_123",
            call_connection_id="call_456",
        )

    Resolution order for start_agent and agents:
    1. Explicit start_agent parameter
    2. app_state (if provided)
    3. Scenario configuration (AGENT_SCENARIO env var or scenario_name param)
    4. Default values

    Args:
        start_agent: Override initial agent name (None = auto-resolve)
        model_name: LLM deployment name (defaults to AZURE_OPENAI_DEPLOYMENT)
        call_connection_id: ACS call ID for tracing
        session_id: Session ID for tracing
        scenario_name: Override scenario name
        app_state: FastAPI app.state for pre-loaded config
        **kwargs: Additional configuration

    Returns:
        Configured CascadeOrchestratorAdapter
    """
    # Resolve configuration
    # Priority: explicit scenario_name overrides app_state preloads so per-session
    # scenarios (stored in MemoManager) take effect for cascade mode.
    if scenario_name:
        config = resolve_orchestrator_config(
            session_id=session_id,
            scenario_name=scenario_name,
            start_agent=start_agent,
        )
    elif app_state is not None:
        config = resolve_from_app_state(app_state)
    else:
        config = resolve_orchestrator_config(
            session_id=session_id,
            start_agent=start_agent,
        )

    # Use resolved start_agent unless explicitly overridden
    effective_start_agent = start_agent or config.start_agent

    return CascadeOrchestratorAdapter.create(
        start_agent=effective_start_agent,
        model_name=model_name,
        call_connection_id=call_connection_id,
        session_id=session_id,
        agents=config.agents,
        handoff_map=config.handoff_map,
        streaming=True,  # Explicitly disable streaming for cascade
        **kwargs,
    )


def create_cascade_orchestrator_func(
    *,
    start_agent: str | None = None,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    scenario_name: str | None = None,
    app_state: Any | None = None,
) -> Callable[[MemoManager, str], Awaitable[str | None]]:
    """
    DEPRECATED: Create an orchestrator function for SpeechCascadeHandler.

    This function is deprecated. Use CascadeOrchestratorAdapter.create() and
    process_turn() directly:

        adapter = CascadeOrchestratorAdapter.create(start_agent="MyAgent")

        async def orchestrator_func(cm, transcript):
            result = await adapter.process_turn(
                user_text=transcript,
                memo_manager=cm,
            )
            return result.response_text

    Usage (legacy):
        handler = SpeechCascadeHandler(
            orchestrator_func=create_cascade_orchestrator_func(
                # Let scenario determine start_agent
            ),
            ...
        )

    Args:
        start_agent: Override initial agent name (None = auto-resolve from scenario)
        call_connection_id: ACS call ID for tracing
        session_id: Session ID for tracing
        scenario_name: Override scenario name
        app_state: FastAPI app.state for pre-loaded config

    Returns:
        Orchestrator function compatible with SpeechCascadeHandler
    """
    adapter = get_cascade_orchestrator(
        start_agent=start_agent,
        call_connection_id=call_connection_id,
        session_id=session_id,
        scenario_name=scenario_name,
        app_state=app_state,
    )
    return adapter.as_orchestrator_func()


__all__ = [
    "CascadeOrchestratorAdapter",
    "CascadeConfig",
    "CascadeHandoffContext",
    "StateKeys",
    "get_cascade_orchestrator",
    "create_cascade_orchestrator_func",
]
