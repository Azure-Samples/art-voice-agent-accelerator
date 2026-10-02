"""VoiceLive SDK handler bridging ACS media streams to multi-agent orchestration."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from apps.artagent.backend.registries.agentstore.base import (
    MAI_TRANSCRIPTION_MODELS,
    MAI_VOICELIVE_API_VERSION,
    byom_profile_model_conflict,
    is_managed_voicelive_model,
    validate_voicelive_transcription,
)

# Import agents loader for dynamic handoff_map building
from apps.artagent.backend.registries.agentstore.loader import (
    build_agent_summaries,
    discover_agents,
)
from apps.artagent.backend.src.orchestration.naming import find_agent_by_name
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
from apps.artagent.backend.src.services.session_loader import load_user_profile_by_email
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
    build_effective_registry,
    resolve_orchestrator_config,
)
from apps.artagent.backend.voice.shared.close import cancel_and_join, finish_persistence
from apps.artagent.backend.voice.shared.errors import (
    VoiceErrorInfo,
    classify_voice_error,
    classify_voicelive_server_error,
    emit_voice_error,
)
from apps.artagent.backend.voice.voicelive import session as voicelive_session

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
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from utils.azure_auth import (
    AsyncSubscriptionPinnedAzureCliCredential,
    _is_local_dev,
    _using_managed_identity,
    get_local_cli_credential_options,
)
from utils.ml_logging import get_logger
from utils.telemetry_decorators import ConversationTurnSpan

from .dtmf_processor import DTMFProcessor
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

# Azure Identity credentials are reusable across connections.
_CACHED_CREDENTIAL: Any | None = None
_CREDENTIAL_LOCK = asyncio.Lock()

_DTMF_FLUSH_DELAY_SECONDS = 1.5
_VOICELIVE_WARMUP_WAIT_SECONDS = 0.75

# Models that managed Voice Live (BYOM OFF) can actually serve are defined once in
# agentstore.base (MANAGED_VOICELIVE_MODELS / is_managed_voicelive_model) so the
# save-time guard (agent_builder) and this connect-time check can never diverge.
# Connecting with a model outside that set succeeds at the WebSocket level but the
# model never produces a response — the agent "stops responding" and the session
# ends in a ~900s idle timeout. We only WARN (never block) here because the managed
# catalog grows over time; a warning makes the misconfiguration obvious in the logs
# without breaking a newly-added-but-unlisted model.


@dataclass
class VoiceLivePreparedConnection:
    """Prepared VoiceLive connection that can be adopted by a real media handler."""

    connection: Any
    connection_cm: Any
    credential: AzureKeyCredential | TokenCredential
    settings: Any
    model: str
    byom_query: dict[str, str] | None = None
    session_prepared: bool = False
    created_at: float = field(default_factory=time.perf_counter)
    claimed: bool = False
    api_version: str | None = None
    _close_task: asyncio.Task | None = field(default=None, init=False, repr=False)

    def matches(
        self, model: str, byom_query: dict[str, str] | None, *, api_version: str | None = None
    ) -> bool:
        return (
            self.model == model
            and (self.byom_query or None) == (byom_query or None)
            and self.api_version == api_version
        )

    def claim(self) -> None:
        if self._close_task is not None:
            raise RuntimeError("Cannot claim a closing prepared VoiceLive connection")
        self.claimed = True

    async def close(self) -> None:
        if self.claimed:
            return
        if self._close_task is None:
            self._close_task = asyncio.create_task(
                self.connection_cm.__aexit__(None, None, None), name="voicelive-prepared-close"
            )
        await asyncio.shield(self._close_task)


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


# Type alias for background task function (used by _SessionMessenger)
BackgroundTaskFn = Callable[[Awaitable[Any], str], asyncio.Task]


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

    def __init__(
        self,
        websocket: WebSocket,
        *,
        background_task_fn: BackgroundTaskFn,
        is_acs: bool = True,
    ) -> None:
        self._ws = websocket
        self._background_task_fn = background_task_fn
        self._is_acs = is_acs
        self._default_sender: str | None = None
        self._missing_session_warned = False
        self._active_turn_id: str | None = None
        self._active_segment_id: str | None = None
        self._pending_user_turn_id: str | None = None
        self._active_agent_name: str | None = None
        self._active_agent_label: str | None = None
        self._last_announced_agent: str | None = None
        self._last_session_contract: dict[str, Any] | None = None
        self._turn_sequence: int = 0  # Track tool call boundaries within a turn
        self._base_turn_id: str | None = None  # Original turn_id before tool calls
        # Deduplication: track (turn_id, text_hash) of sent final messages
        self._sent_messages: set[tuple[str, int]] = set()
        self._user_transcript_text = ""
        self._user_transcript_sequence = 0
        self._assistant_segments: dict[str, str] = {}
        self._assistant_segment_order: list[str] = []
        self._assistant_sequence = 0

    def _ensure_turn_id(self, candidate: str | None, *, allow_generate: bool = True) -> str | None:
        # A VoiceLive response_id is not a user-turn ID. Once speech_started has
        # established the canonical item_id, preserve it across every response
        # and tool phase belonging to that utterance.
        if self._active_turn_id:
            return self._active_turn_id
        if candidate:
            self._active_turn_id = candidate
            self._active_segment_id = candidate
            return candidate
        if not allow_generate:
            return None
        generated = uuid.uuid4().hex
        self._active_turn_id = generated
        self._active_segment_id = generated
        return generated

    def _release_turn(self, turn_id: str | None) -> None:
        if turn_id and self._active_turn_id == turn_id:
            self._active_turn_id = None
            self._active_segment_id = None
        elif turn_id is None:
            self._active_turn_id = None
            self._active_segment_id = None

    def advance_turn_for_tool(self) -> str | None:
        """
        Advance the turn_id after a tool call to create a new message segment.

        This ensures post-tool assistant responses appear as new messages
        rather than overwriting pre-tool content in the UI.

        Returns:
            The new turn_id to use for post-tool responses, or None if no turn active.
        """
        if not self._active_turn_id:
            return None

        # Store the canonical turn ID as base if not already set.
        if not self._base_turn_id:
            self._base_turn_id = self._active_turn_id

        # Advance only the response segment. The canonical turn ID never changes,
        # so the UI keeps one assistant response bubble for the whole turn.
        self._turn_sequence += 1
        new_turn_id = f"{self._base_turn_id}_s{self._turn_sequence}"
        self._active_segment_id = new_turn_id

        logger.debug(
            "[TurnAdvance] Advanced turn_id: base=%s, seq=%d, new=%s",
            self._base_turn_id,
            self._turn_sequence,
            new_turn_id,
        )
        return new_turn_id

    def reset_turn_sequence(self) -> None:
        """Reset turn sequence tracking for a new user turn."""
        self._turn_sequence = 0
        self._base_turn_id = self._active_turn_id
        self._active_segment_id = self._active_turn_id
        # Clear sent message deduplication cache for new turn
        self._sent_messages.clear()
        self._user_transcript_text = ""
        self._user_transcript_sequence = 0
        self._assistant_segments.clear()
        self._assistant_segment_order.clear()
        self._assistant_sequence = 0

    def begin_user_turn(self, turn_id: str | None) -> str | None:
        """Initialise a user turn and emit a placeholder streaming message."""
        if not turn_id:
            self._pending_user_turn_id = None
            return None
        if self._pending_user_turn_id == turn_id:
            return turn_id
        self._pending_user_turn_id = turn_id
        self._active_turn_id = turn_id
        # Reset turn sequence for new user turn - post-tool segments start fresh
        self.reset_turn_sequence()
        if not self._can_emit():
            return turn_id

        payload: dict[str, Any] = {
            "type": "user",
            "message": "",
            "content": "",
            "streaming": True,
            "streaming_type": "stt_partial",
            "content_mode": "snapshot",
            "sequence": 0,
            "is_final": False,
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

        self._background_task_fn(
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
        if self._pending_user_turn_id:
            return self._pending_user_turn_id
        if candidate:
            self._pending_user_turn_id = candidate
            if not self._active_turn_id:
                self._active_turn_id = candidate
                self._active_segment_id = candidate
            return candidate
        return self._active_turn_id

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
        if self._can_emit() and agent_name and previous_agent:
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
            self._background_task_fn(
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
            self._last_announced_agent = agent_name
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

    async def send_user_partial(
        self,
        text_delta: str,
        *,
        turn_id: str | None = None,
        language: str | None = None,
    ) -> None:
        """Emit a cumulative VoiceLive input-transcription snapshot."""
        if not text_delta or not self._can_emit():
            return

        resolved_turn = self.resolve_user_turn_id(turn_id) or self._ensure_turn_id(None)
        if not resolved_turn:
            return

        self._user_transcript_text += text_delta
        self._user_transcript_sequence += 1
        payload: dict[str, Any] = {
            "type": "user",
            "message": self._user_transcript_text,
            "content": self._user_transcript_text,
            "streaming": True,
            "streaming_type": "stt_partial",
            "content_mode": "snapshot",
            "sequence": self._user_transcript_sequence,
            "is_final": False,
            "turn_id": resolved_turn,
            "response_id": resolved_turn,
            "status": "streaming",
            "source": "voicelive",
        }
        if language:
            payload["language"] = language

        envelope = make_envelope(
            etype="event",
            sender="User",
            payload=payload,
            topic="session",
            session_id=self._session_id,
            call_id=self._call_id,
        )
        self._background_task_fn(
            send_session_envelope(
                self._ws,
                envelope,
                session_id=self._session_id,
                conn_id=None,
                event_label="voicelive_user_transcript_partial",
                broadcast_only=True,
            ),
            label="user_transcript_partial",
        )

    async def send_user_message(self, text: str, *, turn_id: str | None = None) -> None:
        """Forward a user transcript to all session listeners."""
        if not text or not self._can_emit():
            return

        resolved_turn = self.resolve_user_turn_id(turn_id) or self._ensure_turn_id(None)
        if not resolved_turn:
            return
        self._user_transcript_text = text
        self._user_transcript_sequence += 1

        self._background_task_fn(
            send_user_transcript(
                self._ws,
                text,
                session_id=self._session_id,
                conn_id=None,
                broadcast_only=True,
                turn_id=resolved_turn,
                active_agent=self._active_agent_name,
                active_agent_label=self._active_agent_label,
                sequence=self._user_transcript_sequence,
            ),
            label="send_user_transcript",
        )

    def _current_segment_id(self) -> str:
        return self._active_segment_id or self._active_turn_id or "response"

    def _set_assistant_segment(self, segment_id: str, text: str, *, append: bool) -> str:
        if segment_id not in self._assistant_segments:
            self._assistant_segment_order.append(segment_id)
            self._assistant_segments[segment_id] = ""
        if append:
            self._assistant_segments[segment_id] += text
        else:
            self._assistant_segments[segment_id] = text
        return "\n\n".join(
            self._assistant_segments[key]
            for key in self._assistant_segment_order
            if self._assistant_segments[key]
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

        segment_id = self._current_segment_id()
        message_text = self._set_assistant_segment(segment_id, text or "", append=False)

        # Deduplication: prevent sending the same message twice for the same turn_id
        # This can happen when TRANSCRIPT_DONE fires multiple times or events race
        msg_key = (turn_id, hash(message_text))
        if msg_key in self._sent_messages:
            logger.debug(
                "[Dedup] Skipping duplicate message | turn_id=%s text_len=%d",
                turn_id,
                len(message_text),
            )
            return
        self._sent_messages.add(msg_key)

        sender_name = self._resolve_sender(sender)
        payload = {
            "type": "assistant",
            "message": message_text,
            "content": message_text,
            "streaming": False,
            "turn_id": turn_id,
            "segment_id": segment_id,
            "response_id": response_id or turn_id,
            "content_mode": "final_turn",
            "sequence": self._assistant_sequence + 1,
            "is_final": True,
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

        self._background_task_fn(
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
        self._assistant_sequence += 1
        # NOTE: Do NOT call _release_turn() here. The turn_id must remain active
        # until advance_turn_for_tool() can use it. The turn will be naturally
        # reset when begin_user_turn() is called for the next user turn.

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

        segment_id = self._current_segment_id()
        message_text = self._set_assistant_segment(segment_id, text, append=True)
        self._assistant_sequence += 1

        sender_name = self._resolve_sender(sender)
        envelope = make_assistant_streaming_envelope(
            message_text,
            sender=sender_name,
            session_id=self._session_id,
            call_id=self._call_id,
        )
        if self._active_agent_name:
            envelope["sender"] = self._active_agent_name

        payload = envelope.setdefault("payload", {})
        payload.setdefault("message", message_text)
        payload["turn_id"] = turn_id
        payload["segment_id"] = segment_id
        payload["response_id"] = response_id or turn_id
        payload["content_mode"] = "snapshot"
        payload["sequence"] = self._assistant_sequence
        payload["is_final"] = False
        payload["status"] = "streaming"
        payload["active_agent"] = self._active_agent_name
        payload["active_agent_label"] = self._active_agent_label
        payload["sender"] = self._active_agent_name
        self._background_task_fn(
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
            "segment_id": self._current_segment_id(),
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

        self._background_task_fn(
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
        contract: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast session configuration updates to the UI.

        Keyword Args:
            agent_name: The agent the session is currently running as.
            session_obj: The ``session.updated`` echo from the service.
            transport: Transport label (``acs``, ``browser``...).
            contract: Result of ``LiveOrchestrator._verify_session_contract()``,
                i.e. the requested-vs-applied comparison for voice and model
                plus the local agent/model divergences. Attached verbatim so the
                UI can show what was asked for next to what is actually running
                without re-deriving (or string-comparing) anything.
        """
        if not self._can_emit():
            return
        announce_agent = agent_name != self._last_announced_agent
        serialized_contract = _safe_primitive(contract) if contract else None
        if not announce_agent and (
            serialized_contract is None or serialized_contract == self._last_session_contract
        ):
            return

        payload: dict[str, Any] = {
            "event_type": "session_updated",
            "announce_agent": announce_agent,
            "agent_label": _resolve_agent_label(agent_name),
            "agent_name": agent_name,
            "transport": transport,
            "session": _serialize_session_config(session_obj),
        }

        if serialized_contract:
            payload["contract"] = serialized_contract

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

        self._background_task_fn(
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
        self._last_announced_agent = agent_name
        self._last_session_contract = serialized_contract

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

        self._background_task_fn(
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
            self._background_task_fn(
                push_tool_start(
                    self._ws,
                    name,  # tool_name
                    call_id,  # call_id
                    args,  # arguments
                    is_acs=self._is_acs,
                    session_id=self._session_id,
                    turn_id=self._active_turn_id,
                    segment_id=self._current_segment_id(),
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

            self._background_task_fn(
                push_tool_end(
                    self._ws,
                    name,  # tool_name
                    call_id,  # call_id
                    tool_result,  # result (status is derived from this)
                    is_acs=self._is_acs,
                    session_id=self._session_id,
                    duration_ms=elapsed_ms,
                    turn_id=self._active_turn_id,
                    segment_id=self._current_segment_id(),
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
        prepared_connection: VoiceLivePreparedConnection | None = None,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.call_connection_id = call_connection_id or session_id

        # Track pending background tasks at instance level to avoid memory leaks
        self._pending_background_tasks: set[asyncio.Task] = set()
        self._warmup_cleanup_tasks: set[asyncio.Task] = set()

        # Pass background task function to messenger for tracked task creation
        self._messenger = _SessionMessenger(
            websocket,
            background_task_fn=self._background_task,
            is_acs=transport == "acs",
        )
        self._transport: VoiceLiveTransport = transport
        self._manual_commit_enabled = transport == "acs"
        self._user_email = user_email

        self._settings = None
        self._credential: AzureKeyCredential | TokenCredential | None = None
        self._connection = None
        self._connection_cm = None
        self._prepared_connection = prepared_connection
        self._orchestrator: LiveOrchestrator | None = None
        # Generative model actually bound to the VoiceLive connection (resolved from the
        # start agent's voicelive_model at connect time; falls back to the global setting).
        self._active_model_name: str | None = None
        # Where the bound model came from: "agent_override" or "settings_default".
        self._active_model_source: str | None = None
        # Start agent resolved at connect time, retained for error attribution.
        self._active_start_agent: str | None = None
        # Classified startup failure, retained so the endpoint can close the
        # WebSocket with a meaningful reason instead of a bare disconnect.
        self._startup_error: VoiceErrorInfo | None = None
        self._event_task: asyncio.Task | None = None
        self._running = False
        # Resource presence drives partial-start cleanup; the retained task below
        # gives every stop caller the same completion, rather than a boolean no-op.
        self._stopping = False
        self._shutdown_task: asyncio.Task | None = None
        self._startup_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._acs_sample_rate = 16000
        self._active_response_ids: set[str] = set()
        self._stop_audio_pending = False
        self._response_audio_frames: dict[str, int] = {}
        self._fallback_audio_frame_index = 0
        # Responses cancelled by barge-in: their trailing audio deltas are
        # dropped so no AudioData reaches the transport after a StopAudio.
        self._cancelled_response_ids: set[str] = set()
        # DTMFProcessor handles tone buffering, timing, and callbacks
        self._dtmf_processor = DTMFProcessor(
            session_id=session_id,
            on_sequence=self._on_dtmf_sequence,
            flush_delay=_DTMF_FLUSH_DELAY_SECONDS,
        )
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

    def _background_task(self, coro: Awaitable[Any], *, label: str) -> asyncio.Task:
        """Create a tracked background task that will be cleaned up on handler stop."""
        task = asyncio.create_task(coro, name=f"voicelive-bg-{label}")
        self._pending_background_tasks.add(task)

        def _cleanup_task(t: asyncio.Task) -> None:
            self._pending_background_tasks.discard(t)
            try:
                t.result()
            except asyncio.CancelledError:
                pass  # Expected during cleanup
            except Exception:
                logger.debug("Background task '%s' failed", label, exc_info=True)

        task.add_done_callback(_cleanup_task)
        return task

    def _get_metadata(self, key: str, default: Any = None) -> Any:
        """Read per-connection metadata from the websocket.state (or default)."""
        return getattr(self.websocket.state, key, default)

    def _mark_audio_playback(self, active: bool, *, reset_cancel: bool = True) -> None:
        # single source of truth for "assistant is speaking"
        self._set_metadata("audio_playing", active)
        self._set_metadata("tts_active", active)
        if reset_cancel:
            self._set_metadata("tts_cancel_requested", False)

    async def _start_turn_span(self) -> None:
        await self._end_active_turn_span()
        transport = (
            self._transport.value if hasattr(self._transport, "value") else str(self._transport)
        )
        turn = ConversationTurnSpan(
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            turn_number=self._turn_number,
            transport_type=transport,
        )
        await turn.__aenter__()
        self._active_turn_span = turn

    async def _end_active_turn_span(self) -> None:
        turn = self._active_turn_span
        if not turn:
            return
        self._active_turn_span = None
        await turn.__aexit__(None, None, None)

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
        """Start once; stop owns any startup still suspended in a provider await."""
        if self._shutdown_task is not None:
            raise RuntimeError("Cannot restart a closed VoiceLive handler")
        if self._startup_task is None:
            self._startup_task = asyncio.create_task(self._start(), name="voicelive-start")
        try:
            await asyncio.shield(self._startup_task)
        except BaseException:
            await self.stop()
            raise

    async def _start(self) -> None:
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
                if self._transport == "acs" and self._prepared_connection is None:
                    self._prepared_connection = await consume_voicelive_call_warmup(
                        self.websocket.app.state,
                        call_connection_id=self.call_connection_id,
                        cleanup_tasks=self._warmup_cleanup_tasks,
                    )
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
                # ─────────────────────────────────────────────────────────────
                # PARALLEL PHASE: WebSocket connect + agent/scenario resolution
                # These are independent and can run concurrently to cut startup time.
                # ─────────────────────────────────────────────────────────────

                async def _connect_voicelive(
                    connection_model: str,
                    byom_query: dict[str, str] | None = None,
                    *,
                    api_version: str | None = None,
                ):
                    """Establish VoiceLive WebSocket connection.

                    NOTE: The VoiceLive SDK fixes the generative model at connect() time;
                    it cannot be changed later via session.update(). The model must therefore
                    be resolved from the start agent BEFORE connecting (see resolution below).

                    ``byom_query`` carries the BYOM (Bring Your Own Model) connect-time
                    params (``profile`` and optional ``foundry-resource-override``) when
                    the start agent opts into BYOM; None preserves managed VoiceLive.
                    """
                    t0 = time.perf_counter()
                    with tracer.start_as_current_span(
                        "voicelive.connect",
                        kind=SpanKind.SERVER,
                        attributes=conn_attrs,
                    ) as conn_span:
                        self._credential = await self._build_credential(self._settings)
                        self._connection_cm = connect(
                            endpoint=self._settings.azure_voicelive_endpoint,
                            credential=self._credential,
                            model=connection_model,
                            connection_options=connection_options,
                            **({"query": byom_query} if byom_query else {}),
                            **({"api_version": api_version} if api_version else {}),
                        )
                        self._connection = await self._connection_cm.__aenter__()
                        conn_span.set_attribute("voicelive.model", connection_model)
                        if byom_query:
                            conn_span.set_attribute(
                                "voicelive.byom_profile", byom_query.get("profile", "")
                            )
                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "[VoiceLive Startup] connect_ms=%.1f | session=%s",
                        elapsed,
                        self.session_id,
                    )

                async def _resolve_agents_and_scenario():
                    """Resolve agents, scenario, session agent, and user profile."""
                    t0 = time.perf_counter()
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
                            from apps.artagent.backend.src.orchestration.naming import (
                                get_scenario_from_corememory,
                            )

                            scenario_name = get_scenario_from_corememory(memo_mgr)
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

                    if (
                        app_state
                        and hasattr(app_state, "unified_agents")
                        and app_state.unified_agents
                    ):
                        agents = app_state.unified_agents
                        orchestrator_config = resolve_orchestrator_config(
                            session_id=self.session_id,
                            scenario_name=scenario_name,
                        )
                        logger.info(
                            "Using unified agents for VoiceLive | count=%d start_agent=%s scenario=%s session_id=%s",
                            len(agents),
                            orchestrator_config.start_agent if orchestrator_config else "default",
                            scenario_name
                            or getattr(orchestrator_config, "scenario_name", None)
                            or "(none)",
                            self.session_id or "(none)",
                        )
                        agent_source = "unified"
                    else:
                        logger.info(
                            "No unified agents in app.state - discovering from agents directory",
                        )
                        agents = discover_agents()
                        orchestrator_config = resolve_orchestrator_config(
                            session_id=self.session_id,
                            scenario_name=scenario_name,
                        )
                        logger.info(
                            "Discovered unified agents | count=%d start_agent=%s scenario=%s session_id=%s",
                            len(agents),
                            orchestrator_config.start_agent if orchestrator_config else "default",
                            scenario_name
                            or getattr(orchestrator_config, "scenario_name", None)
                            or "(none)",
                            self.session_id or "(none)",
                        )
                        agent_source = "discovered"

                    agents, session_agent, effective_start_agent = _select_voicelive_agents(
                        agents,
                        orchestrator_config,
                        session_id=self.session_id,
                        configured_start_agent=getattr(self._settings, "start_agent", None),
                    )
                    if orchestrator_config and orchestrator_config.has_scenario:
                        logger.info(
                            "Loaded scenario configuration | scenario=%s start_agent=%s",
                            orchestrator_config.scenario_name,
                            orchestrator_config.start_agent,
                        )
                    if session_agent:
                        logger.info(
                            "Session agent found (Agent Builder) | name=%s voice=%s session_id=%s",
                            session_agent.name,
                            session_agent.voice.name if session_agent.voice else "default",
                            self.session_id,
                        )

                    _, _, effective_handoff_map = build_effective_registry(
                        orchestrator_config,
                        base_agents=agents,
                        session_agent=session_agent,
                        app_state_handoff_map=getattr(app_state, "handoff_map", None),
                    )

                    # Load user profile (fast in-memory lookup)
                    user_profile = None
                    if hasattr(self, "_user_email") and self._user_email:
                        user_profile = await load_user_profile_by_email(self._user_email)

                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "[VoiceLive Startup] resolve_agents_ms=%.1f | agents=%d scenario=%s session=%s",
                        elapsed,
                        len(agents),
                        getattr(orchestrator_config, "scenario_name", None) or "(none)",
                        self.session_id,
                    )
                    return (
                        agents,
                        orchestrator_config,
                        session_agent,
                        effective_start_agent,
                        effective_handoff_map,
                        user_profile,
                        agent_source,
                        app_state,
                    )

                # Resolve agents/scenario FIRST so we know which generative model the
                # start agent requires. The VoiceLive SDK binds the model at connect()
                # time and it cannot be changed afterwards, so per-agent voicelive_model
                # overrides must be applied here — before the WebSocket is established.
                (
                    agents,
                    orchestrator_config,
                    session_agent,
                    effective_start_agent,
                    effective_handoff_map,
                    user_profile,
                    agent_source,
                    app_state,
                ) = await _resolve_agents_and_scenario()

                # Derive the connection model from the start agent's voicelive_model,
                # falling back to the global setting when the agent has no override.
                connection_model = self._settings.azure_voicelive_model
                start_agent_obj = agents.get(effective_start_agent) if agents else None
                self._active_start_agent = effective_start_agent
                if start_agent_obj is not None:
                    try:
                        vl_model = start_agent_obj.get_model_for_mode("voicelive")
                        if vl_model and getattr(vl_model, "deployment_id", None):
                            connection_model = vl_model.deployment_id
                    except Exception as model_err:  # pragma: no cover - defensive
                        logger.warning(
                            "[VoiceLive Startup] Failed to resolve per-agent model for %s, "
                            "falling back to settings model %s | err=%s",
                            effective_start_agent,
                            self._settings.azure_voicelive_model,
                            model_err,
                        )
                self._active_model_name = connection_model
                model_source = (
                    "agent_override"
                    if connection_model != self._settings.azure_voicelive_model
                    else "settings_default"
                )
                self._active_model_source = model_source
                # Unconditional model-resolution KPI. VoiceLive binds the generative
                # model at connect() (it cannot change mid-call), so this single line
                # confirms exactly which model will process the session and where it
                # came from — enabling selected-vs-processed model validation.
                logger.info(
                    "[VoiceLive Startup] model_resolved | mode=voicelive agent=%s model=%s "
                    "source=%s settings_default=%s session=%s",
                    effective_start_agent,
                    connection_model,
                    model_source,
                    self._settings.azure_voicelive_model,
                    self.session_id,
                )

                # Resolve per-agent BYOM (Bring Your Own Model) config from the start
                # agent. Like the model, BYOM is bound at connect() time (it's a
                # WebSocket query param), so it must come from the START agent. None =
                # managed VoiceLive (no profile param sent).
                byom_query = _resolve_voicelive_byom_query(
                    start_agent_obj, connection_model, session_id=self.session_id
                )

                transcription = validate_voicelive_transcription(
                    (
                        (start_agent_obj.session or {}).get("input_audio_transcription_settings")
                        if start_agent_obj is not None
                        else None
                    ),
                    model_name=connection_model,
                    byom_profile=(byom_query or {}).get("profile"),
                )
                api_version = (
                    MAI_VOICELIVE_API_VERSION
                    if transcription.get("model") in MAI_TRANSCRIPTION_MODELS
                    else None
                )

                if byom_query:
                    logger.info(
                        "[VoiceLive Startup] BYOM enabled | agent=%s profile=%s%s session=%s",
                        effective_start_agent,
                        byom_query.get("profile"),
                        (
                            f" foundry_override={byom_query['foundry-resource-override']}"
                            if "foundry-resource-override" in byom_query
                            else ""
                        ),
                        self.session_id,
                    )
                elif not is_managed_voicelive_model(connection_model):
                    # Managed Voice Live (no BYOM) with a model outside the known
                    # serveable set: the connection will succeed but the model
                    # typically never responds, so the agent goes silent until the
                    # ~900s idle timeout. Surface it loudly instead of silently
                    # connecting to a dead session (verified via App Insights:
                    # gpt-5-chat / o3-mini connected but completed 0 turns).
                    logger.warning(
                        "[VoiceLive Startup] unsupported_managed_model | agent=%s model=%s "
                        "is not a known managed Voice Live model — the agent may connect but "
                        "never respond (idle timeout). Use a supported model or enable BYOM. "
                        "session=%s",
                        effective_start_agent,
                        connection_model,
                        self.session_id,
                    )

                # Establish the WebSocket connection with the resolved model.
                prepared = self._prepared_connection
                self._prepared_connection = None
                if prepared and prepared.matches(
                    connection_model, byom_query, api_version=api_version
                ):
                    prepared.claim()
                    self._settings = prepared.settings
                    self._credential = prepared.credential
                    self._connection_cm = prepared.connection_cm
                    self._connection = prepared.connection
                    logger.info(
                        "[VoiceLive Startup] adopted_warm_connection=true | session=%s call=%s age_ms=%.1f session_prepared=%s",
                        self.session_id,
                        self.call_connection_id,
                        (time.perf_counter() - prepared.created_at) * 1000,
                        prepared.session_prepared,
                    )
                else:
                    if prepared:
                        logger.info(
                            "[VoiceLive Startup] warm_connection_mismatch | session=%s call=%s warm_model=%s target_model=%s",
                            self.session_id,
                            self.call_connection_id,
                            prepared.model,
                            connection_model,
                        )
                        await prepared.close()
                    await _connect_voicelive(connection_model, byom_query, api_version=api_version)

                # Set span attributes from resolved values
                span.set_attribute("voicelive.agent_source", agent_source)
                span.set_attribute("voicelive.agents_count", len(agents))
                # Model bound to this session (queryable at the session/handler level,
                # not just the nested voicelive.connect span) so selected-vs-processed
                # model can be validated per session.
                span.set_attribute("voicelive.model", connection_model)
                span.set_attribute("gen_ai.request.model", connection_model)
                span.set_attribute("voicelive.model_source", model_source)
                if byom_query:
                    span.set_attribute("voicelive.byom_profile", byom_query.get("profile", ""))
                if orchestrator_config and orchestrator_config.has_scenario:
                    span.set_attribute(
                        "voicelive.scenario", orchestrator_config.scenario_name or ""
                    )
                if session_agent:
                    span.set_attribute("voicelive.session_agent", session_agent.name)
                if user_profile:
                    span.set_attribute("voicelive.user_profile_loaded", True)
                    span.set_attribute(
                        "voicelive.client_id", user_profile.get("client_id", "unknown")
                    )

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
                    model_name=connection_model,
                    byom_profile=(byom_query or {}).get("profile"),
                    memo_manager=memo_manager,
                    # Hand over the scenario we actually connected with; otherwise the
                    # orchestrator re-resolves without a scenario name and loses the
                    # declarative handoff instructions and routing.
                    orchestrator_config=orchestrator_config,
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

                # Surface *before* stop(): a bad model/deployment or credential
                # here would otherwise close the socket with no explanation.
                info = classify_voice_error(
                    e,
                    source="voicelive",
                    model=self._active_model_name
                    or getattr(self._settings, "azure_voicelive_model", None),
                    agent=self._active_start_agent,
                )
                span.set_attribute("error.code", info.code)
                self._startup_error = info
                await emit_voice_error(
                    self.websocket,
                    info,
                    session_id=self.session_id,
                    call_id=self.call_connection_id,
                )
                raise

    async def stop(self) -> None:
        """Await retained cleanup; all callers observe its same completion/result."""
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._close_resources(), name=f"voicelive-close-{self.session_id}"
            )
        await asyncio.shield(self._shutdown_task)

    async def _close_resources(self) -> None:
        self._stopping = True
        self._running = False
        self._shutdown.set()
        if self._orchestrator is not None:
            unregister_voicelive_orchestrator(self.session_id, expected=self._orchestrator)
        errors: list[Exception] = []
        try:
            await cancel_and_join([self._startup_task] if self._startup_task else [])
        except Exception as exc:
            errors.append(exc)
        try:
            await self._dtmf_processor.cleanup()
        except Exception as exc:
            errors.append(exc)
        try:
            tasks = set(self._pending_background_tasks)
            if self._event_task:
                tasks.add(self._event_task)
            await cancel_and_join(tasks)
        except Exception as exc:
            errors.append(exc)
        try:
            if self._orchestrator:
                await self._orchestrator.cancel_and_join_tasks()
        except Exception as exc:
            errors.append(exc)
        try:
            await cancel_and_join(self._warmup_cleanup_tasks, cancel=False)
        except Exception as exc:
            errors.append(exc)
        quiesced = not errors
        memo = getattr(self.websocket.state, "cm", None) if self.websocket else None
        redis = getattr(self.websocket.app.state, "redis", None) if self.websocket else None
        try:
            if quiesced and self._orchestrator:
                self._orchestrator._sync_to_memo_manager()
        except Exception as exc:
            errors.append(exc)
        try:
            await finish_persistence(memo, redis, quiesced=quiesced and not errors)
        except Exception as exc:
            errors.append(exc)
        # Sockets are closed even if a producer failed; never erase references
        # to unacknowledged tasks or native resources and pretend they stopped.
        if self._connection_cm:
            try:
                await self._connection_cm.__aexit__(None, None, None)
            except Exception as exc:
                errors.append(exc)
            else:
                self._connection_cm = None
                self._connection = None
        if self._prepared_connection:
            try:
                await self._prepared_connection.close()
            except Exception as exc:
                errors.append(exc)
            else:
                self._prepared_connection = None
        from apps.artagent.backend.src.orchestration.session_memory import (
            release_session_memory,
        )

        try:
            await release_session_memory(self.session_id, memo, self.websocket)
        except Exception as exc:
            errors.append(exc)
        if quiesced:
            if self._orchestrator:
                self._orchestrator.cleanup()
                self._orchestrator = None
            self._event_task = None
            self._pending_background_tasks.clear()
            self._warmup_cleanup_tasks.clear()
            self._credential = None
            self._messenger = None
        if errors:
            raise ExceptionGroup("VoiceLive close failed", errors)

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
            stt_latency_ms = None
            if self._vad_end_time:
                stt_latency_ms = (self._transcript_final_time - self._vad_end_time) * 1000
            elif self._turn_start_time:
                stt_latency_ms = (self._transcript_final_time - self._turn_start_time) * 1000
            if self._active_turn_span and transcript:
                self._active_turn_span.record_stt_complete(
                    text=transcript,
                    latency_ms=stt_latency_ms,
                    language=getattr(event, "language", None),
                )
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

            # Drop trailing audio from a response cancelled by barge-in so no
            # AudioData is relayed after the StopAudio. The first delta of a
            # fresh response clears the now-stale cancellation set.
            if response_id and response_id in self._cancelled_response_ids:
                logger.debug(
                    "[VoiceLive] Dropping audio from cancelled response | session=%s response=%s",
                    self.session_id,
                    response_id,
                )
                return
            if response_id and self._cancelled_response_ids:
                self._cancelled_response_ids.clear()

            # Track TTS TTFB (Time To First Byte) - first audio delta for this turn
            if self._turn_start_time and self._tts_first_audio_time is None:
                self._tts_first_audio_time = time.perf_counter()
                # Calculate latency relative to VAD end (preferred) or turn start
                start_ref = self._vad_end_time or self._turn_start_time
                ttfb_ms = (self._tts_first_audio_time - start_ref) * 1000
                self._current_response_id = response_id
                if self._active_turn_span:
                    self._active_turn_span.add_metadata(
                        "voicelive.response_id", response_id or "unknown"
                    )
                    self._active_turn_span.record_tts_first_audio()

                # Record OTel metric for App Insights Performance view
                record_tts_ttfb(
                    ttfb_ms,
                    session_id=self.session_id,
                    turn_number=self._turn_number,
                    reference="vad_end" if self._vad_end_time else "turn_start",
                    agent_name=self._messenger._active_agent_name or "unknown",
                )

                logger.debug(
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
                self._cancelled_response_ids.discard(response_id)
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

            # Capture in-flight responses so their trailing audio deltas are
            # dropped — no AudioData may reach the transport after the StopAudio
            # dispatched below.
            if self._current_response_id:
                self._cancelled_response_ids.add(self._current_response_id)
            self._cancelled_response_ids |= self._active_response_ids

            # Start new turn tracking
            self._turn_number += 1
            self._turn_start_time = time.perf_counter()
            self._vad_end_time = None
            self._transcript_final_time = None
            self._llm_first_token_time = None
            self._tts_first_audio_time = None
            self._current_response_id = None
            await self._start_turn_span()

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
            if self._active_turn_span:
                self._active_turn_span.record_tts_start()
            logger.debug("🎤 User paused speaking")
            logger.debug("🤖 Generating assistant reply")
            self._mark_audio_playback(False)

        elif etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_DELTA:
            transcript_text = getattr(event, "transcript", "") or getattr(event, "delta", "")
            if not transcript_text:
                return
            turn_id = self._messenger.resolve_user_turn_id(self._extract_item_id(event))
            await self._messenger.send_user_partial(
                transcript_text,
                turn_id=turn_id,
                language=getattr(event, "language", None),
            )

        elif etype == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            self.record_llm_first_token()

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            tts_total_ms = None
            if self._tts_first_audio_time:
                tts_total_ms = (time.perf_counter() - self._tts_first_audio_time) * 1000
            if self._active_turn_span:
                self._active_turn_span.record_tts_complete(total_ms=tts_total_ms)
            logger.debug(
                "[VoiceLiveSDK] Audio stream marked done | session=%s response=%s",
                self.session_id,
                getattr(event, "response_id", "unknown"),
            )
            # Agent finished speaking -> finalize and close voice.turn.N.total now so
            # the turn span is tightly scoped (user speech -> response audio done) and
            # reads sequentially, instead of lingering until the next utterance.
            # _finalize_turn_metrics is idempotent (it resets _turn_start_time), so the
            # safety-net finalize at the next user-speech-start becomes a no-op. Tool-only
            # responses emit no audio, so this does not fire mid-turn for tool calls.
            await self._finalize_turn_metrics()
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
                if not self._websocket_open:
                    logger.debug("[VoiceLiveSDK] Skipping audio delta: WebSocket closed")
                    return
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
        if not self._websocket_open:
            self._stop_audio_pending = False
            return
        stop_message = {"kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        try:
            await self.websocket.send_json(stop_message)
            self._stop_audio_pending = True
        except Exception:
            self._stop_audio_pending = False
            logger.debug("Failed to send StopAudio", exc_info=True)

    async def _send_error(self, event: Any) -> None:
        """Relay an ``ErrorData`` frame on the raw ACS transport."""
        if not self._websocket_open:
            return
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
        """Handle a VoiceLive ``error`` server event.

        Benign cancel-race codes are ignored. Everything else stops playback,
        relays an ``ErrorData`` frame on the ACS transport, and broadcasts a
        classified session envelope so the operator UI shows the real cause.
        """
        error_obj = getattr(event, "error", None)
        code = getattr(error_obj, "code", "VoiceLiveError")
        message = getattr(error_obj, "message", "Unknown VoiceLive error")
        details = getattr(error_obj, "details", None)

        # Benign cancel-race errors: a barge-in / response.cancel arrives just
        # after the response already finished, so VoiceLive reports there is no
        # active response to cancel. This is NOT a real failure — do not stop
        # audio or surface an error to the UI, or the next turn gets cut off.
        info = classify_voicelive_server_error(
            code,
            message,
            details=details,
            model=self._active_model_name,
            agent=self._active_start_agent,
        )
        if info is None:
            logger.info(
                "[VoiceLiveSDK] Ignoring benign cancel-race error | session=%s code=%s",
                self.session_id,
                code,
            )
            return

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
        await emit_voice_error(
            self.websocket,
            info,
            session_id=self.session_id,
            call_id=self.call_connection_id,
        )

    async def _handle_dtmf_tone(self, raw_tone: Any) -> None:
        """Delegate DTMF tone handling to the DTMFProcessor."""
        await self._dtmf_processor.handle_tone(raw_tone)

    async def _on_dtmf_sequence(self, sequence: str, reason: str) -> None:
        """Callback invoked by DTMFProcessor when a DTMF sequence is ready."""
        if not sequence or not self._connection:
            return
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": sequence}],
        }
        try:
            await self._connection.conversation.item.create(item=item)
            await self._connection.response.create()
            logger.info(
                "Forwarded DTMF sequence (%s digits) via %s | session=%s",
                len(sequence),
                reason,
                self.session_id,
            )
        except Exception:
            logger.exception(
                "Failed to forward DTMF digits to VoiceLive | session=%s", self.session_id
            )

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

            # Echo user message back to frontend so it appears in the chat UI
            if self._messenger:
                turn_id = uuid.uuid4().hex
                self._messenger.begin_user_turn(turn_id)
                await self._messenger.send_user_message(text, turn_id=turn_id)
                self._messenger.finish_user_turn(turn_id)

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

        # Skip creating telemetry for high-frequency noisy events.
        if type_str in self._NOISY_EVENT_TYPES:
            return

        # Lifecycle events are already recorded as span events on the event-loop
        # span via loop_span.add_event("voicelive.event_received", ...). We do NOT
        # create a standalone 0-duration span per event here: that previously
        # flooded the dependencies table with ~80 empty "voicelive.event.<type>"
        # spans per call and made the end-to-end transaction view unusable.
        logger.debug(
            "[VoiceLiveSDK] Event received | session=%s type=%s",
            self.session_id,
            type_str,
        )

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
        """Resample audio from 24kHz to target rate with proper anti-aliasing.

        Uses a windowed sinc interpolation which is significantly better than
        linear interpolation for audio signals. This avoids aliasing artifacts
        and preserves audio fidelity better than np.interp.
        """
        try:
            source = np.frombuffer(audio_bytes, dtype=np.int16)
            source_rate = 24000
            target_rate = max(self._acs_sample_rate, 1)
            if source_rate == target_rate:
                return base64.b64encode(audio_bytes).decode("utf-8")

            # Calculate resampling parameters
            ratio = target_rate / source_rate
            new_len = max(int(len(source) * ratio), 1)

            # Convert to float for processing
            source_float = source.astype(np.float64)

            # Apply simple anti-aliasing low-pass filter before downsampling
            # For 24kHz -> 16kHz, we need to filter out frequencies above 8kHz
            # Using a simple FIR filter with a Hann window
            if ratio < 1.0:
                # Downsampling: apply low-pass filter first
                filter_len = 15  # Odd number for symmetric filter
                n = np.arange(filter_len)
                # Sinc filter with cutoff at ratio * Nyquist
                cutoff = ratio * 0.9  # Slight margin to avoid aliasing
                h = np.sinc(cutoff * (n - (filter_len - 1) / 2))
                # Apply Hann window
                window = 0.5 - 0.5 * np.cos(2 * np.pi * n / (filter_len - 1))
                h = h * window
                h = h / np.sum(h)  # Normalize

                # Apply filter using convolution
                source_float = np.convolve(source_float, h, mode="same")

            # Use higher-quality sinc interpolation instead of linear
            # Create output sample positions in terms of input indices
            new_indices = np.linspace(0, len(source_float) - 1, new_len)

            # Sinc interpolation with 4-point window (Lanczos-like)
            # This is much better than linear but still fast
            resampled = np.zeros(new_len, dtype=np.float64)
            for i, idx in enumerate(new_indices):
                # Get integer and fractional parts
                idx_int = int(idx)
                frac = idx - idx_int

                # 4-point Hermite interpolation (cubic, smoother than linear)
                if idx_int <= 0:
                    resampled[i] = source_float[0]
                elif idx_int >= len(source_float) - 2:
                    resampled[i] = source_float[-1]
                else:
                    # Cubic Hermite spline interpolation
                    p0 = source_float[max(0, idx_int - 1)]
                    p1 = source_float[idx_int]
                    p2 = source_float[min(len(source_float) - 1, idx_int + 1)]
                    p3 = source_float[min(len(source_float) - 1, idx_int + 2)]

                    # Catmull-Rom spline coefficients
                    a = -0.5 * p0 + 1.5 * p1 - 1.5 * p2 + 0.5 * p3
                    b = p0 - 2.5 * p1 + 2.0 * p2 - 0.5 * p3
                    c = -0.5 * p0 + 0.5 * p2
                    d = p1

                    resampled[i] = a * frac**3 + b * frac**2 + c * frac + d

            # Clip and convert back to int16
            resampled = np.clip(resampled, -32768, 32767)
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
    async def _build_credential(settings) -> AzureKeyCredential | TokenCredential:
        if settings.has_api_key_auth:
            return AzureKeyCredential(settings.azure_voicelive_api_key)
        global _CACHED_CREDENTIAL
        if _CACHED_CREDENTIAL is None:
            async with _CREDENTIAL_LOCK:
                # Double-check after acquiring lock
                if _CACHED_CREDENTIAL is None:
                    if _using_managed_identity():
                        client_id = getattr(settings, "azure_client_id", None) or os.getenv(
                            "AZURE_CLIENT_ID"
                        )
                        _CACHED_CREDENTIAL = ManagedIdentityCredential(client_id=client_id)
                        logger.info(
                            "Created shared ManagedIdentityCredential for VoiceLive (cached for process lifetime)"
                        )
                    elif _is_local_dev() and get_local_cli_credential_options():
                        _CACHED_CREDENTIAL = AsyncSubscriptionPinnedAzureCliCredential(
                            **get_local_cli_credential_options()
                        )
                        logger.info(
                            "Created subscription-pinned local Azure CLI credential for VoiceLive"
                        )
                    elif _is_local_dev():
                        _CACHED_CREDENTIAL = DefaultAzureCredential(
                            exclude_environment_credential=False,
                            exclude_managed_identity_credential=True,
                            exclude_workload_identity_credential=True,
                            exclude_shared_token_cache_credential=True,
                            exclude_visual_studio_code_credential=True,
                            exclude_cli_credential=False,
                            exclude_powershell_credential=True,
                            exclude_interactive_browser_credential=True,
                        )
                        logger.info(
                            "Created shared local DefaultAzureCredential for VoiceLive without managed identity probing"
                        )
                    else:
                        _CACHED_CREDENTIAL = DefaultAzureCredential(
                            exclude_environment_credential=False,
                            exclude_managed_identity_credential=False,
                            exclude_workload_identity_credential=True,
                            exclude_shared_token_cache_credential=True,
                            exclude_visual_studio_code_credential=True,
                            exclude_cli_credential=True,
                            exclude_powershell_credential=True,
                            exclude_interactive_browser_credential=True,
                        )
                        logger.info(
                            "Created shared production DefaultAzureCredential for VoiceLive"
                        )
        return _CACHED_CREDENTIAL

    # =========================================================================
    # Turn-Level Latency Tracking Methods
    # =========================================================================

    def record_llm_first_token(self) -> None:
        """Record LLM first token timing (TTFT) for the current turn."""
        if self._turn_start_time and self._llm_first_token_time is None:
            self._llm_first_token_time = time.perf_counter()
            # Measure from VAD end (user finished speaking) so TTFT is directly
            # comparable to STT/TTS latencies (all referenced to vad_end).
            start_ref = self._vad_end_time or self._turn_start_time
            ttft_ms = (self._llm_first_token_time - start_ref) * 1000

            # Record OTel metric for App Insights Performance view
            record_llm_ttft(
                ttft_ms,
                session_id=self.session_id,
                turn_number=self._turn_number,
                agent_name=self._messenger._active_agent_name or "unknown",
            )

            if self._active_turn_span:
                self._active_turn_span.record_llm_first_token()

            logger.debug(
                "[VoiceLive] LLM TTFT | session=%s turn=%d ttft_ms=%.2f ref=%s",
                self.session_id,
                self._turn_number,
                ttft_ms,
                "vad_end" if self._vad_end_time else "turn_start",
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

        if self._llm_first_token_time and latency_base:
            # E2E processing time: VAD End (user finished) -> LLM First Token,
            # using the same vad_end reference as STT/TTS so the summary numbers
            # are apples-to-apples and the histograms line up.
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

        # TTS synthesis delta: first LLM token -> first audio byte (render +
        # delivery). Both legs are VAD-end anchored, so the difference isolates
        # the synthesis portion of TTFB.
        synth_ms = (
            tts_ttfb_ms - llm_ttft_ms
            if tts_ttfb_ms is not None and llm_ttft_ms is not None
            else None
        )

        # Stamp the structured per-turn latency profile (stt / ttft / ttfb /
        # synth / wall) on the voice.turn.N.total span through the shared helper so
        # VoiceLive and Cascade surface identical attributes in App Insights.
        if self._active_turn_span:
            self._active_turn_span.record_turn_kpis(
                ttft_ms=llm_ttft_ms,
                ttfb_ms=tts_ttfb_ms,
                synth_ms=synth_ms,
                stt_ms=stt_latency_ms,
                turn_wall_ms=total_turn_duration_ms,
                agent_name=self._messenger._active_agent_name or "unknown",
                latency_anchor="vad_end" if self._vad_end_time else "turn_start",
                model=self._active_model_name,
            )

        logger.info(
            "[VoiceLive] Turn %d complete | agent=%s model=%s | ttft=%s ttfb=%s synth=%s "
            "| turn_wall=%.0fms | session=%s",
            self._turn_number,
            self._messenger._active_agent_name or "unknown",
            self._active_model_name or "unknown",
            f"{llm_ttft_ms:.0f}ms" if llm_ttft_ms is not None else "N/A",
            f"{tts_ttfb_ms:.0f}ms" if tts_ttfb_ms is not None else "N/A",
            f"{synth_ms:.0f}ms" if synth_ms is not None else "N/A",
            total_turn_duration_ms,
            self.session_id,
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

        await self._end_active_turn_span()

        # Reset turn tracking state
        self._turn_start_time = None
        self._vad_end_time = None
        self._transcript_final_time = None
        self._llm_first_token_time = None
        self._tts_first_audio_time = None
        self._current_response_id = None


def _voicelive_warmup_registry(app_state: Any) -> tuple[dict[str, asyncio.Task], asyncio.Lock]:
    registry = getattr(app_state, "voicelive_warmups", None)
    if registry is None:
        registry = {}
        app_state.voicelive_warmups = registry

    lock = getattr(app_state, "voicelive_warmups_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app_state.voicelive_warmups_lock = lock

    return registry, lock


def start_voicelive_call_warmup(
    app_state: Any,
    *,
    call_connection_id: str | None,
    session_id: str | None,
    scenario_name: str | None = None,
    user_email: str | None = None,
) -> None:
    """Start best-effort VoiceLive connection warmup for a pending ACS call."""
    if not app_state or not call_connection_id or not session_id:
        return

    registry, _ = _voicelive_warmup_registry(app_state)
    existing = registry.get(call_connection_id)
    if existing and not existing.done():
        return

    task = asyncio.create_task(
        _prepare_voicelive_call_warmup(
            app_state=app_state,
            call_connection_id=call_connection_id,
            session_id=session_id,
            scenario_name=scenario_name,
            user_email=user_email,
        ),
        name=f"voicelive-warmup-{call_connection_id[-8:]}",
    )
    registry[call_connection_id] = task

    def _consume_result(done: asyncio.Task) -> None:
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug(
                "VoiceLive warmup failed | call=%s session=%s",
                call_connection_id,
                session_id,
                exc_info=True,
            )

    task.add_done_callback(_consume_result)


async def consume_voicelive_call_warmup(
    app_state: Any,
    *,
    call_connection_id: str | None,
    cleanup_tasks: set[asyncio.Task],
    timeout_sec: float = _VOICELIVE_WARMUP_WAIT_SECONDS,
) -> VoiceLivePreparedConnection | None:
    """Consume warmup; abandoned work remains in the caller's cleanup task set."""
    if not app_state or not call_connection_id:
        return None

    registry, lock = _voicelive_warmup_registry(app_state)
    async with lock:
        task = registry.pop(call_connection_id, None)

    if not task:
        return None

    def retain_disposal() -> None:
        async def dispose() -> None:
            # Retained cleanup: the handler joins it without cancellation.
            prepared = await task
            if prepared:
                await prepared.close()

        disposing = asyncio.create_task(dispose(), name="voicelive-warmup-disposal")
        cleanup_tasks.add(disposing)

        def observe(done: asyncio.Task) -> None:
            if not done.cancelled() and done.exception() is not None:
                logger.error("VoiceLive warmup disposal failed: %s", done.exception())

        disposing.add_done_callback(observe)

    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout_sec)
    except TimeoutError:
        logger.debug(
            "VoiceLive warmup not ready after %.0fms | call=%s",
            timeout_sec * 1000,
            call_connection_id,
        )

        retain_disposal()
        return None
    except asyncio.CancelledError:
        retain_disposal()
        raise
    except Exception:
        cleanup_tasks.add(task)
        logger.debug("VoiceLive warmup consume failed | call=%s", call_connection_id, exc_info=True)
        return None


async def _prepare_voicelive_call_warmup(
    *,
    app_state: Any,
    call_connection_id: str,
    session_id: str,
    scenario_name: str | None,
    user_email: str | None,
) -> VoiceLivePreparedConnection | None:
    settings = get_settings()
    connection_options = {
        "max_msg_size": settings.ws_max_msg_size,
        "heartbeat": settings.ws_heartbeat,
        "timeout": settings.ws_timeout,
    }

    agents, effective_start_agent, connection_model, byom_query, system_vars = (
        await _resolve_voicelive_warmup_config(
            app_state=app_state,
            session_id=session_id,
            scenario_name=scenario_name,
            settings=settings,
            user_email=user_email,
        )
    )

    start_agent_obj = agents.get(effective_start_agent) if agents else None
    transcription = validate_voicelive_transcription(
        (
            (start_agent_obj.session or {}).get("input_audio_transcription_settings")
            if start_agent_obj is not None
            else None
        ),
        model_name=connection_model,
        byom_profile=(byom_query or {}).get("profile"),
    )
    api_version = (
        MAI_VOICELIVE_API_VERSION if transcription.get("model") in MAI_TRANSCRIPTION_MODELS else None
    )
    credential = await VoiceLiveSDKHandler._build_credential(settings)
    connection_cm = connect(
        endpoint=settings.azure_voicelive_endpoint,
        credential=credential,
        model=connection_model,
        connection_options=connection_options,
        **({"query": byom_query} if byom_query else {}),
        **({"api_version": api_version} if api_version else {}),
    )
    connection = await connection_cm.__aenter__()
    prepared = VoiceLivePreparedConnection(
        connection=connection,
        connection_cm=connection_cm,
        credential=credential,
        settings=settings,
        model=connection_model,
        byom_query=byom_query,
        api_version=api_version,
    )

    try:
        start_agent_obj = agents.get(effective_start_agent) if agents else None
        if start_agent_obj is not None:
            await voicelive_session.apply_voicelive_session(
                start_agent_obj,
                connection,
                system_vars=system_vars,
                say=None,
                session_id=session_id,
                call_connection_id=call_connection_id,
                connection_model=connection_model,
                connection_byom_profile=(byom_query or {}).get("profile"),
                orchestrator_config=resolve_orchestrator_config(
                    session_id=session_id, scenario_name=scenario_name
                ),
            )
            prepared.session_prepared = True
        logger.info(
            "[VoiceLive Warmup] prepared connection | call=%s session=%s model=%s agent=%s session_prepared=%s",
            call_connection_id,
            session_id,
            connection_model,
            effective_start_agent,
            prepared.session_prepared,
        )
        return prepared
    except BaseException:
        await prepared.close()
        raise


def _select_voicelive_agents(
    agents: dict[str, Any],
    orchestrator_config: Any,
    *,
    session_id: str,
    configured_start_agent: str | None,
) -> tuple[dict[str, Any], Any | None, str]:
    """Use the same scenario-scoped start agent for warmup and the actual connection."""
    if orchestrator_config and orchestrator_config.has_scenario:
        scoped_agents = dict(orchestrator_config.agents or {})
        start_key, start_agent = find_agent_by_name(scoped_agents, orchestrator_config.start_agent)
        if not start_key or start_agent is None:
            raise ValueError("The active scenario has no valid VoiceLive starting agent.")
        orchestrator_config.start_agent = start_key
        return scoped_agents, None, start_key

    agents = dict(agents)
    session_agent = get_session_agent(session_id)
    if session_agent:
        start_key, _ = find_agent_by_name(agents, session_agent.name)
        start_key = start_key or session_agent.name
        agents[start_key] = session_agent
        if orchestrator_config is not None:
            orchestrator_config.start_agent = start_key
            orchestrator_config.start_agent_authoritative = True
        return agents, session_agent, start_key
    start_name = (
        getattr(orchestrator_config, "start_agent", None)
        or configured_start_agent
        or DEFAULT_START_AGENT
    )
    start_key, _ = find_agent_by_name(agents, start_name)
    return agents, None, start_key or start_name


def _resolve_voicelive_byom_query(
    agent: Any | None, connection_model: str, *, session_id: str
) -> dict[str, str] | None:
    """Resolve the same usable connection profile for warmup and startup."""
    query = agent.get_byom_query() if agent is not None else None
    if query:
        conflict = byom_profile_model_conflict(query.get("profile"), connection_model)
        if conflict:
            # Known incompatible API/model pairs connect but never answer. Recover
            # persisted pairs through managed Voice Live, consistently on both paths.
            logger.warning(
                "[VoiceLive] byom_profile_model_conflict | agent=%s profile=%s model=%s "
                "session=%s — %s Falling back to managed Voice Live for this connection.",
                agent.name,
                query.get("profile"),
                connection_model,
                session_id,
                conflict,
            )
            return None
    return query


async def _resolve_voicelive_warmup_config(
    *,
    app_state: Any,
    session_id: str,
    scenario_name: str | None,
    settings: Any,
    user_email: str | None,
) -> tuple[dict[str, Any], str, str, dict[str, str] | None, dict[str, Any]]:
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    if app_state and getattr(app_state, "unified_agents", None):
        agents = app_state.unified_agents
    else:
        agents = discover_agents()

    orchestrator_config = resolve_orchestrator_config(
        session_id=session_id,
        scenario_name=scenario_name,
    )
    agents, _, effective_start_agent = _select_voicelive_agents(
        agents,
        orchestrator_config,
        session_id=session_id,
        configured_start_agent=getattr(settings, "start_agent", None),
    )

    connection_model = settings.azure_voicelive_model
    byom_query: dict[str, str] | None = None
    start_agent_obj = agents.get(effective_start_agent) if agents else None
    if start_agent_obj is not None:
        with contextlib.suppress(Exception):
            vl_model = start_agent_obj.get_model_for_mode("voicelive")
            if vl_model and getattr(vl_model, "deployment_id", None):
                connection_model = vl_model.deployment_id
        byom_query = _resolve_voicelive_byom_query(
            start_agent_obj, connection_model, session_id=session_id
        )

    system_vars: dict[str, Any] = {"active_agent": effective_start_agent}
    if user_email:
        user_profile = await load_user_profile_by_email(user_email)
        if user_profile:
            system_vars.update(
                {
                    "session_profile": user_profile,
                    "client_id": user_profile.get("client_id"),
                    "customer_intelligence": user_profile.get("customer_intelligence", {}),
                    "caller_name": user_profile.get("full_name"),
                }
            )
            if user_profile.get("institution_name"):
                system_vars["institution_name"] = user_profile["institution_name"]

    return agents, effective_start_agent, connection_model, byom_query, system_vars


__all__ = [
    "VoiceLiveSDKHandler",
    "VoiceLivePreparedConnection",
    "consume_voicelive_call_warmup",
    "start_voicelive_call_warmup",
]
