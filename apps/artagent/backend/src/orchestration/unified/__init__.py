"""
Unified Agent Orchestrator
===========================

Orchestration layer that uses the new unified agent structure
(apps/artagent/agents/) with CascadeOrchestratorAdapter.

This replaces the legacy ARTAgent orchestration in:
- apps/artagent/backend/src/orchestration/artagent/orchestrator.py

Key differences from legacy:
- Uses UnifiedAgent from apps/artagent/agents/
- Uses CascadeOrchestratorAdapter for multi-agent handoffs
- Scenario-aware configuration via AGENT_SCENARIO env var
- Shared tool registry from apps/artagent/agents/tools/

Usage:
    # In media_handler.py, replace:
    from apps.artagent.backend.src.orchestration.artagent.orchestrator import route_turn

    # With:
    from apps.artagent.backend.src.orchestration.unified.orchestrator import route_turn
"""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    register_adapter_update_callback,
)
from apps.artagent.backend.src.orchestration.session_scenarios import (
    register_scenario_update_callback,
)
from apps.artagent.backend.src.utils.tracing import (
    create_service_handler_attrs,
)
from apps.artagent.backend.voice.shared.config_resolver import resolve_orchestrator_config
from apps.artagent.backend.voice import (
    CascadeOrchestratorAdapter,
    OrchestratorContext,
    get_cascade_orchestrator,
    make_assistant_streaming_envelope,
    make_envelope,
    send_session_envelope,
)
from apps.artagent.backend.voice.voicelive.tool_helpers import (
    push_tool_end,
    push_tool_start,
)
from fastapi import WebSocket
from opentelemetry import trace
from utils.ml_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
    from src.stateful.state_managment import MemoManager


# Module-level adapter cache (per session)
_adapters: dict[str, CascadeOrchestratorAdapter] = {}
_STREAM_CACHE_ATTR = "_assistant_stream_cache"

_AGENT_LABELS: dict[str, str] = {
    "FraudAgent": "Fraud Specialist",
    "ComplianceDesk": "Compliance Specialist",
    "AuthAgent": "Auth Agent",
    "TransferAgency": "Transfer Agency Specialist",
    "TradingDesk": "Trading Specialist",
    "EricaConcierge": "Erica",
    "Concierge": "Concierge",
    "CardRecommendation": "Card Specialist",
    "InvestmentAdvisor": "Investment Advisor",
}


def _resolve_agent_label(agent_name: str | None) -> str:
    if not agent_name:
        return "Assistant"
    return _AGENT_LABELS.get(agent_name, agent_name)


def _ensure_stream_cache(ws: WebSocket) -> deque[str]:
    """Return (and lazily create) the assistant stream cache for a websocket."""
    cache = getattr(ws.state, _STREAM_CACHE_ATTR, None)
    if cache is None:
        cache = deque(maxlen=32)
        setattr(ws.state, _STREAM_CACHE_ATTR, cache)
    return cache


def _parse_tool_arguments(raw: object) -> dict:
    """Best-effort parsing of tool arguments produced by AOAI."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"value": raw}
    return {"value": raw}


def _get_correlation_context(ws: WebSocket, cm: MemoManager) -> tuple[str, str]:
    """Extract call_connection_id and session_id from WebSocket and MemoManager."""
    call_connection_id = getattr(ws.state, "call_connection_id", None)
    if not call_connection_id:
        call_connection_id = getattr(cm, "call_connection_id", None) or ""

    session_id = getattr(cm, "session_id", None)
    if not session_id:
        session_id = getattr(ws.state, "session_id", None) or ""

    return call_connection_id, session_id


def _get_or_create_adapter(
    session_id: str,
    call_connection_id: str,
    app_state: any,
    memo_manager: MemoManager | None = None,
) -> CascadeOrchestratorAdapter:
    """
    Get or create a CascadeOrchestratorAdapter for the session.

    Uses app_state to get pre-loaded unified agents and scenario config.
    Also injects any pre-existing session agent from Agent Builder.
    """
    if session_id in _adapters:
        return _adapters[session_id]

    # Get scenario from MemoManager if available
    scenario_name = None
    if memo_manager:
        scenario_name = memo_manager.get_value_from_corememory("scenario_name", None)

    # Create adapter using app.state config
    adapter = get_cascade_orchestrator(
        app_state=app_state,
        call_connection_id=call_connection_id,
        session_id=session_id,
        scenario_name=scenario_name,
    )

    _adapters[session_id] = adapter

    # Check for pre-existing session agent (created via Agent Builder before call started)
    session_agent = get_session_agent(session_id)
    if session_agent:
        adapter.agents[session_agent.name] = session_agent
        adapter._active_agent = session_agent.name
        logger.info(
            "🎨 Injected pre-existing session agent | session=%s agent=%s voice=%s",
            session_id,
            session_agent.name,
            session_agent.voice.name if session_agent.voice else None,
        )

    logger.info(
        "Created CascadeOrchestratorAdapter",
        extra={
            "session_id": session_id,
            "start_agent": adapter.config.start_agent,
            "agent_count": len(adapter.agents),
        },
    )

    return adapter


def cleanup_adapter(session_id: str) -> None:
    """Remove adapter for a completed session."""
    if session_id in _adapters:
        del _adapters[session_id]
        logger.debug("Cleaned up adapter for session: %s", session_id)


def update_session_agent(session_id: str, agent: UnifiedAgent) -> bool:
    """
    Update or inject a dynamic agent into the session's orchestrator adapter.

    This is the single integration point for Agent Builder updates.
    When called, the agent is injected directly into the adapter's agents dict,
    ensuring all downstream voice/model/prompt lookups use the updated config.

    Args:
        session_id: The session to update
        agent: The UnifiedAgent with updated configuration

    Returns:
        True if adapter was found and updated, False if no active adapter exists
    """
    if session_id not in _adapters:
        logger.debug(
            "No active adapter for session %s - agent will be used when adapter is created",
            session_id,
        )
        return False

    adapter = _adapters[session_id]

    # Inject/update the agent in the adapter's agents dict
    # Use a special key for the session agent so it doesn't conflict with base agents
    adapter.agents[agent.name] = agent

    # If this is meant to be the active agent, update the adapter's active agent
    adapter._active_agent = agent.name

    logger.info(
        "🔄 Session agent updated in adapter | session=%s agent=%s voice=%s model=%s",
        session_id,
        agent.name,
        agent.voice.name if agent.voice else None,
        agent.model.deployment_id if agent.model else None,
    )

    return True


# Register the callback so session_agents module can notify us of updates
register_adapter_update_callback(update_session_agent)


def update_session_scenario(session_id: str, scenario) -> bool:
    """
    Update the orchestrator adapter when a session scenario changes.

    This is the integration point for Scenario Builder updates.
    When called, the adapter's agents, handoff_map, and active agent
    are updated to reflect the new scenario configuration.

    Also updates VoiceLive orchestrators if one is active for the session.
    Additionally, updates the system prompts with handoff instructions in MemoManager.

    Args:
        session_id: The session to update
        scenario: The ScenarioConfig with updated configuration

    Returns:
        True if adapter was found and updated, False if no active adapter exists
    """
    updated_cascade = False
    updated_voicelive = False
    updated_memo = False

    # Resolve the new configuration from the scenario
    config = resolve_orchestrator_config(
        session_id=session_id,
        scenario_name=scenario.name,
    )

    # Update system prompts with handoff instructions in MemoManager
    # This ensures agents have handoff instructions immediately, not just on next turn
    try:
        from apps.artagent.backend.src.orchestration.session_scenarios import _redis_manager
        if _redis_manager:
            memo = MemoManager.from_redis(session_id, _redis_manager)
            
            # For each agent in the scenario, update their system prompt with handoff instructions
            for agent_name in scenario.agents:
                agent = config.agents.get(agent_name)
                if agent:
                    # Build the base system prompt from the agent
                    base_prompt = agent.render_prompt({}) or ""
                    
                    # Build handoff instructions from the scenario
                    handoff_instructions = scenario.build_handoff_instructions(agent_name)
                    
                    if handoff_instructions:
                        full_prompt = f"{base_prompt}\n\n{handoff_instructions}" if base_prompt else handoff_instructions
                    else:
                        full_prompt = base_prompt
                    
                    # Update the agent's system prompt in MemoManager
                    if full_prompt:
                        memo.ensure_system_prompt(agent_name, full_prompt)
                        logger.debug(
                            "Updated system prompt with handoff instructions | agent=%s handoff_len=%d",
                            agent_name,
                            len(handoff_instructions) if handoff_instructions else 0,
                        )
            
            # Persist updates to Redis
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(memo.persist_to_redis_async(_redis_manager))
            except RuntimeError:
                # No running loop - use sync persist
                pass
            
            updated_memo = True
            logger.info(
                "🔄 Updated system prompts with handoff instructions | session=%s agents=%s",
                session_id,
                scenario.agents,
            )
    except Exception as e:
        logger.warning("Failed to update system prompts in MemoManager: %s", e)

    # Update CascadeOrchestratorAdapter if present
    if session_id in _adapters:
        adapter = _adapters[session_id]

        # Use the update_scenario method for complete attribute refresh
        # This clears cached HandoffService, visited_agents, etc.
        adapter.update_scenario(
            agents=config.agents,
            handoff_map=config.handoff_map,
            start_agent=scenario.start_agent,
            scenario_name=scenario.name,
        )

        logger.info(
            "🔄 Session scenario updated in adapter | session=%s scenario=%s agents=%d handoffs=%d",
            session_id,
            scenario.name,
            len(config.agents),
            len(config.handoff_map),
        )
        updated_cascade = True

    # Update VoiceLive orchestrator if present
    try:
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            get_voicelive_orchestrator,
        )

        voicelive_orch = get_voicelive_orchestrator(session_id)
        if voicelive_orch:
            # Pass UnifiedAgent dict directly (no adapter needed)
            voicelive_orch.update_scenario(
                agents=config.agents,
                handoff_map=config.handoff_map,
                start_agent=scenario.start_agent,
                scenario_name=scenario.name,
            )
            logger.info(
                "🔄 Session scenario updated in VoiceLive orchestrator | session=%s scenario=%s",
                session_id,
                scenario.name,
            )
            updated_voicelive = True
    except ImportError:
        logger.debug("VoiceLive module not available for scenario update")
    except Exception as e:
        logger.warning("Failed to update VoiceLive orchestrator: %s", e)

    if not updated_cascade and not updated_voicelive and not updated_memo:
        logger.debug(
            "No active adapter for session %s - scenario will be used when adapter is created",
            session_id,
        )
        return False

    return True


# Register the callback so session_scenarios module can notify us of updates
register_scenario_update_callback(update_session_scenario)


async def route_turn(
    cm: MemoManager,
    transcript: str,
    ws: WebSocket,
    *,
    is_acs: bool,
) -> str | None:
    """
    Handle one user turn using unified agents.

    This is a drop-in replacement for the legacy route_turn function.

    Args:
        cm: MemoManager with conversation state
        transcript: User's speech transcript
        ws: WebSocket connection
        is_acs: Whether this is an ACS call

    Returns:
        Response text (or None if streamed via callbacks)
    """
    if cm is None:
        logger.error("❌ MemoManager (cm) is None - cannot process orchestration")
        raise ValueError("MemoManager (cm) parameter cannot be None")

    # Extract correlation context
    call_connection_id, session_id = _get_correlation_context(ws, cm)

    # Generate run_id for latency tracking
    try:
        run_id = ws.state.lt.begin_run(label="turn")
        if hasattr(ws.state.lt, "set_current_run"):
            ws.state.lt.set_current_run(run_id)
    except Exception:
        run_id = uuid.uuid4().hex[:12]

    # Store run_id in memory
    cm.set_corememory("current_run_id", run_id)

    # Get or create orchestrator adapter
    app_state = ws.app.state
    adapter = _get_or_create_adapter(session_id, call_connection_id, app_state, memo_manager=cm)

    # Sync adapter state from MemoManager
    adapter.sync_from_memo_manager(cm)

    # Create span attributes
    span_attrs = create_service_handler_attrs(
        service_name="unified_orchestrator",
        call_connection_id=call_connection_id,
        session_id=session_id,
        operation="route_turn",
        transcript_length=len(transcript),
        is_acs=is_acs,
        active_agent=adapter.current_agent or "unknown",
    )
    span_attrs["run.id"] = run_id

    with tracer.start_as_current_span(
        "unified_orchestrator.route_turn",
        attributes=span_attrs,
    ) as span:
        redis_mgr = app_state.redis

        try:
            # Build session context from MemoManager for prompt rendering
            active_agent = cm.get_value_from_corememory("active_agent") or adapter.current_agent
            session_context = {
                "is_acs": is_acs,
                "run_id": run_id,
                "memo_manager": cm,
                # Session profile and context for Jinja templates
                "session_profile": cm.get_value_from_corememory("session_profile"),
                "caller_name": cm.get_value_from_corememory("caller_name"),
                "client_id": cm.get_value_from_corememory("client_id"),
                "customer_intelligence": cm.get_value_from_corememory("customer_intelligence"),
                "institution_name": cm.get_value_from_corememory("institution_name"),
                "active_agent": active_agent,
                "previous_agent": cm.get_value_from_corememory("previous_agent"),
                "visited_agents": cm.get_value_from_corememory("visited_agents"),
                "handoff_context": cm.get_value_from_corememory("handoff_context"),
                # Add agent_name for prompt templates - use current adapter agent
                "agent_name": adapter.current_agent,
            }

            # Build context for the orchestrator
            context = OrchestratorContext(
                session_id=session_id,
                websocket=ws,
                call_connection_id=call_connection_id,
                user_text=transcript,
                conversation_history=_get_conversation_history(cm),
                metadata=session_context,
            )

            tool_invocations: dict[str, dict[str, float]] = {}

            # Define agent switch callback - emits agent_change envelope for UI cascade updates
            async def on_agent_switch(previous_agent: str, new_agent: str) -> None:
                """Emit agent_change envelope and update voice configuration when handoff occurs."""
                new_label = _resolve_agent_label(new_agent)

                # Update MemoManager with new agent
                try:
                    cm.set_corememory("active_agent", new_agent)
                    cm.set_corememory("previous_agent", previous_agent)
                except Exception:
                    pass

                # Update TTSPlayback active agent for correct voice resolution on greetings
                if hasattr(ws.state, "tts_playback") and ws.state.tts_playback:
                    ws.state.tts_playback.set_active_agent(new_agent)

                # Get new agent's voice configuration for TTS updates
                # Adapter.agents contains session agent overrides from Agent Builder
                new_agent_config = adapter.agents.get(new_agent)
                voice_name = None
                voice_style = None
                voice_rate = None
                if new_agent_config and new_agent_config.voice:
                    voice_name = new_agent_config.voice.name
                    voice_style = new_agent_config.voice.style
                    voice_rate = new_agent_config.voice.rate

                # Emit agent_change envelope for frontend UI (cascade updates)
                envelope = make_envelope(
                    etype="event",
                    sender="System",
                    payload={
                        "event_type": "agent_change",
                        "agent_name": new_agent,
                        "agent_label": new_label,
                        "previous_agent": previous_agent,
                        "voice_name": voice_name,
                        "voice_style": voice_style,
                        "voice_rate": voice_rate,
                        "message": f"Switched to {new_label or new_agent}",
                    },
                    topic="session",
                    session_id=session_id,
                    call_id=call_connection_id,
                )
                try:
                    await send_session_envelope(
                        ws,
                        envelope,
                        session_id=session_id,
                        conn_id=None if is_acs else getattr(ws.state, "conn_id", None),
                        event_label="cascade_agent_change",
                        broadcast_only=is_acs,
                    )
                    logger.info(
                        "Agent change emitted | %s → %s (voice=%s)",
                        previous_agent,
                        new_agent,
                        voice_name,
                    )
                except Exception:
                    logger.debug("Failed to emit agent_change envelope", exc_info=True)

            # Register agent switch callback on adapter
            adapter.set_on_agent_switch(on_agent_switch)

            # Define TTS chunk callback - uses speech_cascade's queue_tts for proper sequencing
            async def on_tts_chunk(text: str) -> None:
                """Queue TTS and broadcast structured assistant streaming envelopes."""
                if not text or not text.strip():
                    return

                normalized = text.strip()
                stream_cache = _ensure_stream_cache(ws)
                stream_cache.append(normalized)

                cm_getter = getattr(cm, "get_value_from_corememory", None)
                memo_agent = None
                if callable(cm_getter):
                    try:
                        memo_agent = cm_getter("active_agent", "Assistant")
                    except Exception:
                        memo_agent = None
                agent_name = adapter.current_agent or memo_agent or "Assistant"
                agent_label = _resolve_agent_label(agent_name)

                # Get current agent's voice configuration for TTS
                # Adapter.agents contains session agent overrides from Agent Builder
                voice_name = None
                voice_style = None
                voice_rate = None
                agent_config = adapter.agents.get(agent_name)
                if agent_config and agent_config.voice:
                    voice_name = agent_config.voice.name
                    voice_style = agent_config.voice.style
                    voice_rate = agent_config.voice.rate

                # Play TTS immediately (bypass queue which is blocked during orchestration)
                if hasattr(ws.state, "speech_cascade") and ws.state.speech_cascade:
                    await ws.state.speech_cascade.play_tts_immediate(
                        text,
                        voice_name=voice_name,
                        voice_style=voice_style,
                        voice_rate=voice_rate,
                    )

                envelope = make_assistant_streaming_envelope(
                    content=text,
                    sender=agent_label,
                    session_id=session_id,
                    call_id=call_connection_id,
                )
                payload = envelope.setdefault("payload", {})
                payload.setdefault("message", text)
                payload["turn_id"] = run_id
                payload["response_id"] = run_id
                payload["status"] = "streaming"
                payload["sender"] = agent_name
                payload["active_agent"] = agent_name
                payload["active_agent_label"] = agent_label
                payload["speaker"] = agent_name
                payload["run_id"] = run_id

                envelope["message"] = text  # Legacy compatibility
                envelope["speaker"] = agent_name
                envelope["sender"] = agent_label

                await send_session_envelope(
                    ws,
                    envelope,
                    session_id=session_id,
                    conn_id=None if is_acs else getattr(ws.state, "conn_id", None),
                    event_label="assistant_streaming",
                    broadcast_only=is_acs,
                )

            async def on_tool_start(tool_name: str, arguments_raw: object) -> None:
                if not tool_name:
                    return
                try:
                    args = _parse_tool_arguments(arguments_raw)
                    call_id = uuid.uuid4().hex[:10]
                    tool_invocations[tool_name] = {
                        "id": call_id,
                        "started": time.perf_counter(),
                    }
                    await push_tool_start(
                        ws,
                        tool_name=tool_name,
                        call_id=call_id,
                        arguments=args,
                        is_acs=is_acs,
                        session_id=session_id,
                    )
                except Exception:
                    logger.debug("Failed to emit tool_start frame", exc_info=True)

            async def on_tool_end(tool_name: str, result: object) -> None:
                if not tool_name:
                    return
                try:
                    info = tool_invocations.pop(tool_name, None)
                    call_id = info.get("id") if info else uuid.uuid4().hex[:10]
                    duration_ms = None
                    if info and info.get("started"):
                        duration_ms = (time.perf_counter() - info["started"]) * 1000.0
                    await push_tool_end(
                        ws,
                        tool_name=tool_name,
                        call_id=call_id,
                        result=result,
                        is_acs=is_acs,
                        session_id=session_id,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    logger.debug("Failed to emit tool_end frame", exc_info=True)

            # Process the turn
            result = await adapter.process_turn(
                context,
                on_tts_chunk=on_tts_chunk,
                on_tool_start=on_tool_start,
                on_tool_end=on_tool_end,
            )

            span.set_attribute("orchestrator.response_length", len(result.response_text or ""))
            span.set_attribute("orchestrator.agent", result.agent_name or "unknown")

            if result.error:
                span.set_attribute("orchestrator.error", result.error)
                logger.warning(
                    "Orchestrator returned error",
                    extra={"error": result.error, "session_id": session_id},
                )

            # Sync adapter state back to MemoManager
            adapter.sync_to_memo_manager(cm)

            if result.response_text:
                cm_getter = getattr(cm, "get_value_from_corememory", None)
                memo_agent = None
                if callable(cm_getter):
                    try:
                        memo_agent = cm_getter("active_agent", "Assistant")
                    except Exception:
                        memo_agent = None
                final_agent = (
                    result.agent_name or adapter.current_agent or memo_agent or "Assistant"
                )
                final_label = _resolve_agent_label(final_agent)
                payload = {
                    "type": "assistant",
                    "message": result.response_text,
                    "content": result.response_text,
                    "streaming": False,
                    "turn_id": run_id,
                    "response_id": run_id,
                    "status": "completed",
                    "sender": final_agent,
                    "speaker": final_agent,
                    "active_agent": final_agent,
                    "active_agent_label": final_label,
                    "run_id": run_id,
                }
                envelope = make_envelope(
                    etype="event",
                    sender=final_label,
                    payload=payload,
                    topic="session",
                    session_id=session_id,
                    call_id=call_connection_id,
                )
                envelope["speaker"] = final_agent
                try:
                    await send_session_envelope(
                        ws,
                        envelope,
                        session_id=session_id,
                        conn_id=None if is_acs else getattr(ws.state, "conn_id", None),
                        event_label="assistant_transcript",
                        broadcast_only=is_acs,
                    )
                    logger.info(
                        "Sent final assistant envelope | agent=%s text_len=%d turn_id=%s",
                        final_agent,
                        len(result.response_text),
                        run_id,
                    )
                except Exception:
                    logger.debug("Failed to emit assistant_final envelope", exc_info=True)
            else:
                logger.warning("No response_text to send as final envelope | turn_id=%s", run_id)

            return result.response_text

        except Exception as exc:
            logger.exception("💥 route_turn crash – session=%s", session_id)
            span.set_attribute("orchestrator.error", "exception")
            try:
                await _emit_orchestrator_error_status(ws, cm, exc)
            except Exception:
                logger.debug("Failed to emit orchestrator error status", exc_info=True)
            raise
        finally:
            # Persist conversation state
            try:
                if hasattr(cm, "persist_to_redis_async"):
                    await cm.persist_to_redis_async(redis_mgr)
                elif hasattr(cm, "persist_background"):
                    await cm.persist_background(redis_mgr)
            except Exception as persist_exc:
                logger.warning(
                    "Failed to persist orchestrator memory for session %s: %s",
                    session_id,
                    persist_exc,
                )


def _get_conversation_history(cm: MemoManager) -> list[dict]:
    """Extract conversation history from MemoManager."""
    history = []

    # Get the active agent to retrieve its history
    active_agent = None
    try:
        active_agent = cm.get_value_from_corememory("active_agent")
    except Exception:
        pass

    # Try to get history from the MemoManager's history for the active agent
    if active_agent and hasattr(cm, "get_history"):
        try:
            agent_history = cm.get_history(active_agent)
            if agent_history:
                history.extend(agent_history)
        except Exception:
            pass

    # Fallback: try working memory (legacy compatibility)
    if not history and hasattr(cm, "workingmemory") and cm.workingmemory:
        for item in cm.workingmemory:
            if isinstance(item, dict) and "role" in item:
                history.append(item)

    return history


def _summarize_orchestrator_exception(exc: Exception) -> tuple[str, str, str]:
    """Return user-friendly message, caption, and tone for frontend display."""
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()

    if "responsibleaipolicyviolation" in lowered or "content_filter" in lowered:
        return (
            "🚫 Response blocked by content policy",
            "Azure OpenAI flagged the last response. Try rephrasing or adjusting the prompt.",
            "warning",
        )

    if "badrequest" in lowered or "400" in lowered:
        excerpt = text[:220]
        return (
            "⚠️ Assistant could not complete the request",
            excerpt,
            "warning",
        )

    excerpt = text[:220]
    return (
        "❌ Assistant ran into an unexpected error",
        excerpt,
        "error",
    )


async def _emit_orchestrator_error_status(
    ws: WebSocket,
    cm: MemoManager,
    exc: Exception,
) -> None:
    """Send a structured status envelope to the frontend describing orchestrator failures."""
    message, caption, tone = _summarize_orchestrator_exception(exc)

    session_id = getattr(cm, "session_id", None) or getattr(ws.state, "session_id", None)
    call_id = getattr(ws.state, "call_connection_id", None) or getattr(
        cm, "call_connection_id", None
    )

    envelope = make_envelope(
        etype="status",
        sender="System",
        payload={
            "message": message,
            "statusTone": tone,
            "statusCaption": caption,
        },
        topic="session",
        session_id=session_id,
        call_id=call_id,
    )

    await send_session_envelope(
        ws,
        envelope,
        session_id=session_id,
        conn_id=getattr(ws.state, "conn_id", None),
        event_label="orchestrator_error",
        broadcast_only=False,
    )


__all__ = [
    "route_turn",
    "cleanup_adapter",
]
