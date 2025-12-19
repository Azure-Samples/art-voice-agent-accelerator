"""
Unified Voice Handler - Phase 3 Implementation
===============================================

Single handler for STT → LLM → TTS voice pipeline, combining:
- MediaHandler (pool management, transport routing, WebSocket lifecycle)
- SpeechCascadeHandler (three-thread architecture, speech recognition)

Architecture:
    WebSocket Endpoint (browser.py or media.py)
           │
           ▼
    VoiceHandler.create(transport="browser"|"acs")
           │
    ┌──────┼──────┐
    │      │      │
    ▼      ▼      ▼
   STT   Turn   Barge-In
  Thread Thread Controller

Usage:
    # Browser mode
    handler = await VoiceHandler.create(config, app_state)
    await handler.start()
    await handler.run()  # Message loop
    await handler.stop()

    # ACS mode
    handler = await VoiceHandler.create(config, app_state)
    await handler.start()
    # Call handler.handle_media_message() per ACS message
    await handler.stop()

Key Improvements (vs. MediaHandler + SpeechCascadeHandler):
- Single class with clear responsibilities
- Uses VoiceSessionContext as source of truth
- Eliminates duplication between handlers
- Barge-in handled in one place
- TTS via TTSPlayback.speak() (no multiple entry points)
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
import threading
import weakref
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Core dependencies - use direct module imports to avoid circular imports
from apps.artagent.backend.voice.shared import TransportType, VoiceSessionContext
from apps.artagent.backend.voice.tts import TTSPlayback
from apps.artagent.backend.voice.speech_cascade.handler import (
    ThreadBridge,
    RouteTurnThread,
    SpeechSDKThread,
    BargeInController,
    SpeechEvent,
    SpeechEventType,
)
from apps.artagent.backend.voice.messaging import (
    BrowserBargeInController,
    send_user_partial_transcript,
    send_user_transcript,
    make_assistant_envelope,
)

# Orchestration imports - session_agents OK, route_turn imported lazily to avoid circular
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
from apps.artagent.backend.voice.shared.config_resolver import resolve_orchestrator_config

# Pool management
from src.pools.session_manager import SessionContext
from src.stateful.state_managment import MemoManager
from src.tools.latency_tool import LatencyTool
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
from src.enums.stream_modes import StreamMode
from config import ACS_STREAMING_MODE, GREETING, STOP_WORDS
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.voice.speech_cascade.orchestrator import CascadeOrchestratorAdapter

logger = get_logger("voice.handler")
tracer = trace.get_tracer(__name__)

# ============================================================================
# Constants
# ============================================================================

RMS_SILENCE_THRESHOLD: int = 300
SILENCE_GAP_MS: int = 500
BROWSER_PCM_SAMPLE_RATE: int = 24000
BROWSER_SPEECH_RMS_THRESHOLD: int = 200
BROWSER_SILENCE_GAP_SECONDS: float = 0.5


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
class VoiceHandlerConfig:
    """Configuration for VoiceHandler creation."""

    websocket: WebSocket
    session_id: str
    transport: TransportType = TransportType.BROWSER
    conn_id: str | None = None  # Browser only
    call_connection_id: str | None = None  # ACS only
    stream_mode: StreamMode = field(default_factory=lambda: ACS_STREAMING_MODE)
    user_email: str | None = None
    scenario: str | None = None  # Industry scenario (banking, default, etc.)


# ============================================================================
# Unified VoiceHandler
# ============================================================================


class VoiceHandler:
    """
    Unified voice handler for STT → LLM → TTS pipeline.

    Combines:
    - MediaHandler (pool management, transport routing)
    - SpeechCascadeHandler (three-thread architecture)

    Single class, clear responsibilities, explicit context.

    Key Methods:
    ------------
    create()              - Factory to build configured handler (use this!)
    start()               - Initialize speech processing and play greeting
    run()                 - Browser: message loop | ACS: N/A
    handle_media_message()- ACS only: process one ACS JSON message
    handle_barge_in()     - Single barge-in implementation (no duplication)
    stop()                - Cleanup resources

    Properties:
    -----------
    context               - VoiceSessionContext (source of truth)
    tts                   - TTSPlayback instance
    """

    def __init__(
        self,
        context: VoiceSessionContext,
        app_state: Any,
        *,
        config: VoiceHandlerConfig,
    ) -> None:
        """
        Initialize VoiceHandler.

        Use create() factory method instead of direct instantiation.

        Args:
            context: Typed session context with all resources.
            app_state: FastAPI app.state.
            config: Handler configuration.
        """
        self._context = context
        self._app_state = app_state
        self._config = config

        # Shortcuts from context
        self._session_id = context.session_id
        self._session_short = context.session_id[-8:] if context.session_id else "unknown"
        self._transport = context.transport

        # Components (not layers)
        self._tts: TTSPlayback | None = None  # Created in factory
        self._orchestrator: CascadeOrchestratorAdapter | None = None

        # Thread management (inlined from SpeechCascadeHandler)
        self._speech_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._thread_bridge = ThreadBridge()
        self._stt_thread: SpeechSDKThread | None = None
        self._route_turn_thread: RouteTurnThread | None = None
        self._barge_in_controller: BargeInController | None = None

        # Browser-specific barge-in (for WebSocket message handling)
        self._browser_barge_in: BrowserBargeInController | None = None

        # Greeting
        self._greeting_text: str = ""
        self._greeting_queued = False

        # State
        self._running = False
        self._stopped = False
        self._metadata_received = False  # ACS only

        # Task tracking
        self._orchestration_tasks: set = set()
        self._current_tts_task: asyncio.Task | None = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def context(self) -> VoiceSessionContext:
        """Get the typed session context."""
        return self._context

    @property
    def tts(self) -> TTSPlayback | None:
        """Get the TTS playback handler."""
        return self._tts

    @property
    def memory_manager(self) -> MemoManager | None:
        """Get the memory manager from context."""
        return self._context.memo_manager

    # =========================================================================
    # Factory
    # =========================================================================

    @classmethod
    async def create(
        cls,
        config: VoiceHandlerConfig,
        app_state: Any,
    ) -> VoiceHandler:
        """
        Create VoiceHandler for either transport.

        Args:
            config: Handler configuration with transport type.
            app_state: FastAPI app.state.

        Returns:
            Configured VoiceHandler.
        """
        redis_mgr = app_state.redis
        session_key = config.call_connection_id or config.session_id

        # Load or create memory manager
        memory_manager = cls._load_memory_manager(redis_mgr, session_key, config.session_id)

        # Store scenario in memory for orchestrator access
        if config.scenario:
            memory_manager.set_corememory("scenario_name", config.scenario)

        # Acquire TTS/STT pools
        try:
            tts_client, tts_tier = await app_state.tts_pool.acquire_for_session(session_key)
        except TimeoutError as exc:
            logger.error("[%s] TTS pool timeout", session_key[-8:])
            await cls._close_websocket_static(config.websocket, 1013, "TTS capacity unavailable")
            raise WebSocketDisconnect(code=1013) from exc

        try:
            stt_client, stt_tier = await app_state.stt_pool.acquire_for_session(session_key)
        except TimeoutError as exc:
            logger.error("[%s] STT pool timeout", session_key[-8:])
            # Release TTS before failing
            await app_state.tts_pool.release(session_key)
            await cls._close_websocket_static(config.websocket, 1013, "STT capacity unavailable")
            raise WebSocketDisconnect(code=1013) from exc

        logger.info(
            "[%s] Acquired STT=%s TTS=%s transport=%s",
            session_key[-8:],
            getattr(stt_tier, "value", "?"),
            getattr(tts_tier, "value", "?"),
            config.transport.value,
        )

        # Create latency tool
        latency_tool = LatencyTool(memory_manager)

        # Get event loop
        try:
            event_loop = asyncio.get_running_loop()
        except RuntimeError:
            event_loop = None

        # Build VoiceSessionContext
        cancel_event = asyncio.Event()
        orchestration_tasks: set = set()

        context = VoiceSessionContext(
            session_id=config.session_id,
            call_connection_id=config.call_connection_id or config.session_id,
            transport=config.transport,
            conn_id=config.conn_id,
            tts_client=tts_client,
            stt_client=stt_client,
            tts_tier=tts_tier,
            stt_tier=stt_tier,
            memo_manager=memory_manager,
            latency_tool=latency_tool,
            session_context=SessionContext(
                session_id=config.session_id,
                memory_manager=memory_manager,
                websocket=config.websocket,
            ),
            stream_mode=config.stream_mode,
            cancel_event=cancel_event,
            orchestration_tasks=orchestration_tasks,
            event_loop=event_loop,
        )

        # Set websocket (private field)
        context._websocket = config.websocket

        # Create handler
        handler = cls(context, app_state, config=config)
        handler._orchestration_tasks = orchestration_tasks

        # Setup websocket state for backward compatibility
        handler._setup_websocket_state()

        # Initialize active agent
        await handler._initialize_active_agent()

        # Derive greeting
        handler._greeting_text = await handler._derive_greeting()

        # Create TTS Playback
        handler._tts = TTSPlayback(context, app_state, latency_tool=latency_tool)
        context.tts_playback = handler._tts

        # Create thread management components
        handler._barge_in_controller = BargeInController(
            session_key,
            on_barge_in=handler._on_barge_in,
        )

        handler._route_turn_thread = RouteTurnThread(
            connection_id=session_key,
            speech_queue=handler._speech_queue,
            orchestrator_func=handler._create_orchestrator_wrapper(),
            memory_manager=memory_manager,
            on_greeting=handler._on_greeting,
            on_announcement=handler._on_announcement,
            on_user_transcript=handler._on_user_transcript,
            on_tts_request=handler._on_tts_request,
        )

        handler._thread_bridge.set_main_loop(event_loop, session_key)
        handler._thread_bridge.set_route_turn_thread(handler._route_turn_thread)

        # Create STT thread
        handler._stt_thread = SpeechSDKThread(
            connection_id=session_key,
            recognizer=stt_client,
            speech_queue=handler._speech_queue,
            thread_bridge=handler._thread_bridge,
            barge_in_controller=handler._barge_in_controller,
            latency_tool=latency_tool,
        )

        # Store reference in context for external access
        context.speech_cascade = handler  # Handler IS the speech cascade now

        # Backward compatibility - expose on websocket.state
        config.websocket.state.speech_cascade = handler

        # Persist memory
        await memory_manager.persist_to_redis_async(redis_mgr)

        logger.info(
            "[%s] VoiceHandler created (%s)",
            handler._session_short,
            config.transport.value,
        )
        return handler

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """
        Start speech processing and queue greeting.

        Initializes:
        - STT recognition thread
        - Route turn processing thread
        - Greeting playback
        """
        if self._running:
            logger.warning("[%s] Already running", self._session_short)
            return

        self._running = True

        # Start threads
        if self._stt_thread:
            self._stt_thread.start()

        if self._route_turn_thread:
            self._route_turn_thread.start()

        # Queue greeting
        if self._greeting_text and not self._greeting_queued:
            self._greeting_queued = True
            event = SpeechEvent(
                event_type=SpeechEventType.GREETING,
                text=self._greeting_text,
                is_greeting=True,
            )
            await self._speech_queue.put(event)

        logger.info("[%s] VoiceHandler started", self._session_short)

    async def run(self) -> None:
        """
        Browser mode: message loop for WebSocket messages.

        For ACS mode, use handle_media_message() instead.
        """
        if self._transport != TransportType.BROWSER:
            raise RuntimeError("run() is only for Browser transport; use handle_media_message() for ACS")

        ws = self._context.websocket
        if not ws:
            raise RuntimeError("No websocket available")

        logger.info("[%s] Starting browser message loop", self._session_short)

        try:
            while self._running:
                try:
                    data = await ws.receive()
                    msg_type = data.get("type")

                    if msg_type == "websocket.disconnect":
                        logger.info("[%s] WebSocket disconnected", self._session_short)
                        break

                    if msg_type == "websocket.receive":
                        if "bytes" in data:
                            await self._handle_browser_audio(data["bytes"])
                        elif "text" in data:
                            await self._handle_browser_message(data["text"])

                except WebSocketDisconnect:
                    logger.info("[%s] WebSocket disconnected", self._session_short)
                    break
                except Exception as e:
                    logger.error("[%s] Message loop error: %s", self._session_short, e)
                    break

        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop speech processing and release resources."""
        if self._stopped:
            return

        self._stopped = True
        self._running = False

        logger.info("[%s] Stopping VoiceHandler", self._session_short)

        # Cancel any running TTS
        if self._context.cancel_event:
            self._context.cancel_event.set()

        # Cancel orchestration tasks
        for task in list(self._orchestration_tasks):
            if not task.done():
                task.cancel()

        # Stop threads
        if self._stt_thread:
            try:
                self._stt_thread.stop()
            except Exception as e:
                logger.error("[%s] STT thread stop error: %s", self._session_short, e)

        if self._route_turn_thread:
            try:
                self._route_turn_thread.stop()
            except Exception as e:
                logger.error("[%s] Route turn thread stop error: %s", self._session_short, e)

        # Release pools
        session_key = self._context.call_connection_id
        try:
            await self._app_state.tts_pool.release(session_key)
            await self._app_state.stt_pool.release(session_key)
            logger.info("[%s] Released TTS/STT pools", self._session_short)
        except Exception as e:
            logger.error("[%s] Pool release error: %s", self._session_short, e)

        logger.info("[%s] VoiceHandler stopped", self._session_short)

    # =========================================================================
    # Audio Handling
    # =========================================================================

    def write_audio(self, audio_bytes: bytes) -> None:
        """
        Write audio bytes to STT recognizer.

        Thread-safe. Can be called from any thread.

        Args:
            audio_bytes: PCM16LE audio data.
        """
        if self._stt_thread:
            self._stt_thread.write_audio(audio_bytes)

    async def _handle_browser_audio(self, audio_bytes: bytes) -> None:
        """Process raw PCM audio from browser WebSocket."""
        # Check for barge-in (RMS-based)
        rms = pcm16le_rms(audio_bytes)
        if rms > BROWSER_SPEECH_RMS_THRESHOLD:
            if self._browser_barge_in:
                await self._browser_barge_in.on_speech_detected()

        # Feed to STT
        self.write_audio(audio_bytes)

    async def _handle_browser_message(self, text: str) -> None:
        """Process JSON control message from browser."""
        try:
            msg = json.loads(text)
            msg_type = msg.get("type")

            if msg_type == "stop":
                logger.info("[%s] Stop requested", self._session_short)
                self._running = False

        except json.JSONDecodeError:
            logger.warning("[%s] Invalid JSON: %s", self._session_short, text[:100])

    async def handle_media_message(self, message: dict) -> None:
        """
        ACS mode: process one ACS JSON message.

        Args:
            message: Parsed ACS WebSocket message.
        """
        kind = message.get("kind")

        if kind == ACSMessageKind.AUDIO_METADATA:
            self._metadata_received = True
            logger.info("[%s] ACS metadata received", self._session_short)

        elif kind == ACSMessageKind.AUDIO_DATA:
            audio_b64 = message.get("audioData", {}).get("data")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                self.write_audio(audio_bytes)

        elif kind == ACSMessageKind.STOP_AUDIO:
            logger.info("[%s] ACS StopAudio received", self._session_short)

        elif kind == ACSMessageKind.DTMF_DATA:
            tone = message.get("dtmfData", {}).get("tone")
            logger.info("[%s] DTMF tone: %s", self._session_short, tone)

    # =========================================================================
    # Barge-In (Single Implementation)
    # =========================================================================

    async def handle_barge_in(self) -> None:
        """
        Handle user barge-in (interrupt).

        Single implementation that:
        1. Signals TTS cancellation
        2. Cancels pending orchestration tasks
        3. Notifies thread bridge
        """
        logger.info("[%s] Barge-in triggered", self._session_short)

        # Signal TTS cancellation
        if self._context.cancel_event:
            self._context.cancel_event.set()

        # Cancel current TTS task
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            self._current_tts_task = None

        # Cancel orchestration tasks
        for task in list(self._orchestration_tasks):
            if not task.done():
                task.cancel()
        self._orchestration_tasks.clear()

        # Reset cancel event for next turn
        await asyncio.sleep(0.05)  # Brief delay for cleanup
        if self._context.cancel_event:
            self._context.cancel_event.clear()

    async def _on_barge_in(self) -> None:
        """Internal callback for barge-in detection."""
        await self.handle_barge_in()

    # =========================================================================
    # Callbacks (from threads → main loop)
    # =========================================================================

    async def _on_greeting(self, event: SpeechEvent) -> None:
        """Play greeting via TTS."""
        if self._tts and event.text:
            # Suppress barge-in during greeting
            if self._thread_bridge:
                self._thread_bridge.suppress_barge_in()

            try:
                await self._tts.speak(event.text, is_greeting=True)
            finally:
                if self._thread_bridge:
                    self._thread_bridge.allow_barge_in()

    async def _on_announcement(self, event: SpeechEvent) -> None:
        """Play announcement via TTS."""
        if self._tts and event.text:
            await self._tts.speak(event.text)

    async def _on_user_transcript(self, text: str) -> None:
        """Handle final user transcript."""
        ws = self._context.websocket
        if ws:
            await send_user_transcript(ws, text)

    async def _on_partial_transcript(self, text: str, language: str, speaker: str | None) -> None:
        """Handle partial (interim) transcript."""
        ws = self._context.websocket
        if ws:
            await send_user_partial_transcript(ws, text)

    async def _on_tts_request(self, text: str, event_type: SpeechEventType) -> None:
        """Handle TTS request from orchestrator."""
        if self._tts and text:
            await self._tts.speak(text)

    # =========================================================================
    # Orchestrator
    # =========================================================================

    def _create_orchestrator_wrapper(self) -> Callable:
        """Create orchestrator function wrapper for route_turn."""
        # Import route_turn lazily to avoid circular import
        # (route_turn imports from voice/__init__.py which imports this module)
        from apps.artagent.backend.src.orchestration.unified import route_turn

        memo_manager = self._context.memo_manager
        ws = self._context.websocket
        is_acs = self._transport in (TransportType.ACS,)

        async def wrapped(cm: MemoManager, transcript: str) -> str:
            return await route_turn(cm, transcript, ws, is_acs=is_acs)

        return wrapped

    # =========================================================================
    # Helpers
    # =========================================================================

    def _setup_websocket_state(self) -> None:
        """Setup websocket.state for backward compatibility."""
        ws = self._config.websocket
        ctx = self._context

        # Populate from context
        ws.state.session_id = ctx.session_id
        ws.state.call_connection_id = ctx.call_connection_id
        ws.state.transport = ctx.transport
        ws.state.conn_id = ctx.conn_id
        ws.state.stream_mode = ctx.stream_mode
        ws.state.tts_client = ctx.tts_client
        ws.state.stt_client = ctx.stt_client
        ws.state.tts_tier = ctx.tts_tier
        ws.state.stt_tier = ctx.stt_tier
        ws.state.memo_manager = ctx.memo_manager
        ws.state.memory_manager = ctx.memo_manager  # Alias
        ws.state.latency_tool = ctx.latency_tool
        ws.state.session_context = ctx.session_context
        ws.state.cancel_event = ctx.cancel_event
        ws.state.orchestration_tasks = ctx.orchestration_tasks
        ws.state.event_loop = ctx.event_loop

    async def _initialize_active_agent(self) -> None:
        """Initialize active agent from session agent or scenario config."""
        memory_manager = self._context.memo_manager
        config = self._config
        session_short = self._session_short

        # Priority: 1. Session agent, 2. Scenario start_agent, 3. Default
        scenario_start_agent = None
        if config.scenario:
            try:
                scenario_cfg = resolve_orchestrator_config(scenario_name=config.scenario)
                scenario_start_agent = scenario_cfg.start_agent or scenario_start_agent
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to resolve scenario start_agent for '%s': %s",
                    session_short,
                    config.scenario,
                    exc,
                )

        session_agent = get_session_agent(config.session_id)
        if session_agent:
            start_agent_name = session_agent.name
            logger.info(
                "[%s] Session initialized with session agent: %s",
                session_short,
                start_agent_name,
            )
        elif scenario_start_agent:
            start_agent_name = scenario_start_agent
            logger.info(
                "[%s] Session initialized with scenario agent: %s",
                session_short,
                start_agent_name,
            )
        else:
            start_agent_name = getattr(self._app_state, "start_agent", "Concierge")
            logger.info(
                "[%s] Session initialized with default agent: %s",
                session_short,
                start_agent_name,
            )

        if memory_manager:
            memory_manager.update_corememory("active_agent", start_agent_name)

    async def _derive_greeting(self) -> str:
        """Generate contextual greeting."""
        memory_manager = self._context.memo_manager
        app_state = self._app_state
        session_id = self._session_id

        # Check for session agent greeting
        session_agent = get_session_agent(session_id) if session_id else None
        if session_agent:
            # Use agent's greeting if available
            context = {}
            if memory_manager:
                context = {
                    "caller_name": memory_manager.get_value_from_corememory("caller_name", None),
                    "agent_name": session_agent.name,
                }

            if hasattr(session_agent, "render_greeting"):
                rendered = session_agent.render_greeting(context)
                if rendered:
                    return rendered

        # Fall back to unified agents
        unified_agents = getattr(app_state, "unified_agents", {})
        start_agent_name = getattr(app_state, "start_agent", "Concierge")
        start_agent = unified_agents.get(start_agent_name)

        if start_agent and hasattr(start_agent, "render_greeting"):
            context = {}
            if memory_manager:
                context = {
                    "caller_name": memory_manager.get_value_from_corememory("caller_name", None),
                    "agent_name": start_agent_name,
                }
            rendered = start_agent.render_greeting(context)
            if rendered:
                return rendered

        # Default greeting
        return GREETING

    @staticmethod
    async def _close_websocket_static(ws: WebSocket, code: int, reason: str) -> None:
        """Close websocket with error code (static method for factory)."""
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code, reason)
        except Exception as e:
            logger.error("Failed to close websocket: %s", e)

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

    # =========================================================================
    # Queue Methods (for external event injection)
    # =========================================================================

    def queue_event(self, event: SpeechEvent) -> None:
        """
        Queue a speech event for processing.

        Thread-safe. Can be called from any thread.

        Args:
            event: Speech event to queue.
        """
        if self._thread_bridge:
            self._thread_bridge.queue_speech_result(self._speech_queue, event)
        else:
            try:
                self._speech_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("[%s] Queue full, dropping event", self._session_short)

    def queue_greeting(self, text: str) -> None:
        """
        Queue a greeting for playback.

        Convenience method that creates a GREETING event.

        Args:
            text: Greeting text.
        """
        event = SpeechEvent(
            event_type=SpeechEventType.GREETING,
            text=text,
            is_greeting=True,
        )
        self.queue_event(event)

    def queue_announcement(self, text: str) -> None:
        """
        Queue an announcement for playback.

        Args:
            text: Announcement text.
        """
        event = SpeechEvent(
            event_type=SpeechEventType.ANNOUNCEMENT,
            text=text,
        )
        self.queue_event(event)


# ============================================================================
# Backward Compatibility Alias
# ============================================================================

# MediaHandler can be imported from here for gradual migration
# In future, MediaHandler in api/v1/handlers/media_handler.py will become a thin shim
