"""
Unified Media Handler - Speech Cascade Mode
============================================

Single handler for both ACS and Browser WebSocket media streaming.
Composes with SpeechCascadeHandler for unified 3-thread architecture.

Architecture:
    WebSocket Endpoint (browser.py or media.py)
           │
           ▼
    MediaHandler.create(transport="browser"|"acs")
           │
           ▼
    SpeechCascadeHandler
           │
    ┌──────┼──────┐
    │      │      │
    ▼      ▼      ▼
   STT   Turn   Barge-In
  Thread Thread Controller

Usage:
    # Browser mode
    handler = await MediaHandler.create(transport="browser", ...)
    await handler.start()
    await handler.run()
    await handler.stop()

    # ACS mode
    handler = await MediaHandler.create(transport="acs", ...)
    await handler.start()
    # Call handler.handle_media_message() for each ACS message
    await handler.stop()
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Personalized greeting generation
from apps.artagent.backend.registries.toolstore.personalized_greeting import (
    generate_personalized_greeting,
)
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
from apps.artagent.backend.voice.shared.config_resolver import resolve_orchestrator_config

# Use unified orchestrator (new modular agent structure)
from apps.artagent.backend.src.orchestration.unified import route_turn

# ACS call control services
from apps.artagent.backend.src.services.acs.call_transfer import (
    transfer_call as transfer_call_service,
)

# ─────────────────────────────────────────────────────────────────────────────
# Voice Module Imports (self-contained speech orchestration layer)
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.voice import (  # Browser barge-in controller; Speech Cascade Handler; Messaging (transcript/envelope helpers)
    BrowserBargeInController,
    SpeechCascadeHandler,
    SpeechEvent,
    SpeechEventType,
    make_assistant_envelope,
    make_assistant_streaming_envelope,
    make_envelope,
    send_session_envelope,
    send_user_partial_transcript,
    send_user_transcript,
)

# Unified TTS Playback - single source of truth for voice synthesis
from apps.artagent.backend.voice.speech_cascade.tts import TTSPlayback
from config import ACS_STREAMING_MODE, GREETING, STOP_WORDS
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.stream_modes import StreamMode
from src.pools.session_manager import SessionContext
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger

logger = get_logger("api.v1.handlers.media_handler")
tracer = trace.get_tracer(__name__)

# ============================================================================
# Constants
# ============================================================================

RMS_SILENCE_THRESHOLD: int = 300
SILENCE_GAP_MS: int = 500
BROWSER_PCM_SAMPLE_RATE: int = 24000
BROWSER_SPEECH_RMS_THRESHOLD: int = 200
BROWSER_SILENCE_GAP_SECONDS: float = 0.5

# Legacy aliases
VOICE_LIVE_PCM_SAMPLE_RATE = BROWSER_PCM_SAMPLE_RATE
VOICE_LIVE_SPEECH_RMS_THRESHOLD = BROWSER_SPEECH_RMS_THRESHOLD
VOICE_LIVE_SILENCE_GAP_SECONDS = BROWSER_SILENCE_GAP_SECONDS


class TransportType(str, Enum):
    """Media transport types."""

    BROWSER = "browser"
    ACS = "acs"


class ACSMessageKind:
    """ACS WebSocket message types."""

    AUDIO_METADATA = "AudioMetadata"
    AUDIO_DATA = "AudioData"
    DTMF_DATA = "DtmfData"
    STOP_AUDIO = "StopAudio"


def pcm16le_rms(pcm_bytes: bytes) -> float:
    """Calculate RMS of PCM16LE audio for silence detection."""
    if len(pcm_bytes) < 2:
        return 0.0
    sample_count = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
    sum_sq = sum(s * s for s in samples)
    return (sum_sq / sample_count) ** 0.5 if sample_count else 0.0


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class MediaHandlerConfig:
    """Configuration for MediaHandler creation."""

    websocket: WebSocket
    session_id: str
    transport: TransportType = TransportType.BROWSER
    conn_id: str | None = None  # Browser only
    call_connection_id: str | None = None  # ACS only
    stream_mode: StreamMode = field(default_factory=lambda: ACS_STREAMING_MODE)
    user_email: str | None = None
    scenario: str | None = None  # Industry scenario (banking, default, etc.)


# ============================================================================
# Unified MediaHandler
# ============================================================================


class MediaHandler:
    """
    Unified media handler for Browser and ACS transports.

    This is the main entry point for voice conversations. It:
    1. Manages TTS/STT pool resources (acquired on create, released on stop)
    2. Wraps SpeechCascadeHandler for actual speech processing
    3. Translates transport-specific messages to common speech events

    Transport Differences:
    ----------------------
    BROWSER: Raw PCM bytes over WebSocket, JSON control messages
    ACS:     Base64-wrapped JSON messages, StopAudio protocol

    Key Methods:
    ------------
    create()              - Factory to build configured handler (use this!)
    start()               - Initialize speech processing
    run()                 - Browser: message loop | ACS: N/A (call handle_media_message)
    handle_media_message()- ACS only: process one ACS JSON message
    stop()                - Cleanup resources

    Callbacks (implemented here, called by SpeechCascadeHandler):
    -------------------------------------------------------------
    _on_barge_in         - User interrupted → stop TTS, cancel tasks
    _on_greeting         - Play greeting audio to user
    _on_partial_transcript- Interim STT result → show "typing" indicator
    _on_user_transcript  - Final STT result → trigger AI response
    _on_tts_request      - AI response ready → play audio

    Example:
    --------
        handler = await MediaHandler.create(config, app_state)
        await handler.start()
        if config.transport == TransportType.BROWSER:
            await handler.run()  # Message loop
        # For ACS, call handler.handle_media_message() per message
        await handler.stop()

    See Also:
    ---------
    - SpeechCascadeHandler: Core speech processing (protocol-agnostic)
    - README.md: Architecture overview
    """

    def __init__(
        self,
        config: MediaHandlerConfig,
        memory_manager: MemoManager,
        app_state: Any,
    ) -> None:
        """Initialize (use create() factory instead)."""
        self.config = config
        self._websocket = config.websocket
        self._transport = config.transport
        self._session_id = config.session_id
        self._session_short = config.session_id[-8:] if config.session_id else "unknown"
        self._conn_id = config.conn_id
        self._call_connection_id = config.call_connection_id or config.session_id
        self._stream_mode = config.stream_mode
        self.memory_manager = memory_manager
        self._app_state = app_state

        # Resources
        self._tts_client: Any = None
        self._stt_client: Any = None
        self._tts_tier = None
        self._stt_tier = None

        # Speech cascade
        self.speech_cascade: SpeechCascadeHandler | None = None
        self._greeting_text: str = ""
        self._greeting_queued = False

        # TTS Playback - unified handler for both transports
        self._tts_cancel_event: asyncio.Event = asyncio.Event()
        self._tts_playback: TTSPlayback | None = None  # Created in factory
        self._current_tts_task: asyncio.Task | None = None
        self._orchestration_tasks: set = set()

        # Barge-in state (for browser BrowserBargeInController compatibility)
        self._barge_in_active: bool = False
        self._last_barge_in_ts: float = 0.0
        self._barge_in_controller: BrowserBargeInController | None = None

        # State
        self._running = False
        self._stopped = False
        self._metadata_received = False  # ACS only

    # =========================================================================
    # Factory
    # =========================================================================

    @classmethod
    async def create(
        cls,
        config: MediaHandlerConfig,
        app_state: Any,
    ) -> MediaHandler:
        """
        Create MediaHandler for either transport.

        Args:
            config: Handler configuration with transport type.
            app_state: FastAPI app.state.

        Returns:
            Configured MediaHandler.
        """
        redis_mgr = app_state.redis
        session_key = config.call_connection_id or config.session_id
        memory_manager = cls._load_memory_manager(redis_mgr, session_key, config.session_id)

        # Store scenario in memory for orchestrator access
        if config.scenario:
            memory_manager.set_corememory("scenario_name", config.scenario)

        handler = cls(config, memory_manager, app_state)

        # Acquire pools
        try:
            tts_client, tts_tier = await app_state.tts_pool.acquire_for_session(session_key)
            handler._tts_client = tts_client
            handler._tts_tier = tts_tier
        except TimeoutError as exc:
            logger.error("[%s] TTS pool timeout", handler._session_short)
            await handler._close_websocket(1013, "TTS capacity temporarily unavailable")
            raise WebSocketDisconnect(code=1013) from exc

        try:
            stt_client, stt_tier = await app_state.stt_pool.acquire_for_session(session_key)
            handler._stt_client = stt_client
            handler._stt_tier = stt_tier
        except TimeoutError as exc:
            logger.error("[%s] STT pool timeout", handler._session_short)
            await handler._close_websocket(1013, "STT capacity temporarily unavailable")
            raise WebSocketDisconnect(code=1013) from exc

        logger.info(
            "[%s] Acquired STT=%s TTS=%s transport=%s",
            handler._session_short,
            getattr(stt_tier, "value", "?"),
            getattr(tts_tier, "value", "?"),
            config.transport.value,
        )

        # Setup websocket state
        handler._setup_websocket_state(memory_manager, tts_client, stt_client)

        # Initialize active agent in memory for this session
        # Priority: 1. Session agent (Agent Builder), 2. Session scenario (ScenarioBuilder),
        #           3. URL scenario param, 4. Unified agent (from disk)
        scenario_start_agent = None
        try:
            # Always call resolve_orchestrator_config with session_id to check for
            # session-scoped scenarios (created via ScenarioBuilder). The resolver
            # will also check for URL-based scenarios if scenario_name is provided.
            scenario_cfg = resolve_orchestrator_config(
                session_id=config.session_id,
                scenario_name=config.scenario,  # May be None, that's fine
            )
            scenario_start_agent = scenario_cfg.start_agent or scenario_start_agent
            if scenario_start_agent:
                logger.info(
                    "[%s] Resolved start_agent from scenario: %s (scenario=%s)",
                    handler._session_short,
                    scenario_start_agent,
                    scenario_cfg.scenario_name,
                )
        except Exception as exc:
            logger.warning(
                "[%s] Failed to resolve scenario start_agent: %s",
                handler._session_short,
                exc,
            )

        session_agent = get_session_agent(config.session_id)
        if session_agent:
            start_agent = session_agent
            start_agent_name = session_agent.name
            logger.info(
                "[%s] Session initialized with session agent: %s (voice=%s)",
                handler._session_short,
                start_agent_name,
                session_agent.voice.name if session_agent.voice else "default",
            )
        else:
            if scenario_start_agent:
                start_agent_name = scenario_start_agent
            else:
                start_agent_name = getattr(app_state, "start_agent", "Concierge")
            unified_agents = getattr(app_state, "unified_agents", {})
            start_agent = unified_agents.get(start_agent_name)

            if start_agent:
                logger.info(
                    "[%s] Session initialized with start agent: %s",
                    handler._session_short,
                    start_agent_name,
                )
            else:
                logger.warning(
                    "[%s] Start agent '%s' not found in unified_agents (%d agents)",
                    handler._session_short,
                    start_agent_name,
                    len(unified_agents),
                )

        if start_agent:
            memory_manager.update_corememory("active_agent", start_agent_name)

        # Derive greeting
        handler._greeting_text = await handler._derive_greeting()

        # Initialize TTS Playback (unified handler for voice synthesis)
        handler._tts_playback = TTSPlayback(
            websocket=config.websocket,
            app_state=app_state,
            session_id=config.session_id,
            cancel_event=handler._tts_cancel_event,
        )

        # Set active agent on TTS playback to ensure greetings use the correct voice
        if start_agent_name:
            handler._tts_playback.set_active_agent(start_agent_name)

        # Create speech cascade
        handler.speech_cascade = SpeechCascadeHandler(
            connection_id=session_key,
            orchestrator_func=handler._create_orchestrator_wrapper(),
            recognizer=stt_client,
            memory_manager=memory_manager,
            on_barge_in=handler._on_barge_in,
            on_greeting=handler._on_greeting,
            on_announcement=handler._on_announcement,
            on_partial_transcript=handler._on_partial_transcript,
            on_user_transcript=handler._on_user_transcript,
            on_tts_request=handler._on_tts_request,
            redis_mgr=redis_mgr,
        )

        # Expose speech_cascade on websocket.state for orchestrator TTS callbacks
        handler._websocket.state.speech_cascade = handler.speech_cascade
        # Expose tts_playback for voice configuration updates on agent switch
        handler._websocket.state.tts_playback = handler._tts_playback

        # Persist
        await memory_manager.persist_to_redis_async(redis_mgr)

        logger.info(
            "[%s] MediaHandler created (%s)", handler._session_short, config.transport.value
        )
        return handler

    @staticmethod
    def _load_memory_manager(redis_mgr, session_key: str, session_id: str) -> MemoManager:
        """Load or create memory manager."""
        try:
            mm = MemoManager.from_redis(session_key, redis_mgr)
            if mm is None:
                return MemoManager(session_id=session_id)
            mm.session_id = session_id
            return mm
        except Exception as e:
            logger.error("Failed to load memory: %s", e)
            return MemoManager(session_id=session_id)

    async def _derive_greeting(self) -> str:
        """Generate contextual greeting with agent assistance when possible."""
        return self._derive_default_greeting(
            self.memory_manager,
            self._app_state,
            session_id=self._session_id,
        )

    @staticmethod
    def _derive_default_greeting(
        memory_manager: MemoManager | None,
        app_state: Any,
        session_id: str | None = None,
    ) -> str:
        """Derive greeting from session agent, unified agent config, or memory context.

        Priority:
        1. Session agent (from Agent Builder)
        2. Unified agents (from disk/YAML)
        """
        # First, check for session agent (Agent Builder override)
        start_agent = None
        start_agent_name = None

        if session_id:
            session_agent = get_session_agent(session_id)
            if session_agent:
                start_agent = session_agent
                start_agent_name = session_agent.name
                logger.debug(
                    "Using session agent for greeting: %s",
                    session_agent.name,
                )

        # Fall back to unified agents if no session agent
        if not start_agent:
            unified_agents = getattr(app_state, "unified_agents", {})
            start_agent_name = getattr(app_state, "start_agent", "Concierge")
            start_agent = unified_agents.get(start_agent_name)

        # Fall back to legacy auth_agent if unified not available
        if not start_agent:
            start_agent = getattr(app_state, "auth_agent", None)

        # Build context for greeting templating from session memory
        context = {}
        if memory_manager:
            # Get session_profile for rich context
            session_profile = memory_manager.get_value_from_corememory("session_profile", None)
            active_agent = memory_manager.get_value_from_corememory("active_agent", None)
            context = {
                "session_profile": session_profile,
                "caller_name": memory_manager.get_value_from_corememory("caller_name", None),
                "client_id": memory_manager.get_value_from_corememory("client_id", None),
                "customer_intelligence": memory_manager.get_value_from_corememory(
                    "customer_intelligence", None
                ),
                "institution_name": memory_manager.get_value_from_corememory(
                    "institution_name", None
                ),
                "active_agent": active_agent,
                "previous_agent": memory_manager.get_value_from_corememory("previous_agent", None),
                # Add agent_name for greeting template (use active_agent or start_agent name)
                "agent_name": active_agent or start_agent_name,
            }
            # Also extract from session_profile if available
            if session_profile:
                if not context.get("caller_name"):
                    context["caller_name"] = session_profile.get("full_name")
                if not context.get("client_id"):
                    context["client_id"] = session_profile.get("client_id")
                if not context.get("customer_intelligence"):
                    context["customer_intelligence"] = session_profile.get("customer_intelligence")

        # Check for return greeting (resume)
        if memory_manager and memory_manager.get_value_from_corememory("greeting_sent", False):
            if start_agent:
                # Use render_return_greeting for Jinja2 template rendering
                if hasattr(start_agent, "render_return_greeting"):
                    rendered = start_agent.render_return_greeting(context)
                    if rendered:
                        return rendered
                # Fallback to raw return_greeting (legacy agents)
                return_greeting = getattr(start_agent, "return_greeting", None)
                if return_greeting:
                    return return_greeting
            active = (memory_manager.get_value_from_corememory("active_agent", "") or "").strip()
            if active:
                return return_greeting
            return "Session resumed with your previous assistant."

        # Agent config greeting (from unified agent YAML)
        if start_agent:
            # Use render_greeting for Jinja2 template rendering
            if hasattr(start_agent, "render_greeting"):
                rendered = start_agent.render_greeting(context)
                if rendered:
                    return rendered
            # Fallback to raw greeting (legacy agents)
            agent_greeting = getattr(start_agent, "greeting", None)
            if agent_greeting:
                return agent_greeting

        # Try personalized greeting from customer intel
        if memory_manager:
            try:
                customer_intel = memory_manager.get_value_from_corememory(
                    "customer_intelligence", None
                )
                if customer_intel:
                    caller = (
                        memory_manager.get_value_from_corememory("caller_name", "") or ""
                    ).strip()
                    agent = (
                        memory_manager.get_value_from_corememory("active_agent", "") or ""
                    ).strip() or "Support"
                    inst = (
                        memory_manager.get_value_from_corememory("institution_name", "") or ""
                    ).strip()
                    topic = (memory_manager.get_value_from_corememory("topic", "") or "").strip()
                    personalized = generate_personalized_greeting(
                        agent_name=agent,
                        caller_name=caller or None,
                        institution_name=inst or "our team",
                        customer_intelligence=customer_intel,
                        is_return_visit=memory_manager.get_value_from_corememory(
                            "greeting_sent", False
                        ),
                    )
                    if personalized and personalized.get("greeting"):
                        return personalized["greeting"]
            except Exception:
                pass

        return GREETING

    def _setup_websocket_state(self, mm: MemoManager, tts, stt) -> None:
        """Set up websocket state attributes for orchestrator compatibility."""
        ws = self._websocket
        try:
            ws.state.session_context = SessionContext(
                session_id=self._session_id,
                memory_manager=mm,
                websocket=ws,
            )
            ws.state.tts_client = tts
            ws.state.stt_client = stt
            ws.state.cm = mm
            ws.state.session_id = self._session_id
            ws.state.stream_mode = self._stream_mode
            ws.state.is_synthesizing = False
            ws.state.audio_playing = False
            ws.state.tts_cancel_requested = False
            ws.state.tts_cancel_event = self._tts_cancel_event
            ws.state.orchestration_tasks = self._orchestration_tasks

            # Capture event loop for thread-safe scheduling
            try:
                ws.state._loop = asyncio.get_running_loop()
            except RuntimeError:
                ws.state._loop = None

            if self._call_connection_id:
                ws._call_connection_id = self._call_connection_id

            # Set up barge-in controller for browser transport
            if self._transport == TransportType.BROWSER:
                self._setup_browser_barge_in_controller()

        except Exception as e:
            logger.debug("[%s] State setup error: %s", self._session_short, e)

    def _setup_browser_barge_in_controller(self) -> None:
        """Set up BargeInController for browser transport."""
        ws = self._websocket

        def get_metadata(key: str, default=None):
            """Get metadata from websocket state."""
            return getattr(ws.state, key, default)

        def set_metadata(key: str, value) -> None:
            """Set metadata on websocket state."""
            setattr(ws.state, key, value)

        def signal_tts_cancel() -> None:
            """Signal TTS cancellation."""
            self._tts_cancel_event.set()
            # Cancel current TTS task
            if self._current_tts_task and not self._current_tts_task.done():
                self._current_tts_task.cancel()

        self._barge_in_controller = BrowserBargeInController(
            websocket=ws,
            session_id=self._session_id,
            conn_id=self._conn_id,
            get_metadata=get_metadata,
            set_metadata=set_metadata,
            signal_tts_cancel=signal_tts_cancel,
            logger=logger,
        )
        ws.state.barge_in_controller = self._barge_in_controller
        ws.state.request_barge_in = self._barge_in_controller.request

    def _create_orchestrator_wrapper(self) -> Callable:
        """Create orchestrator wrapper with transport-specific params."""
        is_acs = self._transport == TransportType.ACS

        async def wrapped(cm: MemoManager, transcript: str):
            return await route_turn(
                cm=cm,
                transcript=transcript,
                ws=self._websocket,
                is_acs=is_acs,
            )

        return wrapped

    async def _close_websocket(self, code: int, reason: str) -> None:
        """Close websocket if connected."""
        if self._websocket.client_state == WebSocketState.CONNECTED:
            try:
                await self._websocket.close(code=code, reason=reason)
            except Exception:
                pass

    # =========================================================================
    # Speech Cascade Callbacks - Barge-In
    # =========================================================================

    async def _on_barge_in(self) -> None:
        """
        Handle barge-in interruption.

        Common flow:
        1. Signal cancellation (event + state flags)
        2. Stop TTS client
        3. Cancel pending tasks
        4. Send transport-specific stop signal (ACS StopAudio / Browser control msg)

        Note: ACS sends StopAudio to ACS websocket only (phone doesn't need UI update).
        Browser sends control messages to the browser connection.
        """
        # Debounce + guard
        now = time.monotonic()
        if self._barge_in_active or (now - self._last_barge_in_ts) < 0.05:
            return

        self._barge_in_active = True
        self._last_barge_in_ts = now

        try:
            logger.info("[%s] Barge-in (transport=%s)", self._session_short, self._transport.value)

            # 1. Signal cancellation
            self._tts_cancel_event.set()
            self._tts_playing = False
            self._websocket.state.is_synthesizing = False
            self._websocket.state.audio_playing = False
            self._websocket.state.tts_cancel_requested = True

            # 2. Stop TTS client
            if self._tts_client:
                try:
                    self._tts_client.stop_speaking()
                except Exception:
                    pass

            # 3. Cancel tasks
            await self._cancel_pending_tasks()

            # 4. Transport-specific stop
            if self._transport == TransportType.ACS:
                await self._send_stop_audio_acs()
            else:
                await self._send_barge_in_browser()

        except Exception as e:
            logger.error("[%s] Barge-in error: %s", self._session_short, e)
        finally:
            asyncio.create_task(self._reset_barge_in_state())

    async def _cancel_pending_tasks(self) -> None:
        """Cancel TTS and orchestration tasks including ACS playback queue."""
        ws = self._websocket

        # Cancel ACS playback tail (the queue chain from gpt_flow)
        if self._transport == TransportType.ACS:
            playback_tail = getattr(ws.state, "acs_playback_tail", None)
            if playback_tail and not playback_tail.done():
                playback_tail.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(playback_tail), timeout=0.2)
                except (TimeoutError, asyncio.CancelledError):
                    pass
                ws.state.acs_playback_tail = None
                logger.debug("[%s] ACS playback tail cancelled", self._session_short)

            # Also cancel the current streaming task (frame streaming)
            streaming_task = getattr(ws.state, "current_streaming_task", None)
            if streaming_task and not streaming_task.done():
                streaming_task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(streaming_task), timeout=0.2)
                except (TimeoutError, asyncio.CancelledError):
                    pass
                ws.state.current_streaming_task = None
                logger.debug("[%s] ACS streaming task cancelled", self._session_short)

        # Cancel handler's TTS task
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._current_tts_task), timeout=0.2)
            except (TimeoutError, asyncio.CancelledError):
                pass
            self._current_tts_task = None

        # Cancel orchestration tasks
        for task in list(self._orchestration_tasks):
            if task and not task.done():
                task.cancel()
        if self._orchestration_tasks:
            await asyncio.sleep(0.05)
        self._orchestration_tasks.clear()

    async def _reset_barge_in_state(self) -> None:
        """Reset barge-in state after delay."""
        await asyncio.sleep(0.1)
        self._barge_in_active = False
        self._tts_cancel_event.clear()
        try:
            self._websocket.state.tts_cancel_requested = False
        except Exception:
            pass

    async def _send_stop_audio_acs(self) -> bool:
        """Send StopAudio to ACS media websocket."""
        ws = self._websocket
        client_state = getattr(ws, "client_state", None)
        app_state = getattr(ws, "application_state", None)

        if client_state != WebSocketState.CONNECTED or app_state != WebSocketState.CONNECTED:
            logger.debug("[%s] StopAudio skipped (ws closing)", self._session_short)
            return False

        try:
            stop_audio = {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
            await ws.send_text(json.dumps(stop_audio))
            logger.debug("[%s] StopAudio sent to ACS", self._session_short)
            return True
        except Exception as e:
            # Check state again - might have disconnected
            client_state = getattr(ws, "client_state", None)
            if client_state == WebSocketState.CONNECTED:
                logger.warning("[%s] StopAudio failed: %s", self._session_short, e)
            return False

    async def _send_barge_in_browser(self) -> None:
        """Send barge-in control messages to browser via connection manager."""
        if not self._conn_id:
            logger.debug("[%s] No conn_id for barge-in", self._session_short)
            return

        cancel_msg = {
            "type": "control",
            "action": "tts_cancelled",
            "reason": "barge_in",
            "session_id": self._session_id,
        }
        stop_msg = {
            "type": "control",
            "action": "audio_stop",
            "reason": "barge_in",
            "session_id": self._session_id,
        }

        try:
            # Send via connection manager (consistent with browser flow)
            mgr = self._app_state.conn_manager
            await mgr.send_to_connection(self._conn_id, cancel_msg)
            await mgr.send_to_connection(self._conn_id, stop_msg)
            logger.debug("[%s] Barge-in messages sent to browser", self._session_short)
        except Exception as e:
            logger.debug("[%s] Barge-in send failed: %s", self._session_short, e)

    async def _on_greeting(self, event: SpeechEvent) -> None:
        """Handle greeting TTS."""
        await self._send_tts(
            event.text,
            is_greeting=True,
            voice_name=event.voice_name,
            voice_style=event.voice_style,
            voice_rate=event.voice_rate,
        )

    async def _on_announcement(self, event: SpeechEvent) -> None:
        """Handle announcement TTS."""
        await self._send_tts(
            event.text,
            is_greeting=False,
            voice_name=event.voice_name,
            voice_style=event.voice_style,
            voice_rate=event.voice_rate,
        )

    def _on_partial_transcript(self, text: str, language: str, speaker_id: str | None) -> None:
        """
        Handle partial (interim) STT transcript.

        Called from STT thread, so we schedule the async work on the main loop.
        Uses send_user_partial_transcript which broadcasts to all session connections.
        """
        loop = self.speech_cascade.thread_bridge.main_loop if self.speech_cascade else None
        if not loop or loop.is_closed():
            return

        # Broadcast partial to session (works for both transports)
        coro = send_user_partial_transcript(
            self._websocket,
            text,
            language=language,
            speaker_id=speaker_id,
            session_id=self._session_id,
        )

        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            logger.debug("[%s] Partial emit failed: %s", self._session_short, e)

    async def _on_user_transcript(self, text: str) -> None:
        """Handle final user transcript."""
        if not self._is_connected():
            return

        try:
            # Use send_user_transcript for both transports - broadcasts to session
            await send_user_transcript(
                self._websocket,
                text,
                session_id=self._session_id,
                broadcast_only=True,
            )
        except Exception as e:
            logger.warning("[%s] Transcript emit failed: %s", self._session_short, e)

    async def _on_tts_request(
        self,
        text: str,
        event_type: SpeechEventType,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
    ) -> None:
        """Handle TTS request with optional voice configuration."""
        await self._send_tts(
            text,
            is_greeting=(event_type == SpeechEventType.GREETING),
            voice_name=voice_name,
            voice_style=voice_style,
            voice_rate=voice_rate,
        )

    # =========================================================================
    # TTS Playback (delegates to TTSPlayback for unified handling)
    # =========================================================================

    async def _send_tts(
        self,
        text: str,
        *,
        is_greeting: bool = False,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
    ) -> None:
        """
        Send TTS via appropriate transport.

        Voice is resolved from agent config by TTSPlayback if not provided.
        """
        if not text or not text.strip() or not self._is_connected():
            return

        if self._tts_cancel_event.is_set():
            logger.debug("[%s] TTS skipped (barge-in active)", self._session_short)
            return

        label = "greeting" if is_greeting else "response"
        logger.debug("[%s] TTS %s (len=%d)", self._session_short, label, len(text))

        try:
            # Record greeting in memory
            if is_greeting:
                self._record_greeting(text)

            # Emit to UI (dashboard) - use non-streaming envelope for greeting
            await self._emit_to_ui(text, is_greeting=is_greeting)

            # Callback for turn telemetry
            on_first_audio = None
            if self.speech_cascade and not is_greeting:
                on_first_audio = self.speech_cascade.record_tts_first_audio

            # Play via unified TTS handler
            if self._transport == TransportType.ACS:
                success = await self._tts_playback.play_to_acs(
                    text,
                    voice_name=voice_name,
                    voice_style=voice_style,
                    voice_rate=voice_rate,
                    blocking=True,
                    on_first_audio=on_first_audio,
                )
            else:
                success = await self._tts_playback.play_to_browser(
                    text,
                    voice_name=voice_name,
                    voice_style=voice_style,
                    voice_rate=voice_rate,
                    on_first_audio=on_first_audio,
                )

            # Record completion for turn telemetry
            if success and self.speech_cascade and not is_greeting:
                self.speech_cascade.record_tts_complete()

            if success and is_greeting:
                logger.info("[%s] Greeting completed", self._session_short)

        except asyncio.CancelledError:
            logger.debug("[%s] TTS cancelled (barge-in)", self._session_short)
        except Exception as e:
            logger.error("[%s] TTS failed: %s", self._session_short, e)

    def _record_greeting(self, text: str) -> None:
        """Record greeting in memory (with duplicate prevention)."""
        if not self.memory_manager:
            return
        try:
            auth_agent = getattr(self._app_state, "auth_agent", None)
            agent_name = getattr(auth_agent, "name", None) if auth_agent else None
            agent_name = agent_name or self.memory_manager.get_value_from_corememory(
                "active_agent", "System"
            )
            
            # Check if this exact greeting is already in history to prevent duplicates
            existing_history = self.memory_manager.get_history(agent_name) or []
            normalized_text = text.strip()
            
            # Check last few messages to avoid duplicate greetings
            for msg in existing_history[-3:]:  # Check last 3 messages
                if msg.get("role") == "assistant" and msg.get("content", "").strip() == normalized_text:
                    logger.debug(
                        "[%s] Skipping duplicate greeting in history",
                        getattr(self, "_session_short", ""),
                    )
                    return  # Already recorded, skip
            
            self.memory_manager.append_to_history(agent_name, "assistant", text)
            self.memory_manager.update_corememory("greeting_sent", True)
        except Exception as e:
            logger.debug("[%s] Greeting record failed: %s", self._session_short, e)

    async def _emit_to_ui(self, text: str, *, is_greeting: bool = False) -> None:
        """Emit message to UI with proper agent labeling.

        Args:
            text: Message text to emit
            is_greeting: If True, use non-streaming envelope and don't dedupe
        """
        try:
            normalized = (text or "").strip()

            # For greetings, always emit (don't check stream cache)
            # For streaming responses, skip if already broadcast
            if not is_greeting:
                cache = getattr(self._websocket.state, "_assistant_stream_cache", None)
                if normalized and cache:
                    try:
                        cache.remove(normalized)
                        # Skip emitting because route_turn already broadcast this chunk
                        return
                    except ValueError:
                        pass

            # Get active agent name from memory manager
            agent_name = "Assistant"
            if self.memory_manager:
                agent_name = (
                    self.memory_manager.get_value_from_corememory("active_agent", "Assistant")
                    or "Assistant"
                )

            # Use non-streaming envelope for greetings, streaming for other messages
            if is_greeting:
                envelope = make_assistant_envelope(
                    content=text,
                    sender=agent_name,
                    session_id=self._session_id,
                )
            else:
                envelope = make_assistant_streaming_envelope(
                    content=text,
                    sender=agent_name,
                    session_id=self._session_id,
                )
            envelope["speaker"] = agent_name
            envelope["message"] = text  # Legacy compatibility

            if self._transport == TransportType.ACS:
                await send_session_envelope(
                    self._websocket,
                    envelope,
                    session_id=self._session_id,
                    conn_id=None,
                    event_label="assistant_streaming",
                    broadcast_only=True,
                )
            else:
                await self._app_state.conn_manager.send_to_connection(self._conn_id, envelope)
        except Exception as e:
            logger.debug("[%s] UI emit failed: %s", self._session_short, e)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start handler and speech cascade."""
        with tracer.start_as_current_span("media_handler.start", kind=SpanKind.INTERNAL):
            try:
                logger.info("[%s] Starting (%s)", self._session_short, self._transport.value)
                self._running = True
                await self.speech_cascade.start()

                # Queue greeting (browser queues immediately, ACS waits for metadata)
                if self._transport == TransportType.BROWSER:
                    if not self._greeting_queued and self._greeting_text:
                        # Get voice from TTSPlayback (resolves from agent config)
                        voice_name, voice_style, voice_rate = self._tts_playback.get_agent_voice()
                        self.speech_cascade.queue_greeting(
                            self._greeting_text,
                            voice_name=voice_name,
                            voice_style=voice_style,
                            voice_rate=voice_rate,
                        )
                        self._greeting_queued = True

                logger.info("[%s] Started", self._session_short)
            except Exception as e:
                logger.error("[%s] Start failed: %s", self._session_short, e)
                await self.stop()
                raise

    async def run(self) -> None:
        """Run browser message loop (not used for ACS)."""
        if self._transport != TransportType.BROWSER:
            raise RuntimeError("run() only for browser transport")

        with tracer.start_as_current_span("media_handler.run") as span:
            try:
                count = 0
                while self._is_connected() and self._running:
                    msg = await self._websocket.receive()
                    count += 1

                    if msg.get("type") == "websocket.disconnect":
                        break
                    if msg.get("type") != "websocket.receive":
                        continue

                    # Text input
                    text = msg.get("text")
                    if text and text.strip():
                        # Check for exit keywords (inline stopwords check)
                        if any(stop in text.strip().lower() for stop in STOP_WORDS):
                            await self._handle_goodbye()
                            break
                        self.speech_cascade.queue_user_text(text.strip())

                    # Audio input
                    audio = msg.get("bytes")
                    if audio:
                        self.speech_cascade.write_audio(audio)

                span.set_attribute("messages", count)
                span.set_status(Status(StatusCode.OK))

            except WebSocketDisconnect:
                span.set_status(Status(StatusCode.OK, "disconnect"))
                raise
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.error("[%s] Run error: %s", self._session_short, e)
                raise

    async def handle_media_message(self, raw_message: str) -> None:
        """Handle ACS WebSocket message (ACS only)."""
        if self._transport != TransportType.ACS:
            return

        try:
            data = json.loads(raw_message)
            if not isinstance(data, dict):
                return
        except json.JSONDecodeError:
            return

        kind = data.get("kind")
        if kind == ACSMessageKind.AUDIO_METADATA:
            await self._handle_audio_metadata()
        elif kind == ACSMessageKind.AUDIO_DATA:
            self._handle_audio_data(data)
        elif kind == ACSMessageKind.DTMF_DATA:
            self._handle_dtmf(data)

    async def _handle_audio_metadata(self) -> None:
        """Handle ACS AudioMetadata."""
        logger.debug("[%s] AudioMetadata received", self._session_short)
        self._metadata_received = True

        if self.speech_cascade.speech_sdk_thread:
            self.speech_cascade.speech_sdk_thread.start_recognizer()

        if not self._greeting_queued and self._greeting_text:
            # Get voice from TTSPlayback (resolves from agent config)
            voice_name, voice_style, voice_rate = self._tts_playback.get_agent_voice()
            self.speech_cascade.queue_greeting(
                self._greeting_text,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
            )
            self._greeting_queued = True

    def _handle_audio_data(self, data: dict[str, Any]) -> None:
        """Handle ACS AudioData."""
        section = data.get("audioData") or data.get("AudioData") or {}
        if section.get("silent", True):
            return

        b64 = section.get("data")
        if not b64:
            return

        try:
            self.speech_cascade.write_audio(base64.b64decode(b64))
        except Exception as e:
            logger.error("[%s] Audio decode error: %s", self._session_short, e)

    def _handle_dtmf(self, data: dict[str, Any]) -> None:
        """Handle ACS DTMF."""
        section = data.get("dtmfData") or data.get("DtmfData") or {}
        tone = section.get("data")
        if tone:
            logger.info("[%s] DTMF: %s", self._session_short, tone)

    async def _handle_goodbye(self) -> None:
        """Handle goodbye/exit."""
        goodbye = "Thank you for using our service. Goodbye."
        envelope = make_envelope(
            etype="exit",
            sender="System",
            payload={"type": "exit", "message": goodbye},
            topic="session",
            session_id=self._session_id,
        )
        await self._app_state.conn_manager.broadcast_session(self._session_id, envelope)

        # Use TTSPlayback for goodbye (gets voice from agent)
        await self._tts_playback.play_to_browser(goodbye)

    async def stop(self) -> None:
        """Stop handler and release resources."""
        if self._stopped:
            return

        with tracer.start_as_current_span("media_handler.stop", kind=SpanKind.INTERNAL):
            try:
                logger.info("[%s] Stopping", self._session_short)
                self._stopped = True
                self._running = False

                if self.speech_cascade:
                    try:
                        await self.speech_cascade.stop()
                    except Exception as e:
                        logger.error("[%s] Cascade stop error: %s", self._session_short, e)

                await self._release_pools()
                logger.info("[%s] Stopped", self._session_short)

            except Exception as e:
                logger.error("[%s] Stop error: %s", self._session_short, e)

    async def _release_pools(self) -> None:
        """Release STT/TTS pools."""
        session_key = self._call_connection_id or self._session_id
        app = self._app_state

        if self._tts_client:
            try:
                self._tts_client.stop_speaking()
            except Exception:
                pass
            pool = getattr(app, "tts_pool", None)
            if pool:
                try:
                    await pool.release_for_session(session_key, self._tts_client)
                except Exception as e:
                    logger.error("[%s] TTS release error: %s", self._session_short, e)
            self._tts_client = None

        if self._stt_client:
            try:
                self._stt_client.stop()
            except Exception:
                pass
            pool = getattr(app, "stt_pool", None)
            if pool:
                try:
                    await pool.release_for_session(session_key, self._stt_client)
                except Exception as e:
                    logger.error("[%s] STT release error: %s", self._session_short, e)
            self._stt_client = None

    # =========================================================================
    # Helpers & Properties
    # =========================================================================

    def _is_connected(self) -> bool:
        """Check WebSocket connected."""
        return (
            self._websocket.client_state == WebSocketState.CONNECTED
            and self._websocket.application_state == WebSocketState.CONNECTED
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def websocket(self) -> WebSocket:
        return self._websocket

    @property
    def call_connection_id(self) -> str:
        return self._call_connection_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def stream_mode(self) -> StreamMode:
        return self._stream_mode

    @property
    def metadata(self) -> dict:
        return {
            "cm": self.memory_manager,
            "session_id": self._session_id,
            "stream_mode": self._stream_mode,
            "transport": self._transport.value,
            "tts_client": self._tts_client,
            "stt_client": self._stt_client,
        }

    # ACS-specific operations
    async def transfer_call(self, target: str, **kwargs) -> dict[str, Any]:
        """Transfer ACS call."""
        return await transfer_call_service(
            call_connection_id=self._call_connection_id, target_address=target, **kwargs
        )

    def queue_direct_text_playback(
        self,
        text: str,
        playback_type: SpeechEventType = SpeechEventType.ANNOUNCEMENT,
        language: str = "en-US",
    ) -> bool:
        """Queue text for TTS playback."""
        if not self._running:
            return False
        return self.speech_cascade.queue_event(
            SpeechEvent(event_type=playback_type, text=text, language=language)
        )

    # Legacy aliases
    async def cleanup(self, app_state: Any = None) -> None:
        await self.stop()

    async def send_stop_audio(self) -> bool:
        """Legacy ACS stop audio."""
        return await self._send_stop_audio_acs()


# Backward compatibility alias
ACSMediaHandler = MediaHandler

__all__ = [
    "MediaHandler",
    "MediaHandlerConfig",
    "TransportType",
    "ACSMediaHandler",
    "ACSMessageKind",
    "pcm16le_rms",
    "RMS_SILENCE_THRESHOLD",
    "SILENCE_GAP_MS",
    "BROWSER_PCM_SAMPLE_RATE",
    "BROWSER_SPEECH_RMS_THRESHOLD",
    "BROWSER_SILENCE_GAP_SECONDS",
    "VOICE_LIVE_PCM_SAMPLE_RATE",
    "VOICE_LIVE_SPEECH_RMS_THRESHOLD",
    "VOICE_LIVE_SILENCE_GAP_SECONDS",
]
