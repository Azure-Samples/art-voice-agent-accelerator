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
import uuid
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.voice.shared.context import VoiceSessionContext
    from src.tools.latency_tool import LatencyTool

# Audio sample rates
SAMPLE_RATE_BROWSER = 48000  # Browser WebAudio prefers 48kHz
SAMPLE_RATE_ACS = 16000  # ACS telephony uses 16kHz

logger = get_logger("voice.tts.playback")


class TTSPlayback:
    """
    Unified TTS playback for all voice transports.

    Single source of truth for TTS:
    - Accepts VoiceSessionContext (no global state lookups)
    - Voice resolved from context.current_agent or fallback
    - Routes to appropriate transport (Browser/ACS) automatically
    - Thread-safe cancellation via context.cancel_event
    """

    def __init__(
        self,
        context: VoiceSessionContext,
        app_state: Any,
        *,
        latency_tool: LatencyTool | None = None,
    ):
        """
        Initialize TTS playback.

        Args:
            context: VoiceSessionContext with session, websocket, and agent info
            app_state: Application state with TTS pool and executor
            latency_tool: Optional latency tracking
        """
        self._context = context
        self._app_state = app_state
        self._latency_tool = latency_tool
        self._tts_lock = asyncio.Lock()
        self._is_playing = False

    @property
    def context(self) -> VoiceSessionContext:
        """Get the voice session context."""
        return self._context

    @property
    def is_playing(self) -> bool:
        """Check if TTS is currently playing."""
        return self._is_playing

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

        # Fallback to start agent from unified agents
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

        if transport.value == "browser":
            return await self.play_to_browser(
                text,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
                on_first_audio=on_first_audio,
            )
        else:
            # ACS and VoiceLive both use ACS format
            return await self.play_to_acs(
                text,
                voice_name=voice_name,
                voice_style=voice_style,
                voice_rate=voice_rate,
                on_first_audio=on_first_audio,
            )

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

        if executor:
            result = await loop.run_in_executor(executor, synth_func)
        else:
            result = await loop.run_in_executor(None, synth_func)

        if result:
            logger.info("[%s] Synthesis complete: %d bytes", self._session_short, len(result))
        else:
            logger.warning("[%s] Synthesis returned None/empty", self._session_short)

        return result

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
                self._cancel_event.clear()
                logger.debug("[%s] Browser stream cancelled", self._session_short)
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
        chunk_size = 640  # 40ms at 16kHz mono 16-bit
        first_sent = False

        for i in range(0, len(pcm_bytes), chunk_size):
            if self._cancel_event.is_set():
                self._cancel_event.clear()
                logger.debug("[%s] ACS stream cancelled", self._session_short)
                return False

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

        logger.debug(
            "[%s] ACS TTS complete: %d bytes (run=%s)",
            self._session_short,
            len(pcm_bytes),
            run_id,
        )
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
