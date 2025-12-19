"""VoiceLive SDK handler bridging ACS media streams to multi-agent orchestration."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from collections.abc import Awaitable
from typing import Any, Literal

import numpy as np

# Import agents loader for dynamic handoff_map building
from apps.artagent.backend.registries.agentstore.loader import (
    build_agent_summaries,
    build_handoff_map,
    discover_agents,
)
from apps.artagent.backend.src.utils.tracing import (
    create_service_dependency_attrs,
    create_service_handler_attrs,
)
from apps.artagent.backend.src.ws_helpers.envelopes import (
    make_assistant_streaming_envelope,
    make_envelope,
)

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Helpers
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.src.ws_helpers.shared_ws import (
    _set_connection_metadata,
    broadcast_session_envelope,
    send_session_envelope,
    send_user_transcript,
)

# Import config resolver for scenario-aware agent loading
from apps.artagent.backend.voice.shared import (
    DEFAULT_START_AGENT,
    resolve_from_app_state,
    resolve_orchestrator_config,
)
from apps.artagent.backend.src.services.session_loader import load_user_profile_by_email
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent

# ─────────────────────────────────────────────────────────────────────────────
# VoiceLive Channel Imports (local to voice_channels)
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.voice.voicelive.settings import get_settings
from apps.artagent.backend.voice.voicelive.tool_helpers import (
    push_tool_end,
    push_tool_start,
)
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    ClientEventConversationItemCreate,
    ClientEventResponseCreate,
    InputTextContentPart,
    ResponseStatus,
    ServerEventType,
    UserMessageItem,
)
from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.identity.aio import DefaultAzureCredential
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.monitoring import SpanAttr
from utils.ml_logging import get_logger
from utils.telemetry_decorators import ConversationTurnSpan

from .metrics import (
    record_llm_ttft,
    record_stt_latency,
    record_tts_ttfb,
    record_turn_complete,
)

# Import LiveOrchestrator from voicelive (canonical location after deprovisioning)
from .orchestrator import (
    LiveOrchestrator,
    register_voicelive_orchestrator,
    unregister_voicelive_orchestrator,
)

logger = get_logger("voicelive.handler")
tracer = trace.get_tracer(__name__)

_DTMF_FLUSH_DELAY_SECONDS = 1.5

def _resolve_agent_label(agent_name: str | None) -> str | None:
    """Return the agent name as the label (agents define their own display names)."""
    return agent_name


def _safe_primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_primitive(v) for k, v in value.items()}
    return str(value)


# Module-level set to track pending background tasks for cleanup
# This prevents fire-and-forget tasks from causing memory leaks
_pending_background_tasks: set[asyncio.Task] = set()


def _background_task(coro: Awaitable[Any], *, label: str) -> asyncio.Task:
    """Create a tracked background task that will be cleaned up on handler stop."""
    task = asyncio.create_task(coro, name=f"voicelive-bg-{label}")
    _pending_background_tasks.add(task)

    def _cleanup_task(t: asyncio.Task) -> None:
        _pending_background_tasks.discard(t)
        try:
            t.result()
        except asyncio.CancelledError:
            pass  # Expected during cleanup
        except Exception:
            logger.debug("Background task '%s' failed", label, exc_info=True)

    task.add_done_callback(_cleanup_task)
    return task


def _cancel_all_background_tasks() -> int:
    """Cancel all pending background tasks. Returns count of cancelled tasks."""
    cancelled = 0
    for task in list(_pending_background_tasks):
        if not task.done():
            task.cancel()
            cancelled += 1
    _pending_background_tasks.clear()
    return cancelled


def _serialize_session_config(session_obj: Any) -> dict[str, Any] | None:
    if not session_obj:
        return None

    for attr in ("model_dump", "to_dict", "as_dict", "dict"):
        method = getattr(session_obj, attr, None)
        if callable(method):
            try:
                data = method()
                if isinstance(data, dict):
                    return data
            except Exception:
                logger.debug("Failed to serialize session via %s", attr, exc_info=True)

    serializer = getattr(session_obj, "serialize", None) or getattr(session_obj, "to_json", None)
    if callable(serializer):
        try:
            data = serializer()
            if isinstance(data, str):
                return json.loads(data)
            if isinstance(data, dict):
                return data
        except Exception:
            logger.debug("Failed to serialize session via serializer", exc_info=True)

    try:
        raw = vars(session_obj)
    except Exception:
        return None

    return {k: _safe_primitive(v) for k, v in raw.items()}


class _SessionMessenger:
    """Bridge VoiceLive events to the session-aware WebSocket manager."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._default_sender: str | None = None
        self._missing_session_warned = False
        self._active_turn_id: str | None = None
        self._pending_user_turn_id: str | None = None
        self._active_agent_name: str | None = None
        self._active_agent_label: str | None = None

    def _ensure_turn_id(self, candidate: str | None, *, allow_generate: bool = True) -> str | None:
        if candidate:
            self._active_turn_id = candidate
            return candidate
        if self._active_turn_id:
            return self._active_turn_id
        if not allow_generate:
            return None
        generated = uuid.uuid4().hex
        self._active_turn_id = generated
        return generated

    def _release_turn(self, turn_id: str | None) -> None:
        if turn_id and self._active_turn_id == turn_id:
            self._active_turn_id = None
        elif turn_id is None:
            self._active_turn_id = None

    def begin_user_turn(self, turn_id: str | None) -> str | None:
        """Initialise a user turn and emit a placeholder streaming message."""
        if not turn_id:
            self._pending_user_turn_id = None
            return None
        if self._pending_user_turn_id == turn_id:
            return turn_id
        self._pending_user_turn_id = turn_id
        if not self._can_emit():
            return turn_id

        payload: dict[str, Any] = {
            "type": "user",
            "message": "",
            "content": "",
            "streaming": True,
            "turn_id": turn_id,
            "response_id": turn_id,
            "status": "streaming",
        }
        envelope = make_envelope(
            etype="event",
            sender="User",
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )

        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_user_turn_started",
                broadcast_only=True,
            ),
            label="user_turn_started",
        )
        return turn_id

    def resolve_user_turn_id(self, candidate: str | None) -> str | None:
        """Ensure user turn IDs remain consistent across delta and final events."""
        if candidate:
            self._pending_user_turn_id = candidate
            return candidate
        return self._pending_user_turn_id

    def finish_user_turn(self, turn_id: str | None) -> None:
        resolved = turn_id or self._pending_user_turn_id
        if resolved and self._pending_user_turn_id == resolved:
            self._pending_user_turn_id = None

    def set_active_agent(self, agent_name: str | None) -> None:
        """Update the default sender name and emit agent change envelope."""
        if agent_name == self._active_agent_name:
            return

        previous_agent = self._default_sender
        new_label = _resolve_agent_label(agent_name) or agent_name or None
        self._default_sender = new_label
        self._active_agent_name = agent_name
        self._active_agent_label = new_label

        # Emit agent change envelope for frontend UI (cascade updates)
        if self._can_emit() and agent_name:
            envelope = make_envelope(
                etype="event",
                sender="System",
                payload={
                    "event_type": "agent_change",
                    "agent_name": agent_name,
                    "agent_label": new_label,
                    "previous_agent": previous_agent,
                    "message": f"Switched to {new_label or agent_name}",
                },
                topic="session",
                session_id=self._session_id,
                call_id=self._call_id,
            )
            _background_task(
                send_session_envelope(
                    self._ws,
                    envelope,
                    session_id=self._session_id,
                    conn_id=None,
                    event_label="voicelive_agent_change",
                    broadcast_only=True,
                ),
                label="agent_change_envelope",
            )
            logger.info(
                "[VoiceLive] Agent change emitted: %s → %s",
                previous_agent,
                new_label or agent_name,
            )

    @property
    def _session_id(self) -> str | None:
        return getattr(self._ws.state, "session_id", None)

    @property
    def _call_id(self) -> str | None:
        return getattr(self._ws.state, "call_connection_id", None)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def call_id(self) -> str | None:
        return self._call_id

    def _can_emit(self) -> bool:
        if self._session_id:
            self._missing_session_warned = False
            return True

        if not self._missing_session_warned:
            logger.warning(
                "[VoiceLive] Unable to emit envelope - websocket missing session_id (call=%s)",
                self._call_id,
            )
            self._missing_session_warned = True
        return False

    async def send_user_message(self, text: str, *, turn_id: str | None = None) -> None:
        """Forward a user transcript to all session listeners."""
        if not text or not self._can_emit():
            return

        _background_task(
            send_user_transcript(
                self._ws,
                text,
                session_id=self._session_id,
                conn_id=None,
                broadcast_only=True,
                turn_id=turn_id,
                active_agent=self._active_agent_name,
                active_agent_label=self._active_agent_label,
            ),
            label="send_user_transcript",
        )

    def _resolve_sender(self, sender: str | None) -> str:
        return _resolve_agent_label(sender) or self._default_sender or "Assistant"

    async def send_assistant_message(
        self,
        text: str,
        *,
        sender: str | None = None,
        response_id: str | None = None,
        status: str | None = None,
    ) -> None:
        """Emit assistant transcript chunks to the frontend chat UI."""
        if not self._can_emit():
            return

        turn_id = self._ensure_turn_id(response_id)
        if not turn_id:
            return

        message_text = text or ""
        sender_name = self._resolve_sender(sender)
        payload = {
            "type": "assistant",
            "message": message_text,
            "content": message_text,
            "streaming": False,
            "turn_id": turn_id,
            "response_id": response_id or turn_id,
            "status": status or "completed",
            "active_agent": self._active_agent_name,
            "active_agent_label": self._active_agent_label,
            "sender": self._active_agent_name,
        }
        envelope = make_envelope(
            etype="event",
            sender=sender_name,
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )
        if self._active_agent_name:
            envelope["sender"] = self._active_agent_name

        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_assistant_transcript",
                broadcast_only=True,
            ),
            label="assistant_transcript_envelope",
        )
        self._release_turn(turn_id)

    async def send_assistant_streaming(
        self,
        text: str,
        *,
        sender: str | None = None,
        response_id: str | None = None,
    ) -> None:
        """Emit assistant streaming deltas for progressive rendering."""
        if not text or not self._can_emit():
            return

        turn_id = self._ensure_turn_id(response_id)
        if not turn_id:
            return

        sender_name = self._resolve_sender(sender)
        envelope = make_assistant_streaming_envelope(
            text,
            sender=sender_name,
            session_id=self._session_id,
            call_id=self._call_id,
        )
        if self._active_agent_name:
            envelope["sender"] = self._active_agent_name

        payload = envelope.setdefault("payload", {})
        payload.setdefault("message", text)
        payload["turn_id"] = turn_id
        payload["response_id"] = response_id or turn_id
        payload["status"] = "streaming"
        payload["active_agent"] = self._active_agent_name
        payload["active_agent_label"] = self._active_agent_label
        payload["sender"] = self._active_agent_name
        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_assistant_streaming",
                broadcast_only=True,
            ),
            label="assistant_streaming_envelope",
        )

    async def send_assistant_cancelled(
        self,
        *,
        response_id: str | None,
        sender: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Emit a cancellation update for interrupted assistant turns."""
        if not self._can_emit():
            return

        turn_id = self._ensure_turn_id(response_id, allow_generate=False)
        if not turn_id:
            return

        sender_name = self._resolve_sender(sender)
        payload: dict[str, Any] = {
            "type": "assistant_cancelled",
            "message": "",
            "content": "",
            "streaming": False,
            "turn_id": turn_id,
            "response_id": response_id or turn_id,
            "status": "cancelled",
            "sender": self._active_agent_name,
        }
        if reason:
            payload["cancel_reason"] = reason

        envelope = make_envelope(
            etype="event",
            sender=sender_name,
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )
        if self._active_agent_name:
            envelope["sender"] = self._active_agent_name

        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_assistant_cancelled",
                broadcast_only=True,
            ),
            label="assistant_cancelled_envelope",
        )
        self._release_turn(turn_id)

    async def send_session_update(
        self,
        *,
        agent_name: str | None,
        session_obj: Any | None,
        transport: str | None = None,
    ) -> None:
        """Broadcast session configuration updates to the UI."""
        if not self._can_emit():
            return

        payload: dict[str, Any] = {
            "event_type": "session_updated",
            "agent_label": _resolve_agent_label(agent_name),
            "agent_name": agent_name,
            "transport": transport,
            "session": _serialize_session_config(session_obj),
        }

        agent_label_display = payload.get("agent_label") or agent_name
        if agent_label_display:
            payload["agent_label"] = agent_label_display
            payload.setdefault("active_agent_label", agent_label_display)
            payload.setdefault(
                "message",
                f"Active agent: {agent_label_display}",
            )

        if session_obj:
            payload["session_id"] = getattr(session_obj, "id", None)

            voice = getattr(session_obj, "voice", None)
            if voice:
                payload["voice"] = {
                    "name": getattr(voice, "name", None),
                    "type": getattr(voice, "type", None),
                    "rate": getattr(voice, "rate", None),
                    "style": getattr(voice, "style", None),
                }

            turn_detection = getattr(session_obj, "turn_detection", None)
            if turn_detection:
                payload["turn_detection"] = {
                    "type": getattr(turn_detection, "type", None),
                    "threshold": getattr(turn_detection, "threshold", None),
                    "silence_duration_ms": getattr(turn_detection, "silence_duration_ms", None),
                }

        envelope = make_envelope(
            etype="event",
            sender="System",
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )

        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_session_updated",
                broadcast_only=True,
            ),
            label="session_update_envelope",
        )

    async def send_status_update(
        self,
        text: str,
        *,
        tone: str | None = None,
        caption: str | None = None,
        sender: str | None = None,
        event_label: str = "voicelive_status_update",
    ) -> None:
        """Emit a system status envelope for richer UI feedback."""
        if not text or not self._can_emit():
            return

        payload: dict[str, Any] = {
            "type": "status",
            "message": text,
            "content": text,
        }
        if tone:
            payload["statusTone"] = tone
        if caption:
            payload["statusCaption"] = caption
        sender_name = self._resolve_sender(sender) if (sender or self._default_sender) else "System"

        envelope = make_envelope(
            etype="status",
            sender=sender_name,
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )

        _background_task(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label=event_label,
                broadcast_only=True,
            ),
            label=event_label,
        )

    async def notify_tool_start(
        self, *, call_id: str | None, name: str | None, args: dict[str, Any]
    ) -> None:
        """Relay tool start events to the session dashboard."""
        if not self._can_emit() or not call_id or not name:
            return
        try:
            _background_task(
                push_tool_start(
                    self._ws,
                    name,  # tool_name
                    call_id,  # call_id
                    args,  # arguments
                    is_acs=True,
                    session_id=self._session_id,
                ),
                label=f"tool_start_{name}",
            )
        except Exception:
            logger.debug("Failed to emit tool_start frame for VoiceLive session", exc_info=True)

    async def notify_tool_end(
        self,
        *,
        call_id: str | None,
        name: str | None,
        status: str,
        elapsed_ms: float,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Relay tool completion events (success or failure)."""
        if not self._can_emit() or not call_id or not name:
            return
        try:
            # Build result dict that push_tool_end can derive status from
            tool_result = result if result is not None else {}
            if status == "error":
                tool_result = {"success": False, "error": error or "Tool execution failed"}

            _background_task(
                push_tool_end(
                    self._ws,
                    name,  # tool_name
                    call_id,  # call_id
                    tool_result,  # result (status is derived from this)
                    is_acs=True,
                    session_id=self._session_id,
                    duration_ms=elapsed_ms,
                ),
                label=f"tool_end_{name}",
            )
        except Exception:
            logger.debug("Failed to emit tool_end frame for VoiceLive session", exc_info=True)


VoiceLiveTransport = Literal["acs", "realtime"]


class VoiceLiveSDKHandler:
    """Minimal VoiceLive handler that mirrors the vlagent multi-agent sample.

    The handler streams ACS audio into Azure VoiceLive, delegates orchestration to the
    shared multi-agent orchestrator, and relays VoiceLive audio deltas back to ACS.

    Args:
            websocket: ACS WebSocket connection for bidirectional media.
            session_id: Identifier used for logging and latency tracking.
            call_connection_id: ACS call connection identifier for diagnostics.
    """

    def __init__(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        call_connection_id: str | None = None,
        transport: VoiceLiveTransport = "acs",
        user_email: str | None = None,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.call_connection_id = call_connection_id or session_id
        self._messenger = _SessionMessenger(websocket)
        self._transport: VoiceLiveTransport = transport
        self._manual_commit_enabled = transport == "acs"
        self._user_email = user_email

        self._settings = None
        self._credential: AzureKeyCredential | TokenCredential | None = None
        self._connection = None
        self._connection_cm = None
        self._orchestrator: LiveOrchestrator | None = None
        self._event_task: asyncio.Task | None = None
        self._running = False
        self._shutdown = asyncio.Event()
        self._acs_sample_rate = 16000
        self._active_response_ids: set[str] = set()
        self._stop_audio_pending = False
        self._response_audio_frames: dict[str, int] = {}
        self._fallback_audio_frame_index = 0
        self._dtmf_digits: list[str] = []
        self._dtmf_flush_task: asyncio.Task | None = None
        self._dtmf_flush_delay = _DTMF_FLUSH_DELAY_SECONDS
        self._dtmf_lock = asyncio.Lock()
        self._last_user_transcript: str | None = None
        self._last_user_turn_id: str | None = None

        # Turn-level latency tracking
        self._turn_number: int = 0
        self._active_turn_span: ConversationTurnSpan | None = None
        self._turn_start_time: float | None = None
        self._vad_end_time: float | None = None
        self._transcript_final_time: float | None = None
        self._llm_first_token_time: float | None = None
        self._tts_first_audio_time: float | None = None
        self._current_response_id: str | None = None

    def _set_metadata(self, key: str, value: Any) -> None:
        if not _set_connection_metadata(self.websocket, key, value):
            setattr(self.websocket.state, key, value)

    def _get_metadata(self, key: str, default: Any = None) -> Any:
        """Read per-connection metadata from the websocket.state (or default)."""
        return getattr(self.websocket.state, key, default)

    def _mark_audio_playback(self, active: bool, *, reset_cancel: bool = True) -> None:
        # single source of truth for "assistant is speaking"
        self._set_metadata("audio_playing", active)
        self._set_metadata("tts_active", active)
        if reset_cancel:
            self._set_metadata("tts_cancel_requested", False)

    def _trigger_barge_in(
        self,
        trigger: str,
        stage: str,
        *,
        energy_level: float | None = None,
        reset_audio_state: bool = True,
    ) -> None:
        request_fn = getattr(self.websocket.state, "request_barge_in", None)
        if callable(request_fn):
            try:
                kwargs: dict[str, Any] = {}
                if energy_level is not None:
                    kwargs["energy_level"] = energy_level
                request_fn(trigger, stage, **kwargs)
            except Exception:
                logger.debug("Failed to dispatch barge-in request", exc_info=True)
        else:
            logger.debug("[%s] No barge-in handler available for realtime trigger", self.session_id)

        self._set_metadata("tts_cancel_requested", True)
        if reset_audio_state:
            self._mark_audio_playback(False, reset_cancel=False)

    async def start(self) -> None:
        """Establish VoiceLive connection and start event processing."""
        if self._running:
            return

        span_attrs = create_service_handler_attrs(
            service_name="voicelive_sdk_handler",
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            operation="start",
            transport=self._transport,
        )
        with tracer.start_as_current_span(
            "voicelive.handler.start",
            kind=SpanKind.SERVER,
            attributes=span_attrs,
        ) as span:
            start_ts = time.perf_counter()
            try:
                self._settings = get_settings()
                connection_options = {
                    "max_msg_size": self._settings.ws_max_msg_size,
                    "heartbeat": self._settings.ws_heartbeat,
                    "timeout": self._settings.ws_timeout,
                }

                # Trace VoiceLive connection establishment
                conn_attrs = create_service_dependency_attrs(
                    source_service="voicelive_sdk_handler",
                    target_service="azure_voicelive",
                    call_connection_id=self.call_connection_id,
                    session_id=self.session_id,
                    ws=True,
                )
                with tracer.start_as_current_span(
                    "voicelive.connect",
                    kind=SpanKind.SERVER,
                    attributes=conn_attrs,
                ) as conn_span:
                    self._credential = self._build_credential(self._settings)
                    self._connection_cm = connect(
                        endpoint=self._settings.azure_voicelive_endpoint,
                        credential=self._credential,
                        model=self._settings.azure_voicelive_model,
                        connection_options=connection_options,
                    )
                    self._connection = await self._connection_cm.__aenter__()
                    conn_span.set_attribute("voicelive.model", self._settings.azure_voicelive_model)

                # ─────────────────────────────────────────────────────────────
                # Agent Loading - Prefer unified agents from app.state
                # ─────────────────────────────────────────────────────────────
                agents = None
                orchestrator_config = None
                
                # Resolve scenario from multiple sources (priority order):
                # 1. websocket.state.scenario (set by browser endpoint)
                # 2. MemoManager corememory (set by media_handler or call setup)
                # 3. Session-scoped scenario (from ScenarioBuilder)
                scenario_name = getattr(self.websocket.state, "scenario", None)
                if not scenario_name:
                    memo_mgr = getattr(self.websocket.state, "cm", None)
                    if memo_mgr and hasattr(memo_mgr, "get_value_from_corememory"):
                        scenario_name = memo_mgr.get_value_from_corememory("scenario_name", None)
                        if scenario_name:
                            logger.debug(
                                "[VoiceLiveSDK] Resolved scenario from MemoManager | scenario=%s session=%s",
                                scenario_name,
                                self.session_id,
                            )

                # Try to get unified agents from app.state (set in main.py)
                app_state = getattr(self.websocket, "app", None)
                if app_state:
                    app_state = getattr(app_state, "state", None)

                if app_state and hasattr(app_state, "unified_agents") and app_state.unified_agents:
                    # Use unified agents directly (no adapter needed)
                    agents = app_state.unified_agents
                    orchestrator_config = resolve_orchestrator_config(
                        session_id=self.session_id,
                        scenario_name=scenario_name,
                    )
                    span.set_attribute("voicelive.agent_source", "unified")
                    logger.info(
                        "Using unified agents for VoiceLive | count=%d start_agent=%s scenario=%s session_id=%s",
                        len(agents),
                        orchestrator_config.start_agent if orchestrator_config else "default",
                        scenario_name or getattr(orchestrator_config, "scenario_name", None) or "(none)",
                        self.session_id or "(none)",
                    )
                else:
                    # Fallback to auto-discovery of unified agents
                    logger.info(
                        "No unified agents in app.state - discovering from agents directory",
                    )
                    agents = discover_agents()
                    orchestrator_config = resolve_orchestrator_config(
                        session_id=self.session_id,
                        scenario_name=scenario_name,
                    )
                    span.set_attribute("voicelive.agent_source", "discovered")
                    logger.info(
                        "Discovered unified agents | count=%d start_agent=%s scenario=%s session_id=%s",
                        len(agents),
                        orchestrator_config.start_agent if orchestrator_config else "default",
                        scenario_name or getattr(orchestrator_config, "scenario_name", None) or "(none)",
                        self.session_id or "(none)",
                    )

                span.set_attribute("voicelive.agents_count", len(agents))

                # Merge scenario agents if scenario is active
                if orchestrator_config and orchestrator_config.has_scenario:
                    if orchestrator_config.agents:
                        # Scenario agents take precedence (already UnifiedAgent)
                        merged_agents = dict(agents)
                        merged_agents.update(orchestrator_config.agents)
                        agents = merged_agents
                    span.set_attribute(
                        "voicelive.scenario", orchestrator_config.scenario_name or ""
                    )
                    logger.info(
                        "Loaded scenario configuration | scenario=%s start_agent=%s",
                        orchestrator_config.scenario_name,
                        orchestrator_config.start_agent,
                    )

                # ─────────────────────────────────────────────────────────────
                # Session Agent Check (Agent Builder) - Priority 1
                # If a session agent exists, inject it into agents and use as start
                # ─────────────────────────────────────────────────────────────
                session_agent = get_session_agent(self.session_id)
                if session_agent:
                    # Session agent is already UnifiedAgent - inject directly
                    agents = dict(agents)  # Make mutable copy
                    agents[session_agent.name] = session_agent
                    span.set_attribute("voicelive.session_agent", session_agent.name)
                    logger.info(
                        "Session agent found (Agent Builder) | name=%s voice=%s session_id=%s",
                        session_agent.name,
                        session_agent.voice.name if session_agent.voice else "default",
                        self.session_id,
                    )

                # Determine effective start agent
                # Priority: 1. Session agent, 2. Scenario start_agent, 3. Settings default
                effective_start_agent = DEFAULT_START_AGENT
                if session_agent:
                    effective_start_agent = session_agent.name
                elif orchestrator_config and orchestrator_config.start_agent:
                    effective_start_agent = orchestrator_config.start_agent
                elif hasattr(self._settings, "start_agent") and self._settings.start_agent:
                    effective_start_agent = self._settings.start_agent

                user_profile = None
                if hasattr(self, "_user_email") and self._user_email:
                    logger.info("Loading user profile for session | email=%s", self._user_email)
                    user_profile = await load_user_profile_by_email(self._user_email)
                    if user_profile:
                        span.set_attribute("voicelive.user_profile_loaded", True)
                        span.set_attribute(
                            "voicelive.client_id", user_profile.get("client_id", "unknown")
                        )

                # Determine handoff map - prefer from app.state or orchestrator config,
                # fallback to dynamically building from current agents
                effective_handoff_map: dict[str, str] = {}
                if app_state and hasattr(app_state, "handoff_map") and app_state.handoff_map:
                    effective_handoff_map = app_state.handoff_map
                elif orchestrator_config and orchestrator_config.handoff_map:
                    effective_handoff_map = orchestrator_config.handoff_map
                else:
                    # Build dynamically from agent declarations (single source of truth)
                    effective_handoff_map = build_handoff_map(agents)

                # Get MemoManager from websocket state (set by media_handler)
                memo_manager = getattr(self.websocket.state, "cm", None)
                if memo_manager:
                    logger.debug("[VoiceLiveSDK] Using MemoManager from websocket state")

                self._orchestrator = LiveOrchestrator(
                    conn=self._connection,
                    agents=agents,
                    handoff_map=effective_handoff_map,
                    start_agent=effective_start_agent,
                    audio_processor=None,
                    messenger=self._messenger,
                    call_connection_id=self.call_connection_id,
                    transport=self._transport,
                    model_name=self._settings.azure_voicelive_model,
                    memo_manager=memo_manager,
                )
                span.set_attribute("voicelive.start_agent", effective_start_agent)

                # Register orchestrator for scenario updates
                register_voicelive_orchestrator(self.session_id, self._orchestrator)

                # Emit agent inventory to dashboard clients for debugging/visualization
                try:
                    await self._emit_agent_inventory(
                        agents=agents,
                        start_agent=effective_start_agent,
                        source=(
                            "unified"
                            if app_state and getattr(app_state, "unified_agents", None)
                            else "legacy"
                        ),
                        scenario=orchestrator_config.scenario_name if orchestrator_config else None,
                        handoff_map=effective_handoff_map,
                    )
                except Exception:
                    logger.debug("Failed to emit agent inventory snapshot", exc_info=True)

                system_vars = {}

                # Priority 1: User profile from email login
                if user_profile:
                    system_vars["session_profile"] = user_profile
                    system_vars["client_id"] = user_profile.get("client_id")
                    system_vars["customer_intelligence"] = user_profile.get(
                        "customer_intelligence", {}
                    )
                    system_vars["caller_name"] = user_profile.get("full_name")
                    if user_profile.get("institution_name"):
                        system_vars["institution_name"] = user_profile["institution_name"]
                    logger.info(
                        "Session initialized with user profile | client_id=%s name=%s",
                        user_profile.get("client_id"),
                        user_profile.get("full_name"),
                    )
                # Priority 2: Restore from MemoManager (previous session context)
                elif memo_manager and hasattr(memo_manager, "get_value_from_corememory"):
                    stored_profile = memo_manager.get_value_from_corememory("session_profile")
                    if stored_profile:
                        system_vars["session_profile"] = stored_profile
                        system_vars["client_id"] = stored_profile.get("client_id")
                        system_vars["customer_intelligence"] = stored_profile.get(
                            "customer_intelligence", {}
                        )
                        system_vars["caller_name"] = stored_profile.get("full_name")
                        if stored_profile.get("institution_name"):
                            system_vars["institution_name"] = stored_profile["institution_name"]
                        logger.info(
                            "🔄 Restored session context from memory | client_id=%s name=%s",
                            stored_profile.get("client_id"),
                            stored_profile.get("full_name"),
                        )
                    else:
                        # Try individual fields as fallback
                        for key in (
                            "client_id",
                            "caller_name",
                            "customer_intelligence",
                            "institution_name",
                        ):
                            val = memo_manager.get_value_from_corememory(key)
                            if val:
                                system_vars[key] = val
                        if system_vars.get("client_id"):
                            logger.info(
                                "🔄 Restored partial context from memory | client_id=%s",
                                system_vars.get("client_id"),
                            )

                await self._orchestrator.start(system_vars=system_vars)

                self._running = True
                self._shutdown.clear()
                self._event_task = asyncio.create_task(self._event_loop())

                elapsed_ms = (time.perf_counter() - start_ts) * 1000
                span.set_attribute("voicelive.startup_ms", round(elapsed_ms, 2))
                logger.info(
                    "VoiceLive SDK handler started | session=%s call=%s startup_ms=%.2f",
                    self.session_id,
                    self.call_connection_id,
                    elapsed_ms,
                )
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                await self.stop()
                raise

    async def stop(self) -> None:
        """Stop event processing and release VoiceLive resources."""
        if not self._running:
            return

        with tracer.start_as_current_span(
            "voicelive_handler.stop",
            kind=trace.SpanKind.INTERNAL,
            attributes=create_service_handler_attrs(
                service_name="VoiceLiveSDKHandler.stop",
                call_connection_id=self.call_connection_id,
                session_id=self.session_id,
            ),
        ) as stop_span:
            self._running = False
            self._shutdown.set()

            # Unregister from scenario update callbacks
            unregister_voicelive_orchestrator(self.session_id)

            # Persist session state to Redis before stopping
            try:
                memo_manager = getattr(self.websocket.state, "cm", None) if self.websocket else None
                redis_mgr = (
                    getattr(self.websocket.app.state, "redis", None) if self.websocket else None
                )
                if memo_manager and redis_mgr:
                    # Sync orchestrator state to memo_manager first
                    if self._orchestrator and hasattr(self._orchestrator, "_sync_to_memo_manager"):
                        self._orchestrator._sync_to_memo_manager()
                    await memo_manager.persist_to_redis_async(redis_mgr)
                    logger.info(
                        "📦 Session state persisted to Redis | session=%s",
                        self.session_id,
                    )
            except Exception as persist_error:
                logger.warning(
                    "Failed to persist session state: %s | session=%s",
                    persist_error,
                    self.session_id,
                )

            if self._dtmf_flush_task:
                self._dtmf_flush_task.cancel()
                try:
                    await self._dtmf_flush_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._dtmf_flush_task = None
            self._dtmf_digits.clear()

            if self._event_task:
                self._event_task.cancel()
                try:
                    await self._event_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._event_task = None

            if self._connection_cm:
                try:
                    with tracer.start_as_current_span(
                        "voicelive.connection.close",
                        kind=trace.SpanKind.SERVER,
                        attributes=create_service_dependency_attrs(
                            source_service="voicelive_handler",
                            target_service="azure_voicelive",
                            call_connection_id=self.call_connection_id,
                            session_id=self.session_id,
                        ),
                    ):
                        await self._connection_cm.__aexit__(None, None, None)
                except Exception:
                    logger.exception("Error closing VoiceLive connection")
                finally:
                    self._connection_cm = None
                    self._connection = None

            # Cleanup orchestrator resources (greeting tasks, references)
            if self._orchestrator:
                try:
                    self._orchestrator.cleanup()
                except Exception:
                    logger.debug("Failed to cleanup orchestrator", exc_info=True)
                finally:
                    self._orchestrator = None

            # Cancel all pending background tasks to prevent memory leaks
            cancelled_count = _cancel_all_background_tasks()
            if cancelled_count > 0:
                logger.debug(
                    "Cancelled %d background tasks on stop | session=%s",
                    cancelled_count,
                    self.session_id,
                )

            # Close credential - always attempt in finally block
            credential = self._credential
            self._credential = None
            if isinstance(credential, DefaultAzureCredential):
                try:
                    await credential.close()
                except Exception:
                    logger.debug("Failed to close DefaultAzureCredential", exc_info=True)

            # Clear messenger reference to break circular refs
            self._messenger = None

            stop_span.set_status(trace.StatusCode.OK)
            logger.info(
                "VoiceLive SDK handler stopped | session=%s call=%s",
                self.session_id,
                self.call_connection_id,
            )

    async def handle_audio_data(self, message_data: str) -> None:
        """Forward ACS media payloads to VoiceLive."""
        if not self._running or not self._connection:
            logger.debug("VoiceLive handler inactive; dropping media message")
            return

        try:
            payload = json.loads(message_data)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON media message")
            return

        kind = payload.get("kind") or payload.get("Kind")

        if kind == "AudioMetadata":
            metadata = payload.get("payload", {})
            self._acs_sample_rate = metadata.get("rate", self._acs_sample_rate)
            logger.info(
                "Updated ACS audio metadata | session=%s rate=%s channels=%s",
                self.session_id,
                self._acs_sample_rate,
                metadata.get("channels", 1),
            )
            return

        if kind == "AudioData":
            audio_section = payload.get("audioData") or payload.get("AudioData") or {}
            if audio_section.get("silent"):
                return
            encoded = audio_section.get("data")
            if not encoded:
                return
            await self._connection.input_audio_buffer.append(audio=encoded)
            return

        if kind == "StopAudio":
            if self._manual_commit_enabled:
                await self._commit_input_buffer()
            return

        if kind == "DtmfData":
            tone = (payload.get("dtmfData") or payload.get("DtmfData") or {}).get("data")
            await self._handle_dtmf_tone(tone)
            return

    async def handle_pcm_chunk(self, audio_bytes: bytes, sample_rate: int = 16000) -> None:
        """Forward raw PCM frames (e.g., from realtime WS) to VoiceLive."""
        if not self._running or not self._connection or not audio_bytes:
            return

        try:
            encoded = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception:
            logger.debug("Failed to encode realtime PCM chunk for VoiceLive", exc_info=True)
            return

        self._acs_sample_rate = sample_rate or self._acs_sample_rate
        await self._connection.input_audio_buffer.append(audio=encoded)

    async def commit_audio_buffer(self) -> None:
        """Commit the current VoiceLive input buffer to trigger response generation."""
        if not self._manual_commit_enabled:
            return
        await self._commit_input_buffer()

    async def _event_loop(self) -> None:
        """Consume VoiceLive events, orchestrate tools, and stream audio to ACS."""
        assert self._connection is not None
        with tracer.start_as_current_span(
            "voicelive_handler.event_loop",
            kind=trace.SpanKind.INTERNAL,
            attributes=create_service_handler_attrs(
                service_name="VoiceLiveSDKHandler._event_loop",
                call_connection_id=self.call_connection_id,
                session_id=self.session_id,
            ),
        ) as loop_span:
            event_count = 0
            try:
                async for event in self._connection:
                    if self._shutdown.is_set():
                        break

                    event_count += 1
                    etype = event.type if hasattr(event, "type") else None
                    event_type_str = (
                        etype.value
                        if hasattr(etype, "value")
                        else str(etype) if etype else "unknown"
                    )

                    # Add span event for each VoiceLive event (batched, not per-event spans)
                    # Filter out high-frequency noisy events
                    if event_type_str not in (
                        "response.audio_transcript.delta",
                        "response.audio.delta",
                    ):
                        loop_span.add_event(
                            "voicelive.event_received",
                            {"event_type": event_type_str, "event_index": event_count},
                        )

                    self._observe_event(event)

                    # CRITICAL: Forward audio events FIRST before orchestrator processing
                    # This ensures audio delivery is not blocked by orchestrator network calls
                    # (session.update, MemoManager sync, etc.)
                    await self._forward_event_to_acs(event)

                    # Orchestrator handles higher-level logic (handoffs, context, metrics)
                    # This may involve network calls but should not block audio delivery
                    if self._orchestrator:
                        await self._orchestrator.handle_event(event)

                loop_span.set_attribute("voicelive.total_events", event_count)
                loop_span.set_status(trace.StatusCode.OK)
            except asyncio.CancelledError:
                loop_span.set_attribute("voicelive.total_events", event_count)
                loop_span.add_event("event_loop.cancelled")
                logger.debug("VoiceLive event loop cancelled | session=%s", self.session_id)
                raise
            except Exception as ex:
                loop_span.set_attribute("voicelive.total_events", event_count)
                loop_span.set_status(trace.StatusCode.ERROR, str(ex))
                loop_span.add_event(
                    "event_loop.error", {"error.type": type(ex).__name__, "error.message": str(ex)}
                )
                logger.exception("VoiceLive event loop error | session=%s", self.session_id)
            finally:
                self._shutdown.set()

    async def _forward_event_to_acs(self, event: Any) -> None:
        if not self._websocket_open:
            return

        etype = event.type if hasattr(event, "type") else None

        # Log all events for debugging
        if etype:
            logger.debug(
                "[VoiceLive] Event: %s | session=%s",
                etype.value if hasattr(etype, "value") else str(etype),
                self.session_id,
            )

        if etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            self._transcript_final_time = time.perf_counter()
            transcript = getattr(event, "transcript", "")
            turn_id = self._messenger.resolve_user_turn_id(self._extract_item_id(event))
            if transcript and (
                transcript != self._last_user_transcript or turn_id != self._last_user_turn_id
            ):
                await self._messenger.send_user_message(transcript, turn_id=turn_id)
                logger.info(
                    "[VoiceLiveSDK] User transcript | session=%s text='%s'",
                    self.session_id,
                    transcript,
                )
                self._last_user_transcript = transcript
                self._last_user_turn_id = turn_id
                self._messenger.finish_user_turn(turn_id)
            return
        elif etype == ServerEventType.RESPONSE_AUDIO_DELTA:
            response_id = getattr(event, "response_id", None)
            delta_bytes = getattr(event, "delta", None)

            # Track TTS TTFB (Time To First Byte) - first audio delta for this turn
            if self._turn_start_time and self._tts_first_audio_time is None:
                self._tts_first_audio_time = time.perf_counter()
                # Calculate latency relative to VAD end (preferred) or turn start
                start_ref = self._vad_end_time or self._turn_start_time
                ttfb_ms = (self._tts_first_audio_time - start_ref) * 1000
                self._current_response_id = response_id

                # Record OTel metric for App Insights Performance view
                record_tts_ttfb(
                    ttfb_ms,
                    session_id=self.session_id,
                    turn_number=self._turn_number,
                    reference="vad_end" if self._vad_end_time else "turn_start",
                    agent_name=self._messenger._active_agent_name or "unknown",
                )

                # Emit TTFB metric as a span for App Insights Performance tab
                with tracer.start_as_current_span(
                    "voicelive.tts.ttfb",
                    kind=SpanKind.INTERNAL,
                    attributes={
                        SpanAttr.TURN_NUMBER.value: self._turn_number,
                        SpanAttr.TURN_TTS_TTFB_MS.value: ttfb_ms,
                        SpanAttr.SESSION_ID.value: self.session_id,
                        SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id,
                        "voicelive.response_id": response_id or "unknown",
                        "latency.reference": "vad_end" if self._vad_end_time else "turn_start",
                    },
                ) as ttfb_span:
                    ttfb_span.add_event("tts.first_audio", {"ttfb_ms": ttfb_ms})
                    logger.info(
                        "[VoiceLive] TTS TTFB | session=%s turn=%d ttfb_ms=%.2f ref=%s",
                        self.session_id,
                        self._turn_number,
                        ttfb_ms,
                        "vad_end" if self._vad_end_time else "turn_start",
                    )

            logger.debug(
                "[VoiceLive] Audio delta received | session=%s response=%s bytes=%s",
                self.session_id,
                response_id,
                len(delta_bytes) if delta_bytes else 0,
            )
            if response_id:
                self._active_response_ids.add(response_id)
            self._stop_audio_pending = False
            await self._send_audio_delta(event.delta, response_id=response_id)

        elif etype == ServerEventType.RESPONSE_DONE:
            response_id = self._extract_response_id(event)
            if response_id:
                logger.debug(
                    "[VoiceLive] Response done | session=%s response=%s",
                    self.session_id,
                    response_id,
                )
                if (
                    self._should_stop_for_response(event)
                    and response_id in self._active_response_ids
                ):
                    await self._send_stop_audio()
                self._active_response_ids.discard(response_id)
                self._mark_audio_playback(False)
            else:
                logger.debug(
                    "[VoiceLive] Response done without audio playback | session=%s",
                    self.session_id,
                )
                self._mark_audio_playback(False)

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            # User started speaking - stop assistant playback and start turn tracking
            logger.info(
                "[VoiceLive] User speech started | session=%s",
                self.session_id,
            )

            # Finalize previous turn if still active
            await self._finalize_turn_metrics()

            # Start new turn tracking
            self._turn_number += 1
            self._turn_start_time = time.perf_counter()
            self._vad_end_time = None
            self._transcript_final_time = None
            self._llm_first_token_time = None
            self._tts_first_audio_time = None
            self._current_response_id = None

            self._active_response_ids.clear()
            energy = getattr(event, "speech_energy", None)
            turn_id = self._extract_item_id(event)
            resolved_turn = self._messenger.begin_user_turn(turn_id)
            if resolved_turn:
                self._last_user_turn_id = resolved_turn
                self._last_user_transcript = ""
            self._trigger_barge_in(
                "voicelive_vad",
                "speech_started",
                energy_level=energy,
            )
            await self._send_stop_audio()
            self._stop_audio_pending = False

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            self._vad_end_time = time.perf_counter()
            logger.debug("🎤 User paused speaking")
            logger.debug("🤖 Generating assistant reply")
            self._mark_audio_playback(False)

        elif etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_DELTA:
            transcript_text = getattr(event, "transcript", "") or getattr(event, "delta", "")
            if not transcript_text:
                return
            session_id = self._messenger._session_id
            if not session_id:
                return
            turn_id = self._messenger.resolve_user_turn_id(self._extract_item_id(event))
            payload = {
                "type": "user",
                "message": "...",
                "content": transcript_text,
                "streaming": True,
                "active_agent": self._messenger._active_agent_name,
                "active_agent_label": self._messenger._active_agent_label,
            }
            if turn_id:
                payload["turn_id"] = turn_id
                payload["response_id"] = turn_id
            envelope = make_envelope(
                etype="event",
                sender="User",
                payload=payload,
                topic="session",
                session_id=session_id,
                call_id=self.call_connection_id,
            )
            _background_task(
                send_session_envelope(
                    self.websocket,
                    envelope,
                    session_id=session_id,
                    conn_id=None,
                    event_label="voicelive_user_transcript_delta",
                    broadcast_only=True,
                ),
                label="voicelive_user_transcript_delta",
            )

        elif etype == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            if self._llm_first_token_time is None:
                self._llm_first_token_time = time.perf_counter()

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            logger.debug(
                "[VoiceLiveSDK] Audio stream marked done | session=%s response=%s",
                self.session_id,
                getattr(event, "response_id", "unknown"),
            )
            response_id = getattr(event, "response_id", None)
            if response_id:
                self._active_response_ids.discard(response_id)
                await self._emit_audio_frame_to_ui(
                    response_id,
                    data_b64=None,
                    frame_index=self._final_frame_index(response_id),
                    is_final=True,
                )
            else:
                await self._emit_audio_frame_to_ui(
                    None, data_b64=None, frame_index=self._final_frame_index(None), is_final=True
                )
        elif etype == ServerEventType.ERROR:
            await self._handle_server_error(event)
            self._mark_audio_playback(False)

        elif etype == ServerEventType.CONVERSATION_ITEM_CREATED:
            logger.debug("Conversation item created: %s", event.item.id)

    async def _send_audio_delta(self, audio_bytes: bytes, *, response_id: str | None) -> None:
        pcm_bytes = self._to_pcm_bytes(audio_bytes)
        if not pcm_bytes:
            return

        # Resample VoiceLive 24 kHz PCM to match ACS expectations.
        resampled = self._resample_audio(pcm_bytes)
        frame_index = self._allocate_frame_index(response_id)
        try:
            logger.debug(
                "[VoiceLiveSDK] Sending audio delta | session=%s bytes=%s",
                self.session_id,
                len(pcm_bytes),
            )
            self._mark_audio_playback(True)
            if self._transport == "acs":
                message = {
                    "kind": "AudioData",
                    "AudioData": {"data": resampled},
                    "StopAudio": None,
                }
                await self.websocket.send_json(message)
            await self._emit_audio_frame_to_ui(
                response_id,
                data_b64=resampled,
                frame_index=frame_index,
                is_final=False,
            )
        except Exception:
            logger.debug("Failed to relay audio delta", exc_info=True)

    async def _emit_audio_frame_to_ui(
        self,
        response_id: str | None,
        *,
        data_b64: str | None,
        frame_index: int,
        is_final: bool,
    ) -> None:
        if not self._websocket_open:
            return
        if is_final:
            self._mark_audio_playback(False)
        payload = {
            "type": "audio_data",
            "frame_index": frame_index,
            "total_frames": None,
            "sample_rate": self._acs_sample_rate,
            "is_final": is_final,
            "response_id": response_id,
        }
        if data_b64:
            payload["data"] = data_b64
        try:
            await self.websocket.send_json(payload)
        except Exception:
            logger.debug("Failed to emit UI audio frame", exc_info=True)

    def _allocate_frame_index(self, response_id: str | None) -> int:
        if response_id:
            current = self._response_audio_frames.get(response_id, 0)
            self._response_audio_frames[response_id] = current + 1
            return current
        current = self._fallback_audio_frame_index
        self._fallback_audio_frame_index += 1
        return current

    def _final_frame_index(self, response_id: str | None) -> int:
        if response_id and response_id in self._response_audio_frames:
            next_idx = self._response_audio_frames.pop(response_id)
            return max(next_idx - 1, 0)
        if not response_id:
            final_idx = max(self._fallback_audio_frame_index - 1, 0)
            self._fallback_audio_frame_index = 0
            return final_idx
        return 0

    async def _send_stop_audio(self) -> None:
        self._mark_audio_playback(False, reset_cancel=False)
        if self._transport != "acs":
            self._stop_audio_pending = False
            return
        if self._stop_audio_pending:
            return
        stop_message = {"kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        try:
            await self.websocket.send_json(stop_message)
            self._stop_audio_pending = True
        except Exception:
            self._stop_audio_pending = False
            logger.debug("Failed to send StopAudio", exc_info=True)

    async def _send_error(self, event: Any) -> None:
        error_info: dict[str, Any] = {
            "kind": "ErrorData",
            "errorData": {
                "code": getattr(event.error, "code", "VoiceLiveError"),
                "message": getattr(event.error, "message", "Unknown VoiceLive error"),
            },
        }
        try:
            await self.websocket.send_json(error_info)
        except Exception:
            logger.debug("Failed to send error message", exc_info=True)

    async def _handle_server_error(self, event: Any) -> None:
        error_obj = getattr(event, "error", None)
        code = getattr(error_obj, "code", "VoiceLiveError")
        message = getattr(error_obj, "message", "Unknown VoiceLive error")
        details = getattr(error_obj, "details", None)

        logger.error(
            "[VoiceLiveSDK] Server error received | session=%s call=%s code=%s message=%s",
            self.session_id,
            self.call_connection_id,
            code,
            message,
        )
        if details:
            logger.error(
                "[VoiceLiveSDK] Error details | session=%s call=%s details=%s",
                self.session_id,
                self.call_connection_id,
                details,
            )

        await self._send_stop_audio()
        await self._send_error(event)

    async def _handle_dtmf_tone(self, raw_tone: Any) -> None:
        normalized = self._normalize_dtmf_tone(raw_tone)
        if not normalized:
            logger.debug("Ignoring invalid DTMF tone %s | session=%s", raw_tone, self.session_id)
            return

        if normalized == "#":
            self._cancel_dtmf_flush_timer()
            await self._flush_dtmf_buffer(reason="terminator")
            return
        if normalized == "*":
            await self._clear_dtmf_buffer()
            return

        async with self._dtmf_lock:
            self._dtmf_digits.append(normalized)
            buffer_len = len(self._dtmf_digits)
        logger.info(
            "Received DTMF tone %s (buffer_len=%s) | session=%s",
            normalized,
            buffer_len,
            self.session_id,
        )
        self._schedule_dtmf_flush()

    def _schedule_dtmf_flush(self) -> None:
        self._cancel_dtmf_flush_timer()
        self._dtmf_flush_task = asyncio.create_task(self._delayed_dtmf_flush())

    def _cancel_dtmf_flush_timer(self) -> None:
        if self._dtmf_flush_task:
            self._dtmf_flush_task.cancel()
            self._dtmf_flush_task = None

    async def _delayed_dtmf_flush(self) -> None:
        try:
            await asyncio.sleep(self._dtmf_flush_delay)
            await self._flush_dtmf_buffer(reason="timeout")
        except asyncio.CancelledError:
            return
        finally:
            self._dtmf_flush_task = None

    async def _flush_dtmf_buffer(self, *, reason: str) -> None:
        async with self._dtmf_lock:
            if not self._dtmf_digits:
                return
            sequence = "".join(self._dtmf_digits)
            self._dtmf_digits.clear()
        await self._send_dtmf_user_message(sequence, reason=reason)

    async def _clear_dtmf_buffer(self) -> None:
        self._cancel_dtmf_flush_timer()
        async with self._dtmf_lock:
            if self._dtmf_digits:
                logger.info(
                    "Clearing DTMF buffer without forwarding (buffer_len=%s) | session=%s",
                    len(self._dtmf_digits),
                    self.session_id,
                )
            self._dtmf_digits.clear()

    async def send_text_message(self, text: str) -> None:
        """Send a text message from the user to the VoiceLive conversation.

        With Azure Semantic VAD enabled, text messages are sent via conversation.item.create
        using UserMessageItem with InputTextContentPart, not through audio buffer.

        Implements barge-in: triggers interruption if agent is currently speaking.
        """
        if not text or not self._connection:
            return

        try:
            # BARGE-IN: trigger interruption if TTS is currently active
            is_playing = self._get_metadata("tts_active", False)
            if is_playing:
                self._trigger_barge_in(
                    trigger="user_text_input",
                    stage="text_message_send",
                    reset_audio_state=True,
                )
                # Actively send StopAudio to ACS so playback halts immediately
                try:
                    await self._send_stop_audio()
                except Exception:
                    logger.debug("Failed to send StopAudio during text barge-in", exc_info=True)

                logger.info(
                    "Text barge-in triggered (agent was speaking) | session=%s",
                    self.session_id,
                )

            # Create a text content part
            text_part = InputTextContentPart(text=text)

            # Wrap it as a user message item
            user_message = UserMessageItem(content=[text_part])

            # Send conversation.item.create
            await self._connection.send(ClientEventConversationItemCreate(item=user_message))

            # Ask for a model response considering all history (audio + text)
            await self._connection.send(ClientEventResponseCreate())

            logger.info(
                "Forwarded user text message (%s chars) | session=%s",
                len(text),
                self.session_id,
            )
        except Exception:
            logger.exception(
                "Failed to forward user text to VoiceLive | session=%s",
                self.session_id,
            )

    async def _send_dtmf_user_message(self, digits: str, *, reason: str) -> None:
        if not digits or not self._connection:
            return
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": digits}],
        }
        try:
            await self._connection.conversation.item.create(item=item)
            await self._connection.response.create()
            logger.info(
                "Forwarded DTMF sequence (%s digits) via %s | session=%s",
                len(digits),
                reason,
                self.session_id,
            )
        except Exception:
            logger.exception(
                "Failed to forward DTMF digits to VoiceLive | session=%s", self.session_id
            )

    @staticmethod
    def _normalize_dtmf_tone(raw_tone: Any) -> str | None:
        if raw_tone is None:
            return None
        tone = str(raw_tone).strip().lower()
        tone_map = {
            "0": "0",
            "zero": "0",
            "1": "1",
            "one": "1",
            "2": "2",
            "two": "2",
            "3": "3",
            "three": "3",
            "4": "4",
            "four": "4",
            "5": "5",
            "five": "5",
            "6": "6",
            "six": "6",
            "7": "7",
            "seven": "7",
            "8": "8",
            "eight": "8",
            "9": "9",
            "nine": "9",
            "*": "*",
            "star": "*",
            "asterisk": "*",
            "#": "#",
            "pound": "#",
            "hash": "#",
        }
        return tone_map.get(tone)

    def _to_pcm_bytes(self, audio_payload: Any) -> bytes | None:
        if isinstance(audio_payload, bytes):
            return audio_payload
        if isinstance(audio_payload, str):
            try:
                return base64.b64decode(audio_payload)
            except Exception:
                logger.debug("Failed to decode base64 audio payload", exc_info=True)
        return None

    # High-frequency events to skip tracing (would create excessive noise)
    _NOISY_EVENT_TYPES = {
        # Audio streaming events (very high frequency)
        "response.audio.delta",
        "response.audio_transcript.delta",
        "input_audio_buffer.speech_started",
        "input_audio_buffer.speech_stopped",
        "input_audio_buffer.committed",
        "input_audio_buffer.cleared",
        # Function call streaming (many small deltas per call)
        "response.function_call_arguments.delta",
        # Conversation deltas
        "response.text.delta",
        "response.content_part.delta",
    }

    def _observe_event(self, event: Any) -> None:
        type_value = getattr(event, "type", "unknown")
        type_str = type_value.value if isinstance(type_value, ServerEventType) else str(type_value)

        # Skip creating spans for high-frequency noisy events
        # These would create thousands of spans per conversation and make traces unusable
        if type_str in self._NOISY_EVENT_TYPES:
            return

        logger.debug(
            "[VoiceLiveSDK] Event received | session=%s type=%s",
            self.session_id,
            type_str,
        )

        attributes = {
            "voicelive.event.type": type_str,
            "voicelive.session_id": self.session_id,
            "call.connection.id": self.call_connection_id,
        }
        if hasattr(event, "transcript") and event.transcript:
            transcript = event.transcript
            attributes["voicelive.transcript.length"] = len(transcript)
        if hasattr(event, "delta") and event.delta:
            delta = event.delta
            attributes["voicelive.delta.size"] = (
                len(delta) if isinstance(delta, (bytes, str)) else 0
            )

        # Create span with descriptive name: voicelive.event.<event_type>
        # e.g., voicelive.event.session.created, voicelive.event.response.done
        span_name = f"voicelive.event.{type_str}" if type_str != "unknown" else "voicelive.event"

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ):
            pass

    async def _commit_input_buffer(self) -> None:
        if not self._connection:
            return
        try:
            await self._connection.input_audio_buffer.commit()
            logger.debug(
                "[VoiceLiveSDK] Committed input audio buffer | session=%s",
                self.session_id,
            )
        except Exception:
            logger.warning(
                "[VoiceLiveSDK] Failed to commit input audio buffer | session=%s",
                self.session_id,
                exc_info=True,
            )

    def _resample_audio(self, audio_bytes: bytes) -> str:
        try:
            source = np.frombuffer(audio_bytes, dtype=np.int16)
            source_rate = 24000
            target_rate = max(self._acs_sample_rate, 1)
            if source_rate == target_rate:
                return base64.b64encode(audio_bytes).decode("utf-8")

            ratio = target_rate / source_rate
            new_len = max(int(len(source) * ratio), 1)
            new_idx = np.linspace(0, len(source) - 1, new_len)
            resampled = np.interp(new_idx, np.arange(len(source)), source.astype(np.float32))
            resampled_int16 = resampled.astype(np.int16).tobytes()
            return base64.b64encode(resampled_int16).decode("utf-8")
        except Exception:
            logger.debug("Audio resample failed; returning original", exc_info=True)
            return base64.b64encode(audio_bytes).decode("utf-8")

    @property
    def _websocket_open(self) -> bool:
        return (
            hasattr(self.websocket, "application_state")
            and hasattr(self.websocket, "client_state")
            and self.websocket.application_state == WebSocketState.CONNECTED
            and self.websocket.client_state == WebSocketState.CONNECTED
        )

    @staticmethod
    def _extract_item_id(event: Any) -> str | None:
        for attr in (
            "item_id",
            "conversation_item_id",
            "input_audio_item_id",
            "id",
        ):
            value = getattr(event, attr, None)
            if value:
                return value
        item = getattr(event, "item", None)
        if item and hasattr(item, "id"):
            return item.id
        return None

    @staticmethod
    def _extract_response_id(event: Any) -> str | None:
        response = getattr(event, "response", None)
        if response and hasattr(response, "id"):
            return response.id
        return None

    async def _emit_agent_inventory(
        self,
        *,
        agents: dict[str, Any],
        start_agent: str | None,
        source: str,
        scenario: str | None,
        handoff_map: dict[str, Any],
    ) -> None:
        """Broadcast a lightweight agent snapshot for dashboard/debug UIs."""
        app_state = getattr(self.websocket, "app", None)
        if app_state and hasattr(app_state, "state"):
            app_state = app_state.state

        if not app_state or not hasattr(app_state, "conn_manager"):
            logger.debug("Skipping agent inventory broadcast (no app_state/conn_manager)")
            return

        try:
            summaries = build_agent_summaries(agents)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to build agent summaries", exc_info=True)
            summaries = [
                {"name": name, "description": getattr(agent, "description", "")}
                for name, agent in (agents or {}).items()
            ]

        payload = {
            "type": "agent_inventory",
            "event_type": "agent_inventory",
            "source": source,
            "scenario": scenario,
            "start_agent": start_agent,
            "agent_count": len(summaries),
            "agents": summaries,
            "handoff_map": handoff_map or {},
        }

        envelope = make_envelope(
            etype="event",
            sender="System",
            payload=payload,
            topic="dashboard",
            session_id=self.session_id,
            call_id=self.call_connection_id,
        )

        try:
            await broadcast_session_envelope(
                app_state,
                envelope,
                session_id=self.session_id,
                event_label="agent_inventory",
            )
            logger.debug(
                "Agent inventory emitted",
                extra={
                    "session_id": self.session_id,
                    "agent_count": len(summaries),
                    "scenario": scenario,
                    "source": source,
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to emit agent inventory snapshot", exc_info=True)

    def _should_stop_for_response(self, event: Any) -> bool:
        response = getattr(event, "response", None)
        if not response:
            return bool(self._active_response_ids)

        status = getattr(response, "status", None)
        if isinstance(status, ResponseStatus):
            return status != ResponseStatus.IN_PROGRESS
        if isinstance(status, str):
            return status.lower() != ResponseStatus.IN_PROGRESS.value
        return True

    @staticmethod
    def _build_credential(settings) -> AzureKeyCredential | TokenCredential:
        if settings.has_api_key_auth:
            return AzureKeyCredential(settings.azure_voicelive_api_key)
        return DefaultAzureCredential()

    # =========================================================================
    # Turn-Level Latency Tracking Methods
    # =========================================================================

    def record_llm_first_token(self) -> None:
        """Record LLM first token timing (TTFT) for the current turn."""
        if self._turn_start_time and self._llm_first_token_time is None:
            self._llm_first_token_time = time.perf_counter()
            ttft_ms = (self._llm_first_token_time - self._turn_start_time) * 1000

            # Record OTel metric for App Insights Performance view
            record_llm_ttft(
                ttft_ms,
                session_id=self.session_id,
                turn_number=self._turn_number,
                agent_name=self._messenger._active_agent_name or "unknown",
            )

            # Emit TTFT metric as a span for App Insights Performance tab
            with tracer.start_as_current_span(
                "voicelive.llm.ttft",
                kind=SpanKind.INTERNAL,
                attributes={
                    SpanAttr.TURN_NUMBER.value: self._turn_number,
                    SpanAttr.TURN_LLM_TTFB_MS.value: ttft_ms,
                    SpanAttr.SESSION_ID.value: self.session_id,
                    SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id,
                },
            ) as ttft_span:
                ttft_span.add_event("llm.first_token", {"ttft_ms": ttft_ms})
                logger.info(
                    "[VoiceLive] LLM TTFT | session=%s turn=%d ttft_ms=%.2f",
                    self.session_id,
                    self._turn_number,
                    ttft_ms,
                )

    async def _finalize_turn_metrics(self) -> None:
        """Finalize and emit turn-level metrics when a turn completes."""
        if not self._turn_start_time:
            return

        turn_end_time = time.perf_counter()
        total_turn_duration_ms = (turn_end_time - self._turn_start_time) * 1000

        # Calculate individual latencies relative to VAD End (User Finished Speaking)
        stt_latency_ms = None
        llm_ttft_ms = None
        tts_ttfb_ms = None

        # Base reference for system latency is VAD End
        latency_base = self._vad_end_time or self._turn_start_time

        if self._transcript_final_time and self._vad_end_time:
            stt_latency_ms = (self._transcript_final_time - self._vad_end_time) * 1000

        if self._llm_first_token_time and self._transcript_final_time:
            # Processing time: Transcript Final -> LLM First Token
            llm_ttft_ms = (self._llm_first_token_time - self._transcript_final_time) * 1000
        elif self._llm_first_token_time and latency_base:
            # Fallback: VAD End -> LLM First Token
            llm_ttft_ms = (self._llm_first_token_time - latency_base) * 1000

        if self._tts_first_audio_time and latency_base:
            # End-to-End Latency: VAD End -> TTS First Audio
            tts_ttfb_ms = (self._tts_first_audio_time - latency_base) * 1000

        # Record OTel metrics for App Insights Performance view
        if stt_latency_ms is not None:
            record_stt_latency(
                stt_latency_ms,
                session_id=self.session_id,
                turn_number=self._turn_number,
            )

        # Record turn completion metric (aggregates duration + count)
        record_turn_complete(
            total_turn_duration_ms,
            session_id=self.session_id,
            turn_number=self._turn_number,
            stt_latency_ms=stt_latency_ms,
            llm_ttft_ms=llm_ttft_ms,
            tts_ttfb_ms=tts_ttfb_ms,
            agent_name=self._messenger._active_agent_name or "unknown",
        )

        # Emit comprehensive turn metrics span
        with tracer.start_as_current_span(
            f"voicelive.turn.{self._turn_number}.complete",
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttr.TURN_NUMBER.value: self._turn_number,
                SpanAttr.TURN_TOTAL_LATENCY_MS.value: total_turn_duration_ms,  # Renamed concept, kept key
                SpanAttr.SESSION_ID.value: self.session_id,
                SpanAttr.CALL_CONNECTION_ID.value: self.call_connection_id,
                SpanAttr.TURN_TRANSPORT_TYPE.value: self._transport,
                "latency.reference": "vad_end" if self._vad_end_time else "turn_start",
            },
        ) as turn_span:
            if stt_latency_ms is not None:
                turn_span.set_attribute("turn.stt_latency_ms", stt_latency_ms)
            if llm_ttft_ms is not None:
                turn_span.set_attribute(SpanAttr.TURN_LLM_TTFB_MS.value, llm_ttft_ms)
            if tts_ttfb_ms is not None:
                turn_span.set_attribute(SpanAttr.TURN_TTS_TTFB_MS.value, tts_ttfb_ms)

            turn_span.add_event(
                "turn.complete",
                {
                    "turn.number": self._turn_number,
                    "turn.duration_ms": total_turn_duration_ms,
                    **({"stt_latency_ms": stt_latency_ms} if stt_latency_ms else {}),
                    **({"llm_ttft_ms": llm_ttft_ms} if llm_ttft_ms else {}),
                    **({"tts_ttfb_ms": tts_ttfb_ms} if tts_ttfb_ms else {}),
                },
            )

            logger.info(
                "[VoiceLive] Turn %d metrics | E2E: %s | STT: %s | LLM: %s | Duration: %.2f",
                self._turn_number,
                f"{tts_ttfb_ms:.0f}ms" if tts_ttfb_ms else "N/A",
                f"{stt_latency_ms:.0f}ms" if stt_latency_ms else "N/A",
                f"{llm_ttft_ms:.0f}ms" if llm_ttft_ms else "N/A",
                total_turn_duration_ms,
            )

        # Send turn metrics to frontend via WebSocket
        try:
            metrics_envelope = make_envelope(
                etype="turn_metrics",
                sender=self._messenger._active_agent_name or "System",
                session_id=self.session_id,
                payload={
                    "turn_number": self._turn_number,
                    "duration_ms": round(total_turn_duration_ms, 1),
                    "stt_latency_ms": round(stt_latency_ms, 1) if stt_latency_ms else None,
                    "llm_ttft_ms": round(llm_ttft_ms, 1) if llm_ttft_ms else None,
                    "tts_ttfb_ms": round(tts_ttfb_ms, 1) if tts_ttfb_ms else None,
                    "agent_name": self._messenger._active_agent_name,
                },
            )
            await send_session_envelope(
                self.websocket,
                metrics_envelope,
                session_id=self.session_id,
                event_label="turn_metrics",
            )
        except Exception as e:
            logger.debug("Failed to send turn metrics to frontend: %s", e)

        # Reset turn tracking state
        self._turn_start_time = None
        self._vad_end_time = None
        self._transcript_final_time = None
        self._llm_first_token_time = None
        self._tts_first_audio_time = None
        self._current_response_id = None


__all__ = ["VoiceLiveSDKHandler"]
