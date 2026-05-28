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
import base64
import json
import time
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.registries.agentstore.loader import (
    build_handoff_map,
    discover_agents,
)
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
from apps.artagent.backend.voice.shared import (
    DEFAULT_START_AGENT,
    resolve_from_app_state,
    resolve_orchestrator_config,
)
from apps.artagent.backend.voice.voicelive.orchestrator import (
    LiveOrchestrator,
    register_voicelive_orchestrator,
    unregister_voicelive_orchestrator,
)
from apps.artagent.backend.voice.voicelive.settings import get_settings
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import ServerEventType
from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from utils.ml_logging import get_logger

from .audio_codec import convert_voicelive_delta_to_ulaw, ulaw_8khz_to_pcm16_24khz_b64
from .protocol import (
    CLIENT_MSG_CLOSE,
    CLIENT_MSG_DTMF,
    CLIENT_MSG_ERROR,
    CLIENT_MSG_OPEN,
    CLIENT_MSG_PING,
    CLIENT_MSG_PLAYBACK_COMPLETED,
    CLIENT_MSG_PLAYBACK_STARTED,
    CLIENT_MSG_UPDATE,
    DISCONNECT_COMPLETED,
    DISCONNECT_ERROR,
    GenesysProtocol,
)

if TYPE_CHECKING:
    from src.stateful.state_managment import MemoManager

logger = get_logger("genesys.handler")
tracer = trace.get_tracer(__name__)

# Module-level credential cache (shared across sessions)
_CACHED_CREDENTIAL: DefaultAzureCredential | None = None
_CREDENTIAL_LOCK = asyncio.Lock()


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
        self, text: str, *, sender: str | None = None,
        response_id: str | None = None, status: str | None = None,
    ) -> None:
        logger.info("[Genesys] Assistant: %s | session=%s", text, self._session_id)

    async def send_assistant_streaming(
        self, text: str, *, sender: str | None = None,
        response_id: str | None = None,
    ) -> None:
        pass

    async def send_assistant_cancelled(
        self, *, response_id: str | None, sender: str | None = None,
        reason: str | None = None,
    ) -> None:
        logger.debug("[Genesys] Assistant cancelled | session=%s", self._session_id)

    async def send_session_update(
        self, *, agent_name: str | None, session_obj: Any | None,
        transport: str | None = None,
    ) -> None:
        pass

    async def send_status_update(
        self, text: str, *, tone: str | None = None,
        caption: str | None = None, sender: str | None = None,
        event_label: str = "genesys_status",
    ) -> None:
        pass

    async def notify_tool_start(
        self, *, call_id: str | None, name: str | None, args: dict[str, Any],
    ) -> None:
        logger.debug("[Genesys] Tool start: %s | session=%s", name, self._session_id)

    async def notify_tool_end(
        self, *, call_id: str | None, name: str | None, status: str,
        elapsed_ms: float, result: dict[str, Any] | None = None,
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
        self._credential: AzureKeyCredential | DefaultAzureCredential | None = None
        self._connection = None
        self._connection_cm = None
        self._orchestrator: LiveOrchestrator | None = None

        self._running = False
        self._session_opened = False
        self._shutdown = asyncio.Event()
        self._event_task: asyncio.Task | None = None

        # Serialised outbound queue (prevents seq number corruption)
        self._outbound_queue: asyncio.Queue[bytes | dict[str, Any]] = asyncio.Queue()
        self._writer_task: asyncio.Task | None = None

        # Audio playback state
        self._is_playing = False
        self._audio_buffer: list[bytes] = []
        self._active_response_ids: set[str] = set()

        # Accumulate small audio chunks before sending (200ms = 1600 bytes at 8kHz µ-law)
        self._audio_accum = bytearray()
        self._AUDIO_CHUNK_SIZE = 2000  # 250ms at 8kHz µ-law mono (1 byte/sample)
        self._AUDIO_PACE_MS = 250  # Send one chunk every 250ms (matching reference)
        self._pacer_task: asyncio.Task | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the outbound writer. VoiceLive connection is deferred to session open."""
        self._running = True
        self._shutdown.clear()
        self._writer_task = asyncio.create_task(self._outbound_writer(), name="genesys-writer")
        logger.info("[Genesys] Handler started | session=%s", self.session_id)

    async def stop(self) -> None:
        """Shut down VoiceLive connection, orchestrator, and outbound writer."""
        if not self._running:
            return

        self._running = False
        self._shutdown.set()

        unregister_voicelive_orchestrator(self.session_id)

        if self._orchestrator:
            try:
                self._orchestrator.cleanup()
            except Exception:
                logger.debug("Failed to cleanup orchestrator", exc_info=True)
            self._orchestrator = None

        if self._event_task:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None

        if self._connection_cm:
            try:
                await self._connection_cm.__aexit__(None, None, None)
            except Exception:
                logger.debug("Error closing VoiceLive connection", exc_info=True)
            self._connection_cm = None
            self._connection = None

        # Drain and stop writer
        if self._writer_task:
            # Signal writer to exit
            await self._outbound_queue.put(None)  # type: ignore[arg-type]
            try:
                await asyncio.wait_for(self._writer_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._writer_task.cancel()
            self._writer_task = None

        self._credential = None
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
                self._protocol.create_disconnect(
                    "error", "Invalid message format or sequence"
                )
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
                code, err_msg, self.session_id,
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
            pcm16_b64 = ulaw_8khz_to_pcm16_24khz_b64(data)
            await self._connection.input_audio_buffer.append(audio=pcm16_b64)
        except Exception:
            logger.debug("Failed to forward audio to VoiceLive", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Protocol message handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_open(self, msg: dict[str, Any]) -> None:
        """Process session open and establish VoiceLive connection."""
        media = self._protocol.process_open(msg)
        if not media:
            await self._enqueue_message(
                self._protocol.create_disconnect("error", "No supported media format")
            )
            return

        # Connection probe: Genesys validates the integration with a synthetic
        # session (null-UUID conversationId) on activate/save. Complete the
        # open/opened handshake so the probe passes, but do NOT allocate VoiceLive
        # or orchestrator resources for it (per AudioHook patterns-and-practices).
        if self._protocol.is_connection_probe(msg):
            logger.info(
                "[Genesys] Connection probe detected — short-circuiting open "
                "(no VoiceLive allocation) | session=%s",
                self.session_id,
            )
            await self._enqueue_message(self._protocol.create_opened(media))
            self._session_opened = True
            return

        # Send opened response immediately
        await self._enqueue_message(self._protocol.create_opened(media))
        self._session_opened = True

        # Update messenger with conversation context
        self._messenger._call_id = self._protocol.conversation_id
        self._messenger._session_id = self._protocol.conversation_id or self.session_id

        # Establish VoiceLive connection and start orchestrator
        try:
            await self._connect_voicelive()
        except Exception as e:
            logger.exception("[Genesys] Failed to connect to VoiceLive | session=%s", self.session_id)
            await self._enqueue_message(
                self._protocol.create_disconnect("error", f"VoiceLive connection failed: {e}")
            )
            return

    async def _handle_close(self) -> None:
        """Handle session close request."""
        await self._enqueue_message(self._protocol.create_closed())
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
                InputTextContentPart,
                UserMessageItem,
                ClientEventConversationItemCreate,
                ClientEventResponseCreate,
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
        self._settings = get_settings()

        # Build credential
        if self._settings.azure_voicelive_api_key and not self._settings.use_default_credential:
            self._credential = AzureKeyCredential(self._settings.azure_voicelive_api_key)
        else:
            global _CACHED_CREDENTIAL, _CREDENTIAL_LOCK
            async with _CREDENTIAL_LOCK:
                if _CACHED_CREDENTIAL is None:
                    _CACHED_CREDENTIAL = DefaultAzureCredential()
                self._credential = _CACHED_CREDENTIAL

        connection_options = {
            "max_msg_size": self._settings.ws_max_msg_size,
            "heartbeat": self._settings.ws_heartbeat,
            "timeout": self._settings.ws_timeout,
        }

        # Connect to VoiceLive
        t0 = time.perf_counter()
        self._connection_cm = connect(
            endpoint=self._settings.azure_voicelive_endpoint,
            credential=self._credential,
            model=self._settings.azure_voicelive_model,
            connection_options=connection_options,
        )
        self._connection = await self._connection_cm.__aenter__()
        connect_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[Genesys] VoiceLive connected | connect_ms=%.1f session=%s",
            connect_ms, self.session_id,
        )

        # Resolve agents (reuse same logic as VoiceLiveSDKHandler)
        agents, orchestrator_config, effective_start_agent, handoff_map = (
            await self._resolve_agents()
        )

        # Build MemoManager
        redis_mgr = getattr(self.websocket.app.state, "redis", None) if self.websocket else None
        effective_session_id = self._protocol.conversation_id or self.session_id
        memo_manager = None
        if redis_mgr:
            from src.stateful.state_managment import MemoManager

            memo_manager = MemoManager.from_redis(effective_session_id, redis_mgr)

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
            model_name=self._settings.azure_voicelive_model,
            memo_manager=memo_manager,
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

        # Start event processing loop
        self._event_task = asyncio.create_task(
            self._event_loop(), name="genesys-voicelive-events"
        )
        logger.info("[Genesys] Orchestrator started | session=%s", self.session_id)

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

        # Merge scenario agents
        if orchestrator_config and orchestrator_config.has_scenario and orchestrator_config.agents:
            merged = dict(agents)
            merged.update(orchestrator_config.agents)
            agents = merged

        # Session agent (Agent Builder)
        session_agent = get_session_agent(self.session_id)
        if session_agent:
            agents = dict(agents)
            agents[session_agent.name] = session_agent

        # Determine start agent
        effective_start_agent = DEFAULT_START_AGENT
        if session_agent:
            effective_start_agent = session_agent.name
        elif orchestrator_config and orchestrator_config.start_agent:
            effective_start_agent = orchestrator_config.start_agent

        # Build handoff map
        handoff_map: dict[str, str] = {}
        if app_state and hasattr(app_state, "handoff_map") and app_state.handoff_map:
            handoff_map = app_state.handoff_map
        elif orchestrator_config and orchestrator_config.handoff_map:
            handoff_map = orchestrator_config.handoff_map
        else:
            handoff_map = build_handoff_map(agents)

        logger.info(
            "[Genesys] Agents resolved | count=%d start=%s session=%s",
            len(agents), effective_start_agent, self.session_id,
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
        if etype == ServerEventType.RESPONSE_AUDIO_DELTA:
            delta = getattr(event, "delta", None)
            if not delta:
                logger.warning("[Genesys] Audio delta with no data | session=%s", self.session_id)
                return

            # First audio chunk → send playback lifecycle
            response_id = getattr(event, "response_id", None)
            if response_id and response_id not in self._active_response_ids:
                self._active_response_ids.add(response_id)
                self._is_playing = True
                logger.info("[Genesys] First audio chunk for response=%s | session=%s", response_id, self.session_id)

            # Convert PCM16 24kHz (raw bytes or base64) → µ-law 8kHz raw bytes
            try:
                delta_type = type(delta).__name__
                delta_size = len(delta) if isinstance(delta, (bytes, str)) else 0
                ulaw_bytes = convert_voicelive_delta_to_ulaw(delta)
                logger.info(
                    "[Genesys] Audio delta: input_type=%s input_size=%d → µ-law_size=%d | session=%s",
                    delta_type, delta_size, len(ulaw_bytes), self.session_id,
                )
                await self._enqueue_binary(ulaw_bytes)
            except Exception:
                logger.exception("Failed to convert audio delta")

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            response_id = getattr(event, "response_id", None)
            if response_id:
                self._active_response_ids.discard(response_id)
            # Flush remaining buffered audio
            await self._flush_audio_buffer()
            logger.debug("[Genesys] Audio done | session=%s", self.session_id)

        elif etype == ServerEventType.RESPONSE_DONE:
            response_id = self._extract_response_id(event)
            if response_id:
                self._active_response_ids.discard(response_id)
            await self._flush_audio_buffer()
            self._is_playing = False
            logger.debug("[Genesys] Response done | session=%s", self.session_id)

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            logger.info("[Genesys] Speech started → barge-in | session=%s", self.session_id)
            # Cancel pacer and clear accumulated audio
            if self._pacer_task and not self._pacer_task.done():
                self._pacer_task.cancel()
            self._audio_accum.clear()
            self._audio_buffer.clear()
            # Send barge-in event
            await self._enqueue_message(self._protocol.create_barge_in_event())
            self._is_playing = False
            self._active_response_ids.clear()

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            logger.debug("[Genesys] Speech stopped | session=%s", self.session_id)

        elif etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = getattr(event, "transcript", "")
            if transcript:
                logger.info(
                    "[Genesys] User transcript: '%s' | session=%s",
                    transcript, self.session_id,
                )
                await self._enqueue_message(
                    self._protocol.create_transcript_event(transcript)
                )

        elif etype == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            # LLM streaming text (logged for debugging)
            pass

        elif etype == ServerEventType.ERROR:
            error_msg = getattr(event, "message", "") or str(event)
            logger.error("[Genesys] VoiceLive error: %s | session=%s", error_msg, self.session_id)

        else:
            logger.info("[Genesys] Unhandled VoiceLive event: %s | session=%s", etype, self.session_id)

    @staticmethod
    def _extract_response_id(event: Any) -> str | None:
        response = getattr(event, "response", None)
        if response:
            return getattr(response, "id", None)
        return getattr(event, "response_id", None)

    # ─────────────────────────────────────────────────────────────────────────
    # Outbound message queue (single writer for sequence integrity)
    # ─────────────────────────────────────────────────────────────────────────

    async def _enqueue_message(self, msg: dict[str, Any]) -> None:
        """Enqueue a JSON protocol message for serialised sending."""
        await self._outbound_queue.put(msg)

    async def _enqueue_binary(self, data: bytes) -> None:
        """Accumulate audio data. A pacer task drains it at real-time rate."""
        if not data:
            return
        self._audio_accum.extend(data)
        # Start pacer if not running
        if self._pacer_task is None or self._pacer_task.done():
            self._pacer_task = asyncio.create_task(
                self._audio_pacer(), name="genesys-audio-pacer"
            )

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

                if len(self._audio_accum) == 0:
                    return  # No more data; pacer exits, re-started on next enqueue

                # Send up to one chunk (2000 bytes = 250ms at 8kHz µ-law mono)
                chunk_size = min(self._AUDIO_CHUNK_SIZE, len(self._audio_accum))
                chunk = bytes(self._audio_accum[:chunk_size])
                del self._audio_accum[:chunk_size]
                await self._outbound_queue.put(chunk)
        except asyncio.CancelledError:
            pass

    async def _flush_audio_buffer(self) -> None:
        """Flush any remaining accumulated audio (e.g., at end of response)."""
        # Cancel pacer — we'll send everything via paced sends
        if self._pacer_task and not self._pacer_task.done():
            self._pacer_task.cancel()
            try:
                await self._pacer_task
            except asyncio.CancelledError:
                pass
        if self._audio_accum:
            # Send remaining in paced chunks
            while len(self._audio_accum) > 0:
                chunk_size = min(self._AUDIO_CHUNK_SIZE, len(self._audio_accum))
                chunk = bytes(self._audio_accum[:chunk_size])
                del self._audio_accum[:chunk_size]
                await self._outbound_queue.put(chunk)
                if self._audio_accum:
                    await asyncio.sleep(self._AUDIO_PACE_MS / 1000.0)
            self._audio_accum.clear()

    async def _outbound_writer(self) -> None:
        """Single writer task that sends all outbound frames to Genesys.

        This ensures proper sequence numbering and prevents interleaving
        of JSON protocol messages and binary audio frames.
        """
        try:
            while self._running or not self._outbound_queue.empty():
                try:
                    item = await asyncio.wait_for(self._outbound_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
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
                            msg_type, self.session_id,
                        )
                        await self.websocket.send_text(json.dumps(item))
                    elif isinstance(item, bytes):
                        await self.websocket.send_bytes(item)
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
