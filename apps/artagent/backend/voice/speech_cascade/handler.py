"""
Speech Cascade Handler - Three-Thread Architecture
===================================================

Generic speech processing handler implementing the three-thread architecture
for low-latency voice interactions. This handler is protocol-agnostic and
can be composed with different transport handlers (ACS, VoiceLive, Websocket, etc.).

🧵 Thread 1: Speech SDK Thread (Never Blocks)
- Continuous audio recognition
- Immediate barge-in detection via on_partial callbacks
- Cross-thread communication via run_coroutine_threadsafe

🧵 Thread 2: Route Turn Thread (Blocks on Queue Only)
- AI processing and response generation
- Orchestrator delegation for TTS and playback
- Queue-based serialization of conversation turns

🧵 Thread 3: Main Event Loop (Never Blocks)
- Task cancellation for barge-in scenarios
- Non-blocking coordination with transport layer

Architecture:
    Transport Handler (ACS/VoiceLive/Websocket)
           │
           ▼
    SpeechCascadeHandler
           │
    ┌──────┼──────┐
    │      │      │
    ▼      ▼      ▼
  Speech  Route   Main
   SDK    Turn   Event
  Thread  Thread  Loop
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import weakref
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger
from utils.telemetry_decorators import ConversationTurnSpan

if TYPE_CHECKING:
    pass

logger = get_logger("v1.handlers.speech_cascade_handler")
tracer = trace.get_tracer(__name__)

# Thread pool for cleanup operations
_handlers_cleanup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="handler-cleanup")


class SpeechEventType(Enum):
    """Types of speech recognition events."""

    PARTIAL = "partial"
    FINAL = "final"
    ERROR = "error"
    GREETING = "greeting"
    ANNOUNCEMENT = "announcement"
    STATUS_UPDATE = "status"
    ERROR_MESSAGE = "error_msg"
    TTS_RESPONSE = "tts_response"  # Queued TTS from orchestrator/gpt_flow


@dataclass
class SpeechEvent:
    """Speech recognition event with metadata."""

    event_type: SpeechEventType
    text: str
    language: str | None = None
    speaker_id: str | None = None
    confidence: float | None = None
    timestamp: float | None = field(default_factory=time.time)
    # Wall-clock time (time.time) of the first partial for this utterance, i.e.
    # when the user started speaking. Used to draw a real STT recognition span.
    recognition_start_ts: float | None = None
    # perf_counter() captured at recognition finalization (end of user speech).
    # Shares a clock with the LLM/TTS latency markers, so it anchors the per-turn
    # "end of recognition -> first token / first audio" KPIs.
    recognition_end_perf: float | None = None
    # Voice configuration for TTS events
    voice_name: str | None = None
    voice_style: str | None = None
    voice_rate: str | None = None
    is_greeting: bool = False


class ResponseSender(Protocol):
    """Protocol for sending responses (TTS) to the transport layer."""

    async def send_response(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        rate: str | None = None,
    ) -> None:
        """Send a text response via TTS."""
        ...


class TranscriptEmitter(Protocol):
    """Protocol for emitting transcripts to UI/dashboard."""

    async def emit_user_transcript(
        self, text: str, *, partial: bool = False, turn_id: str | None = None
    ) -> None:
        """Emit user transcript to connected clients."""
        ...

    async def emit_assistant_transcript(self, text: str, *, sender: str | None = None) -> None:
        """Emit assistant transcript to connected clients."""
        ...


class ThreadBridge:
    """
    Cross-thread communication bridge.

    Provides thread-safe communication between Speech SDK Thread and Main Event Loop.
    Implements the non-blocking patterns for barge-in detection.
    """

    def __init__(self):
        """Initialize cross-thread communication bridge."""
        self.main_loop: asyncio.AbstractEventLoop | None = None
        self.connection_id = "unknown"
        self._route_turn_thread_ref: weakref.ReferenceType | None = None
        # Thread-safe flag to suppress barge-in during agent transitions/greetings
        self._suppress_barge_in = threading.Event()
        # Pre-speech turn guard: armed the moment a final transcript is produced
        # and held until the agent actually starts speaking (first audio chunk).
        # While armed, partials are ignored because they are the trailing tail of
        # the utterance that just spawned the turn -- acting on them would cancel
        # that very turn and tell the UI to drop its audio. A monotonic deadline
        # is a safety backstop in case first-audio never fires (e.g. tool-only
        # turn); the turn's finally block also disarms it.
        self._turn_guard = threading.Event()
        self._turn_guard_deadline: float = 0.0
        # Lock for atomic queue eviction operations
        self._queue_lock = threading.Lock()
        # perf_counter timestamp of the most recent barge-in detection, used to
        # measure how long barge-in takes to take effect (detection -> TTS stop).
        self.last_barge_in_detected_ts: float | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop, connection_id: str = None) -> None:
        """
        Set the main event loop reference for cross-thread communication.

        Args:
            loop: Main event loop instance for cross-thread coroutine scheduling.
            connection_id: Optional connection ID for logging context.
        """
        self.main_loop = loop
        if connection_id:
            self.connection_id = connection_id

    def set_route_turn_thread(self, route_turn_thread: RouteTurnThread) -> None:
        """Store a weak reference to the RouteTurnThread for coordinated cancellation."""
        try:
            self._route_turn_thread_ref = weakref.ref(route_turn_thread)
        except TypeError:
            self._route_turn_thread_ref = None

    def suppress_barge_in(self) -> None:
        """
        Suppress barge-in detection during agent transitions/greetings.

        Call this before playing handoff/greeting audio to prevent
        audio echo from triggering false barge-in events.
        """
        self._suppress_barge_in.set()
        logger.debug(f"[{self.connection_id}] Barge-in suppressed")

    def allow_barge_in(self) -> None:
        """
        Re-enable barge-in detection after agent transition completes.
        """
        self._suppress_barge_in.clear()
        logger.debug(f"[{self.connection_id}] Barge-in allowed")

    @property
    def barge_in_suppressed(self) -> bool:
        """Check if barge-in is currently suppressed (thread-safe)."""
        return self._suppress_barge_in.is_set()

    def arm_turn_guard(self, max_duration_s: float = 15.0) -> None:
        """Suppress trailing-partial barge-in until the agent starts speaking.

        Called from the STT thread when a final transcript is produced. Any
        partials that arrive after this belong to the just-finished utterance and
        must not cancel the turn it spawns.
        """
        self._turn_guard_deadline = time.monotonic() + max_duration_s
        self._turn_guard.set()

    def disarm_turn_guard(self) -> None:
        """Re-enable barge-in (agent has started speaking, or the turn ended)."""
        self._turn_guard.clear()

    @property
    def turn_guard_active(self) -> bool:
        """True while trailing-partial barge-in suppression is in effect."""
        return self._turn_guard.is_set() and time.monotonic() < self._turn_guard_deadline

    def schedule_barge_in(self, handler_func: Callable) -> None:
        """
        Schedule barge-in handler to execute on main event loop with priority.

        Args:
            handler_func: Callable barge-in handler function to schedule.
        """
        # Hard kill switch: half-duplex mode. When set, the user cannot interrupt
        # the agent, but trailing partials can never cancel a turn's audio either.
        # Useful to isolate barge-in as the cause of dropped turn audio.
        if os.getenv("CASCADE_DISABLE_BARGE_IN", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            logger.debug(f"[{self.connection_id}] Barge-in disabled (CASCADE_DISABLE_BARGE_IN)")
            return

        # Check suppression flag (thread-safe)
        if self._suppress_barge_in.is_set():
            logger.debug(
                f"[{self.connection_id}] Barge-in skipped (suppressed during handoff/greeting)"
            )
            return

        # Stamp detection time so the handler can report barge-in effect latency.
        self.last_barge_in_detected_ts = time.perf_counter()

        if not self.main_loop or self.main_loop.is_closed():
            logger.warning(f"[{self.connection_id}] No main loop for barge-in scheduling")
            return

        try:
            asyncio.run_coroutine_threadsafe(handler_func(), self.main_loop)
        except Exception as e:
            logger.error(f"[{self.connection_id}] Failed to schedule barge-in: {e}")

    def queue_speech_result(self, speech_queue: asyncio.Queue, event: SpeechEvent) -> None:
        """
        Queue speech recognition result for Route Turn Thread processing.

        Thread-safe implementation that uses locking to prevent race conditions
        during queue eviction operations.

        Args:
            speech_queue: Async queue for speech event transfer between threads.
            event: Speech recognition event containing transcription results.
        """
        if not isinstance(event, SpeechEvent):
            logger.error(f"[{self.connection_id}] Non-SpeechEvent enqueued: {type(event).__name__}")
            return

        try:
            speech_queue.put_nowait(event)
            if event.event_type != SpeechEventType.PARTIAL:
                logger.info(
                    f"[{self.connection_id}] Enqueued speech event type={event.event_type.value} qsize={speech_queue.qsize()}"
                )
        except asyncio.QueueFull:
            # Only evict PARTIAL (interim) transcriptions - never drop TTS responses
            if event.event_type == SpeechEventType.PARTIAL:
                logger.debug(f"[{self.connection_id}] Queue full, dropping PARTIAL event")
                return

            # For important events (TTS, FINAL, etc.), try to evict PARTIAL events
            # Use lock to make eviction atomic and prevent race conditions
            with self._queue_lock:
                evicted = False
                try:
                    # Drain queue while holding lock to prevent concurrent modifications
                    temp_events = []
                    while not speech_queue.empty():
                        try:
                            old_event = speech_queue.get_nowait()
                            if not evicted and old_event.event_type == SpeechEventType.PARTIAL:
                                evicted = True
                                logger.debug(
                                    f"[{self.connection_id}] Evicted PARTIAL to make room for {event.event_type.value}"
                                )
                            else:
                                temp_events.append(old_event)
                        except asyncio.QueueEmpty:
                            break

                    # Restore non-evicted events in original order
                    for e in temp_events:
                        try:
                            speech_queue.put_nowait(e)
                        except asyncio.QueueFull:
                            logger.error(
                                f"[{self.connection_id}] Lost event during eviction restore: {e.event_type.value}"
                            )
                            break
                except Exception as exc:
                    logger.debug(f"[{self.connection_id}] Queue eviction error: {exc}")

                # Now try to add the important event (still under lock)
                try:
                    speech_queue.put_nowait(event)
                    logger.info(
                        f"[{self.connection_id}] Enqueued {event.event_type.value} after eviction"
                    )
                except asyncio.QueueFull:
                    # For TTS_RESPONSE, use blocking put - must not drop
                    if event.event_type == SpeechEventType.TTS_RESPONSE:
                        logger.warning(
                            f"[{self.connection_id}] Queue full for TTS, using blocking put"
                        )
                        if self.main_loop and not self.main_loop.is_closed():
                            try:
                                future = asyncio.run_coroutine_threadsafe(
                                    speech_queue.put(event), self.main_loop
                                )
                                future.result(timeout=5.0)  # Wait up to 5s for queue space
                            except Exception as e:
                                logger.error(f"[{self.connection_id}] Failed to queue TTS: {e}")
                    else:
                        logger.error(
                            f"[{self.connection_id}] Queue still full after eviction; dropping {event.event_type.value}"
                        )
        except Exception:
            # Fallback to run_coroutine_threadsafe
            if self.main_loop and not self.main_loop.is_closed():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        speech_queue.put(event), self.main_loop
                    )
                    future.result(timeout=0.1)
                except Exception as e:
                    logger.error(f"[{self.connection_id}] Failed to queue speech: {e}")


class SpeechSDKThread:
    """
    Speech SDK Thread Manager - handles continuous audio recognition.

    Key Characteristics:
    - Runs in dedicated background thread
    - Immediate callback execution (< 10ms)
    - Cross-thread communication via ThreadBridge
    - Never blocks on queue operations
    """

    def __init__(
        self,
        connection_id: str,
        recognizer: StreamingSpeechRecognizerFromBytes,
        thread_bridge: ThreadBridge,
        barge_in_handler: Callable,
        speech_queue: asyncio.Queue,
        *,
        on_partial_transcript: Callable[[str, str, str | None], None] | None = None,
    ):
        """
        Initialize Speech SDK Thread.

        Args:
            connection_id: Connection identifier for logging.
            recognizer: Speech recognizer instance.
            thread_bridge: Cross-thread communication bridge.
            barge_in_handler: Handler to call on barge-in detection.
            speech_queue: Queue for final speech results.
            on_partial_transcript: Optional callback for partial transcripts.
        """
        self.connection_id = connection_id
        self._conn_short = connection_id[-8:] if connection_id else "unknown"
        self.recognizer = recognizer
        self.thread_bridge = thread_bridge
        self.barge_in_handler = barge_in_handler
        self.speech_queue = speech_queue
        self.on_partial_transcript = on_partial_transcript

        self.thread_obj: threading.Thread | None = None
        self.thread_running = False
        self.recognizer_started = False
        self.stop_event = threading.Event()
        self._stopped = False
        # Wall-clock time of the first partial of the current utterance (user
        # started speaking). Reset after each final. Drives the STT span.
        self._utterance_start_ts: float | None = None

        self._setup_callbacks()
        self._pre_initialize_recognizer()

    def _pre_initialize_recognizer(self) -> None:
        """Pre-initialize push_stream to prevent audio data loss."""
        try:
            if hasattr(self.recognizer, "push_stream") and self.recognizer.push_stream is not None:
                logger.debug(f"[{self._conn_short}] Push_stream already exists, skipping pre-init")
                return

            if hasattr(self.recognizer, "create_push_stream"):
                self.recognizer.create_push_stream()
                logger.info(f"[{self._conn_short}] Pre-initialized push_stream")
            elif hasattr(self.recognizer, "prepare_stream"):
                self.recognizer.prepare_stream()
                logger.info(f"[{self._conn_short}] Pre-initialized via prepare_stream")
            else:
                logger.warning(f"[{self._conn_short}] No direct push_stream method found")
                self.recognizer.prepare_start()

        except Exception as e:
            logger.warning(f"[{self._conn_short}] Failed to pre-init push_stream: {e}")

    def _setup_callbacks(self) -> None:
        """Configure speech recognition callbacks."""

        def on_partial(text: str, lang: str, speaker_id: str | None = None):
            logger.info(
                f"[{self._conn_short}] Partial speech: '{text}' ({lang}) len={len(text.strip())}"
            )
            # Stamp the start of this utterance (user started speaking) on the
            # first partial so we can draw an accurate STT recognition span.
            if self._utterance_start_ts is None:
                self._utterance_start_ts = time.time()
            if len(text.strip()) > 3:
                # While a turn is mid-flight and the agent has not started
                # speaking yet, this partial is the trailing tail of the utterance
                # that produced the turn. Acting on it would cancel that very turn
                # and signal the UI to drop the response audio, so skip it (no
                # barge-in, no partial envelope) until the agent speaks.
                if self.thread_bridge.turn_guard_active:
                    logger.debug(f"[{self._conn_short}] Partial ignored (pre-speech turn guard)")
                    return
                try:
                    self.thread_bridge.schedule_barge_in(self.barge_in_handler)
                except Exception as e:
                    logger.error(f"[{self._conn_short}] Barge-in error: {e}")

                if self.on_partial_transcript:
                    try:
                        self.on_partial_transcript(text.strip(), lang, speaker_id)
                    except Exception as e:
                        logger.debug(f"[{self._conn_short}] Partial transcript callback error: {e}")

        def on_final(text: str, lang: str, speaker_id: str | None = None):
            logger.debug(
                f"[{self._conn_short}] Final speech: '{text}' ({lang}) len={len(text.strip())}"
            )

            if len(text.strip()) > 1:
                logger.info(f"[{self._conn_short}] Speech: '{text}' ({lang})")
                # Arm the pre-speech guard at finalization so trailing partials of
                # this utterance cannot cancel the turn it is about to spawn.
                self.thread_bridge.arm_turn_guard()
                event = SpeechEvent(
                    event_type=SpeechEventType.FINAL,
                    text=text,
                    language=lang,
                    speaker_id=speaker_id,
                    recognition_start_ts=self._utterance_start_ts,
                    recognition_end_perf=time.perf_counter(),
                )
                self.thread_bridge.queue_speech_result(self.speech_queue, event)
            # Reset utterance start for the next utterance.
            self._utterance_start_ts = None

        def on_error(error: str):
            logger.error(f"[{self._conn_short}] Speech error: {error}")
            error_event = SpeechEvent(event_type=SpeechEventType.ERROR, text=error)
            self.thread_bridge.queue_speech_result(self.speech_queue, error_event)

        try:
            self.recognizer.set_partial_result_callback(on_partial)
            self.recognizer.set_final_result_callback(on_final)
            self.recognizer.set_cancel_callback(on_error)
            logger.info(f"[{self._conn_short}] Speech callbacks registered")
        except Exception as e:
            logger.error(f"[{self._conn_short}] Failed to setup callbacks: {e}")
            raise

    def prepare_thread(self) -> None:
        """Prepare the speech recognition thread."""
        if self.thread_running:
            return

        def recognition_thread():
            try:
                self.thread_running = True
                while self.thread_running and not self.stop_event.is_set():
                    self.stop_event.wait(0.1)
            except Exception as e:
                logger.error(f"[{self._conn_short}] Speech thread error: {e}")
            finally:
                self.thread_running = False

        self.thread_obj = threading.Thread(target=recognition_thread, daemon=True)
        self.thread_obj.start()

    def start_recognizer(self) -> None:
        """Start the speech recognizer."""
        if self.recognizer_started or not self.thread_running:
            return

        try:
            logger.info(
                f"[{self._conn_short}] Starting speech recognizer, push_stream_exists={bool(self.recognizer.push_stream)}"
            )
            self.recognizer.start()
            self.recognizer_started = True
            logger.info(f"[{self._conn_short}] Speech recognizer started")
        except Exception as e:
            logger.error(f"[{self._conn_short}] Failed to start recognizer: {e}")
            raise

    def write_audio(self, audio_bytes: bytes) -> None:
        """
        Write audio bytes to the recognizer.

        Args:
            audio_bytes: Raw audio bytes to process.
        """
        if self.recognizer:
            self.recognizer.write_bytes(audio_bytes)

    def stop_stt_timer_for_barge_in(self) -> None:
        """
        Stop any active STT timer during barge-in.

        Called when user interrupts to end current recognition session.
        This signals to the recognizer that the current utterance is complete
        due to user interruption.
        """
        logger.debug(f"[{self._conn_short}] STT timer stopped for barge-in")
        # Signal recognizer to finalize current audio buffer if supported
        if self.recognizer and hasattr(self.recognizer, "finalize_current_utterance"):
            try:
                self.recognizer.finalize_current_utterance()
            except Exception as e:
                logger.debug(f"[{self._conn_short}] Error finalizing utterance: {e}")

    def stop(self) -> None:
        """Stop speech recognition and thread."""
        if self._stopped:
            return

        try:
            logger.info(f"[{self._conn_short}] Stopping speech SDK thread")
            self._stopped = True
            self.thread_running = False
            self.recognizer_started = False
            self.stop_event.set()

            if self.recognizer:
                try:
                    self.recognizer.stop()
                except Exception as e:
                    logger.error(f"[{self._conn_short}] Error stopping recognizer: {e}")

            if self.thread_obj and self.thread_obj.is_alive():
                self.thread_obj.join(timeout=2.0)
                if self.thread_obj.is_alive():
                    logger.warning(
                        f"[{self._conn_short}] Recognition thread did not stop within timeout"
                    )

            logger.info(f"[{self._conn_short}] Speech SDK thread stopped")

        except Exception as e:
            logger.error(f"[{self._conn_short}] Error during speech SDK thread stop: {e}")


def _background_task(coro: Awaitable[Any], *, label: str) -> None:
    """Create a background task with logging."""
    task = asyncio.create_task(coro)

    def _log_outcome(t: asyncio.Task) -> None:
        try:
            t.result()
        except Exception:
            logger.debug("Background task '%s' failed", label, exc_info=True)

    task.add_done_callback(_log_outcome)


class RouteTurnThread:
    """
    Route Turn Thread Manager - handles AI processing and response generation.

    Key Characteristics:
    - Blocks only on queue.get() operations
    - Serializes conversation turns via queue
    - Delegates to orchestrator for response generation
    - Emits events to transport layer for coordination
    - Isolated from real-time operations
    """

    def __init__(
        self,
        connection_id: str,
        speech_queue: asyncio.Queue,
        orchestrator_func: Callable,
        memory_manager: MemoManager | None,
        *,
        response_sender: ResponseSender | None = None,
        transcript_emitter: TranscriptEmitter | None = None,
        on_greeting: Callable[[SpeechEvent], Awaitable[None]] | None = None,
        on_announcement: Callable[[SpeechEvent], Awaitable[None]] | None = None,
        on_user_transcript: Callable[[str], Awaitable[None]] | None = None,
        on_tts_request: Callable[[str, SpeechEventType], Awaitable[None]] | None = None,
        thread_bridge: "ThreadBridge | None" = None,
    ):
        """
        Initialize Route Turn Thread.

        Args:
            connection_id: Connection identifier for logging.
            speech_queue: Queue for receiving speech events.
            orchestrator_func: Function to call for AI processing.
            memory_manager: Memory manager for conversation state.
            response_sender: Protocol implementation for sending TTS responses.
            transcript_emitter: Protocol implementation for emitting transcripts.
            on_greeting: Callback for greeting events (emitted to transport).
            on_announcement: Callback for announcement events (emitted to transport).
            on_user_transcript: Callback for final user transcripts (emitted to transport).
            on_tts_request: Callback for TTS playback requests. Signature:
                (text, event_type, *, voice_name, voice_style, voice_rate) -> None
        """
        self.connection_id = connection_id
        self._conn_short = connection_id[-8:] if connection_id else "unknown"
        self.speech_queue = speech_queue
        self.orchestrator_func = orchestrator_func
        self.memory_manager = memory_manager
        self.response_sender = response_sender
        self.transcript_emitter = transcript_emitter
        self.on_greeting = on_greeting
        self.on_announcement = on_announcement
        self.on_user_transcript = on_user_transcript
        self.on_tts_request = on_tts_request
        # Shared cross-thread bridge; used to disarm the pre-speech turn guard
        # once the agent starts speaking / the turn ends.
        self.thread_bridge = thread_bridge

        self.processing_task: asyncio.Task | None = None
        self.current_response_task: asyncio.Task | None = None
        self.running = False
        self._stopped = False

        # Turn tracking for telemetry
        self._turn_number: int = 0
        self._active_turn_span: ConversationTurnSpan | None = None
        # perf_counter() of the most recent FINAL recognition (end of user
        # speech). Read by the orchestrator KPI summary to anchor the per-turn
        # "recognition end -> first token / first audio" latencies.
        self._last_recog_end_perf: float | None = None

    async def start(self) -> None:
        """Start the route turn processing loop."""
        if self.running:
            return

        self.running = True
        self.processing_task = asyncio.create_task(self._processing_loop())

    async def _processing_loop(self) -> None:
        """Main processing loop."""
        while self.running:
            try:
                speech_event = await asyncio.wait_for(self.speech_queue.get(), timeout=1.0)

                try:
                    logger.debug(
                        f"[{self._conn_short}] Routing speech event type={getattr(speech_event, 'event_type', 'unknown')}"
                    )
                    if speech_event.event_type == SpeechEventType.FINAL:
                        # End previous turn if active
                        await self._end_active_turn()
                        # Start new turn
                        await self._process_final_speech(speech_event)
                    elif speech_event.event_type == SpeechEventType.TTS_RESPONSE:
                        # TTS response from orchestrator - use on_tts_request callback
                        # This ensures sequential playback through the unified queue
                        if self.on_tts_request:
                            await self.on_tts_request(
                                speech_event.text,
                                speech_event.event_type,
                                voice_name=speech_event.voice_name,
                                voice_style=speech_event.voice_style,
                                voice_rate=speech_event.voice_rate,
                            )
                        logger.debug(
                            f"[{self._conn_short}] TTS response processed: {speech_event.text[:50]}..."
                        )
                    elif speech_event.event_type == SpeechEventType.GREETING:
                        # Use on_greeting if available, otherwise fall back to on_tts_request
                        if self.on_greeting:
                            await self.on_greeting(speech_event)
                        elif self.on_tts_request:
                            await self.on_tts_request(
                                speech_event.text,
                                speech_event.event_type,
                                voice_name=speech_event.voice_name,
                                voice_style=speech_event.voice_style,
                                voice_rate=speech_event.voice_rate,
                            )
                    elif speech_event.event_type in {
                        SpeechEventType.ANNOUNCEMENT,
                        SpeechEventType.STATUS_UPDATE,
                        SpeechEventType.ERROR_MESSAGE,
                    }:
                        # Use on_announcement if available, otherwise fall back to on_tts_request
                        if self.on_announcement:
                            await self.on_announcement(speech_event)
                        elif self.on_tts_request:
                            await self.on_tts_request(
                                speech_event.text,
                                speech_event.event_type,
                                voice_name=speech_event.voice_name,
                                voice_style=speech_event.voice_style,
                                voice_rate=speech_event.voice_rate,
                            )
                    elif speech_event.event_type == SpeechEventType.ERROR:
                        logger.error(f"[{self._conn_short}] Speech error: {speech_event.text}")
                except asyncio.CancelledError:
                    continue  # Barge-in cancellation
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[{self._conn_short}] Processing loop error: {e}")
                break

    async def _end_active_turn(self) -> None:
        """End the currently active turn span if it exists."""
        if self._active_turn_span:
            try:
                await self._active_turn_span.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[{self._conn_short}] Error closing turn span: {e}")
            finally:
                self._active_turn_span = None

    async def _process_final_speech(self, event: SpeechEvent) -> None:
        """
        Process final speech through orchestrator with turn-level telemetry.

        Creates a ConversationTurnSpan that tracks the full turn lifecycle:
        - STT completion (when this method is called)
        - LLM processing (during orchestrator execution)
        - TTS synthesis (when TTS callback fires)
        """
        # Increment turn counter
        self._turn_number += 1

        # Capture recognition-end (perf clock) so the orchestrator KPI summary
        # can anchor TTFT/TTFB at the moment the user stopped speaking.
        self._last_recog_end_perf = getattr(event, "recognition_end_perf", None)

        # Get session_id from memory manager for correlation
        session_id = (
            getattr(self.memory_manager, "session_id", None) if self.memory_manager else None
        )

        # Create ConversationTurnSpan for end-to-end turn tracking
        # Manually manage span lifecycle to cover async TTS events.
        # Backdate the span to when the user started speaking (first partial) so
        # voice.turn.N.total frames the full STT → LLM → TTS pipeline.
        recognition_start_ts = getattr(event, "recognition_start_ts", None)
        turn = ConversationTurnSpan(
            call_connection_id=self.connection_id,
            session_id=session_id,
            turn_number=self._turn_number,
            transport_type="cascade",
            user_intent_preview=event.text[:50] if event.text else None,
            start_time_ns=int(recognition_start_ts * 1e9) if recognition_start_ts else None,
        )
        await turn.__aenter__()
        self._active_turn_span = turn

        # Record STT complete (we just received the final transcript)
        turn.record_stt_complete(
            text=event.text,
            language=event.language,
        )

        # Draw a real STT recognition span (user started speaking → final) so STT
        # shows as its own timeline line item instead of an unexplained gap.
        if recognition_start_ts:
            turn.add_stt_recognition_span(
                start_ts=recognition_start_ts,
                end_ts=event.timestamp,
                text=event.text,
                language=event.language,
            )

        # Parent the orchestrator work under the turn span so voice.turn.N.total
        # visually frames the whole turn (STT → LLM → TTS) instead of floating as
        # a sibling. trace.use_span activates the turn span as current context
        # without ending it (it stays open for later TTS events / barge-in).
        with trace.use_span(turn.span, end_on_exit=False):
            with tracer.start_as_current_span(
                "route_turn_thread.process_speech",
                kind=SpanKind.INTERNAL,  # INTERNAL for in-process orchestration (not external call)
                attributes={
                    "speech.text": event.text,
                    "speech.language": event.language,
                    "turn.number": self._turn_number,
                },
            ):
                try:
                    if not self.memory_manager:
                        logger.error(f"[{self._conn_short}] No memory manager available")
                        return

                    # Emit user transcript via callback (for transport coordination)
                    if self.on_user_transcript:
                        try:
                            await self.on_user_transcript(event.text)
                        except Exception as e:
                            logger.warning(
                                f"[{self._conn_short}] Failed to invoke on_user_transcript: {e}"
                            )

                    # Legacy: emit via transcript emitter (deprecated)
                    if self.transcript_emitter:
                        try:
                            await self.transcript_emitter.emit_user_transcript(event.text)
                        except Exception as e:
                            logger.warning(
                                f"[{self._conn_short}] Failed to emit user transcript: {e}"
                            )

                    # Call orchestrator (LLM processing happens here)
                    if self.orchestrator_func:
                        # Record LLM start (approximation - actual first token comes from agent)
                        turn.record_tts_start()  # TTS will start streaming during orchestrator

                        coro = self.orchestrator_func(
                            cm=self.memory_manager,
                            transcript=event.text,
                        )
                        if coro:
                            self.current_response_task = asyncio.create_task(coro)
                            await self.current_response_task

                except asyncio.CancelledError:
                    logger.info(
                        f"[{self._conn_short}] Orchestrator processing cancelled (turn {self._turn_number})"
                    )
                    raise
                except Exception as e:
                    logger.error(
                        f"[{self._conn_short}] Error processing speech with orchestrator: {e}"
                    )
                finally:
                    # Turn finished (or errored) -> ensure the pre-speech guard is
                    # released even when the turn produced no audio at all.
                    if self.thread_bridge is not None:
                        self.thread_bridge.disarm_turn_guard()
                    if self.current_response_task and not self.current_response_task.done():
                        self.current_response_task.cancel()
                    self.current_response_task = None
                    # Close voice.turn.N.total now that the response is fully generated
                    # and TTS has been dispatched. The core KPIs (ttft/ttfb/synth/wall)
                    # are already stamped during orchestration via record_turn_kpis, so
                    # this keeps the turn span tightly scoped (recognition start ->
                    # response done) and sequential instead of lingering through the idle
                    # gap until the next utterance. Barge-in cancels the task above and
                    # still routes through this finally.
                    await self._end_active_turn()

    def record_llm_first_token(self) -> None:
        """Record LLM first token timing on the active turn span (call from agent)."""
        if self._active_turn_span:
            self._active_turn_span.record_llm_first_token()

    def record_llm_complete(
        self,
        total_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        response_text: str | None = None,
    ) -> None:
        """Record LLM completion timing on the active turn span."""
        if self._active_turn_span:
            self._active_turn_span.record_llm_complete(
                total_ms=total_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_text=response_text,
            )

    def record_tts_first_audio(self) -> None:
        """Record TTS first audio timing on the active turn span (call from TTS callback)."""
        # Agent is now speaking -> trailing-partial window is over; allow genuine
        # barge-in for the rest of this turn.
        if self.thread_bridge is not None:
            self.thread_bridge.disarm_turn_guard()
        if self._active_turn_span:
            self._active_turn_span.record_tts_first_audio()

    def record_tts_complete(self, total_ms: float | None = None) -> None:
        """Record TTS completion on the active turn span."""
        if self._active_turn_span:
            self._active_turn_span.record_tts_complete(total_ms=total_ms)

    def add_turn_metadata(self, key: str, value: Any) -> None:
        """Attach a KPI value to the active turn span (turn.metadata.<key>)."""
        if self._active_turn_span:
            self._active_turn_span.add_metadata(key, value)

    def record_turn_kpis(
        self,
        *,
        ttft_ms: float | None = None,
        ttfb_ms: float | None = None,
        synth_ms: float | None = None,
        stt_ms: float | None = None,
        llm_ttft_ms: float | None = None,
        llm_total_ms: float | None = None,
        tts_total_ms: float | None = None,
        turn_wall_ms: float | None = None,
        agent_name: str | None = None,
        latency_anchor: str | None = None,
    ) -> None:
        """Stamp the structured per-turn latency profile on the active turn span."""
        if self._active_turn_span:
            self._active_turn_span.record_turn_kpis(
                ttft_ms=ttft_ms,
                ttfb_ms=ttfb_ms,
                synth_ms=synth_ms,
                stt_ms=stt_ms,
                llm_ttft_ms=llm_ttft_ms,
                llm_total_ms=llm_total_ms,
                tts_total_ms=tts_total_ms,
                turn_wall_ms=turn_wall_ms,
                agent_name=agent_name,
                latency_anchor=latency_anchor,
            )

    @property
    def turn_number(self) -> int:
        """Current turn number for external reference."""
        return self._turn_number

    @property
    def last_recog_end_perf(self) -> float | None:
        """perf_counter() of the last finalized recognition (end of user speech)."""
        return self._last_recog_end_perf

    @property
    def has_active_response(self) -> bool:
        """Whether a response task is currently running and safe to interrupt."""
        return self.current_response_task is not None and not self.current_response_task.done()

    async def cancel_current_processing(self) -> None:
        """Cancel current processing for barge-in."""
        try:
            # End active turn span on barge-in
            await self._end_active_turn()

            # Clear speech queue
            cleared_count = 0
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break

            if cleared_count > 0:
                logger.debug(f"[{self._conn_short}] Cleared {cleared_count} events during barge-in")

            # Cancel current response task
            if self.current_response_task and not self.current_response_task.done():
                self.current_response_task.cancel()
                try:
                    await self.current_response_task
                except asyncio.CancelledError:
                    pass
            self.current_response_task = None

        except Exception as e:
            logger.error(f"[{self._conn_short}] Error cancelling processing: {e}")

    async def stop(self) -> None:
        """Stop the route turn processing loop."""
        if self._stopped:
            return

        self._stopped = True
        self.running = False
        await self.cancel_current_processing()
        await self._end_active_turn()

        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        await self._clear_speech_queue()

    async def _clear_speech_queue(self) -> None:
        """Clear remaining events from the speech queue."""
        try:
            cleared_count = 0
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break

            if cleared_count > 0:
                logger.info(
                    f"[{self._conn_short}] Cleared {cleared_count} speech events during stop"
                )
        except Exception as e:
            logger.error(f"[{self._conn_short}] Error clearing speech queue: {e}")


class BargeInController:
    """
    Barge-in detection and handling controller.

    Coordinates immediate response to user interruptions across
    all threads without blocking.
    """

    def __init__(
        self,
        connection_id: str,
        *,
        on_barge_in: Callable[[], Awaitable[None]] | None = None,
    ):
        """
        Initialize barge-in controller.

        Args:
            connection_id: Connection identifier for logging.
            on_barge_in: Callback when barge-in is detected.
        """
        self.connection_id = connection_id
        self._conn_short = connection_id[-8:] if connection_id else "unknown"
        self.on_barge_in = on_barge_in
        self.barge_in_active = threading.Event()
        self.current_playback_task: asyncio.Task | None = None

    async def handle_barge_in(self) -> None:
        """Handle barge-in interruption."""
        if self.barge_in_active.is_set():
            return

        self.barge_in_active.set()

        try:
            # Cancel current playback
            if self.current_playback_task and not self.current_playback_task.done():
                self.current_playback_task.cancel()
                try:
                    await self.current_playback_task
                except asyncio.CancelledError:
                    pass

            # Call transport-specific barge-in handler
            if self.on_barge_in:
                await self.on_barge_in()

        except Exception as e:
            logger.error(f"[{self._conn_short}] Barge-in error: {e}")
        finally:
            asyncio.create_task(self._reset_barge_in_state())

    async def _reset_barge_in_state(self) -> None:
        """Reset barge-in state after brief delay."""
        await asyncio.sleep(0.1)
        self.barge_in_active.clear()


class SpeechCascadeHandler:
    """
    Generic Speech Cascade Handler - Three-Thread Architecture Implementation

    Coordinates the three-thread architecture for low-latency voice interactions.
    This handler is protocol-agnostic and can be composed with different
    transport handlers (ACS, VoiceLive, Websocket, etc.).

    Usage:
        handler = SpeechCascadeHandler(
            connection_id="call_123",
            orchestrator_func=my_orchestrator,
            recognizer=speech_recognizer,
            memory_manager=memo_manager,
        )
        await handler.start()
        # Feed audio via handler.write_audio(bytes)
        # Queue events via handler.queue_event(event)
        await handler.stop()
    """

    def __init__(
        self,
        connection_id: str,
        orchestrator_func: Callable,
        recognizer: StreamingSpeechRecognizerFromBytes | None = None,
        memory_manager: MemoManager | None = None,
        *,
        on_barge_in: Callable[[], Awaitable[None]] | None = None,
        on_greeting: Callable[[SpeechEvent], Awaitable[None]] | None = None,
        on_announcement: Callable[[SpeechEvent], Awaitable[None]] | None = None,
        on_partial_transcript: Callable[[str, str, str | None], None] | None = None,
        on_user_transcript: Callable[[str], Awaitable[None]] | None = None,
        on_tts_request: Callable[[str, SpeechEventType], Awaitable[None]] | None = None,
        transcript_emitter: TranscriptEmitter | None = None,
        response_sender: ResponseSender | None = None,
        redis_mgr: Any | None = None,
    ):
        """
        Initialize the speech cascade handler.

        Args:
            connection_id: Unique connection identifier.
            orchestrator_func: Orchestrator function for conversation management.
            recognizer: Speech recognition client instance.
            memory_manager: Memory manager for conversation state.
            on_barge_in: Callback for barge-in events (transport-specific).
            on_greeting: Callback for greeting playback.
            on_announcement: Callback for announcement playback.
            on_partial_transcript: Callback for partial transcripts.
            on_user_transcript: Callback for final user transcripts (emitted to transport).
            on_tts_request: Callback for TTS playback requests (emitted to transport).
            transcript_emitter: Protocol implementation for emitting transcripts.
            response_sender: Protocol implementation for sending TTS responses.
            redis_mgr: Optional redis manager for session persistence.
        """
        self.connection_id = connection_id
        self._conn_short = connection_id[-8:] if connection_id else "unknown"
        self.orchestrator_func = orchestrator_func
        self.memory_manager = memory_manager
        self._redis_mgr = redis_mgr

        # Store callbacks for transport layer coordination
        self.on_user_transcript = on_user_transcript
        self.on_tts_request = on_tts_request

        # Initialize speech recognizer
        self.recognizer = recognizer or StreamingSpeechRecognizerFromBytes(
            candidate_languages=["en-US", "fr-FR", "de-DE", "es-ES", "it-IT"],
            vad_silence_timeout_ms=800,
            audio_format="pcm",
            use_semantic_segmentation=False,
            enable_diarisation=False,
        )

        # Cross-thread communication
        self.speech_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.thread_bridge = ThreadBridge()

        # Barge-in controller
        self.barge_in_controller = BargeInController(connection_id, on_barge_in=on_barge_in)

        # Route Turn Thread
        self.route_turn_thread = RouteTurnThread(
            connection_id=connection_id,
            speech_queue=self.speech_queue,
            orchestrator_func=orchestrator_func,
            memory_manager=memory_manager,
            transcript_emitter=transcript_emitter,
            response_sender=response_sender,
            on_greeting=on_greeting,
            on_announcement=on_announcement,
            on_user_transcript=on_user_transcript,
            on_tts_request=on_tts_request,
            thread_bridge=self.thread_bridge,
        )

        # Speech SDK Thread
        self.speech_sdk_thread = SpeechSDKThread(
            connection_id=connection_id,
            recognizer=self.recognizer,
            thread_bridge=self.thread_bridge,
            barge_in_handler=self._handle_barge_in_with_stt_stop,
            speech_queue=self.speech_queue,
            on_partial_transcript=on_partial_transcript,
        )

        self.thread_bridge.set_route_turn_thread(self.route_turn_thread)

        # Lifecycle
        self.running = False
        self._stopped = False

    async def _handle_barge_in_with_stt_stop(self) -> None:
        """Handle barge-in with STT timer stop."""
        # Stop STT timer first (barge-in ends the current recognition)
        if self.speech_sdk_thread:
            self.speech_sdk_thread.stop_stt_timer_for_barge_in()
        # Then delegate to the barge-in controller
        await self.barge_in_controller.handle_barge_in()

    async def start(self) -> None:
        """Start all threads."""
        with tracer.start_as_current_span(
            "speech_cascade_handler.start",
            kind=SpanKind.INTERNAL,
            attributes={"connection.id": self.connection_id},
        ):
            try:
                logger.info(f"[{self._conn_short}] Starting speech cascade handler")
                self.running = True

                # Capture main event loop
                main_loop = asyncio.get_running_loop()
                self.thread_bridge.set_main_loop(main_loop, self.connection_id)

                # Start threads
                self.speech_sdk_thread.prepare_thread()

                # Wait for thread to be ready
                for _ in range(10):
                    if self.speech_sdk_thread.thread_running:
                        break
                    await asyncio.sleep(0.05)

                # Start recognizer
                await asyncio.get_running_loop().run_in_executor(
                    None, self.speech_sdk_thread.start_recognizer
                )

                await self.route_turn_thread.start()

                logger.info(f"[{self._conn_short}] Speech cascade handler started")

            except Exception as e:
                logger.error(f"[{self._conn_short}] Failed to start: {e}")
                await self.stop()
                raise

    def write_audio(self, audio_bytes: bytes) -> None:
        """
        Write audio bytes to the speech recognizer.

        Args:
            audio_bytes: Raw audio bytes to process.
        """
        if self.running and self.speech_sdk_thread:
            self.speech_sdk_thread.write_audio(audio_bytes)

    def queue_event(self, event: SpeechEvent) -> bool:
        """
        Queue a speech event for processing.

        Args:
            event: Speech event to queue.

        Returns:
            True if successfully queued, False otherwise.
        """
        if not self.running:
            return False

        try:
            self.thread_bridge.queue_speech_result(self.speech_queue, event)
            return True
        except Exception as e:
            logger.error(f"[{self._conn_short}] Failed to queue event: {e}")
            return False

    def queue_greeting(
        self,
        text: str,
        language: str = "en-US",
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
    ) -> bool:
        """Queue a greeting for playback with optional voice configuration."""
        return self.queue_event(
            SpeechEvent(
                event_type=SpeechEventType.GREETING,
                text=text,
                language=language,
                speaker_id=self.connection_id,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
            )
        )

    def queue_announcement(
        self,
        text: str,
        language: str = "en-US",
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
    ) -> bool:
        """Queue an announcement for playback with optional voice configuration."""
        return self.queue_event(
            SpeechEvent(
                event_type=SpeechEventType.ANNOUNCEMENT,
                text=text,
                language=language,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
            )
        )

    async def play_tts_immediate(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
    ) -> None:
        """
        Play TTS immediately without queueing.

        Use this during LLM streaming to get immediate audio playback.
        Bypasses the speech_queue which may be blocked during orchestrator execution.

        Args:
            text: Text to synthesize and play.
            voice_name: Optional Azure TTS voice name override.
            voice_style: Optional voice style (e.g., "cheerful").
            voice_rate: Optional speech rate (e.g., "1.1").
        """
        if not text or not text.strip():
            return

        if self.on_tts_request:
            await self.on_tts_request(
                text,
                SpeechEventType.TTS_RESPONSE,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
            )

    def queue_tts(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
        language: str = "en-US",
    ) -> bool:
        """
        Queue TTS response for unified sequential playback.

        All TTS audio (LLM responses, greetings, announcements) should use this
        to ensure proper sequencing and avoid audio overlaps during handoffs.

        Args:
            text: Text to synthesize and play.
            voice_name: Optional Azure TTS voice name override.
            voice_style: Optional voice style (e.g., "cheerful").
            voice_rate: Optional speech rate (e.g., "1.1").
            language: Language code for synthesis.

        Returns:
            True if successfully queued, False otherwise.
        """
        return self.queue_event(
            SpeechEvent(
                event_type=SpeechEventType.TTS_RESPONSE,
                text=text,
                language=language,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
            )
        )

    def queue_user_text(self, text: str, language: str = "en-US") -> bool:
        """
        Queue user text input for orchestration.

        Used for text input (e.g., browser chat) that bypasses STT.

        Args:
            text: User text input.
            language: Language code.

        Returns:
            True if successfully queued, False otherwise.
        """
        return self.queue_event(
            SpeechEvent(
                event_type=SpeechEventType.FINAL,
                text=text,
                language=language,
                speaker_id=self.connection_id,
            )
        )

    async def stop(self) -> None:
        """Stop all threads and persist session state."""
        if self._stopped:
            return

        with tracer.start_as_current_span("speech_cascade_handler.stop", kind=SpanKind.INTERNAL):
            try:
                logger.info(f"[{self._conn_short}] Stopping speech cascade handler")
                self._stopped = True
                self.running = False

                cleanup_errors = []

                # Persist session state to Redis before stopping
                if self.memory_manager and self._redis_mgr:
                    try:
                        await self.memory_manager.persist_to_redis_async(self._redis_mgr)
                        logger.info(f"[{self._conn_short}] Session state persisted to Redis")
                    except Exception as e:
                        cleanup_errors.append(f"redis_persist: {e}")
                        logger.warning(f"[{self._conn_short}] Failed to persist to Redis: {e}")

                try:
                    await self.route_turn_thread.stop()
                except Exception as e:
                    cleanup_errors.append(f"route_turn_thread: {e}")

                try:
                    self.speech_sdk_thread.stop()
                except Exception as e:
                    cleanup_errors.append(f"speech_sdk_thread: {e}")

                try:
                    await self._clear_speech_queue_final()
                except Exception as e:
                    cleanup_errors.append(f"speech_queue_cleanup: {e}")

                if cleanup_errors:
                    logger.warning(
                        f"[{self._conn_short}] Stopped with {len(cleanup_errors)} cleanup errors"
                    )
                else:
                    logger.info(f"[{self._conn_short}] Speech cascade handler stopped")

            except Exception as e:
                logger.error(f"[{self._conn_short}] Critical stop error: {e}")

    async def _clear_speech_queue_final(self) -> None:
        """Final cleanup of speech queue."""
        try:
            cleared_count = 0
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break

            if cleared_count > 0:
                logger.info(
                    f"[{self._conn_short}] Final cleanup: cleared {cleared_count} speech events"
                )
        except Exception as e:
            logger.error(f"[{self._conn_short}] Error in final speech queue cleanup: {e}")

    # =========================================================================
    # Turn Telemetry Methods (delegate to route_turn_thread)
    # =========================================================================

    def record_llm_first_token(self) -> None:
        """Record LLM first token timing on the active turn span."""
        self.route_turn_thread.record_llm_first_token()

    def record_llm_complete(
        self,
        total_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        response_text: str | None = None,
    ) -> None:
        """Record LLM completion timing on the active turn span."""
        self.route_turn_thread.record_llm_complete(
            total_ms=total_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_text=response_text,
        )

    def record_tts_first_audio(self) -> None:
        """Record TTS first audio timing on the active turn span."""
        self.route_turn_thread.record_tts_first_audio()

    def record_tts_complete(self, total_ms: float | None = None) -> None:
        """Record TTS completion on the active turn span."""
        self.route_turn_thread.record_tts_complete(total_ms=total_ms)

    @property
    def turn_number(self) -> int:
        """Current turn number for external reference."""
        return self.route_turn_thread.turn_number


__all__ = [
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "SpeechSDKThread",
    "RouteTurnThread",
    "BargeInController",
    "ResponseSender",
    "TranscriptEmitter",
]
