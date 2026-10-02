"""
Genesys VoiceLive Handler
==========================

Bridges Genesys Cloud AudioConnector (AudioHook v2) to Azure VoiceLive API,
enabling the ART multi-agent orchestrator to handle Genesys telephony calls.

Audio flow:
    Genesys (µ-law 8kHz binary) → decode/upsample → VoiceLive (PCM16 24kHz base64)
    VoiceLive (PCM16 24kHz base64) → downsample/encode → Genesys (µ-law 8kHz binary)

Key design decisions:
    - Single outbound writer queue serialises all Genesys messages to prevent
      sequence number corruption from concurrent coroutines.
    - Server VAD in VoiceLive handles turn detection (no manual commit needed).
    - Barge-in cancels VoiceLive response, flushes outbound buffer, and sends
      barge_in event to Genesys.
    - Playback lifecycle events (playback_started/completed) are mapped from
      VoiceLive audio events.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from apps.artagent.backend.registries.agentstore.base import (
    MAI_TRANSCRIPTION_MODELS,
    MAI_VOICELIVE_API_VERSION,
    byom_profile_model_conflict,
    validate_voicelive_transcription,
)
from apps.artagent.backend.registries.agentstore.loader import (
    discover_agents,
)
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
from apps.artagent.backend.voice.shared import (
    DEFAULT_START_AGENT,
    build_effective_registry,
    resolve_orchestrator_config,
)
from apps.artagent.backend.voice.shared.close import cancel_and_join, finish_persistence
from apps.artagent.backend.voice.voicelive.orchestrator import (
    LiveOrchestrator,
    register_voicelive_orchestrator,
    unregister_voicelive_orchestrator,
)
from apps.artagent.backend.voice.voicelive.settings import get_settings
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import ServerEventType
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger

from .audio_codec import (
    PCM16_24kToULaw8kStreamEncoder,
    ULaw8kToPCM16_24kStreamDecoder,
)
from .protocol import (
    CLIENT_MSG_CLOSE,
    CLIENT_MSG_DTMF,
    CLIENT_MSG_ERROR,
    CLIENT_MSG_OPEN,
    CLIENT_MSG_PING,
    CLIENT_MSG_PLAYBACK_COMPLETED,
    CLIENT_MSG_PLAYBACK_STARTED,
    CLIENT_MSG_UPDATE,
    DISCONNECT_ERROR,
    GenesysProtocol,
)

logger = get_logger("genesys.handler")
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True)
class _OutboundAudioFrame:
    """Audio queued for the single Genesys writer, tagged to a provider response."""

    response_id: str
    payload: bytes


class _GenesysMessenger:
    """Minimal messenger interface for LiveOrchestrator in Genesys context.

    LiveOrchestrator calls messenger methods for UI updates, tool lifecycle,
    and agent change notifications. In Genesys context, most of these are
    logged but have no browser UI to update.
    """

    def __init__(self, session_id: str, call_id: str | None = None) -> None:
        self._session_id = session_id
        self._call_id = call_id
        self._active_agent_name: str | None = None
        self._active_agent_label: str | None = None
        self._active_turn_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def call_id(self) -> str | None:
        return self._call_id

    def set_active_agent(self, agent_name: str | None) -> None:
        if agent_name != self._active_agent_name:
            logger.info(
                "[Genesys] Agent changed: %s → %s | session=%s",
                self._active_agent_name,
                agent_name,
                self._session_id,
            )
            self._active_agent_name = agent_name
            self._active_agent_label = agent_name

    def _ensure_turn_id(self, candidate: str | None, *, allow_generate: bool = True) -> str | None:
        if candidate:
            self._active_turn_id = candidate
            return candidate
        return self._active_turn_id

    def _release_turn(self, turn_id: str | None) -> None:
        if turn_id and self._active_turn_id == turn_id:
            self._active_turn_id = None

    def advance_turn_for_tool(self) -> str | None:
        return self._active_turn_id

    def reset_turn_sequence(self) -> None:
        pass

    def begin_user_turn(self, turn_id: str | None) -> str | None:
        self._active_turn_id = turn_id
        return turn_id

    def resolve_user_turn_id(self, candidate: str | None) -> str | None:
        if candidate:
            return candidate
        return self._active_turn_id

    def finish_user_turn(self, turn_id: str | None) -> None:
        pass

    async def send_user_message(self, text: str, *, turn_id: str | None = None) -> None:
        logger.info("[Genesys] User: %s | session=%s", text, self._session_id)

    async def send_assistant_message(
        self,
        text: str,
        *,
        sender: str | None = None,
        response_id: str | None = None,
        status: str | None = None,
    ) -> None:
        logger.info("[Genesys] Assistant: %s | session=%s", text, self._session_id)

    async def send_assistant_streaming(
        self,
        text: str,
        *,
        sender: str | None = None,
        response_id: str | None = None,
    ) -> None:
        pass

    async def send_assistant_cancelled(
        self,
        *,
        response_id: str | None,
        sender: str | None = None,
        reason: str | None = None,
    ) -> None:
        logger.debug("[Genesys] Assistant cancelled | session=%s", self._session_id)

    async def send_session_update(
        self,
        *,
        agent_name: str | None,
        session_obj: Any | None,
        transport: str | None = None,
        contract: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def send_status_update(
        self,
        text: str,
        *,
        tone: str | None = None,
        caption: str | None = None,
        sender: str | None = None,
        event_label: str = "genesys_status",
    ) -> None:
        pass

    async def notify_tool_start(
        self,
        *,
        call_id: str | None,
        name: str | None,
        args: dict[str, Any],
    ) -> None:
        logger.debug("[Genesys] Tool start: %s | session=%s", name, self._session_id)

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
        logger.debug(
            "[Genesys] Tool end: %s status=%s | session=%s", name, status, self._session_id
        )


class GenesysVoiceLiveHandler:
    """Bridges Genesys AudioHook v2 WebSocket to Azure VoiceLive API.

    Implements the full AudioHook v2 server-side protocol while leveraging
    the ART VoiceLive SDK and LiveOrchestrator for multi-agent AI.

    Args:
        websocket: FastAPI WebSocket connection from Genesys/Simulator.
        session_id: AudioHook session ID (from audiohook-session-id header).
    """

    def __init__(self, *, websocket: WebSocket, session_id: str) -> None:
        self.websocket = websocket
        self.session_id = session_id

        self._protocol = GenesysProtocol(session_id)
        self._messenger = _GenesysMessenger(session_id)
        self._settings = None
        self._credential: Any | None = None
        self._connection = None
        self._connection_cm = None
        self._orchestrator: LiveOrchestrator | None = None

        self._running = False
        self._session_opened = False
        self._shutdown = asyncio.Event()
        self._event_task: asyncio.Task | None = None
        self._shutdown_task: asyncio.Task | None = None
        self._connect_task: asyncio.Task | None = None
        self._memo_manager: MemoManager | None = None

        # Serialised outbound queue (prevents seq number corruption)
        self._outbound_queue: asyncio.Queue[_OutboundAudioFrame | dict[str, Any] | None] = (
            asyncio.Queue()
        )
        self._queue_lock = asyncio.Lock()
        self._writer_task: asyncio.Task | None = None

        # Audio playback state
        self._is_playing = False
        self._active_response_ids: set[str] = set()
        self._cancelled_response_ids: set[str] = set()
        self._current_response_id: str | None = None
        self._outbound_audio_encoder = PCM16_24kToULaw8kStreamEncoder()
        self._outbound_audio_response_id: str | None = None
        self._inbound_audio_decoder = ULaw8kToPCM16_24kStreamDecoder()

        # Response-scoped outbound audio buffers drained by the pacer/writer pair.
        self._response_audio_buffers: dict[str, bytearray] = {}
        self._response_audio_order: deque[str] = deque()
        self._buffered_response_ids: set[str] = set()
        self._AUDIO_CHUNK_SIZE = 2000  # 250ms at 8kHz µ-law mono (1 byte/sample)
        self._AUDIO_PACE_MS = 250  # Send one chunk every 250ms (matching reference)
        self._MAX_OUTBOUND_AUDIO_BYTES = self._AUDIO_CHUNK_SIZE * 80  # 20s at 8 kHz µ-law
        self._pending_audio_bytes = 0
        self._pacer_task: asyncio.Task | None = None
        self._terminal_disconnect_enqueued = False
        self._terminal_disconnect_sent = False
        self._terminal_shutdown_task: asyncio.Task | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the outbound writer. VoiceLive connection is deferred to session open."""
        if self._shutdown_task is not None:
            raise RuntimeError("Cannot restart a closed Genesys handler")
        if self._writer_task is not None:
            return
        self._running = True
        self._shutdown.clear()
        self._terminal_disconnect_enqueued = False
        self._terminal_disconnect_sent = False
        self._writer_task = asyncio.create_task(self._outbound_writer(), name="genesys-writer")
        logger.info("[Genesys] Handler started | session=%s", self.session_id)

    async def stop(self) -> None:
        """Await retained cleanup, including producers, persistence and socket."""
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._close_resources(asyncio.current_task()),
                name=f"genesys-close-{self.session_id}",
            )
        await asyncio.shield(self._shutdown_task)

    async def _close_resources(self, initiator: asyncio.Task | None) -> None:
        self._running = False
        self._shutdown.set()
        errors: list[Exception] = []
        try:
            await cancel_and_join(
                task
                for task in (
                    self._connect_task,
                    self._pacer_task,
                    self._writer_task,
                    self._terminal_shutdown_task,
                )
                if task is not None
                and not (task is self._terminal_shutdown_task and task is initiator)
            )
        except Exception as exc:
            errors.append(exc)
        try:
            await self._close_voicelive_runtime(producers_quiesced=not errors)
        except Exception as exc:
            errors.append(exc)
        if not errors:
            await self._clear_buffered_audio()
            await self._clear_outbound_queue()
            self._writer_task = None
            self._pacer_task = None
            self._terminal_shutdown_task = None
            self._credential = None
            self._session_opened = False
            self._current_response_id = None
            self._active_response_ids.clear()
            self._cancelled_response_ids.clear()
            self._terminal_disconnect_enqueued = False
            self._terminal_disconnect_sent = False
        if errors:
            raise ExceptionGroup("Genesys close failed", errors)
        logger.info("[Genesys] Handler stopped | session=%s", self.session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Inbound message processing (from Genesys)
    # ─────────────────────────────────────────────────────────────────────────

    async def handle_text_message(self, raw: str) -> None:
        """Process an inbound text (JSON) message from Genesys."""
        if not self._running:
            return

        msg = self._protocol.validate_message(raw)
        if msg is None:
            await self._enqueue_message(
                self._protocol.create_disconnect("error", "Invalid message format or sequence"),
                drop_audio=True,
            )
            return

        msg_type = msg.get("type", "")
        logger.debug("[Genesys] Received %s | session=%s", msg_type, self.session_id)

        if msg_type == CLIENT_MSG_OPEN:
            await self._handle_open(msg)
        elif msg_type == CLIENT_MSG_CLOSE:
            await self._handle_close()
        elif msg_type == CLIENT_MSG_PING:
            await self._handle_ping()
        elif msg_type == CLIENT_MSG_PLAYBACK_STARTED:
            self._is_playing = True
        elif msg_type == CLIENT_MSG_PLAYBACK_COMPLETED:
            self._is_playing = False
        elif msg_type == CLIENT_MSG_DTMF:
            digit = msg.get("parameters", {}).get("digit")
            if digit:
                await self._handle_dtmf(digit)
        elif msg_type == CLIENT_MSG_ERROR:
            code = msg.get("parameters", {}).get("code")
            err_msg = msg.get("parameters", {}).get("message", "")
            logger.warning(
                "[Genesys] Client error: code=%s msg=%s | session=%s",
                code,
                err_msg,
                self.session_id,
            )
        elif msg_type == CLIENT_MSG_UPDATE:
            await self._enqueue_message(self._protocol.create_updated())
        else:
            logger.debug("[Genesys] Unhandled message type: %s", msg_type)

    async def handle_binary_message(self, data: bytes) -> None:
        """Process inbound binary audio (µ-law 8kHz) from Genesys."""
        if not self._running or not self._session_opened or not self._connection:
            return

        try:
            pcm16_bytes = self._inbound_audio_decoder.decode_chunk(data)
            if pcm16_bytes:
                await self._connection.input_audio_buffer.append(
                    audio=self._encode_pcm16_b64(pcm16_bytes)
                )
        except Exception as exc:
            logger.exception(
                "[Genesys] Failed to forward audio to VoiceLive | session=%s", self.session_id
            )
            await self._enqueue_message(
                self._protocol.create_disconnect(
                    DISCONNECT_ERROR,
                    f"Genesys inbound audio conversion failed: {exc}",
                ),
                drop_audio=True,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Protocol message handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_open(self, msg: dict[str, Any]) -> None:
        """Process session open and establish VoiceLive connection."""
        media = self._protocol.process_open(msg)
        if not media:
            await self._enqueue_message(
                self._protocol.create_disconnect("error", "No supported media format"),
                drop_audio=True,
            )
            return

        # Send opened response immediately
        await self._enqueue_message(self._protocol.create_opened(media))
        self._session_opened = True

        # Update messenger with conversation context
        self._messenger._call_id = self._protocol.conversation_id
        self._messenger._session_id = self._protocol.conversation_id or self.session_id

        # Establish VoiceLive connection and start orchestrator
        try:
            self._connect_task = asyncio.create_task(
                self._connect_voicelive(), name="genesys-connect"
            )
            await asyncio.shield(self._connect_task)
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception as e:
            self._session_opened = False
            logger.exception(
                "[Genesys] Failed to connect to VoiceLive | session=%s", self.session_id
            )
            await self._enqueue_message(
                self._protocol.create_disconnect("error", f"VoiceLive connection failed: {e}"),
                drop_audio=True,
            )
            return

    async def _handle_close(self) -> None:
        """Handle session close request."""
        await self._enqueue_message(self._protocol.create_closed(), drop_audio=True)
        logger.info("[Genesys] Session closed by client | session=%s", self.session_id)

    async def _handle_ping(self) -> None:
        """Respond to keep-alive ping."""
        await self._enqueue_message(self._protocol.create_pong())

    async def _handle_dtmf(self, digit: str) -> None:
        """Forward DTMF digit as text input to VoiceLive."""
        if not self._connection:
            return

        logger.info("[Genesys] DTMF digit: %s | session=%s", digit, self.session_id)
        # DTMF digits are forwarded as text to the model
        if self._orchestrator:
            from azure.ai.voicelive.models import (
                ClientEventConversationItemCreate,
                ClientEventResponseCreate,
                InputTextContentPart,
                UserMessageItem,
            )

            dtmf_item = ClientEventConversationItemCreate(
                item=UserMessageItem(
                    content=[InputTextContentPart(text=f"DTMF digit pressed: {digit}")]
                )
            )
            await self._connection.send(dtmf_item)
            await self._connection.send(ClientEventResponseCreate())

    # ─────────────────────────────────────────────────────────────────────────
    # VoiceLive connection and event processing
    # ─────────────────────────────────────────────────────────────────────────

    async def _connect_voicelive(self) -> None:
        """Establish VoiceLive WebSocket and initialise the orchestrator."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        self._settings = get_settings()

        connection_options = {
            "max_msg_size": self._settings.ws_max_msg_size,
            "heartbeat": self._settings.ws_heartbeat,
            "timeout": self._settings.ws_timeout,
        }
        redis_mgr = getattr(self.websocket.app.state, "redis", None)
        effective_session_id = self._protocol.conversation_id or self.session_id
        memo_manager = (
            await MemoManager.from_redis_async(effective_session_id, redis_mgr)
            if redis_mgr is not None
            else MemoManager(session_id=effective_session_id)
        )
        self._memo_manager = memo_manager
        self.websocket.state.cm = memo_manager
        from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

        await prime_session_definitions(self.session_id, memo=memo_manager)
        session_manager = getattr(self.websocket.app.state, "session_manager", None)
        if session_manager is not None:
            await session_manager.add_session(self.session_id, memo_manager, self.websocket)

        # Resolve agents BEFORE connecting: the VoiceLive SDK binds the generative model
        # at connect() time and it cannot be changed via session.update() afterwards, so
        # the start agent's voicelive_model override must be applied up front.
        agents, orchestrator_config, effective_start_agent, handoff_map = (
            await self._resolve_agents()
        )

        start_agent_obj = agents.get(effective_start_agent) if agents else None
        connection_model = self._settings.azure_voicelive_model
        byom_query: dict[str, str] | None = None
        if start_agent_obj is not None:
            try:
                vl_model = start_agent_obj.get_model_for_mode("voicelive")
                if vl_model and getattr(vl_model, "deployment_id", None):
                    connection_model = vl_model.deployment_id
                byom_query = start_agent_obj.get_byom_query()
            except Exception as model_err:  # pragma: no cover - defensive
                logger.warning(
                    "[Genesys] Failed to resolve per-agent model for %s, falling back to %s | err=%s",
                    effective_start_agent,
                    self._settings.azure_voicelive_model,
                    model_err,
                )
        if connection_model != self._settings.azure_voicelive_model:
            logger.info(
                "[Genesys] Using per-agent model override | agent=%s model=%s (default=%s) session=%s",
                effective_start_agent,
                connection_model,
                self._settings.azure_voicelive_model,
                self.session_id,
            )
        if byom_query:
            conflict = byom_profile_model_conflict(byom_query.get("profile"), connection_model)
            if conflict:
                logger.warning(
                    "[Genesys] byom_profile_model_conflict | agent=%s profile=%s model=%s "
                    "session=%s — %s Falling back to managed Voice Live for this connection.",
                    effective_start_agent,
                    byom_query.get("profile"),
                    connection_model,
                    self.session_id,
                    conflict,
                )
                byom_query = None

        transcription = validate_voicelive_transcription(
            (
                (start_agent_obj.session or {}).get("input_audio_transcription_settings")
                if start_agent_obj
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
                "[Genesys] Using BYOM profile | agent=%s model=%s profile=%s%s session=%s",
                effective_start_agent,
                connection_model,
                byom_query.get("profile"),
                (
                    f" foundry_override={byom_query['foundry-resource-override']}"
                    if "foundry-resource-override" in byom_query
                    else ""
                ),
                self.session_id,
            )

        try:
            self._credential = await VoiceLiveSDKHandler._build_credential(self._settings)

            t0 = time.perf_counter()
            self._connection_cm = connect(
                endpoint=self._settings.azure_voicelive_endpoint,
                credential=self._credential,
                model=connection_model,
                connection_options=connection_options,
                **({"query": byom_query} if byom_query else {}),
                **({"api_version": api_version} if api_version else {}),
            )
            self._connection = await self._connection_cm.__aenter__()
            connect_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "[Genesys] VoiceLive connected | connect_ms=%.1f session=%s",
                connect_ms,
                self.session_id,
            )

            # Store input variables in memo manager
            if memo_manager and self._protocol.input_variables:
                for key, value in self._protocol.input_variables.items():
                    memo_manager.set_corememory(key, value)

            self._orchestrator = LiveOrchestrator(
                conn=self._connection,
                agents=agents,
                handoff_map=handoff_map,
                start_agent=effective_start_agent,
                audio_processor=None,
                messenger=self._messenger,
                call_connection_id=self._protocol.conversation_id or self.session_id,
                transport="genesys",
                model_name=connection_model,
                byom_profile=(byom_query or {}).get("profile"),
                memo_manager=memo_manager,
                orchestrator_config=orchestrator_config,
            )

            register_voicelive_orchestrator(self.session_id, self._orchestrator)

            # Build system vars from Genesys input variables
            system_vars: dict[str, Any] = {}
            iv = self._protocol.input_variables
            if iv.get("phoneNumber"):
                system_vars["caller_phone"] = iv["phoneNumber"]
            if iv.get("emailAddress"):
                system_vars["caller_email"] = iv["emailAddress"]
            if iv.get("promptName"):
                system_vars["genesys_prompt"] = iv["promptName"]

            await self._orchestrator.start(system_vars=system_vars)

            self._event_task = asyncio.create_task(
                self._event_loop(), name="genesys-voicelive-events"
            )
            logger.info("[Genesys] Orchestrator started | session=%s", self.session_id)
        except Exception:
            await self._close_voicelive_runtime()
            raise

    async def _resolve_agents(
        self,
    ) -> tuple[dict, Any, str, dict[str, str]]:
        """Resolve agents, scenario, and handoff map."""
        app_state = getattr(self.websocket, "app", None)
        if app_state:
            app_state = getattr(app_state, "state", None)

        scenario_name = None
        agents = None

        if app_state and hasattr(app_state, "unified_agents") and app_state.unified_agents:
            agents = app_state.unified_agents
        else:
            agents = discover_agents()

        orchestrator_config = resolve_orchestrator_config(
            session_id=self.session_id,
            scenario_name=scenario_name,
        )

        # Shared merge: scenario overrides overlay the full registry, the session
        # agent (Agent Builder / Quick Tune) replaces its slot and becomes the start
        # agent, and scenario handoff edges overlay the global map.
        session_agent = get_session_agent(self.session_id)
        agents, effective_start_agent, handoff_map = build_effective_registry(
            orchestrator_config,
            base_agents=agents,
            session_agent=session_agent,
            app_state_handoff_map=getattr(app_state, "handoff_map", None),
        )
        if not session_agent and not getattr(orchestrator_config, "start_agent", None):
            effective_start_agent = DEFAULT_START_AGENT

        logger.info(
            "[Genesys] Agents resolved | count=%d start=%s session=%s",
            len(agents),
            effective_start_agent,
            self.session_id,
        )
        return agents, orchestrator_config, effective_start_agent, handoff_map

    async def _event_loop(self) -> None:
        """Consume VoiceLive events and forward audio/events to Genesys."""
        assert self._connection is not None
        event_count = 0
        try:
            async for event in self._connection:
                if self._shutdown.is_set():
                    break

                event_count += 1
                etype = event.type if hasattr(event, "type") else None

                # Forward audio to Genesys (highest priority)
                await self._handle_voicelive_event(event, etype)

                # Orchestrator handles agents, tools, handoffs
                if self._orchestrator:
                    await self._orchestrator.handle_event(event)

        except asyncio.CancelledError:
            logger.debug("[Genesys] Event loop cancelled | events=%d", event_count)
        except Exception:
            logger.exception("[Genesys] Event loop error | events=%d", event_count)
        finally:
            self._shutdown.set()

    async def _handle_voicelive_event(self, event: Any, etype: Any) -> None:
        """Map VoiceLive events to Genesys AudioHook v2 protocol actions."""
        if etype == ServerEventType.RESPONSE_CREATED:
            response_id = self._extract_response_id(event)
            if response_id and response_id not in self._cancelled_response_ids:
                self._current_response_id = response_id

        elif etype == ServerEventType.RESPONSE_AUDIO_DELTA:
            delta = getattr(event, "delta", None)
            if not delta:
                logger.warning("[Genesys] Audio delta with no data | session=%s", self.session_id)
                return

            response_id = self._extract_response_id(event)
            if not response_id:
                logger.warning(
                    "[Genesys] Dropping audio delta without response id | session=%s",
                    self.session_id,
                )
                return
            if response_id in self._cancelled_response_ids:
                logger.debug(
                    "[Genesys] Dropping late audio for cancelled response=%s | session=%s",
                    response_id,
                    self.session_id,
                )
                return

            if response_id and response_id not in self._active_response_ids:
                self._active_response_ids.add(response_id)
                self._is_playing = True
                logger.info(
                    "[Genesys] First audio chunk for response=%s | session=%s",
                    response_id,
                    self.session_id,
                )
            self._current_response_id = response_id

            try:
                delta_type = type(delta).__name__
                delta_size = len(delta) if isinstance(delta, (bytes, str)) else 0
                ulaw_bytes = await self._convert_voicelive_delta(delta, response_id=response_id)
                logger.info(
                    "[Genesys] Audio delta: response=%s input_type=%s input_size=%d → µ-law_size=%d | session=%s",
                    response_id,
                    delta_type,
                    delta_size,
                    len(ulaw_bytes),
                    self.session_id,
                )
                await self._enqueue_binary(ulaw_bytes, response_id=response_id)
            except Exception as exc:
                await self._handle_conversion_failure(
                    direction="outbound",
                    exc=exc,
                    response_id=response_id,
                )

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            await self._handle_response_done_event(event, label="audio done")
            logger.debug("[Genesys] Audio done | session=%s", self.session_id)

        elif etype == ServerEventType.RESPONSE_DONE:
            await self._handle_response_done_event(event, label="response done")
            self._is_playing = False
            logger.debug("[Genesys] Response done | session=%s", self.session_id)

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            logger.info("[Genesys] Speech started → barge-in | session=%s", self.session_id)
            await self._invalidate_active_audio()
            await self._enqueue_message(self._protocol.create_barge_in_event(), drop_audio=True)
            self._is_playing = False

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            logger.debug("[Genesys] Speech stopped | session=%s", self.session_id)

        elif etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = getattr(event, "transcript", "")
            if transcript:
                logger.info(
                    "[Genesys] User transcript: '%s' | session=%s",
                    transcript,
                    self.session_id,
                )
                await self._enqueue_message(self._protocol.create_transcript_event(transcript))

        elif etype == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            # LLM streaming text (logged for debugging)
            pass

        elif etype == ServerEventType.ERROR:
            error_msg = getattr(event, "message", "") or str(event)
            logger.error("[Genesys] VoiceLive error: %s | session=%s", error_msg, self.session_id)

        else:
            logger.info(
                "[Genesys] Unhandled VoiceLive event: %s | session=%s", etype, self.session_id
            )

    @staticmethod
    def _extract_response_id(event: Any) -> str | None:
        response = getattr(event, "response", None)
        if response:
            return getattr(response, "id", None)
        return getattr(event, "response_id", None)

    # ─────────────────────────────────────────────────────────────────────────
    # Outbound message queue (single writer for sequence integrity)
    # ─────────────────────────────────────────────────────────────────────────

    async def _enqueue_message(self, msg: dict[str, Any], *, drop_audio: bool = False) -> None:
        """Enqueue a JSON protocol message for serialised sending."""
        if drop_audio:
            await self._stop_pacer()
            await self._clear_buffered_audio()
        async with self._queue_lock:
            self._outbound_queue.put_nowait(msg)

    async def _enqueue_binary(self, data: bytes, *, response_id: str) -> None:
        """Accumulate audio data. A pacer task drains it at real-time rate."""
        if not data:
            return
        if response_id in self._cancelled_response_ids:
            return
        if self._pending_audio_bytes + len(data) > self._MAX_OUTBOUND_AUDIO_BYTES:
            logger.warning(
                "[Genesys] Dropping audio: outbound buffer limit exceeded | response=%s pending=%d incoming=%d limit=%d session=%s",
                response_id,
                self._pending_audio_bytes,
                len(data),
                self._MAX_OUTBOUND_AUDIO_BYTES,
                self.session_id,
            )
            return
        async with self._queue_lock:
            buffer = self._response_audio_buffers.get(response_id)
            if buffer is None:
                buffer = bytearray()
                self._response_audio_buffers[response_id] = buffer
            buffer.extend(data)
            self._pending_audio_bytes += len(data)
            self._remember_buffered_response_locked(response_id)
        self._ensure_pacer_running()

    async def _audio_pacer(self) -> None:
        """Send buffered audio at real-time rate (~200ms chunks every 200ms).

        Mirrors the AudioPacedSender from the reference genesys-voice-live-connector.
        The key: wait a full interval FIRST to let the buffer accumulate, then send
        one chunk-worth of data every interval. This ensures smooth playback.
        """
        try:
            while self._running:
                # Wait first, then send — this lets audio accumulate
                await asyncio.sleep(self._AUDIO_PACE_MS / 1000.0)

                item = await self._dequeue_next_audio_chunk()
                if item is None:
                    return
                async with self._queue_lock:
                    self._outbound_queue.put_nowait(item)
        except asyncio.CancelledError:
            pass

    async def _flush_audio_buffer(self, *, response_id: str | None) -> None:
        """Move buffered audio for a response to the writer queue without pacing."""
        if response_id is None:
            return
        while True:
            item = await self._dequeue_response_chunk(response_id)
            if item is None:
                break
            async with self._queue_lock:
                self._outbound_queue.put_nowait(item)

    async def _outbound_writer(self) -> None:
        """Single writer task that sends all outbound frames to Genesys.

        This ensures proper sequence numbering and prevents interleaving
        of JSON protocol messages and binary audio frames.
        """
        try:
            while self._running or not self._outbound_queue.empty():
                try:
                    item = await asyncio.wait_for(self._outbound_queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                if item is None:
                    break

                if not self._websocket_open:
                    continue

                try:
                    if isinstance(item, dict):
                        msg_type = item.get("type", "")
                        logger.debug(
                            "[Genesys] Sending %s | session=%s",
                            msg_type,
                            self.session_id,
                        )
                        await self.websocket.send_text(json.dumps(item))
                        if msg_type == "disconnect":
                            self._terminal_disconnect_sent = True
                    elif isinstance(item, _OutboundAudioFrame):
                        if item.response_id in self._cancelled_response_ids:
                            self._pending_audio_bytes = max(
                                0,
                                self._pending_audio_bytes - len(item.payload),
                            )
                            continue
                        await self.websocket.send_bytes(item.payload)
                        self._pending_audio_bytes = max(
                            0,
                            self._pending_audio_bytes - len(item.payload),
                        )
                except Exception:
                    logger.debug("Failed to send outbound frame", exc_info=True)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[Genesys] Outbound writer error")

    @property
    def _websocket_open(self) -> bool:
        """Check if the WebSocket is still connected."""
        try:
            return (
                self.websocket.client_state == WebSocketState.CONNECTED
                and self.websocket.application_state == WebSocketState.CONNECTED
            )
        except Exception:
            return False

    @staticmethod
    def _encode_pcm16_b64(raw_bytes: bytes) -> str:
        from base64 import b64encode

        return b64encode(raw_bytes).decode("ascii")

    async def _convert_voicelive_delta(self, delta: bytes | str, *, response_id: str) -> bytes:
        if self._outbound_audio_response_id not in (None, response_id):
            await self._flush_outbound_encoder(self._outbound_audio_response_id)
        if self._outbound_audio_response_id != response_id:
            self._outbound_audio_encoder = PCM16_24kToULaw8kStreamEncoder()
            self._outbound_audio_response_id = response_id

        if isinstance(delta, bytes):
            return self._outbound_audio_encoder.encode_chunk(delta)
        if isinstance(delta, str):
            return self._outbound_audio_encoder.encode_base64_chunk(delta)
        raise TypeError(f"Unsupported VoiceLive audio delta type: {type(delta).__name__}")

    async def _flush_outbound_encoder(self, response_id: str | None) -> None:
        if not response_id or self._outbound_audio_response_id != response_id:
            return
        tail = self._outbound_audio_encoder.flush()
        self._outbound_audio_encoder = PCM16_24kToULaw8kStreamEncoder()
        self._outbound_audio_response_id = None
        if tail:
            await self._enqueue_binary(tail, response_id=response_id)

    async def _handle_conversion_failure(
        self,
        *,
        direction: str,
        exc: Exception,
        response_id: str | None = None,
    ) -> None:
        logger.exception(
            "[Genesys] %s audio conversion failed | session=%s",
            direction,
            self.session_id,
            exc_info=exc,
        )
        if response_id:
            self._cancelled_response_ids.add(response_id)
            self._active_response_ids.discard(response_id)
            if self._current_response_id == response_id:
                self._current_response_id = None
        await self._clear_buffered_audio(response_ids={response_id} if response_id else None)
        self._reset_outbound_encoder(response_id=response_id)

        if not self._terminal_disconnect_enqueued:
            self._terminal_disconnect_enqueued = True
            self._terminal_disconnect_sent = False
            await self._enqueue_message(
                self._protocol.create_disconnect(
                    DISCONNECT_ERROR,
                    f"Genesys {direction} audio conversion failed: {exc}",
                ),
                drop_audio=True,
            )
        self._schedule_terminal_shutdown()

    async def _invalidate_active_audio(self) -> None:
        invalidated = set(self._active_response_ids)
        if self._current_response_id:
            invalidated.add(self._current_response_id)
        if not invalidated:
            return
        self._cancelled_response_ids.update(invalidated)
        self._active_response_ids.difference_update(invalidated)
        self._current_response_id = None
        await self._stop_pacer()
        await self._clear_buffered_audio(response_ids=invalidated)

    async def _stop_pacer(self) -> None:
        task = self._pacer_task
        self._pacer_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # Expected acknowledgement of the cancellation requested above.
                pass

    async def _close_voicelive_runtime(self, *, producers_quiesced: bool = True) -> None:
        if self._orchestrator is not None:
            unregister_voicelive_orchestrator(self.session_id, expected=self._orchestrator)
        errors: list[Exception] = []
        try:
            await cancel_and_join([self._event_task] if self._event_task else [])
        except Exception as exc:
            errors.append(exc)
        try:
            if self._orchestrator:
                await self._orchestrator.cancel_and_join_tasks()
        except Exception as exc:
            errors.append(exc)
        quiesced = producers_quiesced and not errors
        try:
            if quiesced and self._orchestrator:
                self._orchestrator._sync_to_memo_manager()
        except Exception as exc:
            errors.append(exc)
        try:
            redis = getattr(self.websocket.app.state, "redis", None)
            await finish_persistence(self._memo_manager, redis, quiesced=quiesced and not errors)
        except Exception as exc:
            errors.append(exc)
        if self._connection_cm:
            try:
                await self._connection_cm.__aexit__(None, None, None)
            except Exception as exc:
                errors.append(exc)
            else:
                self._connection_cm = None
                self._connection = None
        from apps.artagent.backend.src.orchestration.session_memory import (
            release_session_memory,
        )

        try:
            await release_session_memory(self.session_id, self._memo_manager, self.websocket)
        except Exception as exc:
            errors.append(exc)
        if quiesced:
            self._event_task = None
            if self._orchestrator:
                self._orchestrator.cleanup()
                self._orchestrator = None
        if errors:
            raise ExceptionGroup("Genesys VoiceLive runtime close failed", errors)

    async def _clear_outbound_queue(self) -> None:
        async with self._queue_lock:
            kept_sentinel = False
            while True:
                try:
                    item = self._outbound_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item is None:
                    kept_sentinel = True
                    continue
                if isinstance(item, _OutboundAudioFrame):
                    self._pending_audio_bytes = max(
                        0,
                        self._pending_audio_bytes - len(item.payload),
                    )
            if kept_sentinel:
                self._outbound_queue.put_nowait(None)

    async def _clear_buffered_audio(self, response_ids: set[str] | None = None) -> None:
        async with self._queue_lock:
            self._drop_queued_audio_locked(response_ids=response_ids)
            if response_ids is None:
                for response_id, buffer in self._response_audio_buffers.items():
                    self._pending_audio_bytes = max(0, self._pending_audio_bytes - len(buffer))
                    self._buffered_response_ids.discard(response_id)
                self._response_audio_buffers.clear()
                self._response_audio_order.clear()
                self._buffered_response_ids.clear()
            else:
                self._response_audio_order = deque(
                    response_id
                    for response_id in self._response_audio_order
                    if response_id not in response_ids
                )
                self._buffered_response_ids.difference_update(response_ids)
                for response_id in response_ids:
                    buffer = self._response_audio_buffers.pop(response_id, None)
                    if buffer is not None:
                        self._pending_audio_bytes = max(0, self._pending_audio_bytes - len(buffer))
            if response_ids is None or (
                self._outbound_audio_response_id is not None
                and self._outbound_audio_response_id in response_ids
            ):
                self._reset_outbound_encoder(response_id=None)

    def _drop_queued_audio_locked(self, *, response_ids: set[str] | None) -> None:
        kept: list[_OutboundAudioFrame | dict[str, Any] | None] = []
        while True:
            try:
                item = self._outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(item, _OutboundAudioFrame) and (
                response_ids is None or item.response_id in response_ids
            ):
                self._pending_audio_bytes = max(0, self._pending_audio_bytes - len(item.payload))
                continue
            kept.append(item)
        for item in kept:
            self._outbound_queue.put_nowait(item)

    async def _dequeue_next_audio_chunk(self) -> _OutboundAudioFrame | None:
        async with self._queue_lock:
            while self._response_audio_order:
                response_id = self._response_audio_order[0]
                if response_id in self._cancelled_response_ids:
                    self._discard_response_audio_locked(response_id)
                    continue
                buffer = self._response_audio_buffers.get(response_id)
                if not buffer:
                    self._forget_buffered_response_locked(response_id)
                    self._response_audio_buffers.pop(response_id, None)
                    continue
                chunk = bytes(buffer[: self._AUDIO_CHUNK_SIZE])
                del buffer[: self._AUDIO_CHUNK_SIZE]
                if not buffer:
                    self._response_audio_buffers.pop(response_id, None)
                    self._forget_buffered_response_locked(response_id)
                return _OutboundAudioFrame(response_id=response_id, payload=chunk)
        return None

    async def _dequeue_response_chunk(self, response_id: str) -> _OutboundAudioFrame | None:
        async with self._queue_lock:
            if response_id in self._cancelled_response_ids:
                self._discard_response_audio_locked(response_id)
                return None
            buffer = self._response_audio_buffers.get(response_id)
            if not buffer:
                self._forget_buffered_response_locked(response_id)
                self._response_audio_buffers.pop(response_id, None)
                return None
            chunk = bytes(buffer[: self._AUDIO_CHUNK_SIZE])
            del buffer[: self._AUDIO_CHUNK_SIZE]
            if not buffer:
                self._response_audio_buffers.pop(response_id, None)
                self._forget_buffered_response_locked(response_id)
            return _OutboundAudioFrame(response_id=response_id, payload=chunk)

    async def _handle_response_done_event(self, event: Any, *, label: str) -> None:
        response_id = self._extract_response_id(event)
        if response_id is None:
            logger.warning(
                "[Genesys] %s without response id; leaving response-local state untouched | session=%s",
                label.capitalize(),
                self.session_id,
            )
            return
        try:
            await self._flush_outbound_encoder(response_id)
        except Exception as exc:
            await self._handle_conversion_failure(
                direction="outbound",
                exc=exc,
                response_id=response_id,
            )
            return
        self._cancelled_response_ids.discard(response_id)
        if self._current_response_id == response_id:
            self._current_response_id = None
        self._active_response_ids.discard(response_id)
        self._ensure_pacer_running()

    def _remember_buffered_response_locked(self, response_id: str) -> None:
        if response_id in self._buffered_response_ids:
            return
        self._buffered_response_ids.add(response_id)
        self._response_audio_order.append(response_id)

    def _forget_buffered_response_locked(self, response_id: str) -> None:
        self._buffered_response_ids.discard(response_id)
        try:
            self._response_audio_order.remove(response_id)
        except ValueError:
            # Draining or discarding may already have removed this response.
            pass

    def _discard_response_audio_locked(self, response_id: str) -> None:
        buffer = self._response_audio_buffers.pop(response_id, None)
        if buffer is not None:
            self._pending_audio_bytes = max(0, self._pending_audio_bytes - len(buffer))
        self._forget_buffered_response_locked(response_id)

    def _ensure_pacer_running(self) -> None:
        if self._pacer_task is None or self._pacer_task.done():
            self._pacer_task = asyncio.create_task(self._audio_pacer(), name="genesys-audio-pacer")

    def _reset_outbound_encoder(self, *, response_id: str | None) -> None:
        if response_id is not None and self._outbound_audio_response_id != response_id:
            return
        self._outbound_audio_encoder = PCM16_24kToULaw8kStreamEncoder()
        self._outbound_audio_response_id = None

    def _schedule_terminal_shutdown(self) -> None:
        if self._terminal_shutdown_task and not self._terminal_shutdown_task.done():
            return
        self._terminal_shutdown_task = asyncio.create_task(
            self._shutdown_after_terminal_message(),
            name="genesys-terminal-shutdown",
        )

    async def _shutdown_after_terminal_message(self) -> None:
        deadline = time.monotonic() + 1.0
        while (
            self._writer_task
            and not self._writer_task.done()
            and self._websocket_open
            and not self._terminal_disconnect_sent
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.01)
        await self.stop()
