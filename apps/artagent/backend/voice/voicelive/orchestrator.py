"""
VoiceLive Orchestrator
=======================

Orchestrates agent switching and tool execution for VoiceLive multi-agent system.

All tool execution flows through the shared tool registry for centralized management:
- Handoff tools → trigger agent switching
- Business tools → execute and return results to model

Architecture:
    VoiceLiveSDKHandler
           │
           ▼
    LiveOrchestrator ─► UnifiedAgent registry
           │                    │
           ├─► handle_event()   └─► apply_voicelive_session()
           │                        trigger_voicelive_response()
           └─► _execute_tool_call() ───► shared tool registry

Usage:
    from apps.artagent.backend.voice.voicelive import (
        LiveOrchestrator,
        TRANSFER_TOOL_NAMES,
        CALL_CENTER_TRIGGER_PHRASES,
    )

    orchestrator = LiveOrchestrator(
        conn=voicelive_connection,
        agents=unified_agents,  # dict[str, UnifiedAgent]
        handoff_map=handoff_map,
        start_agent="Concierge",
    )
    await orchestrator.start(system_vars={...})
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import TYPE_CHECKING, Any

# Self-contained tool registry (no legacy vlagent dependency)
from apps.artagent.backend.registries.toolstore import (
    execute_tool,
    initialize_tools,
)
from apps.artagent.backend.src.services.session_loader import load_user_profile_by_client_id
from apps.artagent.backend.voice.handoffs import sanitize_handoff_context
from apps.artagent.backend.voice.shared.handoff_service import HandoffService
from apps.artagent.backend.voice.shared.metrics import OrchestratorMetrics
from apps.artagent.backend.voice.shared.session_state import (
    sync_state_from_memo,
    sync_state_to_memo,
)
from azure.ai.voicelive.models import (
    AssistantMessageItem,
    FunctionCallOutputItem,
    InputTextContentPart,
    OutputTextContentPart,
    ServerEventType,
    UserMessageItem,
)
from opentelemetry import trace

if TYPE_CHECKING:
    from src.stateful.state_managment import MemoManager

from apps.artagent.backend.registries.agentstore.base import UnifiedAgent

from apps.artagent.backend.src.utils.tracing import (
    create_service_dependency_attrs,
    create_service_handler_attrs,
)
from src.enums.monitoring import GenAIOperation, GenAIProvider, SpanAttr
from utils.ml_logging import get_logger

logger = get_logger("voicelive.orchestrator")
tracer = trace.get_tracer(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

TRANSFER_TOOL_NAMES = {"transfer_call_to_destination", "transfer_call_to_call_center"}

CALL_CENTER_TRIGGER_PHRASES = {
    "transfer to call center",
    "transfer me to the call center",
}

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION ORCHESTRATOR REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level registry for VoiceLive orchestrators (per session)
# This enables scenario updates to reach active VoiceLive sessions
# Uses standard dict but includes cleanup of stale entries
_voicelive_orchestrators: dict[str, "LiveOrchestrator"] = {}
_registry_lock = asyncio.Lock()


def register_voicelive_orchestrator(session_id: str, orchestrator: "LiveOrchestrator") -> None:
    """Register a VoiceLive orchestrator for scenario updates."""
    # Clean up stale entries first (orchestrators that may have been orphaned)
    _cleanup_stale_orchestrators()
    _voicelive_orchestrators[session_id] = orchestrator
    logger.debug(
        "Registered VoiceLive orchestrator | session=%s registry_size=%d",
        session_id,
        len(_voicelive_orchestrators),
    )


def unregister_voicelive_orchestrator(session_id: str) -> None:
    """Unregister a VoiceLive orchestrator when session ends."""
    orchestrator = _voicelive_orchestrators.pop(session_id, None)
    if orchestrator:
        logger.debug(
            "Unregistered VoiceLive orchestrator | session=%s registry_size=%d",
            session_id,
            len(_voicelive_orchestrators),
        )


def get_voicelive_orchestrator(session_id: str) -> "LiveOrchestrator | None":
    """Get the VoiceLive orchestrator for a session."""
    return _voicelive_orchestrators.get(session_id)


def _cleanup_stale_orchestrators() -> int:
    """
    Clean up orchestrators that are no longer valid.

    This catches cases where sessions ended without proper cleanup.
    Returns the number of stale entries removed.
    """
    stale_keys = []
    for session_id, orchestrator in list(_voicelive_orchestrators.items()):
        # Check if orchestrator is still valid (has connection reference)
        if orchestrator.conn is None and orchestrator.agents == {}:
            stale_keys.append(session_id)

    for key in stale_keys:
        _voicelive_orchestrators.pop(key, None)

    if stale_keys:
        logger.debug(
            "Cleaned up %d stale orchestrators from registry | remaining=%d",
            len(stale_keys),
            len(_voicelive_orchestrators),
        )

    return len(stale_keys)


def get_orchestrator_registry_size() -> int:
    """Get current size of orchestrator registry (for monitoring)."""
    return len(_voicelive_orchestrators)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def _auto_load_user_context(system_vars: dict[str, Any]) -> None:
    """
    Auto-load user profile into system_vars if client_id is present but session_profile is missing.

    This ensures that agents receiving handoffs with client_id can access user context
    for personalized conversations, even if the originating agent didn't pass full profile.

    Modifies system_vars in-place.
    """
    if system_vars.get("session_profile"):
        # Already have session_profile, no need to load
        return

    client_id = system_vars.get("client_id")
    if not client_id:
        # Check handoff_context for client_id
        handoff_ctx = system_vars.get("handoff_context", {})
        client_id = handoff_ctx.get("client_id") if isinstance(handoff_ctx, dict) else None

    if not client_id:
        return

    try:
        profile = await load_user_profile_by_client_id(client_id)
        if profile:
            system_vars["session_profile"] = profile
            system_vars["client_id"] = profile.get("client_id", client_id)
            system_vars["customer_intelligence"] = profile.get("customer_intelligence", {})
            system_vars["caller_name"] = profile.get("full_name")
            if profile.get("institution_name"):
                system_vars.setdefault("institution_name", profile["institution_name"])
            logger.info(
                "🔄 Auto-loaded user context for handoff | client_id=%s name=%s",
                client_id,
                profile.get("full_name"),
            )
    except Exception as exc:
        logger.warning("Failed to auto-load user context: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════


class LiveOrchestrator:
    """
    Orchestrates agent switching and tool execution for VoiceLive multi-agent system.

    All tool execution flows through the shared tool registry for centralized management:
    - Handoff tools → trigger agent switching
    - Business tools → execute and return results to model

    GenAI Telemetry:
    - Emits invoke_agent spans for App Insights Agents blade
    - Tracks token usage per agent session
    - Records LLM TTFT (Time To First Token) metrics
    """

    def __init__(
        self,
        conn,
        agents: dict[str, UnifiedAgent],
        handoff_map: dict[str, str] | None = None,
        start_agent: str = "Concierge",
        audio_processor=None,
        messenger=None,
        call_connection_id: str | None = None,
        *,
        transport: str = "acs",
        model_name: str | None = None,
        memo_manager: MemoManager | None = None,
    ):
        self.conn = conn
        self.agents = agents
        self._handoff_map = handoff_map or {}
        self.active = start_agent
        self.audio = audio_processor
        self.messenger = messenger
        self._model_name = model_name or "gpt-4o-realtime"
        self.visited_agents: set = set()
        self._pending_greeting: str | None = None
        self._pending_greeting_agent: str | None = None
        # Bounded deque to preserve last N user utterances for better handoff context
        self._user_message_history: deque[str] = deque(maxlen=5)
        self._last_user_message: str | None = None  # Keep for backward compatibility
        # Track assistant responses for conversation history persistence
        self._last_assistant_message: str | None = None
        self.call_connection_id = call_connection_id
        self._call_center_triggered = False
        self._transport = transport
        self._greeting_tasks: set[asyncio.Task] = set()
        self._active_response_id: str | None = None
        self._system_vars: dict[str, Any] = {}

        # MemoManager for session state continuity (consistent with CascadeOrchestratorAdapter)
        self._memo_manager: MemoManager | None = memo_manager

        # Unified metrics tracking (tokens, TTFT, turn count)
        self._metrics = OrchestratorMetrics(
            agent_name=start_agent,
            call_connection_id=call_connection_id,
            session_id=getattr(messenger, "session_id", None) if messenger else None,
        )

        # Throttle session context updates to avoid hot path latency
        self._last_session_update_time: float = 0.0
        self._session_update_min_interval: float = 2.0  # Min seconds between updates
        self._pending_session_update: bool = False

        if self.messenger:
            try:
                self.messenger.set_active_agent(self.active)
            except AttributeError:
                logger.debug("Messenger does not support set_active_agent", exc_info=True)

        if self.active not in self.agents:
            raise ValueError(f"Start agent '{self.active}' not found in registry")

        # Initialize the tool registry
        initialize_tools()

        # Initialize HandoffService for unified handoff resolution
        self._handoff_service: HandoffService | None = None

        # Sync state from MemoManager if available
        if self._memo_manager:
            self._sync_from_memo_manager()

    # ═══════════════════════════════════════════════════════════════════════════
    # MEMO MANAGER SYNC (consistent with CascadeOrchestratorAdapter)
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def memo_manager(self) -> MemoManager | None:
        """Return the current MemoManager instance."""
        return self._memo_manager

    @property
    def _session_id(self) -> str | None:
        """
        Get the session ID from memo_manager or messenger.

        Cached property to avoid repeated attribute access.
        """
        if self._memo_manager:
            session_id = getattr(self._memo_manager, "session_id", None)
            if session_id:
                return session_id
        if self.messenger:
            return getattr(self.messenger, "session_id", None)
        return None

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
            from apps.artagent.backend.voice.shared.config_resolver import resolve_orchestrator_config

            self._cached_orchestrator_config = resolve_orchestrator_config(
                session_id=self._session_id
            )
            logger.debug(
                "[LiveOrchestrator] Cached orchestrator config | scenario=%s session=%s",
                self._cached_orchestrator_config.scenario_name,
                self._session_id,
            )
        return self._cached_orchestrator_config

    def _sync_from_memo_manager(self) -> None:
        """
        Sync orchestrator state from MemoManager.
        Called at initialization and optionally at turn boundaries.

        Uses shared sync_state_from_memo for consistency with CascadeOrchestratorAdapter.
        
        NOTE: For VoiceLive, we intentionally DO NOT sync visited_agents because:
        - VoiceLive starts with a fresh conversation history each connection
        - If we sync visited_agents, we'd show return_greeting but model has no context
        - This causes the model to behave inconsistently (greeting says "welcome back" 
          but model doesn't know what happened before)
        """
        if not self._memo_manager:
            return

        # Use shared sync utility
        state = sync_state_from_memo(
            self._memo_manager,
            available_agents=set(self.agents.keys()),
        )

        # Apply synced state - but NOT visited_agents for VoiceLive
        # VoiceLive conversation history is per-connection, so we always treat as first visit
        if state.active_agent:
            self.active = state.active_agent
            logger.debug("[LiveOrchestrator] Synced active_agent: %s", self.active)

        # IMPORTANT: Do NOT sync visited_agents for VoiceLive
        # Each VoiceLive connection starts fresh - syncing visited_agents causes
        # return_greeting to be used but model has no conversation context
        # if state.visited_agents:
        #     self.visited_agents = state.visited_agents
        #     logger.debug("[LiveOrchestrator] Synced visited_agents: %s", self.visited_agents)
        logger.debug(
            "[LiveOrchestrator] Skipping visited_agents sync - VoiceLive starts fresh each connection"
        )

        if state.system_vars:
            self._system_vars.update(state.system_vars)
            logger.debug("[LiveOrchestrator] Synced system_vars")

        # Restore user message history if available (for session continuity)
        try:
            stored_history = self._memo_manager.get_value_from_corememory("user_message_history")
            if stored_history and isinstance(stored_history, list):
                self._user_message_history = deque(stored_history, maxlen=5)
                if stored_history:
                    self._last_user_message = stored_history[-1]
                logger.debug(
                    "[LiveOrchestrator] Restored %d messages from history",
                    len(stored_history),
                )
        except Exception:
            logger.debug("Failed to restore user message history", exc_info=True)

        # Handle pending handoff if any
        if state.pending_handoff:
            target = state.pending_handoff.get("target_agent")
            if target and target in self.agents:
                logger.info("[LiveOrchestrator] Pending handoff detected: %s", target)
                self.active = target
                # Clear the pending handoff
                sync_state_to_memo(
                    self._memo_manager, active_agent=self.active, clear_pending_handoff=True
                )

    def _sync_to_memo_manager(self) -> None:
        """
        Sync orchestrator state back to MemoManager.
        Called at turn boundaries to persist state.

        Uses shared sync_state_to_memo for consistency with CascadeOrchestratorAdapter.
        """
        if not self._memo_manager:
            return

        # Use shared sync utility
        sync_state_to_memo(
            self._memo_manager,
            active_agent=self.active,
            visited_agents=self.visited_agents,
            system_vars=self._system_vars,
        )

        # Sync last user message (VoiceLive-specific) for backward compatibility
        if hasattr(self._memo_manager, "last_user_message") and self._last_user_message:
            self._memo_manager.last_user_message = self._last_user_message

        # Persist user message history for session continuity
        if self._user_message_history:
            try:
                self._memo_manager.set_corememory(
                    "user_message_history", list(self._user_message_history)
                )
            except Exception:
                logger.debug("Failed to persist user message history", exc_info=True)

        logger.debug("[LiveOrchestrator] Synced state to MemoManager")

    def cleanup(self) -> None:
        """
        Clean up orchestrator resources to prevent memory leaks.

        This should be called when the VoiceLive session ends. It:
        - Cancels all pending greeting tasks
        - Clears references to agents and connections
        - Clears user message history deque
        - Resets all stateful tracking variables

        Note: This method is synchronous and does not await any coroutines.
        For async cleanup, use the handler's stop() method which calls this.
        """
        # Cancel all pending greeting tasks
        self._cancel_pending_greeting_tasks()

        # Clear agents registry reference
        self.agents = {}
        self._handoff_map = {}

        # Clear connection reference (do not close - handler owns it)
        self.conn = None

        # Clear messenger reference to break circular refs
        self.messenger = None
        self.audio = None

        # Clear memo manager reference (handler/endpoint owns lifecycle)
        self._memo_manager = None

        # Clear handoff service
        self._handoff_service = None

        # Clear user message history
        self._user_message_history.clear()
        self._last_user_message = None
        self._last_assistant_message = None

        # Clear pending greeting state
        self._pending_greeting = None
        self._pending_greeting_agent = None

        # Reset tracking variables
        self._active_response_id = None
        self._system_vars.clear()
        self.visited_agents.clear()

        logger.debug("[LiveOrchestrator] Cleanup complete")

    def update_scenario(
        self,
        agents: dict[str, UnifiedAgent],
        handoff_map: dict[str, str],
        start_agent: str | None = None,
        scenario_name: str | None = None,
    ) -> None:
        """
        Update the orchestrator with a new scenario configuration.

        This is called when the user changes scenarios mid-session via the UI.
        The orchestrator's agents and handoff map are updated to reflect
        the new scenario without restarting the VoiceLive connection.

        Args:
            agents: New UnifiedAgent registry (no adapter needed)
            handoff_map: New handoff routing map
            start_agent: Optional new start agent to switch to
            scenario_name: Optional scenario name for logging
        """
        old_agents = list(self.agents.keys())
        old_active = self.active
        needs_session_update = False

        # Update agents registry
        self.agents = agents

        # Update handoff map
        self._handoff_map = handoff_map

        # Clear cached HandoffService so it's recreated with new scenario
        self._handoff_service = None

        # Clear visited agents for fresh scenario experience
        self.visited_agents.clear()

        # Always switch to start_agent when a new scenario is explicitly selected
        if start_agent:
            if start_agent != self.active:
                self.active = start_agent
                needs_session_update = True
                logger.info(
                    "🔄 VoiceLive switching to scenario start_agent | from=%s to=%s scenario=%s",
                    old_active,
                    start_agent,
                    scenario_name or "(unknown)",
                )
            else:
                # Same agent but scenario changed - still need to update session
                needs_session_update = True
        elif self.active not in agents:
            # Current agent not in new scenario - switch to first available
            available = list(agents.keys())
            if available:
                self.active = available[0]
                needs_session_update = True
                logger.warning(
                    "🔄 VoiceLive current agent not in scenario, switching | from=%s to=%s",
                    old_active,
                    self.active,
                )

        logger.info(
            "🔄 VoiceLive scenario updated | old_agents=%s new_agents=%s active=%s scenario=%s",
            old_agents,
            list(agents.keys()),
            self.active,
            scenario_name or "(unknown)",
        )

        # CRITICAL: Trigger a session update to apply the new agent's instructions
        # This ensures VoiceLive uses the correct system prompt for the new agent
        if needs_session_update:
            self._schedule_scenario_session_update()

    def _schedule_scenario_session_update(self) -> None:
        """
        Schedule a session update after scenario change.
        
        This runs in the background to avoid blocking the scenario update call.
        """
        async def _do_update():
            try:
                # Refresh context with new agent
                self._refresh_session_context()
                # Update VoiceLive session with new instructions
                await self._update_session_context()
                logger.info(
                    "🔄 VoiceLive session updated for new agent | agent=%s",
                    self.active,
                )
            except Exception:
                logger.warning("Failed to update session after scenario change", exc_info=True)

        # Schedule on the event loop
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(_do_update(), loop)
        except RuntimeError:
            # No running loop - try create_task if we're in an async context
            try:
                asyncio.create_task(_do_update())
            except RuntimeError:
                logger.warning("Cannot schedule session update - no event loop available")

    async def _inject_conversation_history(self) -> None:
        """
        Inject conversation history as text items into VoiceLive conversation.

        CRITICAL FOR CONTEXT RETENTION:
        VoiceLive processes audio natively, but the model can "forget" context
        between turns. By injecting the conversation history as explicit text
        items, we give the model concrete text to reference.

        This should be called:
        - After session.update on agent switch (_switch_to)
        - Before the first response is triggered

        The text items become part of the conversation context that the model
        sees for all subsequent responses.
        """
        if not self.conn or not self._user_message_history:
            return

        try:
            # Inject each historical user message as a text conversation item
            # This establishes explicit text context for the model
            for msg in self._user_message_history:
                if not msg or not msg.strip():
                    continue
                
                # Create user message item with text content
                text_part = InputTextContentPart(text=msg)
                user_item = UserMessageItem(content=[text_part])
                
                # Add to conversation
                await self.conn.conversation.item.create(item=user_item)
            
            # Also inject last assistant message if available
            if self._last_assistant_message:
                # Create assistant message with text content
                text_part = OutputTextContentPart(text=self._last_assistant_message)
                assistant_item = AssistantMessageItem(content=[text_part])
                await self.conn.conversation.item.create(item=assistant_item)

            logger.info(
                "[LiveOrchestrator] Injected %d conversation items for context",
                len(self._user_message_history) + (1 if self._last_assistant_message else 0),
            )
        except Exception:
            logger.debug("Failed to inject conversation history", exc_info=True)

    def _refresh_session_context(self) -> None:
        """
        Refresh session context from MemoManager at the start of each turn.

        This picks up any external updates such as:
        - CRM lookups completed by tools
        - Session profile updates from MFA verification
        - Slot values filled by previous turns
        - Tool outputs from business logic

        Called from _handle_transcription_completed to ensure each turn
        has fresh context for prompt rendering.
        """
        if not self._memo_manager:
            return

        try:
            # Refresh session profile if updated externally
            session_profile = self._memo_manager.get_value_from_corememory("session_profile")
            if session_profile and isinstance(session_profile, dict):
                # Update system_vars with fresh profile data
                self._system_vars["session_profile"] = session_profile
                self._system_vars["client_id"] = session_profile.get("client_id")
                self._system_vars["caller_name"] = session_profile.get("full_name")
                self._system_vars["customer_intelligence"] = session_profile.get(
                    "customer_intelligence", {}
                )
                if session_profile.get("institution_name"):
                    self._system_vars["institution_name"] = session_profile["institution_name"]

            # Refresh slots (collected information from previous turns)
            slots = self._memo_manager.get_context("slots", {})
            if slots:
                self._system_vars["slots"] = slots
                self._system_vars["collected_information"] = slots

            # Refresh tool outputs for context continuity
            tool_outputs = self._memo_manager.get_context("tool_outputs", {})
            if tool_outputs:
                self._system_vars["tool_outputs"] = tool_outputs

            logger.debug("[LiveOrchestrator] Refreshed session context from MemoManager")
        except Exception:
            logger.debug("Failed to refresh session context", exc_info=True)

    async def _update_session_context(self) -> None:
        """
        Update VoiceLive session instructions with current context.

        This is called BEFORE each model response to ensure the model's instructions
        reflect the latest conversation context. Without this, the realtime model
        tends to forget what was discussed in previous turns.

        The update includes:
        - Base agent instructions (from prompt template)
        - Explicit conversation recap (critical for context retention)
        - Collected slots (e.g., user's name, account info)
        - Tool outputs (e.g., CRM lookup results)
        """
        if not self.conn or not self.active:
            return

        agent = self.agents.get(self.active)
        if not agent:
            return

        try:
            # Build context for prompt rendering
            context_vars = dict(self._system_vars)
            context_vars["active_agent"] = self.active

            # Add conversation context from message history
            if self._user_message_history:
                context_vars["recent_user_messages"] = list(self._user_message_history)
                if len(self._user_message_history) > 1:
                    context_vars["conversation_summary"] = " → ".join(self._user_message_history)

            # Add last assistant response for context continuity
            if self._last_assistant_message:
                context_vars["last_assistant_response"] = self._last_assistant_message

            # Render base instructions from agent prompt template
            base_instructions = agent._agent.render_prompt(context_vars) or ""

            # Inject handoff instructions from scenario configuration
            # Use the cached orchestrator config (supports both file-based and session-scoped)
            config = self._orchestrator_config
            if config.scenario and agent._agent.name:
                # Use scenario.build_handoff_instructions directly (works for session scenarios)
                handoff_instructions = config.scenario.build_handoff_instructions(agent._agent.name)
                if handoff_instructions:
                    base_instructions = f"{base_instructions}\n\n{handoff_instructions}" if base_instructions else handoff_instructions
                    logger.info(
                        "[LiveOrchestrator] Injected handoff instructions | agent=%s scenario=%s len=%d",
                        agent._agent.name,
                        config.scenario_name,
                        len(handoff_instructions),
                    )
            else:
                logger.debug(
                    "[LiveOrchestrator] No scenario or agent name for handoff instructions | scenario=%s agent=%s",
                    config.scenario_name if config.scenario else None,
                    agent._agent.name if hasattr(agent, '_agent') else None,
                )

            # Build conversation recap to append to instructions
            # This is critical for realtime models which tend to forget context
            conversation_recap = self._build_conversation_recap()

            # Combine base instructions with conversation recap
            if conversation_recap:
                updated_instructions = f"{base_instructions}\n\n{conversation_recap}"
            else:
                updated_instructions = base_instructions

            if not updated_instructions:
                return

            # Update session with new instructions
            from azure.ai.voicelive.models import RequestSession

            await self.conn.session.update(
                session=RequestSession(instructions=updated_instructions)
            )

            logger.debug(
                "[LiveOrchestrator] Updated session | agent=%s history_len=%d slots=%s",
                self.active,
                len(self._user_message_history),
                list(context_vars.get("slots", {}).keys()) if context_vars.get("slots") else [],
            )
        except Exception:
            logger.debug("Failed to update session context", exc_info=True)

    def _build_conversation_recap(self) -> str:
        """
        Build an explicit conversation recap to inject into instructions.

        This ensures the realtime model remembers what was discussed,
        even if it tends to forget context between turns.
        """
        parts = []

        # Add conversation history recap
        if self._user_message_history and len(self._user_message_history) > 0:
            parts.append("## CONVERSATION CONTEXT (DO NOT FORGET)")
            parts.append("The user has said the following in this conversation:")
            for i, msg in enumerate(self._user_message_history, 1):
                parts.append(f"  {i}. \"{msg}\"")
            parts.append("")
            parts.append("IMPORTANT: Remember and refer back to what the user has already told you. Do NOT ask them to repeat information they've already provided.")

        # Add collected slots/information
        slots = self._system_vars.get("slots", {})
        if slots:
            parts.append("")
            parts.append("## COLLECTED INFORMATION")
            for key, value in slots.items():
                if value:
                    parts.append(f"  - {key}: {value}")

        # Add last assistant response for context
        if self._last_assistant_message:
            parts.append("")
            parts.append("## YOUR LAST RESPONSE")
            # Truncate if too long
            last_resp = self._last_assistant_message
            if len(last_resp) > 200:
                last_resp = last_resp[:200] + "..."
            parts.append(f'You last said: "{last_resp}"')

        return "\n".join(parts) if parts else ""

    def _schedule_throttled_session_update(self) -> None:
        """
        Schedule a throttled session context update in the background.

        This avoids calling session.update() on the hot path,
        which can add significant latency to each turn.
        The actual network call is performed in a background task.
        """
        now = time.perf_counter()
        elapsed = now - self._last_session_update_time

        # Only update if enough time has passed OR we have a pending update from transcription
        if elapsed < self._session_update_min_interval and not self._pending_session_update:
            logger.debug(
                "[LiveOrchestrator] Skipping session update - throttled (%.1fs < %.1fs)",
                elapsed,
                self._session_update_min_interval,
            )
            return

        self._pending_session_update = False
        self._last_session_update_time = now

        # Refresh context first (fast, local operation)
        self._refresh_session_context()

        # Schedule the actual session update as a background task
        # This prevents blocking the event loop
        async def _do_session_update():
            try:
                await self._update_session_context()
            except Exception:
                logger.debug("Background session update failed", exc_info=True)

        asyncio.create_task(_do_session_update())

    def _schedule_background_sync(self) -> None:
        """
        Schedule MemoManager sync in background to avoid hot path latency.

        The sync is fire-and-forget - failures are logged but don't block.
        """
        if not self._memo_manager:
            return

        def _do_sync():
            try:
                self._sync_to_memo_manager()
            except Exception:
                logger.debug("Background MemoManager sync failed", exc_info=True)

        # Schedule on next event loop iteration to not block current coroutine
        asyncio.get_event_loop().call_soon(_do_sync)

    # ═══════════════════════════════════════════════════════════════════════════
    # HANDOFF RESOLUTION
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def handoff_service(self) -> HandoffService:
        """
        Get or create the HandoffService for unified handoff resolution.

        The service is lazily created on first access and uses the cached
        orchestrator config (supports both file-based and session-scoped scenarios).
        """
        if self._handoff_service is None:
            # Use cached orchestrator config for scenario resolution
            config = self._orchestrator_config

            self._handoff_service = HandoffService(
                scenario_name=config.scenario_name,
                handoff_map=self.handoff_map,
                agents=self.agents,
                memo_manager=self._memo_manager,
                scenario=config.scenario,  # Pass scenario object for session-scoped scenarios
            )
        return self._handoff_service

    def get_handoff_target(self, tool_name: str) -> str | None:
        """
        Get the target agent for a handoff tool.

        Uses the static handoff_map. For runtime resolution with
        scenario context, use HandoffService directly.
        """
        return self._handoff_map.get(tool_name)

    @property
    def handoff_map(self) -> dict[str, str]:
        """Get the current handoff map."""
        return self._handoff_map

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════════════════

    async def start(self, system_vars: dict | None = None):
        """Apply initial agent session and trigger an intro response."""
        with tracer.start_as_current_span(
            "voicelive_orchestrator.start",
            kind=trace.SpanKind.INTERNAL,
            attributes=create_service_handler_attrs(
                service_name="LiveOrchestrator.start",
                call_connection_id=self.call_connection_id,
                session_id=getattr(self.messenger, "session_id", None) if self.messenger else None,
            ),
        ) as start_span:
            start_span.set_attribute("voicelive.start_agent", self.active)
            start_span.set_attribute("voicelive.agent_count", len(self.agents))
            logger.info("[Orchestrator] Starting with agent: %s", self.active)
            self._system_vars = dict(system_vars or {})
            await self._switch_to(self.active, self._system_vars)
            start_span.set_status(trace.StatusCode.OK)

    async def handle_event(self, event):
        """Route VoiceLive events to audio + handoff logic."""
        et = event.type

        if et == ServerEventType.SESSION_UPDATED:
            await self._handle_session_updated(event)

        elif et == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            await self._handle_speech_started()

        elif et == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            await self._handle_speech_stopped()

        elif et == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            await self._handle_transcription_completed(event)

        elif et == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_DELTA:
            await self._handle_transcription_delta(event)

        elif et == ServerEventType.RESPONSE_AUDIO_DELTA:
            if self.audio:
                await self.audio.queue_audio(event.delta)

        elif et == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            await self._handle_transcript_delta(event)

        elif et == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
            await self._handle_transcript_done(event)

        elif et == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            await self._execute_tool_call(
                call_id=getattr(event, "call_id", None),
                name=getattr(event, "name", None),
                args_json=getattr(event, "arguments", None),
            )

        elif et == ServerEventType.RESPONSE_DONE:
            await self._handle_response_done(event)

        elif et == ServerEventType.ERROR:
            logger.error("VoiceLive error: %s", getattr(event.error, "message", "unknown"))

    # ═══════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════

    async def _handle_session_updated(self, event) -> None:
        """Handle SESSION_UPDATED event."""
        session_obj = getattr(event, "session", None)
        session_id = getattr(session_obj, "id", "unknown") if session_obj else "unknown"
        voice_info = getattr(session_obj, "voice", None) if session_obj else None
        logger.info("Session ready: %s | voice=%s", session_id, voice_info)

        if self.messenger:
            try:
                await self.messenger.send_session_update(
                    agent_name=self.active,
                    session_obj=session_obj,
                    transport=self._transport,
                )
            except Exception:
                logger.debug("Failed to emit session update envelope", exc_info=True)

        if self.audio:
            await self.audio.stop_playback()
        try:
            await self.conn.response.cancel()
        except Exception:
            logger.debug("response.cancel() failed during session_ready", exc_info=True)
        if self.audio:
            await self.audio.start_capture()

        if self._pending_greeting and self._pending_greeting_agent == self.active:
            self._cancel_pending_greeting_tasks()
            try:
                await self.agents[self.active].trigger_voicelive_response(
                    self.conn,
                    say=self._pending_greeting,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "[Greeting] Session-ready trigger failed; retrying via fallback", exc_info=True
                )
                self._schedule_greeting_fallback(self.active)
            else:
                self._pending_greeting = None
                self._pending_greeting_agent = None

    async def _handle_speech_started(self) -> None:
        """Handle user speech started (barge-in)."""
        logger.debug("User speech started → cancel current response")
        
        # Sync state to MemoManager in background - don't block barge-in response
        # This ensures any partial response context is preserved
        self._schedule_background_sync()
        
        if self.audio:
            await self.audio.stop_playback()
        try:
            await self.conn.response.cancel()
        except Exception:
            logger.debug("response.cancel() failed during barge-in", exc_info=True)
        if self.messenger and self._active_response_id:
            try:
                await self.messenger.send_assistant_cancelled(
                    response_id=self._active_response_id,
                    sender=self.active,
                    reason="user_barge_in",
                )
            except Exception:
                logger.debug("Failed to notify assistant cancellation on barge-in", exc_info=True)
        self._active_response_id = None

    async def _handle_speech_stopped(self) -> None:
        """Handle user speech stopped."""
        logger.debug("User speech stopped → start playback for assistant")
        if self.audio:
            await self.audio.start_playback()

        # Start new turn (increments turn count, resets TTFT tracking)
        self._metrics.start_turn()

    async def _handle_transcription_completed(self, event) -> None:
        """Handle user transcription completed."""
        user_transcript = getattr(event, "transcript", "")
        if user_transcript:
            logger.info("[USER] Says: %s", user_transcript)
            user_text = user_transcript.strip()
            self._last_user_message = user_text
            # Add to bounded history for better handoff context
            self._user_message_history.append(user_text)
            
            # Persist user turn to MemoManager for session continuity (fast, local)
            if self._memo_manager:
                try:
                    self._memo_manager.append_to_history(self.active, "user", user_text)
                except Exception:
                    logger.debug("Failed to persist user turn to history", exc_info=True)
            
            # Mark that we need a session update (will be done in throttled fashion)
            # Don't call _update_session_context here - it's too slow for the hot path
            # The response_done handler will do a throttled update
            self._pending_session_update = True
            
            await self._maybe_trigger_call_center_transfer(user_transcript)

    async def _handle_transcription_delta(self, event) -> None:
        """Handle user transcription delta."""
        user_transcript = getattr(event, "transcript", "")
        if user_transcript:
            logger.info("[USER delta] Says: %s", user_transcript)
            # Only update _last_user_message for deltas, don't add to deque yet
            # The final message will be added in _handle_transcription_completed
            self._last_user_message = user_transcript.strip()

    async def _handle_transcript_delta(self, event) -> None:
        """Handle assistant transcript delta (streaming)."""
        transcript_delta = getattr(event, "delta", "") or getattr(event, "transcript", "")

        # Track LLM TTFT via metrics
        ttft_ms = self._metrics.record_first_token() if transcript_delta else None
        if ttft_ms is not None:
            session_id = getattr(self.messenger, "session_id", None) if self.messenger else None
            with tracer.start_as_current_span(
                "voicelive.llm.ttft",
                kind=trace.SpanKind.INTERNAL,
                attributes={
                    SpanAttr.TURN_NUMBER.value: self._metrics.turn_count,
                    SpanAttr.TURN_LLM_TTFB_MS.value: ttft_ms,
                    SpanAttr.SESSION_ID.value: session_id or "",
                    SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id or "",
                    "voicelive.active_agent": self.active,
                },
            ) as ttft_span:
                ttft_span.add_event("llm.first_token", {"ttft_ms": ttft_ms})
                logger.info(
                    "[Orchestrator] LLM TTFT | turn=%d ttft_ms=%.2f agent=%s",
                    self._metrics.turn_count,
                    ttft_ms,
                    self.active,
                )

        if transcript_delta and self.messenger:
            response_id = self._response_id_from_event(event)
            if response_id:
                self._active_response_id = response_id
            else:
                response_id = self._active_response_id
            try:
                await self.messenger.send_assistant_streaming(
                    transcript_delta,
                    sender=self.active,
                    response_id=response_id,
                )
            except Exception:
                logger.debug("Failed to relay assistant streaming delta", exc_info=True)

    async def _handle_transcript_done(self, event) -> None:
        """Handle assistant transcript complete."""
        full_transcript = getattr(event, "transcript", "")
        if full_transcript:
            logger.info("[%s] Agent: %s", self.active, full_transcript)
            # Track assistant response for history persistence
            self._last_assistant_message = full_transcript
            
            # Persist assistant turn to MemoManager for session continuity
            if self._memo_manager:
                try:
                    self._memo_manager.append_to_history(self.active, "assistant", full_transcript)
                except Exception:
                    logger.debug("Failed to persist assistant turn to history", exc_info=True)
            
            if self.messenger:
                response_id = self._response_id_from_event(event)
                if not response_id:
                    response_id = self._active_response_id
                try:
                    await self.messenger.send_assistant_message(
                        full_transcript,
                        sender=self.active,
                        response_id=response_id,
                    )
                except Exception:
                    logger.debug(
                        "Failed to relay assistant transcript to session UI", exc_info=True
                    )
                if response_id and response_id == self._active_response_id:
                    self._active_response_id = None

    async def _handle_response_done(self, event) -> None:
        """Handle response complete."""
        logger.debug("Response complete")
        response_id = self._response_id_from_event(event)
        if response_id and response_id == self._active_response_id:
            self._active_response_id = None

        self._emit_model_metrics(event)

        # Sync state to MemoManager in background to avoid hot path latency
        self._schedule_background_sync()

        # Schedule throttled session update in background - don't block the hot path
        self._schedule_throttled_session_update()

    # ═══════════════════════════════════════════════════════════════════════════
    # AGENT SWITCHING
    # ═══════════════════════════════════════════════════════════════════════════

    async def _switch_to(self, agent_name: str, system_vars: dict):
        """Switch to a different agent and apply its session configuration."""
        previous_agent = self.active
        agent = self.agents[agent_name]

        # Emit invoke_agent summary span for the outgoing agent
        if previous_agent != agent_name and self._metrics._response_count > 0:
            self._emit_agent_summary_span(previous_agent)

        with tracer.start_as_current_span(
            "voicelive_orchestrator.switch_agent",
            kind=trace.SpanKind.INTERNAL,
            attributes=create_service_handler_attrs(
                service_name="LiveOrchestrator._switch_to",
                call_connection_id=self.call_connection_id,
                session_id=getattr(self.messenger, "session_id", None) if self.messenger else None,
            ),
        ) as switch_span:
            switch_span.set_attribute("voicelive.previous_agent", previous_agent)
            switch_span.set_attribute("voicelive.target_agent", agent_name)

            self._cancel_pending_greeting_tasks()

            system_vars = dict(system_vars or {})
            system_vars.setdefault("previous_agent", previous_agent)
            system_vars.setdefault("active_agent", agent.name)

            is_first_visit = agent_name not in self.visited_agents
            self.visited_agents.add(agent_name)
            switch_span.set_attribute("voicelive.is_first_visit", is_first_visit)

            logger.info(
                "[Agent Switch] %s → %s | Context: %s | First visit: %s",
                previous_agent,
                agent_name,
                system_vars,
                is_first_visit,
            )

            greeting = self._select_pending_greeting(
                agent=agent,
                agent_name=agent_name,
                system_vars=system_vars,
                is_first_visit=is_first_visit,
            )
            if greeting:
                self._pending_greeting = greeting
                self._pending_greeting_agent = agent_name
            else:
                self._pending_greeting = None
                self._pending_greeting_agent = None

            handoff_context = sanitize_handoff_context(system_vars.get("handoff_context"))
            if handoff_context:
                system_vars["handoff_context"] = handoff_context
                for key in (
                    "caller_name",
                    "client_id",
                    "institution_name",
                    "service_type",
                    "case_id",
                    "issue_summary",
                    "details",
                    "handoff_reason",
                    "user_last_utterance",
                ):
                    if key not in system_vars and handoff_context.get(key) is not None:
                        system_vars[key] = handoff_context.get(key)

            # Include slots and tool outputs from MemoManager for context continuity
            if self._memo_manager:
                slots = self._memo_manager.get_context("slots", {})
                if slots:
                    system_vars.setdefault("slots", slots)
                    # Also merge collected info directly for easier template access
                    system_vars.setdefault("collected_information", slots)

                tool_outputs = self._memo_manager.get_context("tool_outputs", {})
                if tool_outputs:
                    system_vars.setdefault("tool_outputs", tool_outputs)

            # Auto-load user profile if client_id is present but session_profile is missing
            await _auto_load_user_context(system_vars)

            self.active = agent_name

            try:
                if self.messenger:
                    try:
                        self.messenger.set_active_agent(agent_name)
                    except AttributeError:
                        logger.debug("Messenger does not support set_active_agent", exc_info=True)

                has_handoff = bool(system_vars.get("handoff_context"))
                switch_span.set_attribute("voicelive.is_handoff", has_handoff)

                # For handoffs, DON'T use the handoff_message as a greeting.
                # The handoff_message is meant for the OLD agent to say ("I'll connect you to...")
                # but by the time we're here, the session has switched to the NEW agent.
                # Instead, let the new agent respond naturally as itself.
                # We'll trigger a response after session update, and the new agent will introduce itself.

                with tracer.start_as_current_span(
                    "voicelive.agent.apply_session",
                    kind=trace.SpanKind.SERVER,
                    attributes=create_service_dependency_attrs(
                        source_service="voicelive_orchestrator",
                        target_service="azure_voicelive",
                        call_connection_id=self.call_connection_id,
                        session_id=(
                            getattr(self.messenger, "session_id", None) if self.messenger else None
                        ),
                    ),
                ) as session_span:
                    session_span.set_attribute("voicelive.agent_name", agent_name)
                    session_id = (
                        getattr(self.messenger, "session_id", None) if self.messenger else None
                    )
                    await agent.apply_voicelive_session(
                        self.conn,
                        system_vars=system_vars,
                        say=None,
                        session_id=session_id,
                        call_connection_id=self.call_connection_id,
                    )

                # CRITICAL: Inject conversation history as text items for context retention
                # VoiceLive audio models can "forget" context - explicit text items help
                # This must happen AFTER session update but BEFORE first response
                await self._inject_conversation_history()

                # Schedule greeting fallback if we have a pending greeting
                # This applies to both handoffs and normal agent switches
                if self._pending_greeting and self._pending_greeting_agent == agent_name:
                    self._schedule_greeting_fallback(agent_name)

                # Reset metrics for the new agent (captures summary of previous)
                self._metrics.reset_for_agent_switch(agent_name)

                switch_span.set_status(trace.StatusCode.OK)
            except Exception as ex:
                switch_span.set_status(trace.StatusCode.ERROR, str(ex))
                switch_span.add_event(
                    "agent_switch.error",
                    {"error.type": type(ex).__name__, "error.message": str(ex)},
                )
                logger.exception("Failed to apply session for agent '%s'", agent_name)
                raise

            logger.info("[Active Agent] %s is now active", self.active)

    # ═══════════════════════════════════════════════════════════════════════════
    # TOOL EXECUTION
    # ═══════════════════════════════════════════════════════════════════════════

    async def _execute_tool_call(
        self, call_id: str | None, name: str | None, args_json: str | None
    ) -> bool:
        """
        Execute tool call via shared tool registry and send result back to model.

        Returns True if this was a handoff (agent switch), False otherwise.
        """
        if not name or not call_id:
            logger.warning("Missing call_id or name for function call")
            return False

        try:
            args = json.loads(args_json) if args_json else {}
        except Exception:
            logger.warning("Could not parse tool arguments for '%s'; using empty dict", name)
            args = {}

        session_id = getattr(self.messenger, "session_id", None) if self.messenger else None
        with tracer.start_as_current_span(
            f"execute_tool {name}",
            kind=trace.SpanKind.INTERNAL,
            attributes={
                "component": "voicelive",
                "ai.session.id": session_id or "",
                SpanAttr.SESSION_ID.value: session_id or "",
                SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id or "",
                "transport.type": self._transport.upper() if self._transport else "ACS",
                SpanAttr.GENAI_OPERATION_NAME.value: GenAIOperation.EXECUTE_TOOL,
                SpanAttr.GENAI_TOOL_NAME.value: name,
                SpanAttr.GENAI_TOOL_CALL_ID.value: call_id,
                SpanAttr.GENAI_TOOL_TYPE.value: "function",
                SpanAttr.GENAI_PROVIDER_NAME.value: GenAIProvider.AZURE_OPENAI,
                "tool.call_id": call_id,
                "tool.parameters_count": len(args),
                "voicelive.tool_name": name,
                "voicelive.tool_id": call_id,
                "voicelive.agent_name": self.active,
                "voicelive.is_acs": self._transport == "acs",
                "voicelive.args_length": len(args_json) if args_json else 0,
                "voicelive.tool.is_handoff": self.handoff_service.is_handoff(name),
                "voicelive.tool.is_transfer": name in TRANSFER_TOOL_NAMES,
            },
        ) as tool_span:

            if name in TRANSFER_TOOL_NAMES:
                if (
                    self._transport_supports_acs()
                    and (not args.get("call_connection_id"))
                    and self.call_connection_id
                ):
                    args.setdefault("call_connection_id", self.call_connection_id)
                if (
                    self._transport_supports_acs()
                    and (not args.get("call_connection_id"))
                    and self.messenger
                ):
                    fallback_call_id = getattr(self.messenger, "call_id", None)
                    if fallback_call_id:
                        args.setdefault("call_connection_id", fallback_call_id)
                if self.messenger:
                    sess_id = getattr(self.messenger, "session_id", None)
                    if sess_id:
                        args.setdefault("session_id", sess_id)

            logger.info("Executing tool: %s with args: %s", name, args)

            notify_status = "success"
            notify_error: str | None = None

            # Use full message history for better handoff context
            last_user_message = (self._last_user_message or "").strip()
            if self.handoff_service.is_handoff(name):
                # Build conversation summary from message history
                if self._user_message_history:
                    # Use last message for immediate context
                    if last_user_message:
                        for field in ("details", "issue_summary", "summary", "topic", "handoff_reason"):
                            if not args.get(field):
                                args[field] = last_user_message
                        args.setdefault("user_last_utterance", last_user_message)
                    
                    # Include full conversation context for richer handoff
                    if len(self._user_message_history) > 1:
                        conversation_context = " | ".join(self._user_message_history)
                        args.setdefault("conversation_summary", conversation_context)
                        logger.debug(
                            "[Handoff] Including %d messages in context",
                            len(self._user_message_history),
                        )
                elif last_user_message:
                    # Fallback to single message
                    for field in ("details", "issue_summary", "summary", "topic", "handoff_reason"):
                        if not args.get(field):
                            args[field] = last_user_message
                    args.setdefault("user_last_utterance", last_user_message)

            MFA_TOOL_NAMES = {"send_mfa_code", "resend_mfa_code"}

            if self.messenger:
                try:
                    await self.messenger.notify_tool_start(call_id=call_id, name=name, args=args)
                except Exception:
                    logger.debug("Tool start messenger notification failed", exc_info=True)
                if name in MFA_TOOL_NAMES:
                    try:
                        await self.messenger.send_status_update(
                            text="Sending a verification code to your email…",
                            sender=self.active,
                            event_label="mfa_status_update",
                        )
                    except Exception:
                        logger.debug("Failed to emit MFA status update", exc_info=True)

            start_ts = time.perf_counter()
            result: dict[str, Any] = {}

            try:
                with tracer.start_as_current_span(
                    "voicelive.tool.execute",
                    kind=trace.SpanKind.INTERNAL,
                    attributes={"tool.name": name},
                ):
                    result = await execute_tool(name, args)
            except Exception as exc:
                notify_status = "error"
                notify_error = str(exc)
                tool_span.set_status(trace.StatusCode.ERROR, str(exc))
                tool_span.add_event(
                    "tool.execution_error",
                    {"error.type": type(exc).__name__, "error.message": str(exc)},
                )
                if self.messenger:
                    try:
                        await self.messenger.notify_tool_end(
                            call_id=call_id,
                            name=name,
                            status="error",
                            elapsed_ms=(time.perf_counter() - start_ts) * 1000,
                            error=notify_error,
                        )
                    except Exception:
                        logger.debug("Tool end messenger notification failed", exc_info=True)
                raise

            elapsed_ms = (time.perf_counter() - start_ts) * 1000
            tool_span.set_attribute("execution.duration_ms", elapsed_ms)
            tool_span.set_attribute("voicelive.tool.elapsed_ms", elapsed_ms)

            error_payload: str | None = None
            execution_success = True
            if isinstance(result, dict):
                for key in ("success", "ok", "authenticated"):
                    if key in result and not result[key]:
                        notify_status = "error"
                        execution_success = False
                        break
                if notify_status == "error":
                    err_val = result.get("message") or result.get("error")
                    if err_val:
                        error_payload = str(err_val)

            tool_span.set_attribute("execution.success", execution_success)
            tool_span.set_attribute("result.type", type(result).__name__ if result else "None")
            tool_span.set_attribute("voicelive.tool.status", notify_status)

            # Persist slots and tool outputs from result to MemoManager
            # This ensures collected information is available in subsequent turns
            if isinstance(result, dict) and self._memo_manager:
                try:
                    # Update slots if tool returned any
                    if "slots" in result and isinstance(result["slots"], dict):
                        current_slots = self._memo_manager.get_context("slots", {})
                        current_slots.update(result["slots"])
                        self._memo_manager.set_context("slots", current_slots)
                        self._system_vars["slots"] = current_slots
                        self._system_vars["collected_information"] = current_slots
                        logger.info(
                            "[Tool] Updated slots from %s: %s",
                            name,
                            list(result["slots"].keys()),
                        )

                    # Store tool output for context continuity
                    tool_outputs = self._memo_manager.get_context("tool_outputs", {})
                    # Store a summary of the result, not the full payload
                    output_summary = {
                        k: v
                        for k, v in result.items()
                        if k not in ("slots", "raw_response") and not k.startswith("_")
                    }
                    if output_summary:
                        tool_outputs[name] = output_summary
                        self._memo_manager.set_context("tool_outputs", tool_outputs)
                        self._system_vars["tool_outputs"] = tool_outputs
                except Exception:
                    logger.debug("Failed to persist tool results to MemoManager", exc_info=True)

            # Handle transfer tools
            if (
                name in TRANSFER_TOOL_NAMES
                and notify_status != "error"
                and isinstance(result, dict)
            ):
                takeover_message = result.get("message") or "Transferring call to destination."
                tool_span.add_event(
                    "tool.transfer_initiated",
                    {"transfer.message": takeover_message[:100] if takeover_message else ""},
                )
                if self.messenger:
                    try:
                        await self.messenger.send_status_update(
                            text=takeover_message,
                            sender=self.active,
                            event_label="acs_call_transfer_status",
                        )
                    except Exception:
                        logger.debug("Failed to emit transfer status update", exc_info=True)
                try:
                    if result.get("should_interrupt_playback", True):
                        await self.conn.response.cancel()
                except Exception:
                    logger.debug("response.cancel() failed during transfer", exc_info=True)
                if self.audio:
                    try:
                        await self.audio.stop_playback()
                    except Exception:
                        logger.debug("Audio stop playback failed during transfer", exc_info=True)
                if self.messenger:
                    try:
                        await self.messenger.notify_tool_end(
                            call_id=call_id,
                            name=name,
                            status=notify_status,
                            elapsed_ms=(time.perf_counter() - start_ts) * 1000,
                            result=result,
                            error=error_payload,
                        )
                    except Exception:
                        logger.debug("Tool end messenger notification failed", exc_info=True)
                tool_span.set_status(trace.StatusCode.OK)
                return False

            # Handle handoff tools using unified HandoffService
            if self.handoff_service.is_handoff(name):
                # Use HandoffService for consistent resolution across orchestrators
                resolution = self.handoff_service.resolve_handoff(
                    tool_name=name,
                    tool_args=args,
                    source_agent=self.active,
                    current_system_vars=self._system_vars,
                    user_last_utterance=last_user_message,
                    tool_result=result if isinstance(result, dict) else None,
                )

                if not resolution.success:
                    logger.warning(
                        "Handoff resolution failed: %s | tool=%s",
                        resolution.error,
                        name,
                    )
                    notify_status = "error"
                    tool_span.set_status(trace.StatusCode.ERROR, "handoff_resolution_failed")
                    if self.messenger:
                        try:
                            await self.messenger.notify_tool_end(
                                call_id=call_id,
                                name=name,
                                status=notify_status,
                                elapsed_ms=(time.perf_counter() - start_ts) * 1000,
                                result=result if isinstance(result, dict) else None,
                                error=resolution.error or "handoff_resolution_failed",
                            )
                        except Exception:
                            logger.debug("Tool end messenger notification failed", exc_info=True)
                    return False

                target = resolution.target_agent
                tool_span.set_attribute("voicelive.handoff.target_agent", target)
                tool_span.add_event("tool.handoff_triggered", {"target_agent": target})
                tool_span.set_attribute("voicelive.handoff.share_context", resolution.share_context)
                tool_span.set_attribute("voicelive.handoff.greet_on_switch", resolution.greet_on_switch)
                tool_span.set_attribute("voicelive.handoff.type", resolution.handoff_type)

                # CRITICAL: Cancel any ongoing response from the OLD agent immediately.
                # This prevents the old agent from saying "I'll connect you..." while
                # the session switches to the new agent.
                try:
                    await self.conn.response.cancel()
                    logger.debug("[Handoff] Cancelled old agent response before switch")
                except Exception:
                    pass  # No active response to cancel

                # Stop audio playback to prevent old agent's voice from continuing
                if self.audio:
                    try:
                        await self.audio.stop_playback()
                    except Exception:
                        logger.debug("[Handoff] Audio stop failed", exc_info=True)

                # Use system_vars from HandoffService resolution
                ctx = resolution.system_vars

                logger.info("[Handoff Tool] '%s' triggered | %s → %s", name, self.active, target)

                await self._switch_to(target, ctx)
                self._last_user_message = None

                if result.get("call_center_transfer"):
                    transfer_args: dict[str, Any] = {}
                    if self._transport_supports_acs() and self.call_connection_id:
                        transfer_args["call_connection_id"] = self.call_connection_id
                    if self.messenger:
                        sess_id = getattr(self.messenger, "session_id", None)
                        if sess_id:
                            transfer_args["session_id"] = sess_id
                    if transfer_args:
                        self._call_center_triggered = True
                        await self._trigger_call_center_transfer(transfer_args)
                if self.messenger:
                    try:
                        await self.messenger.notify_tool_end(
                            call_id=call_id,
                            name=name,
                            status=notify_status,
                            elapsed_ms=(time.perf_counter() - start_ts) * 1000,
                            result=result if isinstance(result, dict) else None,
                            error=error_payload,
                        )
                    except Exception:
                        logger.debug("Tool end messenger notification failed", exc_info=True)

                # After handoff, send tool result back to model
                # The session update from _switch_to already applied the new agent's config
                try:
                    handoff_output = FunctionCallOutputItem(
                        call_id=call_id,
                        output=(
                            json.dumps(result)
                            if isinstance(result, dict)
                            else json.dumps({"success": True})
                        ),
                    )
                    await self.conn.conversation.item.create(item=handoff_output)
                    logger.debug("Created handoff tool output for call_id=%s", call_id)
                except Exception as item_err:
                    logger.warning("Failed to create handoff tool output: %s", item_err)

                # Trigger the new agent to respond naturally as itself
                # Build context about the handoff for the new agent's instruction
                handoff_ctx = ctx.get("handoff_context", {})
                user_question = (
                    handoff_ctx.get("question")
                    or handoff_ctx.get("details")
                    or last_user_message
                    or "general inquiry"
                )
                handoff_summary = (
                    result.get("handoff_summary", "") if isinstance(result, dict) else ""
                )
                previous_agent = self._system_vars.get("previous_agent", "previous agent")

                # Get handoff mode from context (set by build_handoff_system_vars)
                greet_on_switch = ctx.get("greet_on_switch", True)

                # Schedule response trigger after a brief delay to let session settle.
                # The new agent will respond naturally to the context.
                # NOTE: For announced handoffs, the greeting is already handled by
                # _select_pending_greeting() which renders the agent's greeting template.
                # This response trigger just prompts the agent to address the user's request.
                async def _trigger_handoff_response():
                    await asyncio.sleep(0.25)
                    try:
                        from azure.ai.voicelive.models import (
                            ClientEventResponseCreate,
                            ResponseCreateParams,
                        )

                        # Build instruction based on handoff mode
                        # NOTE: Greeting is handled separately by _select_pending_greeting()
                        # which uses the agent's greeting/return_greeting from agent.yaml.
                        # Here we just instruct the agent on how to handle the conversation.
                        if greet_on_switch:
                            # Announced mode: greeting already rendered from agent.yaml
                            # Just instruct agent to address the request after greeting
                            handoff_instruction = (
                                f'The customer\'s request: "{user_question}". '
                                f"Address their request directly after your greeting."
                            )
                            if handoff_summary:
                                handoff_instruction += f" Context: {handoff_summary}"
                        else:
                            # Discrete mode: silent handoff, no announcement, no greeting
                            handoff_instruction = (
                                f'The customer\'s request: "{user_question}". '
                                f"Address their request directly. "
                                f"Do NOT announce that you are a different agent or mention any transfer. "
                                f"Continue the conversation naturally as if seamless."
                            )
                            if handoff_summary:
                                handoff_instruction += f" Context: {handoff_summary}"

                        await self.conn.send(
                            ClientEventResponseCreate(
                                response=ResponseCreateParams(
                                    instructions=handoff_instruction,
                                )
                            )
                        )
                        logger.info(
                            "[Handoff] Triggered new agent '%s' | greet=%s", target, greet_on_switch
                        )
                    except Exception as e:
                        logger.warning("[Handoff] Failed to trigger response: %s", e)

                asyncio.create_task(_trigger_handoff_response(), name=f"handoff-response-{target}")

                tool_span.set_status(trace.StatusCode.OK)
                return True

            else:
                # Business tool - send result back to model
                output_item = FunctionCallOutputItem(
                    call_id=call_id,
                    output=json.dumps(result),
                )

                with tracer.start_as_current_span(
                    "voicelive.conversation.item_create",
                    kind=trace.SpanKind.SERVER,
                    attributes=create_service_dependency_attrs(
                        source_service="voicelive_orchestrator",
                        target_service="azure_voicelive",
                        call_connection_id=self.call_connection_id,
                        session_id=(
                            getattr(self.messenger, "session_id", None) if self.messenger else None
                        ),
                    ),
                ):
                    await self.conn.conversation.item.create(item=output_item)
                logger.debug("Created function_call_output item for call_id=%s", call_id)

                # Update session instructions with new context BEFORE triggering response
                # This ensures the model sees collected slots/tool outputs when formulating its reply
                await self._update_session_context()

                with tracer.start_as_current_span(
                    "voicelive.response.create",
                    kind=trace.SpanKind.SERVER,
                    attributes=create_service_dependency_attrs(
                        source_service="voicelive_orchestrator",
                        target_service="azure_voicelive",
                        call_connection_id=self.call_connection_id,
                        session_id=(
                            getattr(self.messenger, "session_id", None) if self.messenger else None
                        ),
                    ),
                ):
                    await self.conn.response.create()
                if self.messenger:
                    try:
                        await self.messenger.notify_tool_end(
                            call_id=call_id,
                            name=name,
                            status=notify_status,
                            elapsed_ms=(time.perf_counter() - start_ts) * 1000,
                            result=result if isinstance(result, dict) else None,
                            error=error_payload,
                        )
                    except Exception:
                        logger.debug("Tool end messenger notification failed", exc_info=True)
                tool_span.set_status(trace.StatusCode.OK)
                return False

    # ═══════════════════════════════════════════════════════════════════════════
    # GREETING HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _select_pending_greeting(
        self,
        *,
        agent: UnifiedAgent,
        agent_name: str,
        system_vars: dict,
        is_first_visit: bool,
    ) -> str | None:
        """
        Return a contextual greeting the agent should deliver once the session is ready.

        Delegates to HandoffService.select_greeting() for consistent behavior
        across both orchestrators. The HandoffService handles:
        - Priority 1: Explicit greeting override in system_vars
        - Priority 2: Discrete handoff detection (skip greeting)
        - Priority 3: Render agent's greeting/return_greeting template
        """
        # Determine greet_on_switch from system_vars (set by HandoffService.resolve_handoff)
        greet_on_switch = system_vars.get("greet_on_switch", True)

        greeting = self.handoff_service.select_greeting(
            agent=agent,
            is_first_visit=is_first_visit,
            greet_on_switch=greet_on_switch,
            system_vars=system_vars,
        )

        if greeting:
            logger.debug(
                "[Greeting] Selected greeting for %s | first_visit=%s | len=%d",
                agent_name,
                is_first_visit,
                len(greeting),
            )
        else:
            logger.debug(
                "[Greeting] No greeting for %s | first_visit=%s | greet_on_switch=%s",
                agent_name,
                is_first_visit,
                greet_on_switch,
            )

        return greeting

    def _cancel_pending_greeting_tasks(self) -> None:
        if not self._greeting_tasks:
            return
        for task in list(self._greeting_tasks):
            task.cancel()
        self._greeting_tasks.clear()

    def _schedule_greeting_fallback(self, agent_name: str) -> None:
        if not self._pending_greeting or not self._pending_greeting_agent:
            return

        async def _fallback() -> None:
            try:
                await asyncio.sleep(0.35)
                if self._pending_greeting and self._pending_greeting_agent == agent_name:
                    logger.debug(
                        "[GreetingFallback] Triggering fallback introduction for %s", agent_name
                    )
                    try:
                        await self.agents[agent_name].trigger_voicelive_response(
                            self.conn,
                            say=self._pending_greeting,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.debug("[GreetingFallback] Failed to deliver greeting", exc_info=True)
                        return
                    self._pending_greeting = None
                    self._pending_greeting_agent = None
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("[GreetingFallback] Unexpected error in fallback task", exc_info=True)

        task = asyncio.create_task(
            _fallback(),
            name=f"voicelive-greeting-fallback-{agent_name}",
        )
        task.add_done_callback(lambda t: self._greeting_tasks.discard(t))
        self._greeting_tasks.add(task)

    # ═══════════════════════════════════════════════════════════════════════════
    # CALL CENTER TRANSFER
    # ═══════════════════════════════════════════════════════════════════════════

    async def _maybe_trigger_call_center_transfer(self, transcript: str) -> None:
        """Detect trigger phrases and initiate automatic call center transfer."""
        if self._call_center_triggered:
            return

        normalized = transcript.strip().lower()
        if not normalized:
            return

        if not any(phrase in normalized for phrase in CALL_CENTER_TRIGGER_PHRASES):
            return

        self._call_center_triggered = True
        logger.info(
            "[Auto Transfer] Triggering call center transfer due to phrase match: '%s'", transcript
        )

        args: dict[str, Any] = {}
        if self._transport_supports_acs() and self.call_connection_id:
            args["call_connection_id"] = self.call_connection_id
        if self.messenger:
            session_id = getattr(self.messenger, "session_id", None)
            if session_id:
                args["session_id"] = session_id

        await self._trigger_call_center_transfer(args)

    async def _trigger_call_center_transfer(self, args: dict[str, Any]) -> None:
        """Invoke the call center transfer tool and handle playback cleanup."""
        tool_name = "transfer_call_to_call_center"

        if self.messenger:
            try:
                await self.messenger.send_status_update(
                    text="Routing you to a call center representative…",
                    sender=self.active,
                    event_label="acs_call_transfer_status",
                )
            except Exception:
                logger.debug("Failed to emit pre-transfer status update", exc_info=True)

        try:
            result = await execute_tool(tool_name, args)
        except Exception:
            self._call_center_triggered = False
            logger.exception("Automatic call center transfer failed unexpectedly")
            if self.messenger:
                try:
                    await self.messenger.send_status_update(
                        text="We encountered an issue reaching the call center. Staying with the virtual agent for now.",
                        sender=self.active,
                        event_label="acs_call_transfer_status",
                    )
                except Exception:
                    logger.debug("Failed to emit transfer failure status", exc_info=True)
            return

        if not isinstance(result, dict) or not result.get("success"):
            self._call_center_triggered = False
            error_message = None
            if isinstance(result, dict):
                error_message = result.get("message") or result.get("error")
            logger.warning(
                "Automatic call center transfer request was rejected | result=%s", result
            )
            if self.messenger:
                try:
                    await self.messenger.send_status_update(
                        text=error_message
                        or "Unable to reach the call center right now. I'll stay on the line with you.",
                        sender=self.active,
                        event_label="acs_call_transfer_status",
                    )
                except Exception:
                    logger.debug("Failed to emit transfer rejection status", exc_info=True)
            return

        takeover_message = result.get(
            "message", "Routing you to a live call center representative now."
        )

        if self.messenger:
            try:
                await self.messenger.send_status_update(
                    text=takeover_message,
                    sender=self.active,
                    event_label="acs_call_transfer_status",
                )
            except Exception:
                logger.debug("Failed to emit transfer success status", exc_info=True)

        try:
            if result.get("should_interrupt_playback", True):
                await self.conn.response.cancel()
        except Exception:
            logger.debug(
                "response.cancel() failed during automatic call center transfer", exc_info=True
            )

        if self.audio:
            try:
                await self.audio.stop_playback()
            except Exception:
                logger.debug(
                    "Audio stop playback failed during automatic call center transfer",
                    exc_info=True,
                )

    # ═══════════════════════════════════════════════════════════════════════════
    # TELEMETRY HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _emit_agent_summary_span(self, agent_name: str) -> None:
        """Emit an invoke_agent summary span with accumulated token usage."""
        agent = self.agents.get(agent_name)
        if not agent:
            return

        session_id = getattr(self.messenger, "session_id", None) if self.messenger else None
        # Use metrics for duration and token tracking
        agent_duration_ms = self._metrics.duration_ms

        with tracer.start_as_current_span(
            f"invoke_agent {agent_name}",
            kind=trace.SpanKind.INTERNAL,
            attributes={
                "component": "voicelive",
                "ai.session.id": session_id or "",
                SpanAttr.SESSION_ID.value: session_id or "",
                SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id or "",
                SpanAttr.GENAI_OPERATION_NAME.value: GenAIOperation.INVOKE_AGENT,
                SpanAttr.GENAI_PROVIDER_NAME.value: GenAIProvider.AZURE_OPENAI,
                SpanAttr.GENAI_REQUEST_MODEL.value: self._model_name,
                "gen_ai.agent.name": agent_name,
                "gen_ai.agent.description": getattr(
                    agent, "description", f"VoiceLive agent: {agent_name}"
                ),
                SpanAttr.GENAI_USAGE_INPUT_TOKENS.value: self._metrics.input_tokens,
                SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value: self._metrics.output_tokens,
                "voicelive.agent_name": agent_name,
                "voicelive.response_count": self._metrics._response_count,
                "voicelive.duration_ms": agent_duration_ms,
            },
        ) as agent_span:
            agent_span.add_event(
                "gen_ai.agent.session_complete",
                {
                    "agent": agent_name,
                    "input_tokens": self._metrics.input_tokens,
                    "output_tokens": self._metrics.output_tokens,
                    "response_count": self._metrics._response_count,
                    "duration_ms": agent_duration_ms,
                },
            )
            logger.debug(
                "[Agent Summary] %s complete | tokens=%d/%d responses=%d duration=%.1fms",
                agent_name,
                self._metrics.input_tokens,
                self._metrics.output_tokens,
                self._metrics._response_count,
                agent_duration_ms,
            )

    def _emit_model_metrics(self, event: Any) -> None:
        """Emit GenAI model-level metrics for App Insights Agents blade."""
        response = getattr(event, "response", None)
        if not response:
            return

        response_id = getattr(response, "id", None)

        usage = getattr(response, "usage", None)
        input_tokens = 0
        output_tokens = 0

        if usage:
            input_tokens = getattr(usage, "input_tokens", None) or getattr(
                usage, "prompt_tokens", None
            ) or 0
            output_tokens = getattr(usage, "output_tokens", None) or getattr(
                usage, "completion_tokens", None
            ) or 0

        # Track tokens and response via unified metrics
        self._metrics.add_tokens(input_tokens=input_tokens, output_tokens=output_tokens)
        self._metrics.record_response()

        model = self._model_name
        status = getattr(response, "status", None)

        # Get TTFT from metrics if available
        turn_duration_ms = self._metrics.current_ttft_ms

        session_id = getattr(self.messenger, "session_id", None) if self.messenger else None
        span_name = model if model else "gpt-4o-realtime"

        with tracer.start_as_current_span(
            span_name,
            kind=trace.SpanKind.CLIENT,
            attributes={
                "component": "voicelive",
                "call.connection.id": self.call_connection_id or "",
                "ai.session.id": session_id or "",
                SpanAttr.SESSION_ID.value: session_id or "",
                "ai.user.id": session_id or "",
                "transport.type": self._transport.upper() if self._transport else "ACS",
                SpanAttr.GENAI_OPERATION_NAME.value: GenAIOperation.CHAT,
                SpanAttr.GENAI_SYSTEM.value: "openai",
                SpanAttr.GENAI_REQUEST_MODEL.value: model,
                "voicelive.agent_name": self.active,
            },
        ) as model_span:
            model_span.set_attribute(SpanAttr.GENAI_RESPONSE_MODEL.value, model)

            if response_id:
                model_span.set_attribute(SpanAttr.GENAI_RESPONSE_ID.value, response_id)

            if input_tokens is not None:
                model_span.set_attribute(SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, input_tokens)
            if output_tokens is not None:
                model_span.set_attribute(SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value, output_tokens)

            if turn_duration_ms is not None:
                model_span.set_attribute(
                    SpanAttr.GENAI_CLIENT_OPERATION_DURATION.value, turn_duration_ms
                )

            # Set TTFT if available from metrics
            ttft_ms = self._metrics.current_ttft_ms
            if ttft_ms is not None:
                model_span.set_attribute(SpanAttr.GENAI_SERVER_TIME_TO_FIRST_TOKEN.value, ttft_ms)

            model_span.add_event(
                "gen_ai.response.complete",
                {
                    "response_id": response_id or "",
                    "status": str(status) if status else "",
                    "input_tokens": input_tokens or 0,
                    "output_tokens": output_tokens or 0,
                    "agent": self.active,
                    "turn_number": self._metrics.turn_count,
                },
            )

            logger.debug(
                "[Model Metrics] Response complete | agent=%s model=%s response_id=%s tokens=%s/%s",
                self.active,
                model,
                response_id or "N/A",
                input_tokens or "N/A",
                output_tokens or "N/A",
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITY HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _transport_supports_acs(self) -> bool:
        return self._transport == "acs"

    @staticmethod
    def _response_id_from_event(event: Any) -> str | None:
        response = getattr(event, "response", None)
        if response and hasattr(response, "id"):
            return response.id
        return getattr(event, "response_id", None)


__all__ = [
    "LiveOrchestrator",
    "TRANSFER_TOOL_NAMES",
    "CALL_CENTER_TRIGGER_PHRASES",
    "register_voicelive_orchestrator",
    "unregister_voicelive_orchestrator",
    "get_voicelive_orchestrator",
    "get_orchestrator_registry_size",
]

