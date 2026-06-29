"""
TTS Playback - Unified Text-to-Speech for Voice Handlers
=========================================================

Single source of truth for TTS playback across all voice transports.
Accepts VoiceSessionContext for clean dependency injection.

This module consolidates all TTS logic and eliminates:
- Circular dependency on session_agents (voice now comes from context)
- Scattered TTS code across multiple handlers
- Duplicated voice resolution logic

Usage:
    from apps.artagent.backend.voice.tts import TTSPlayback

    tts = TTSPlayback(context, app_state)
    await tts.speak("Hello, how can I help you?")
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import time
import uuid
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from utils.ml_logging import get_logger
from utils.telemetry_decorators import add_speech_tts_metrics, trace_speech

from apps.artagent.backend.src.orchestration.naming import find_agent_by_name
from apps.artagent.backend.src.orchestration.session_agents import get_session_agent

if TYPE_CHECKING:
    from apps.artagent.backend.voice.shared.context import VoiceSessionContext

# Audio sample rates
SAMPLE_RATE_BROWSER = 48000  # Browser WebAudio prefers 48kHz
SAMPLE_RATE_ACS = 16000  # ACS telephony uses 16kHz
_PCM16_BYTES_PER_SAMPLE = 2

# Streaming synthesis: when enabled, audio chunks are sent to the transport as
# Azure renders them (low time-to-first-audio) instead of waiting for the entire
# utterance. Toggle off (CASCADE_TTS_STREAMING=false) to fall back to blocking
# synthesize-then-stream without a code change.
_STREAMING_ENABLED = os.getenv("CASCADE_TTS_STREAMING", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

try:
    _ACS_STOP_AUDIO_GRACE_SECONDS = max(
        0.0,
        float(os.getenv("CASCADE_ACS_STOP_AUDIO_GRACE_SECONDS", "2.0")),
    )
except ValueError:
    _ACS_STOP_AUDIO_GRACE_SECONDS = 2.0

logger = get_logger("voice.tts.playback")
tracer = trace.get_tracer(__name__)


def _ws_is_connected(ws: WebSocket) -> bool:
    """Return True if both client and application states are active."""
    return (
        ws.client_state == WebSocketState.CONNECTED
        and ws.application_state == WebSocketState.CONNECTED
    )


class TTSPlayback:
    """
    Unified TTS playback for all voice transports.

    Single source of truth for TTS:
    - Accepts VoiceSessionContext (no global state lookups)
    - Voice resolved from context.current_agent or fallback
    - Routes to appropriate transport (Browser/ACS) automatically
    - Thread-safe cancellation via context.cancel_event

    Backward Compatibility:
    - Also accepts legacy parameters (websocket, app_state, session_id)
    - Automatically creates VoiceSessionContext from legacy parameters
    """

    def __init__(
        self,
        context: VoiceSessionContext | WebSocket,
        app_state: Any,
        session_id: str | None = None,
        *,
        cancel_event: asyncio.Event | None = None,
    ):
        """
        Initialize TTS playback.

        Args:
            context: VoiceSessionContext OR WebSocket (legacy)
            app_state: Application state with TTS pool and executor
            session_id: Session ID (legacy, only if context is WebSocket)
            cancel_event: Cancel event (legacy, only if context is WebSocket)
        """
        # Backward compatibility: detect legacy API
        if isinstance(context, WebSocket):
            # Legacy API: context is actually a websocket
            from apps.artagent.backend.voice.shared.context import (
                VoiceSessionContext,
                TransportType,
            )

            websocket = context
            self._context = VoiceSessionContext(
                session_id=session_id or "unknown",
                transport=TransportType.BROWSER,  # Default, will be inferred
                _websocket=websocket,
                cancel_event=cancel_event or asyncio.Event(),
            )
        else:
            # New API: context is VoiceSessionContext
            self._context = context

        self._app_state = app_state
        self._tts_lock = asyncio.Lock()
        self._transport_send_lock = asyncio.Lock()
        self._is_playing = False
        self._transport_playback_until = 0.0
        self._last_transport_audio_sent_at = 0.0

    @property
    def context(self) -> VoiceSessionContext:
        """Get the voice session context."""
        return self._context

    @property
    def is_playing(self) -> bool:
        """Check if TTS is currently playing."""
        return self._is_playing or time.perf_counter() < self._transport_playback_until

    @property
    def has_pending_transport_playback(self) -> bool:
        """Return True while the transport may still be playing queued audio.

        Applies to every transport: ACS/VoiceLive buffer audio server-side, and
        the browser buffers PCM frames client-side via its WebAudio worklet. In
        both cases the backend can finish *sending* frames well before playback
        actually ends, so barge-in must remain armed for the buffered window.
        """
        now = time.perf_counter()
        if self._is_playing or now < self._transport_playback_until:
            return True

        return (
            self._last_transport_audio_sent_at > 0
            and now - self._last_transport_audio_sent_at < _ACS_STOP_AUDIO_GRACE_SECONDS
        )

    @property
    def _ws(self) -> WebSocket:
        """Get WebSocket from context."""
        return self._context.websocket

    @property
    def _session_id(self) -> str:
        """Get session ID from context."""
        return self._context.session_id

    @property
    def _session_short(self) -> str:
        """Get shortened session ID for logging."""
        return self._session_id[-8:] if self._session_id else "unknown"

    @property
    def _cancel_event(self) -> asyncio.Event:
        """Get cancel event from context."""
        return self._context.cancel_event

    async def _get_tts_client(self) -> Any:
        """Return the session-owned TTS client, falling back to pool acquisition."""
        synth = self._context.tts_client
        if synth is not None:
            return synth

        session_key = self._context.call_connection_id or self._session_id
        synth, _ = await self._app_state.tts_pool.acquire_for_session(session_key)
        self._context.tts_client = synth
        return synth

    def get_agent_voice(self) -> tuple[str, str | None, str | None]:
        """
        Get voice configuration from the active agent in context.

        Priority:
        1. context.current_agent (already resolved)
        2. Session agent (Agent Builder override) - fallback
        3. Start agent from unified agents - fallback

        Returns:
            Tuple of (voice_name, voice_style, voice_rate).
            voice_name will always have a value (fallback if needed).
        """
        # First try context.current_agent (already resolved, no circular import)
        current_agent = self._context.current_agent
        if current_agent and hasattr(current_agent, "voice") and current_agent.voice:
            voice = current_agent.voice
            if voice.name:
                agent_name = getattr(current_agent, "name", "unknown")
                logger.debug(
                    "[%s] Voice from context agent '%s': %s",
                    self._session_short,
                    agent_name,
                    voice.name,
                )
                return (voice.name, voice.style, voice.rate)

        # Try session agent (Agent Builder override) - has priority over base agents.
        # Look up by the active/start agent name first, then fall back to the
        # session's default agent: an Agent Builder / Quick Tune edit is stored
        # under the agent's *own* name, which may differ from app_state.start_agent
        # (e.g. when a scenario is active). Without this fallback the override's
        # voice silently never applies.
        start_agent_name = getattr(self._app_state, "start_agent", "Concierge")
        session_agent = get_session_agent(self._context.session_id, start_agent_name)
        if session_agent is None:
            session_agent = get_session_agent(self._context.session_id)
        if session_agent and hasattr(session_agent, "voice") and session_agent.voice:
            voice = session_agent.voice
            if voice.name:
                logger.debug(
                    "[%s] Voice from session agent '%s': %s",
                    self._session_short,
                    getattr(session_agent, "name", start_agent_name),
                    voice.name,
                )
                return (voice.name, voice.style, voice.rate)

        # Fallback to start agent from unified agents (base registry)
        unified_agents = getattr(self._app_state, "unified_agents", {})
        # Use case-insensitive lookup
        _, start_agent = find_agent_by_name(unified_agents, start_agent_name)

        if start_agent and hasattr(start_agent, "voice") and start_agent.voice:
            voice = start_agent.voice
            if voice.name:
                logger.debug(
                    "[%s] Voice from start agent '%s': %s",
                    self._session_short,
                    start_agent_name,
                    voice.name,
                )
                return (voice.name, voice.style, voice.rate)

        # Emergency fallback - should not happen if agents are configured
        logger.warning(
            "[%s] No agent voice found, using fallback voice",
            self._session_short,
        )
        return ("en-US-AvaMultilingualNeural", "conversational", None)

    def set_active_agent(self, agent_name: str | None) -> None:
        """
        Set the current active agent for voice resolution (legacy API).

        For backward compatibility with MediaHandler. New code should
        set context.current_agent directly.

        Args:
            agent_name: Name of the active agent
        """
        if agent_name:
            # First check session agents (Agent Builder overrides have priority)
            session_agent = get_session_agent(self._context.session_id, agent_name)
            if session_agent:
                self._context.current_agent = session_agent
                logger.debug(
                    "[%s] Active agent set from session agents: %s (voice=%s)",
                    self._session_short,
                    agent_name,
                    (
                        getattr(session_agent.voice, "name", "unknown")
                        if session_agent.voice
                        else "none"
                    ),
                )
                return

            # Fallback to unified_agents (base registry)
            unified_agents = getattr(self._app_state, "unified_agents", {})
            actual_key, agent = find_agent_by_name(unified_agents, agent_name)
            if actual_key is not None:
                self._context.current_agent = agent
                logger.debug(
                    "[%s] Active agent set from unified_agents: %s",
                    self._session_short,
                    agent_name,
                )
            else:
                logger.warning(
                    "[%s] Agent '%s' not found in session_agents or unified_agents",
                    self._session_short,
                    agent_name,
                )
        else:
            self._context.current_agent = None

    async def prepare_voice(
        self,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
        sample_rate: int | None = None,
        timeout_sec: float = 2.5,
    ) -> bool:
        """Prime the session TTS client for the next utterance's voice."""
        synth = self._context.tts_client
        if not synth or not getattr(synth, "is_ready", False):
            logger.debug(
                "[%s] TTS voice warmup skipped: synthesizer not ready", self._session_short
            )
            return False

        if not hasattr(synth, "warm_connection"):
            logger.debug(
                "[%s] TTS voice warmup skipped: no warm_connection hook", self._session_short
            )
            return False

        if not voice_name:
            voice_name, voice_style, voice_rate = self.get_agent_voice()

        resolved_sample_rate = sample_rate
        if resolved_sample_rate is None:
            resolved_sample_rate = (
                SAMPLE_RATE_BROWSER if self._context.is_browser else SAMPLE_RATE_ACS
            )

        style = voice_style or "conversational"
        rate = voice_rate or "medium"
        loop = asyncio.get_running_loop()
        executor = getattr(self._app_state, "speech_executor", None)
        warm_func = partial(
            synth.warm_connection,
            voice=voice_name,
            sample_rate=resolved_sample_rate,
            style=style,
            rate=rate,
        )

        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, warm_func),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.debug(
                "[%s] TTS voice warmup timed out | voice=%s sample_rate=%s timeout=%.1fs",
                self._session_short,
                voice_name,
                resolved_sample_rate,
                timeout_sec,
            )
            return False
        except Exception as exc:
            logger.debug("[%s] TTS voice warmup failed: %s", self._session_short, exc)
            return False

        logger.info(
            "[%s] TTS voice warmup %s | voice=%s style=%s rate=%s sample_rate=%s elapsed_ms=%.1f",
            self._session_short,
            "ready" if result else "incomplete",
            voice_name,
            style,
            rate,
            resolved_sample_rate,
            (time.perf_counter() - start) * 1000,
        )
        return bool(result)

    async def speak(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
        is_greeting: bool = False,
        on_first_audio: Callable[[], None] | None = None,
    ) -> bool:
        """
        Speak text via TTS, routing to appropriate transport.

        Automatically determines transport from context.transport:
        - 'browser' -> play_to_browser()
        - 'acs' -> play_to_acs()
        - 'voicelive' -> play_to_acs() (VoiceLive uses ACS format)

        Args:
            text: Text to synthesize
            voice_name: Override voice (uses agent voice if not provided)
            voice_style: Override style
            voice_rate: Override rate
            is_greeting: Whether this is a greeting (for metrics)
            on_first_audio: Callback when first audio chunk is sent

        Returns:
            True if playback completed, False if cancelled or failed
        """
        transport = self._context.transport

        # Dedicated TTS span so synthesis/playback shows as its own line item on
        # the turn timeline (otherwise this awaited work is an unexplained gap
        # inside the LLM/orchestrator span). Tagged with first-audio + total.
        with tracer.start_as_current_span(
            "tts.speak",
            kind=SpanKind.INTERNAL,
            attributes={
                "tts.transport": transport.value,
                "tts.text_length": len(text or ""),
                "tts.is_greeting": is_greeting,
                "tts.voice_name": voice_name or "",
            },
        ) as tts_span:
            tts_start = time.perf_counter()
            first_audio_marked = False

            def _on_first_audio_wrapper() -> None:
                nonlocal first_audio_marked
                if not first_audio_marked:
                    first_audio_marked = True
                    ttfa_ms = (time.perf_counter() - tts_start) * 1000
                    tts_span.set_attribute("tts.ttfa_ms", round(ttfa_ms, 1))
                    tts_span.add_event(
                        "tts.first_audio", attributes={"tts.ttfa_ms": round(ttfa_ms, 1)}
                    )
                if on_first_audio:
                    on_first_audio()

            if transport.value == "browser":
                result = await self.play_to_browser(
                    text,
                    voice_name=voice_name,
                    voice_style=voice_style,
                    voice_rate=voice_rate,
                    on_first_audio=_on_first_audio_wrapper,
                )
            else:
                # ACS and VoiceLive both use ACS format
                result = await self.play_to_acs(
                    text,
                    voice_name=voice_name,
                    voice_style=voice_style,
                    voice_rate=voice_rate,
                    on_first_audio=_on_first_audio_wrapper,
                )

            tts_span.set_attribute(
                "tts.total_ms", round((time.perf_counter() - tts_start) * 1000, 1)
            )
            tts_span.set_attribute("tts.completed", bool(result))
            return result

    async def play_to_browser(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
        on_first_audio: Callable[[], None] | None = None,
    ) -> bool:
        """
        Play TTS audio to browser WebSocket.

        Args:
            text: Text to synthesize
            voice_name: Override voice (uses agent voice if not provided)
            voice_style: Override style
            voice_rate: Override rate
            on_first_audio: Callback when first audio chunk is sent

        Returns:
            True if playback completed, False if cancelled or failed
        """
        if not text or not text.strip():
            return False

        run_id = uuid.uuid4().hex[:8]

        # Resolve voice from agent if not provided
        if not voice_name:
            voice_name, voice_style, voice_rate = self.get_agent_voice()

        style = voice_style or "conversational"
        rate = voice_rate or "medium"

        logger.debug(
            "[%s] Browser TTS: voice=%s style=%s rate=%s (run=%s)",
            self._session_short,
            voice_name,
            style,
            rate,
            run_id,
        )

        # Synthesize under lock, stream without lock to avoid blocking
        # concurrent TTS requests during the (slower) streaming phase.
        pcm_bytes = None
        try:
            async with self._tts_lock:
                # Barge-in owns the cancel event; only read it here so a fresh
                # barge-in signal is not wiped before the handler resets it.
                if self._cancel_event.is_set():
                    return False

                self._is_playing = True
                synth = None

                synth = await self._get_tts_client()

                # Validate synthesizer has valid config
                if not synth or not getattr(synth, "is_ready", False):
                    logger.error(
                        "[%s] TTS synthesizer not initialized (missing speech config) - check Azure credentials",
                        self._session_short,
                    )
                    return False

                # Streaming path: synthesize and send interleaved (low TTFA).
                # Held under lock for the full duration since synthesis and
                # transmission are pipelined together.
                if _STREAMING_ENABLED and hasattr(synth, "synthesize_to_pcm_stream"):
                    return await self._stream_synth_to_browser(
                        synth, text, voice_name, style, rate, on_first_audio, run_id
                    )

                # Synthesize audio (under lock)
                pcm_bytes = await self._synthesize(
                    synth, text, voice_name, style, rate, SAMPLE_RATE_BROWSER
                )

            # Lock released — check cancel before streaming (read-only).
            if self._cancel_event.is_set():
                return False

            if not pcm_bytes:
                logger.warning("[%s] TTS returned empty audio", self._session_short)
                return False

            # Stream to browser (without lock)
            return await self._stream_to_browser(pcm_bytes, on_first_audio, run_id)

        except asyncio.CancelledError:
            logger.debug("[%s] Browser TTS cancelled", self._session_short)
            return False
        except Exception as e:
            logger.error("[%s] Browser TTS failed: %s", self._session_short, e)
            return False
        finally:
            self._is_playing = False

    async def play_to_acs(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_style: str | None = None,
        voice_rate: str | None = None,
        blocking: bool = False,
        on_first_audio: Callable[[], None] | None = None,
    ) -> bool:
        """
        Play TTS audio to ACS WebSocket.

        Args:
            text: Text to synthesize
            voice_name: Override voice (uses agent voice if not provided)
            voice_style: Override style
            voice_rate: Override rate
            blocking: Whether to pace audio for real-time playback
            on_first_audio: Callback when first audio chunk is sent

        Returns:
            True if playback completed, False if cancelled or failed
        """
        if not text or not text.strip():
            logger.warning("[%s] ACS TTS: Empty text, skipping", self._session_short)
            return False

        run_id = uuid.uuid4().hex[:8]

        # Resolve voice from agent if not provided
        if not voice_name:
            voice_name, voice_style, voice_rate = self.get_agent_voice()

        style = voice_style or "conversational"
        rate = voice_rate or "medium"

        logger.info(
            "[%s] ACS TTS START: text='%s...' voice=%s style=%s rate=%s blocking=%s (run=%s)",
            self._session_short,
            text[:50],
            voice_name,
            style,
            rate,
            blocking,
            run_id,
        )

        # Synthesize under lock, stream without lock to avoid blocking
        # concurrent TTS requests during the (slower) streaming phase.
        pcm_bytes = None
        try:
            async with self._tts_lock:
                # Barge-in owns the cancel event; only read it here so a fresh
                # barge-in signal is not wiped before the handler resets it.
                if self._cancel_event.is_set():
                    return False

                self._is_playing = True
                synth = None

                synth = await self._get_tts_client()

                # Validate synthesizer has valid config
                if not synth or not getattr(synth, "is_ready", False):
                    logger.error(
                        "[%s] TTS synthesizer not initialized (missing speech config) - check Azure credentials",
                        self._session_short,
                    )
                    return False

                # Synthesize audio (under lock)
                logger.info(
                    "[%s] ACS TTS: Starting synthesis at %dHz", self._session_short, SAMPLE_RATE_ACS
                )

                # Streaming path: synthesize and send interleaved (low TTFA).
                # Held under lock for the full duration since synthesis and
                # transmission are pipelined together.
                if _STREAMING_ENABLED and hasattr(synth, "synthesize_to_pcm_stream"):
                    result = await self._stream_synth_to_acs(
                        synth, text, voice_name, style, rate, blocking, on_first_audio, run_id
                    )
                    logger.info(
                        "[%s] ACS TTS: Stream complete, result=%s", self._session_short, result
                    )
                    return result

                pcm_bytes = await self._synthesize(
                    synth, text, voice_name, style, rate, SAMPLE_RATE_ACS
                )

            # Lock released — check cancel before streaming (read-only).
            if self._cancel_event.is_set():
                return False

            if not pcm_bytes:
                logger.error(
                    "[%s] ACS TTS returned empty audio (synthesis failed)", self._session_short
                )
                return False

            logger.info(
                "[%s] ACS TTS: Synthesis OK, got %d bytes, starting stream",
                self._session_short,
                len(pcm_bytes),
            )

            # Stream to ACS (without lock)
            result = await self._stream_to_acs(pcm_bytes, blocking, on_first_audio, run_id)
            logger.info("[%s] ACS TTS: Stream complete, result=%s", self._session_short, result)
            return result

        except asyncio.CancelledError:
            logger.debug("[%s] ACS TTS cancelled", self._session_short)
            return False
        except Exception as e:
            logger.error("[%s] ACS TTS failed: %s", self._session_short, e)
            return False
        finally:
            self._is_playing = False

    @trace_speech(operation="tts.synthesize")
    async def _synthesize(
        self,
        synth: Any,
        text: str,
        voice: str,
        style: str,
        rate: str,
        sample_rate: int,
    ) -> bytes | None:
        """Synthesize text to PCM audio bytes."""
        logger.info(
            "[%s] Synthesizing: text_len=%d voice=%s rate=%s sample_rate=%d",
            self._session_short,
            len(text),
            voice,
            rate,
            sample_rate,
        )

        loop = asyncio.get_running_loop()
        executor = getattr(self._app_state, "speech_executor", None)

        synth_func = partial(
            synth.synthesize_to_pcm,
            text=text,
            voice=voice,
            sample_rate=sample_rate,
            style=style,
            rate=rate,
        )

        # Add timeout to prevent indefinite blocking on Speech SDK issues
        # The "Codec decoding is not started within 2s" error can cause hangs
        # Dynamic timeout: base 10s + ~1s per 100 chars (Azure TTS is ~100-200 words/sec)
        base_timeout = 10.0
        per_char_timeout = len(text) / 100.0  # ~1 second per 100 chars
        synthesis_timeout = min(base_timeout + per_char_timeout, 120.0)  # Cap at 2 minutes

        try:
            if executor:
                result = await asyncio.wait_for(
                    loop.run_in_executor(executor, synth_func), timeout=synthesis_timeout
                )
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, synth_func), timeout=synthesis_timeout
                )
        except asyncio.TimeoutError:
            logger.error(
                "[%s] TTS synthesis timed out after %.1fs (voice=%s, text_len=%d)",
                self._session_short,
                synthesis_timeout,
                voice,
                len(text),
            )
            return None

        if result:
            logger.info("[%s] Synthesis complete: %d bytes", self._session_short, len(result))
            add_speech_tts_metrics(
                voice=voice,
                audio_size_bytes=len(result),
                text_length=len(text),
                sample_rate=sample_rate,
            )
        else:
            logger.warning("[%s] Synthesis returned None/empty", self._session_short)

        return result

    async def _iter_synth_chunks(
        self,
        synth: Any,
        text: str,
        voice: str,
        style: str,
        rate: str,
        sample_rate: int,
    ):
        """
        Async-iterate raw PCM chunks from the blocking streaming generator.

        Runs ``synth.synthesize_to_pcm_stream`` (a synchronous generator that
        blocks on Azure ``read_data``) inside the speech executor and bridges
        its output to the event loop via a queue, yielding PCM byte chunks as
        they are produced. Honors barge-in by stopping the producer when the
        cancel event is set.
        """
        loop = asyncio.get_running_loop()
        executor = getattr(self._app_state, "speech_executor", None)
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _producer() -> None:
            try:
                for chunk in synth.synthesize_to_pcm_stream(
                    text=text,
                    voice=voice,
                    sample_rate=sample_rate,
                    style=style,
                    rate=rate,
                ):
                    if self._cancel_event.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # surface to consumer
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        producer_future = loop.run_in_executor(executor, _producer)
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            with contextlib.suppress(Exception):
                await producer_future

    async def _stream_synth_to_browser(
        self,
        synth: Any,
        text: str,
        voice: str,
        style: str,
        rate: str,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Synthesize and stream PCM to the browser WebSocket as it is produced."""
        chunk_size = 4800  # 100ms at 48kHz mono 16-bit
        buffer = bytearray()
        first_sent = False
        frame_index = 0
        total_bytes = 0

        logger.info("[%s] Browser TTS (streaming) START (run=%s)", self._session_short, run_id)

        async def _send_frame(frame: bytes, is_final: bool) -> bool:
            nonlocal first_sent, frame_index
            if not _ws_is_connected(self._ws):
                logger.warning(
                    "[%s] Browser stream aborted: WebSocket disconnected", self._session_short
                )
                return False
            await self._ws.send_json(
                {
                    "type": "audio_data",
                    "data": base64.b64encode(frame).decode("utf-8"),
                    "sample_rate": SAMPLE_RATE_BROWSER,
                    "frame_index": frame_index,
                    # total_frames is unknown while streaming; the frontend only
                    # uses it for cosmetic logging, not playback control.
                    "total_frames": 0,
                    "is_final": is_final,
                }
            )
            self._mark_browser_audio_queued(len(frame))
            frame_index += 1
            if not first_sent:
                first_sent = True
                if on_first_audio:
                    with contextlib.suppress(Exception):
                        on_first_audio()
            await asyncio.sleep(0)
            return True

        try:
            async for pcm in self._iter_synth_chunks(
                synth, text, voice, style, rate, SAMPLE_RATE_BROWSER
            ):
                if self._cancel_event.is_set():
                    logger.debug("[%s] Browser stream cancelled", self._session_short)
                    return False
                buffer.extend(pcm)
                total_bytes += len(pcm)
                while len(buffer) >= chunk_size:
                    frame = bytes(buffer[:chunk_size])
                    del buffer[:chunk_size]
                    if not await _send_frame(frame, is_final=False):
                        return False
        except Exception as e:
            logger.error("[%s] Browser streaming synthesis failed: %s", self._session_short, e)
            return False

        # Flush remaining tail as the final frame.
        if buffer:
            if not await _send_frame(bytes(buffer), is_final=True):
                return False

        if total_bytes:
            add_speech_tts_metrics(
                voice=voice,
                audio_size_bytes=total_bytes,
                text_length=len(text),
                sample_rate=SAMPLE_RATE_BROWSER,
            )

        logger.info(
            "[%s] Browser TTS (streaming) complete: %d bytes, %d frames (run=%s)",
            self._session_short,
            total_bytes,
            frame_index,
            run_id,
        )
        return total_bytes > 0

    async def _stream_synth_to_acs(
        self,
        synth: Any,
        text: str,
        voice: str,
        style: str,
        rate: str,
        blocking: bool,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Synthesize and stream PCM to the ACS WebSocket as it is produced."""
        chunk_size = 1280  # 40ms at 16kHz mono 16-bit
        buffer = bytearray()
        first_sent = False
        chunks_sent = 0
        total_bytes = 0

        if self._ws is None:
            logger.error("[%s] ACS stream ERROR: WebSocket is None!", self._session_short)
            return False

        logger.info(
            "[%s] ACS stream (streaming) START (chunk_size=%d, blocking=%s) ws=%s",
            self._session_short,
            chunk_size,
            blocking,
            type(self._ws).__name__,
        )

        async def _send_frame(frame: bytes) -> bool:
            nonlocal first_sent, chunks_sent
            if not _ws_is_connected(self._ws):
                logger.warning(
                    "[%s] ACS stream aborted: WebSocket disconnected", self._session_short
                )
                return False
            try:
                sent = await self._send_acs_json(
                    {
                        "kind": "AudioData",
                        "audioData": {
                            "data": base64.b64encode(frame).decode("utf-8"),
                            "timestamp": None,
                            "participantRawID": None,
                            "silent": False,
                        },
                    }
                )
            except Exception as e:
                logger.error(
                    "[%s] ACS stream ERROR sending chunk %d: %s",
                    self._session_short,
                    chunks_sent + 1,
                    e,
                )
                return False
            if not sent:
                # Barge-in StopAudio is in effect; stop streaming immediately so
                # no AudioData reaches ACS after the stop.
                logger.debug(
                    "[%s] ACS stream suppressed (barge-in StopAudio)", self._session_short
                )
                return False
            self._mark_acs_audio_queued(len(frame))
            chunks_sent += 1
            if not first_sent:
                first_sent = True
                logger.info("[%s] ACS stream: First chunk sent successfully", self._session_short)
                if on_first_audio:
                    with contextlib.suppress(Exception):
                        on_first_audio()
            await asyncio.sleep(0.04 if blocking else 0)
            return True

        try:
            async for pcm in self._iter_synth_chunks(
                synth, text, voice, style, rate, SAMPLE_RATE_ACS
            ):
                if self._cancel_event.is_set():
                    logger.debug("[%s] ACS stream cancelled", self._session_short)
                    return False
                buffer.extend(pcm)
                total_bytes += len(pcm)
                while len(buffer) >= chunk_size:
                    if self._cancel_event.is_set():
                        logger.debug("[%s] ACS stream cancelled", self._session_short)
                        return False
                    frame = bytes(buffer[:chunk_size])
                    del buffer[:chunk_size]
                    if not await _send_frame(frame):
                        return False
        except Exception as e:
            logger.error("[%s] ACS streaming synthesis failed: %s", self._session_short, e)
            return False

        # Flush remaining tail (sent as-is, matching the blocking path).
        if buffer:
            if not await _send_frame(bytes(buffer)):
                return False

        if total_bytes:
            add_speech_tts_metrics(
                voice=voice,
                audio_size_bytes=total_bytes,
                text_length=len(text),
                sample_rate=SAMPLE_RATE_ACS,
            )

        logger.info(
            "[%s] ACS stream (streaming) COMPLETE: %d chunks sent, %d bytes total (run=%s)",
            self._session_short,
            chunks_sent,
            total_bytes,
            run_id,
        )
        return total_bytes > 0

    async def _stream_to_browser(
        self,
        pcm_bytes: bytes,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Stream PCM audio to browser WebSocket."""
        chunk_size = 4800  # 100ms at 48kHz mono 16-bit
        first_sent = False
        chunks_sent = 0
        total_frames = (len(pcm_bytes) + chunk_size - 1) // chunk_size

        logger.info(
            "[%s] Streaming %d bytes to browser, %d frames (run=%s)",
            self._session_short,
            len(pcm_bytes),
            total_frames,
            run_id,
        )

        for i in range(0, len(pcm_bytes), chunk_size):
            if self._cancel_event.is_set():
                logger.debug("[%s] Browser stream cancelled", self._session_short)
                return False

            # Check WebSocket connection before sending
            if not _ws_is_connected(self._ws):
                logger.warning(
                    "[%s] Browser stream aborted: WebSocket disconnected", self._session_short
                )
                return False

            chunk = pcm_bytes[i : i + chunk_size]
            b64_chunk = base64.b64encode(chunk).decode("utf-8")
            frame_index = chunks_sent
            is_final = (i + chunk_size) >= len(pcm_bytes)

            await self._ws.send_json(
                {
                    "type": "audio_data",
                    "data": b64_chunk,
                    "sample_rate": SAMPLE_RATE_BROWSER,
                    "frame_index": frame_index,
                    "total_frames": total_frames,
                    "is_final": is_final,
                }
            )
            self._mark_browser_audio_queued(len(chunk))
            chunks_sent += 1

            if not first_sent:
                first_sent = True
                if on_first_audio:
                    try:
                        on_first_audio()
                    except Exception:
                        pass

            await asyncio.sleep(0)

        logger.info(
            "[%s] Browser TTS complete: %d bytes, %d chunks (run=%s)",
            self._session_short,
            len(pcm_bytes),
            chunks_sent,
            run_id,
        )
        return True

    async def _stream_to_acs(
        self,
        pcm_bytes: bytes,
        blocking: bool,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Stream PCM audio to ACS WebSocket."""
        chunk_size = 1280  # 40ms at 16kHz mono 16-bit (640 samples × 2 bytes/sample)
        first_sent = False
        chunks_sent = 0
        total_chunks = (len(pcm_bytes) + chunk_size - 1) // chunk_size

        # Verify WebSocket is available
        if self._ws is None:
            logger.error("[%s] ACS stream ERROR: WebSocket is None!", self._session_short)
            return False

        logger.info(
            "[%s] ACS stream START: %d bytes, %d chunks (chunk_size=%d, blocking=%s) ws=%s",
            self._session_short,
            len(pcm_bytes),
            total_chunks,
            chunk_size,
            blocking,
            type(self._ws).__name__,
        )

        for i in range(0, len(pcm_bytes), chunk_size):
            if self._cancel_event.is_set():
                logger.debug("[%s] ACS stream cancelled", self._session_short)
                return False

            chunk = pcm_bytes[i : i + chunk_size]
            b64_chunk = base64.b64encode(chunk).decode("utf-8")

            # Check WebSocket connection before sending
            if not _ws_is_connected(self._ws):
                logger.warning(
                    "[%s] ACS stream aborted: WebSocket disconnected", self._session_short
                )
                return False

            message = {
                "kind": "AudioData",
                "audioData": {
                    "data": b64_chunk,
                    "timestamp": None,
                    "participantRawID": None,
                    "silent": False,
                },
            }

            try:
                sent = await self._send_acs_json(message)
            except Exception as e:
                logger.error(
                    "[%s] ACS stream ERROR sending chunk %d/%d: %s",
                    self._session_short,
                    chunks_sent + 1,
                    total_chunks,
                    e,
                )
                return False
            if not sent:
                # Barge-in StopAudio is in effect; stop streaming immediately so
                # no AudioData reaches ACS after the stop.
                logger.debug(
                    "[%s] ACS stream suppressed (barge-in StopAudio)", self._session_short
                )
                return False
            self._mark_acs_audio_queued(len(chunk))
            chunks_sent += 1
            if chunks_sent == 1:
                logger.info(
                    "[%s] ACS stream: First chunk sent successfully", self._session_short
                )

            if not first_sent:
                first_sent = True
                if on_first_audio:
                    try:
                        on_first_audio()
                    except Exception:
                        pass

            if blocking:
                await asyncio.sleep(0.04)  # 40ms pacing
            else:
                await asyncio.sleep(0)

        logger.info(
            "[%s] ACS stream COMPLETE: %d chunks sent, %d bytes total (run=%s)",
            self._session_short,
            chunks_sent,
            len(pcm_bytes),
            run_id,
        )
        return True

    async def _send_acs_json(
        self, message: dict[str, Any], *, allow_during_cancel: bool = False
    ) -> bool:
        """Serialize ACS media websocket writes across audio and StopAudio control.

        Returns True if the message was written. ``AudioData`` writes are
        suppressed (return False) once a barge-in cancel is in effect, so no
        audio is ever sent *after* a StopAudio control message. The transport
        lock serializes the two: a StopAudio acquires the lock, and any audio
        frame that acquires the lock afterwards observes the cancel flag and is
        dropped. Control messages (StopAudio) pass ``allow_during_cancel=True``
        to bypass the gate so the stop itself is never suppressed.
        """
        async with self._transport_send_lock:
            if not allow_during_cancel and self._cancel_event.is_set():
                return False
            await self._ws.send_json(message)
            return True

    def _note_transport_audio(self, byte_count: int, sample_rate: int) -> None:
        """Track how long the transport may keep playing already-sent audio."""
        if byte_count <= 0:
            return

        frame_seconds = byte_count / (sample_rate * _PCM16_BYTES_PER_SAMPLE)
        now = time.perf_counter()
        self._last_transport_audio_sent_at = now
        self._transport_playback_until = max(now, self._transport_playback_until) + frame_seconds

    def _mark_acs_audio_queued(self, byte_count: int) -> None:
        """Track how long ACS may continue playing already-queued audio."""
        self._note_transport_audio(byte_count, SAMPLE_RATE_ACS)

    def _mark_browser_audio_queued(self, byte_count: int) -> None:
        """Track how long the browser may keep playing already-buffered audio."""
        self._note_transport_audio(byte_count, SAMPLE_RATE_BROWSER)

    def reset_transport_playback_tracking(self) -> None:
        """Clear buffered-playback bookkeeping after a transport stop."""
        self._is_playing = False
        self._transport_playback_until = 0.0
        self._last_transport_audio_sent_at = 0.0

    async def stop_transport_playback(self, *, reason: str = "barge_in") -> bool:
        """Actively stop ACS-side playback and clear any buffered media."""
        self.cancel()
        self.reset_transport_playback_tracking()

        if not (self._context.is_acs or self._context.is_voicelive):
            return False

        if self._ws is None or not _ws_is_connected(self._ws):
            logger.debug("[%s] ACS StopAudio skipped: websocket not connected", self._session_short)
            return False

        stop_message = {
            "kind": "StopAudio",
            "AudioData": None,
            "StopAudio": {},
        }
        try:
            # Bypass the AudioData cancel-gate: the stop itself must always go out.
            await self._send_acs_json(stop_message, allow_during_cancel=True)
        except Exception as exc:
            logger.debug("[%s] Failed to send ACS StopAudio: %s", self._session_short, exc)
            return False

        logger.info("[%s] Sent ACS StopAudio | reason=%s", self._session_short, reason)
        return True

    def cancel(self) -> None:
        """Signal TTS cancellation (for barge-in)."""
        self._cancel_event.set()


# Backward compatibility: also export from old location
# TODO: Remove after Phase 3 (all consumers migrated)
__all__ = [
    "TTSPlayback",
    "SAMPLE_RATE_BROWSER",
    "SAMPLE_RATE_ACS",
]
