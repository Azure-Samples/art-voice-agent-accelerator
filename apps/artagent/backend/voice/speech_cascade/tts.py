"""
TTS Playback - Unified Text-to-Speech for Speech Cascade
=========================================================

Single source of truth for TTS playback in the speech cascade architecture.
Voice configuration comes from the active agent (session or unified).

This module consolidates all TTS logic previously scattered across:
- tts_sender.py (removed)
- shared_ws.py send_tts_audio (deprecated)
- media_handler._send_tts_* methods (simplified to delegate here)

Usage:
    from apps.artagent.backend.voice.speech_cascade.tts import TTSPlayback

    tts = TTSPlayback(websocket, app_state, session_id)
    await tts.play(text, transport=TransportType.BROWSER)
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.tools.latency_tool import LatencyTool
from utils.ml_logging import get_logger

from .metrics import record_tts_streaming, record_tts_synthesis

if TYPE_CHECKING:
    pass

# Audio sample rates
SAMPLE_RATE_BROWSER = 48000  # Browser WebAudio prefers 48kHz
SAMPLE_RATE_ACS = 16000  # ACS telephony uses 16kHz

logger = get_logger("voice.speech_cascade.tts")
tracer = trace.get_tracer(__name__)


class TTSPlayback:
    """
    Unified TTS playback for speech cascade.

    Handles voice resolution from agent config, synthesis, and streaming
    to both browser and ACS transports.
    """

    def __init__(
        self,
        websocket: WebSocket,
        app_state: Any,
        session_id: str,
        *,
        latency_tool: LatencyTool | None = None,
        cancel_event: asyncio.Event | None = None,
    ):
        """
        Initialize TTS playback.

        Args:
            websocket: WebSocket connection for audio streaming
            app_state: Application state with TTS pool and unified agents
            session_id: Session ID for agent lookup and logging
            latency_tool: Optional latency tracking
            cancel_event: Event to signal TTS cancellation (barge-in)
        """
        self._ws = websocket
        self._app_state = app_state
        self._session_id = session_id
        self._session_short = session_id[-8:] if session_id else "unknown"
        self._latency_tool = latency_tool
        self._cancel_event = cancel_event or asyncio.Event()
        self._tts_lock = asyncio.Lock()
        self._is_playing = False
        self._active_agent: str | None = None  # Track current agent for voice lookup

    def set_active_agent(self, agent_name: str | None) -> None:
        """
        Set the current active agent for voice resolution.

        Call this when agent switches occur to ensure TTS uses the correct voice.

        Args:
            agent_name: Name of the active agent, or None to reset.
        """
        self._active_agent = agent_name
        if agent_name:
            logger.debug(
                "[%s] Active agent set for TTS: %s",
                self._session_short,
                agent_name,
            )

    @property
    def is_playing(self) -> bool:
        """Check if TTS is currently playing."""
        return self._is_playing

    def get_agent_voice(self, agent_name: str | None = None) -> tuple[str, str | None, str | None]:
        """
        Get voice configuration from the specified or active agent.

        Priority:
        1. Explicitly provided agent_name parameter
        2. Currently active agent (set via set_active_agent)
        3. Session agent (Agent Builder override)
        4. Start agent from unified agents (loaded from YAML)

        Args:
            agent_name: Optional agent name to look up voice for.
                        If not provided, uses the active agent.

        Returns:
            Tuple of (voice_name, voice_style, voice_rate).
            voice_name will always have a value (fallback if needed).
        """
        # Import here to avoid circular imports
        from apps.artagent.backend.src.orchestration.session_agents import get_session_agent

        # Determine which agent to get voice for
        target_agent = agent_name or self._active_agent

        # If we have a target agent, look it up in unified_agents
        if target_agent:
            unified_agents = getattr(self._app_state, "unified_agents", {})
            agent = unified_agents.get(target_agent)
            if agent and hasattr(agent, "voice") and agent.voice and agent.voice.name:
                logger.debug(
                    "[%s] Voice from agent '%s': %s",
                    self._session_short,
                    target_agent,
                    agent.voice.name,
                )
                return (agent.voice.name, agent.voice.style, agent.voice.rate)

        # Try session agent (Agent Builder override)
        session_agent = get_session_agent(self._session_id)
        if session_agent and hasattr(session_agent, "voice") and session_agent.voice:
            voice = session_agent.voice
            if voice.name:
                logger.debug(
                    "[%s] Voice from session agent '%s': %s",
                    self._session_short,
                    session_agent.name,
                    voice.name,
                )
                return (voice.name, voice.style, voice.rate)

        # Fall back to start agent from unified agents
        unified_agents = getattr(self._app_state, "unified_agents", {})
        start_agent_name = getattr(self._app_state, "start_agent", "Concierge")
        start_agent = unified_agents.get(start_agent_name)

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

        async with self._tts_lock:
            if self._cancel_event.is_set():
                self._cancel_event.clear()
                return False

            self._is_playing = True
            synth = None

            try:
                # Acquire TTS synthesizer from pool
                synth, tier = await self._app_state.tts_pool.acquire_for_session(self._session_id)

                # Validate synthesizer has valid config
                if not synth or not getattr(synth, "is_ready", False):
                    logger.error(
                        "[%s] TTS synthesizer not initialized (missing speech config) - check Azure credentials",
                        self._session_short,
                    )
                    return False

                # Synthesize audio
                pcm_bytes = await self._synthesize(
                    synth, text, voice_name, style, rate, SAMPLE_RATE_BROWSER
                )

                if not pcm_bytes:
                    logger.warning("[%s] TTS returned empty audio", self._session_short)
                    return False

                # Stream to browser
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
            return False

        run_id = uuid.uuid4().hex[:8]

        # Resolve voice from agent if not provided
        if not voice_name:
            voice_name, voice_style, voice_rate = self.get_agent_voice()

        style = voice_style or "conversational"
        rate = voice_rate or "medium"

        logger.debug(
            "[%s] ACS TTS: voice=%s style=%s rate=%s (run=%s)",
            self._session_short,
            voice_name,
            style,
            rate,
            run_id,
        )

        async with self._tts_lock:
            if self._cancel_event.is_set():
                self._cancel_event.clear()
                return False

            self._is_playing = True
            synth = None

            try:
                # Acquire TTS synthesizer from pool
                synth, tier = await self._app_state.tts_pool.acquire_for_session(self._session_id)

                # Validate synthesizer has valid config
                if not synth or not getattr(synth, "is_ready", False):
                    logger.error(
                        "[%s] TTS synthesizer not initialized (missing speech config) - check Azure credentials",
                        self._session_short,
                    )
                    return False

                # Synthesize audio
                pcm_bytes = await self._synthesize(
                    synth, text, voice_name, style, rate, SAMPLE_RATE_ACS
                )

                if not pcm_bytes:
                    logger.warning("[%s] ACS TTS returned empty audio", self._session_short)
                    return False

                # Stream to ACS
                return await self._stream_to_acs(pcm_bytes, blocking, on_first_audio, run_id)

            except asyncio.CancelledError:
                logger.debug("[%s] ACS TTS cancelled", self._session_short)
                return False
            except Exception as e:
                logger.error("[%s] ACS TTS failed: %s", self._session_short, e)
                return False
            finally:
                self._is_playing = False

    async def _synthesize(
        self,
        synth: Any,
        text: str,
        voice: str,
        style: str,
        rate: str,
        sample_rate: int,
    ) -> bytes | None:
        """Synthesize text to PCM audio bytes with tracing and metrics."""
        text_len = len(text)
        transport = "browser" if sample_rate == SAMPLE_RATE_BROWSER else "acs"
        
        with tracer.start_as_current_span(
            "tts.synthesize",
            kind=SpanKind.CLIENT,
            attributes={
                "tts.voice": voice,
                "tts.style": style,
                "tts.rate": rate,
                "tts.sample_rate": sample_rate,
                "tts.text_length": text_len,
                "tts.transport": transport,
                "session.id": self._session_id,
            },
        ) as span:
            logger.info(
                "[%s] Synthesizing: text_len=%d voice=%s rate=%s sample_rate=%d",
                self._session_short,
                text_len,
                voice,
                rate,
                sample_rate,
            )

            start_time = time.perf_counter()
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

            try:
                if executor:
                    result = await loop.run_in_executor(executor, synth_func)
                else:
                    result = await loop.run_in_executor(None, synth_func)

                elapsed_ms = (time.perf_counter() - start_time) * 1000

                if result:
                    audio_bytes = len(result)
                    span.set_attribute("tts.audio_bytes", audio_bytes)
                    span.set_status(Status(StatusCode.OK))
                    logger.info(
                        "[%s] Synthesis complete: %d bytes in %.2fms",
                        self._session_short,
                        audio_bytes,
                        elapsed_ms,
                    )
                    
                    # Record metrics
                    record_tts_synthesis(
                        elapsed_ms,
                        session_id=self._session_id,
                        voice_name=voice,
                        text_length=text_len,
                        audio_bytes=audio_bytes,
                        transport=transport,
                    )
                else:
                    span.set_status(Status(StatusCode.ERROR, "Empty audio result"))
                    logger.warning("[%s] Synthesis returned None/empty", self._session_short)

                return result
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error("[%s] Synthesis failed: %s", self._session_short, e)
                raise

    async def _stream_to_browser(
        self,
        pcm_bytes: bytes,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Stream PCM audio to browser WebSocket with tracing."""
        chunk_size = 4800  # 100ms at 48kHz mono 16-bit
        first_sent = False
        chunks_sent = 0
        total_frames = (len(pcm_bytes) + chunk_size - 1) // chunk_size
        audio_bytes = len(pcm_bytes)
        cancelled = False

        with tracer.start_as_current_span(
            "tts.stream.browser",
            kind=SpanKind.CLIENT,
            attributes={
                "tts.transport": "browser",
                "tts.audio_bytes": audio_bytes,
                "tts.total_frames": total_frames,
                "tts.sample_rate": SAMPLE_RATE_BROWSER,
                "session.id": self._session_id,
            },
        ) as span:
            start_time = time.perf_counter()
            
            logger.info(
                "[%s] Streaming %d bytes to browser, %d frames (run=%s)",
                self._session_short,
                audio_bytes,
                total_frames,
                run_id,
            )

            try:
                for i in range(0, audio_bytes, chunk_size):
                    if self._cancel_event.is_set():
                        self._cancel_event.clear()
                        cancelled = True
                        logger.debug("[%s] Browser stream cancelled", self._session_short)
                        span.set_attribute("tts.cancelled", True)
                        span.set_attribute("tts.chunks_sent", chunks_sent)
                        break

                    chunk = pcm_bytes[i : i + chunk_size]
                    b64_chunk = base64.b64encode(chunk).decode("utf-8")
                    frame_index = chunks_sent
                    is_final = (i + chunk_size) >= audio_bytes

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
                    chunks_sent += 1

                    if not first_sent:
                        first_sent = True
                        first_audio_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("tts.first_audio_ms", first_audio_ms)
                        if on_first_audio:
                            try:
                                on_first_audio()
                            except Exception:
                                pass

                    await asyncio.sleep(0)

                elapsed_ms = (time.perf_counter() - start_time) * 1000
                
                if not cancelled:
                    span.set_attribute("tts.chunks_sent", chunks_sent)
                    span.set_status(Status(StatusCode.OK))
                    logger.info(
                        "[%s] Browser TTS complete: %d bytes, %d chunks in %.2fms (run=%s)",
                        self._session_short,
                        audio_bytes,
                        chunks_sent,
                        elapsed_ms,
                        run_id,
                    )
                
                # Record streaming metrics
                record_tts_streaming(
                    elapsed_ms,
                    session_id=self._session_id,
                    chunks_sent=chunks_sent,
                    audio_bytes=audio_bytes,
                    transport="browser",
                    cancelled=cancelled,
                )
                
                return not cancelled
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error("[%s] Browser streaming failed: %s", self._session_short, e)
                return False

    async def _stream_to_acs(
        self,
        pcm_bytes: bytes,
        blocking: bool,
        on_first_audio: Callable[[], None] | None,
        run_id: str,
    ) -> bool:
        """Stream PCM audio to ACS WebSocket with tracing."""
        chunk_size = 640  # 40ms at 16kHz mono 16-bit
        first_sent = False
        chunks_sent = 0
        audio_bytes = len(pcm_bytes)
        total_frames = (audio_bytes + chunk_size - 1) // chunk_size
        cancelled = False

        with tracer.start_as_current_span(
            "tts.stream.acs",
            kind=SpanKind.CLIENT,
            attributes={
                "tts.transport": "acs",
                "tts.audio_bytes": audio_bytes,
                "tts.total_frames": total_frames,
                "tts.sample_rate": SAMPLE_RATE_ACS,
                "tts.blocking": blocking,
                "session.id": self._session_id,
            },
        ) as span:
            start_time = time.perf_counter()

            try:
                for i in range(0, audio_bytes, chunk_size):
                    if self._cancel_event.is_set():
                        self._cancel_event.clear()
                        cancelled = True
                        logger.debug("[%s] ACS stream cancelled", self._session_short)
                        span.set_attribute("tts.cancelled", True)
                        span.set_attribute("tts.chunks_sent", chunks_sent)
                        break

                    chunk = pcm_bytes[i : i + chunk_size]
                    b64_chunk = base64.b64encode(chunk).decode("utf-8")

                    await self._ws.send_json(
                        {
                            "kind": "AudioData",
                            "audioData": {
                                "data": b64_chunk,
                                "timestamp": None,
                                "participantRawID": None,
                                "silent": False,
                            },
                        }
                    )
                    chunks_sent += 1

                    if not first_sent:
                        first_sent = True
                        first_audio_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("tts.first_audio_ms", first_audio_ms)
                        if on_first_audio:
                            try:
                                on_first_audio()
                            except Exception:
                                pass

                    if blocking:
                        await asyncio.sleep(0.04)  # 40ms pacing
                    else:
                        await asyncio.sleep(0)

                elapsed_ms = (time.perf_counter() - start_time) * 1000

                if not cancelled:
                    span.set_attribute("tts.chunks_sent", chunks_sent)
                    span.set_status(Status(StatusCode.OK))
                    logger.debug(
                        "[%s] ACS TTS complete: %d bytes, %d chunks in %.2fms (run=%s)",
                        self._session_short,
                        audio_bytes,
                        chunks_sent,
                        elapsed_ms,
                        run_id,
                    )

                # Record streaming metrics
                record_tts_streaming(
                    elapsed_ms,
                    session_id=self._session_id,
                    chunks_sent=chunks_sent,
                    audio_bytes=audio_bytes,
                    transport="acs",
                    cancelled=cancelled,
                )

                return not cancelled

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error("[%s] ACS streaming failed: %s", self._session_short, e)
                return False

    def cancel(self) -> None:
        """Signal TTS cancellation (for barge-in)."""
        self._cancel_event.set()


__all__ = [
    "TTSPlayback",
    "SAMPLE_RATE_BROWSER",
    "SAMPLE_RATE_ACS",
]
