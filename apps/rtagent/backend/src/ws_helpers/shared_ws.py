"""
shared_ws.py
============
WebSocket helpers for both realtime and ACS routers:

    • send_tts_audio        – browser TTS
    • send_response_to_acs  – phone-call TTS  
    • push_final            – "close bubble" helper
    • broadcast_message     – relay to /relay dashboards
"""

from __future__ import annotations

import asyncio
from functools import partial
import json
import time
import uuid
from contextlib import suppress
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from config import (
    ACS_STREAMING_MODE,
    DEFAULT_VOICE_RATE,
    DEFAULT_VOICE_STYLE,
    GREETING_VOICE_TTS,
    TTS_SAMPLE_RATE_ACS,
    TTS_SAMPLE_RATE_UI,
)
from src.tools.latency_tool import LatencyTool
from apps.rtagent.backend.src.services.acs.acs_helpers import play_response_with_queue
from apps.rtagent.backend.src.ws_helpers.envelopes import make_status_envelope
from apps.rtagent.backend.src.services.speech_services import SpeechSynthesizer
from src.enums.stream_modes import StreamMode
from utils.ml_logging import get_logger

logger = get_logger("shared_ws")

def _mirror_ws_state(ws: WebSocket, key: str, value) -> None:
    """Store a copy of connection metadata on websocket.state for barge-in fallbacks."""
    try:
        setattr(ws.state, key, value)
    except Exception:
        # Defensive only; failure to mirror should never break the flow.
        pass


def _get_connection_metadata(ws: WebSocket, key: str, default=None):
    """Helper to get metadata using session context with websocket.state fallback."""
    sentinel = object()
    session_context = getattr(ws.state, "session_context", None)
    if session_context:
        value = session_context.get_metadata_nowait(key, sentinel)
        if value is not sentinel:
            _mirror_ws_state(ws, key, value)
            return value

    value = getattr(ws.state, key, sentinel)
    if value is not sentinel:
        return value

    return default


def get_connection_metadata(ws: WebSocket, key: str, default=None):
    """Public accessor for connection metadata with fallback support."""
    return _get_connection_metadata(ws, key, default)


def _set_connection_metadata(ws: WebSocket, key: str, value) -> bool:
    """Helper to set metadata using session context, mirroring websocket.state."""
    updated = False

    session_context = getattr(ws.state, "session_context", None)
    if session_context:
        session_context.set_metadata_nowait(key, value)
        updated = True
    else:
        logger.debug(
            "No session_context available when setting metadata '%s'; websocket.state fallback only.",
            key,
        )

    _mirror_ws_state(ws, key, value)
    return updated


def _lt_stop(latency_tool: Optional[LatencyTool], stage: str, ws: WebSocket, meta=None):
    """Stop latency tracking with error handling and duplicate protection."""
    if latency_tool:
        try:
            #  Check if timer is actually running before stopping
            if (
                hasattr(latency_tool, "_active_timers")
                and stage in latency_tool._active_timers
            ):
                latency_tool.stop(stage, ws.app.state.redis, meta=meta)
            else:
                # Timer not running - this is the source of the warning messages
                logger.debug(
                    f"[PERF] Timer '{stage}' not running, skipping stop (run={meta.get('run_id', 'unknown') if meta else 'unknown'})"
                )
        except Exception as e:
            logger.error(f"Latency stop error for stage '{stage}': {e}")


def _ws_is_connected(ws: WebSocket) -> bool:
    """Return True if both client and application states are active."""
    return (
        ws.client_state == WebSocketState.CONNECTED
        and ws.application_state == WebSocketState.CONNECTED
    )


async def send_session_envelope(
    ws: WebSocket,
    envelope: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    conn_id: Optional[str] = None,
    event_label: str = "unspecified",
    broadcast_only: bool = False,
) -> bool:
    """Deliver payload via connection manager with broadcast fallback.

    Args:
        ws: Active websocket instance managing the session.
        envelope: JSON-serialisable payload to deliver to the frontend.
        session_id: Optional override for session correlation.
        conn_id: Optional override for connection id.
        event_label: Context string for logging when fallbacks trigger.

    Returns:
        bool: True when direct connection delivery succeeds, False otherwise.

    This helper protects against stale connection identifiers by attempting
    a session-scoped broadcast when the targeted connection is unavailable.
    As a final safeguard it falls back to sending directly on the websocket
    if the connection manager is inaccessible.
    """

    manager = getattr(ws.app.state, "conn_manager", None)
    resolved_conn_id = conn_id or getattr(ws.state, "conn_id", None)
    resolved_session_id = session_id or getattr(ws.state, "session_id", None)

    if manager and resolved_conn_id and not broadcast_only:
        try:
            sent = await manager.send_to_connection(resolved_conn_id, envelope)
            if sent:
                return True
            logger.debug(
                "Direct send skipped; connection missing",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Direct send failed; switching to broadcast",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                    "error": str(exc),
                },
            )

    if manager and resolved_session_id:
        try:
            await manager.broadcast_session(resolved_session_id, envelope)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Session broadcast fallback failed",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                    "error": str(exc),
                },
            )

    if _ws_is_connected(ws):
        try:
            await ws.send_json(envelope)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Final websocket fallback failed",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                    "error": str(exc),
                },
            )
        return False

    logger.debug(
        "No delivery path available for envelope",
        extra={
            "session_id": resolved_session_id,
            "conn_id": resolved_conn_id,
            "event": event_label,
        },
    )
    return False


async def send_tts_audio(
    text: str,
    ws: WebSocket,
    latency_tool: Optional[LatencyTool] = None,
    voice_name: Optional[str] = None,
    voice_style: Optional[str] = None,
    rate: Optional[str] = None,
) -> None:
    """Send TTS audio to browser WebSocket client with optimized pool management."""
    run_id = str(uuid.uuid4())[:8]

    if latency_tool:
        try:
            #  Safe timer starts with duplicate detection
            if not hasattr(latency_tool, "_active_timers"):
                latency_tool._active_timers = set()

            if "tts" not in latency_tool._active_timers:
                latency_tool.start("tts")
                latency_tool._active_timers.add("tts")

            if "tts:synthesis" not in latency_tool._active_timers:
                latency_tool.start("tts:synthesis")
                latency_tool._active_timers.add("tts:synthesis")
        except Exception as e:
            logger.error(f"Latency start error (run={run_id}): {e}")

    # Use dedicated TTS client per session
    synth = None
    client_tier = None
    temp_synth = False
    session_id = getattr(ws.state, "session_id", None)
    cancel_event: Optional[asyncio.Event] = _get_connection_metadata(
        ws, "tts_cancel_event"
    )

    voice_to_use = voice_name or GREETING_VOICE_TTS
    style = voice_style or "conversational"
    eff_rate = rate or "medium"

    try:
        (
            synth,
            client_tier,
        ) = await ws.app.state.tts_pool.acquire_for_session(
            session_id
        )
        logger.debug(
            f"[PERF] Using dedicated TTS client for session {session_id} (tier={client_tier.value}, run={run_id})"
        )
    except Exception as e:
        logger.error(
            f"[PERF] Failed to get dedicated TTS client (run={run_id}): {e}"
        )

    # Fallback to legacy pool if dedicated system unavailable
    if not synth:
        synth = _get_connection_metadata(ws, "tts_client")

        if not synth:
            logger.warning(f"[PERF] Falling back to legacy TTS pool (run={run_id})")
            try:
                synth = await ws.app.state.tts_pool.acquire(timeout=2.0)
                temp_synth = True
            except Exception as e:
                logger.error(
                    f"[PERF] TTS pool exhausted! No synthesizer available (run={run_id}): {e}"
                )
                return  # Graceful degradation - don't crash the session

    try:
        if cancel_event and cancel_event.is_set():
            logger.info(
                "[%s] Skipping TTS send due to active cancel signal",
                session_id,
            )
            cancel_event.clear()
            return

        now = time.monotonic()

        if not _set_connection_metadata(ws, "is_synthesizing", True):
            logger.debug("[%s] Unable to flag is_synthesizing=True", session_id)
        if not _set_connection_metadata(ws, "audio_playing", True):
            logger.debug("[%s] Unable to flag audio_playing=True", session_id)
        # Reset any stale cancel request from prior barge-ins
        try:
            _set_connection_metadata(ws, "tts_cancel_requested", False)
        except Exception:
            pass

        _set_connection_metadata(ws, "last_tts_start_ts", now)

        # One-time voice warm-up to avoid first-response decoder stalls
        warm_signature = (voice_to_use, style, eff_rate)
        prepared_voices: set[tuple[str, str, str]] = getattr(
            synth, "_prepared_voices", None
        )
        if prepared_voices is None:
            prepared_voices = set()
            setattr(synth, "_prepared_voices", prepared_voices)

        if warm_signature not in prepared_voices:
            warm_partial = partial(
                synth.synthesize_to_pcm,
                text=" .",
                voice=voice_to_use,
                sample_rate=TTS_SAMPLE_RATE_UI,
                style=style,
                rate=eff_rate,
            )
            try:
                loop = asyncio.get_running_loop()
                executor = getattr(ws.app.state, "speech_executor", None)
                if executor:
                    await asyncio.wait_for(
                        loop.run_in_executor(executor, warm_partial), timeout=4.0
                    )
                else:
                    await asyncio.wait_for(
                        loop.run_in_executor(None, warm_partial), timeout=4.0
                    )
                prepared_voices.add(warm_signature)
                logger.debug(
                    "[%s] Warmed TTS voice=%s style=%s rate=%s (run=%s)",
                    session_id,
                    voice_to_use,
                    style,
                    eff_rate,
                    run_id,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[%s] TTS warm-up timed out for voice=%s style=%s (run=%s)",
                    session_id,
                    voice_to_use,
                    style,
                    run_id,
                )
            except Exception as warm_exc:
                logger.warning(
                    "[%s] TTS warm-up failed for voice=%s style=%s: %s (run=%s)",
                    session_id,
                    voice_to_use,
                    style,
                    warm_exc,
                    run_id,
                )

        logger.debug(
            f"TTS synthesis: voice={voice_to_use}, style={style}, rate={eff_rate} (run={run_id})"
        )

        async def _synthesize() -> bytes:
            loop = asyncio.get_running_loop()
            executor = getattr(ws.app.state, "speech_executor", None)
            synth_partial = partial(
                synth.synthesize_to_pcm,
                text=text,
                voice=voice_to_use,
                sample_rate=TTS_SAMPLE_RATE_UI,
                style=style,
                rate=eff_rate,
            )
            if executor:
                return await loop.run_in_executor(executor, synth_partial)
            return await loop.run_in_executor(None, synth_partial)

        synthesis_task = asyncio.create_task(_synthesize())
        cancel_wait: Optional[asyncio.Task[None]] = None

        try:
            if cancel_event:
                cancel_wait = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    {synthesis_task, cancel_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if cancel_wait in done and cancel_event.is_set():
                    synthesis_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await synthesis_task
                    logger.info(
                        "[%s] Cancelled TTS synthesis before completion (run=%s)",
                        session_id,
                        run_id,
                    )
                    _set_connection_metadata(ws, "last_tts_end_ts", time.monotonic())
                    return

            pcm_bytes = await synthesis_task
        except asyncio.CancelledError:
            logger.debug("[%s] TTS synthesis task cancelled (run=%s)", session_id, run_id)
            raise
        finally:
            if cancel_wait:
                cancel_wait.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_wait

        if cancel_event and cancel_event.is_set():
            logger.info(
                "[%s] TTS cancel signal detected post-synthesis; aborting send (run=%s)",
                session_id,
                run_id,
            )
            _set_connection_metadata(ws, "last_tts_end_ts", time.monotonic())
            return

        _lt_stop(
            latency_tool,
            "tts:synthesis",
            ws,
            meta={"run_id": run_id, "mode": "browser", "voice": voice_to_use},
        )

        # Split into frames
        frames = SpeechSynthesizer.split_pcm_to_base64_frames(
            pcm_bytes, sample_rate=TTS_SAMPLE_RATE_UI
        )
        logger.debug(f"TTS frames prepared: {len(frames)} (run={run_id})")

        if latency_tool:
            try:
                if "tts:send_frames" not in latency_tool._active_timers:
                    latency_tool.start("tts:send_frames")
                    latency_tool._active_timers.add("tts:send_frames")
            except Exception:
                pass

        for i, frame in enumerate(frames):
            # Barge-in: stop sending frames immediately if a cancel is requested
            try:
                cancel_triggered = _get_connection_metadata(
                    ws, "tts_cancel_requested", False
                )
                if cancel_event and cancel_event.is_set():
                    cancel_triggered = True
                if cancel_triggered:
                    logger.info(
                        f"🛑 UI TTS cancel detected; stopping frame send early (run={run_id})"
                    )
                    break
            except Exception:
                # If metadata isn't available, proceed safely
                pass
            if not _ws_is_connected(ws):
                logger.debug(
                    "WebSocket closing during browser frame send (run=%s)", run_id
                )
                break
            try:
                await ws.send_json(
                    {
                        "type": "audio_data",
                        "data": frame,
                        "frame_index": i,
                        "total_frames": len(frames),
                        "sample_rate": TTS_SAMPLE_RATE_UI,
                        "is_final": i == len(frames) - 1,
                    }
                )
            except (WebSocketDisconnect, RuntimeError) as e:
                message = str(e)
                if not _ws_is_connected(ws):
                    logger.debug(
                        "WebSocket closing during browser frame send (run=%s): %s",
                        run_id,
                        message,
                    )
                else:
                    logger.warning(
                        "Browser frame send failed unexpectedly (frame=%s, run=%s): %s",
                        i,
                        run_id,
                        message,
                    )
                break
            except Exception as e:
                logger.error(
                    f"Failed to send audio frame {i} (run={run_id}): {e}"
                )
                break

        #  Safe stop with timer cleanup
        if latency_tool and "tts:send_frames" in latency_tool._active_timers:
            latency_tool._active_timers.remove("tts:send_frames")
        _lt_stop(
            latency_tool,
            "tts:send_frames",
            ws,
            meta={"run_id": run_id, "mode": "browser", "frames": len(frames)},
        )

        logger.debug(f"TTS complete: {len(frames)} frames sent (run={run_id})")

    except Exception as e:
        logger.error(f"TTS synthesis failed (run={run_id}): {e}")
        # Clean up timer state on error
        if latency_tool and "tts:synthesis" in latency_tool._active_timers:
            latency_tool._active_timers.remove("tts:synthesis")
        _lt_stop(
            latency_tool,
            "tts:synthesis",
            ws,
            meta={"run_id": run_id, "mode": "browser", "error": str(e)},
        )
        try:
            await ws.send_json(
                {
                    "type": "tts_error",
                    "error": str(e),
                    "text": text[:100] + "..." if len(text) > 100 else text,
                }
            )
        except Exception:
            pass
    finally:
        # Clean up timer state
        if latency_tool:
            if "tts" in latency_tool._active_timers:
                latency_tool._active_timers.remove("tts")
        _lt_stop(
            latency_tool,
            "tts",
            ws,
            meta={"run_id": run_id, "mode": "browser", "voice": voice_to_use},
        )

        _set_connection_metadata(ws, "is_synthesizing", False)
        _set_connection_metadata(ws, "audio_playing", False)
        try:
            _set_connection_metadata(ws, "tts_cancel_requested", False)
        except Exception:
            pass
        if cancel_event:
            cancel_event.clear()
        _set_connection_metadata(ws, "last_tts_end_ts", time.monotonic())

        # Enhanced pool management with dedicated clients
        if session_id:
            # Dedicated clients are managed by the pool manager, no manual release needed
            logger.debug(
                f"[PERF] Dedicated TTS client usage complete (session={session_id}, run={run_id})"
            )
        elif temp_synth and synth:
            try:
                await ws.app.state.tts_pool.release(synth)
                logger.debug(
                    f"[PERF] Released temporary TTS client back to pool (run={run_id})"
                )
            except Exception as e:
                logger.error(
                    f"Error releasing temporary TTS synthesizer (run={run_id}): {e}"
                )


async def send_response_to_acs(
    ws: WebSocket,
    text: str,
    *,
    blocking: bool = False,
    latency_tool: Optional[LatencyTool] = None,
    stream_mode: StreamMode = ACS_STREAMING_MODE,
    voice_name: Optional[str] = None,
    voice_style: Optional[str] = None,
    rate: Optional[str] = None,
) -> Optional[asyncio.Task]:
    """Send TTS response to ACS phone call."""

    def _record_status(status: str) -> None:
        try:
            _set_connection_metadata(ws, "acs_last_playback_status", status)
        except Exception as exc:
            # Log and continue: failure to set metadata is non-fatal, but should be traceable.
            logger.warning(
                "Failed to set ACS playback status metadata (status=%s, run_id=%s): %s",
                status,
                getattr(ws, "callConnectionId", None),
                exc,
            )
    _record_status("pending")
    playback_status = "pending"
    run_id = str(uuid.uuid4())[:8]
    voice_to_use = voice_name or GREETING_VOICE_TTS
    style_candidate = (voice_style or DEFAULT_VOICE_STYLE or "chat").strip()
    style_key = style_candidate.lower()
    if not style_candidate or style_key in {"neutral", "default", "none"}:
        style = "chat"
    elif style_key == "conversational":
        style = "chat"
    else:
        style = style_candidate

    rate_candidate = (rate or DEFAULT_VOICE_RATE or "+3%").strip()
    if not rate_candidate:
        eff_rate = "+3%"
    elif rate_candidate.lower() == "medium":
        eff_rate = "+3%"
    else:
        eff_rate = rate_candidate
    logger.debug(
        "ACS MEDIA: Using voice params (run=%s): voice=%s, style=%s, rate=%s",
        run_id,
        voice_to_use,
        style,
        eff_rate,
    )
    frames: list[str] = []
    synth = None
    temp_synth = False
    main_event_loop = None
    playback_task: Optional[asyncio.Task] = None

    acs_handler = getattr(ws, "_acs_media_handler", None)
    if acs_handler:
        main_event_loop = getattr(acs_handler, "main_event_loop", None)

    if latency_tool:
        try:
            latency_tool.start("tts")
        except Exception as e:
            logger.debug(f"Latency start error (run={run_id}): {e}")

    if stream_mode == StreamMode.MEDIA:
        synth = _get_connection_metadata(ws, "tts_client")
        if not synth:
            try:
                synth = await ws.app.state.tts_pool.acquire()
                temp_synth = True
                logger.warning("ACS MEDIA: Temporarily acquired TTS synthesizer from pool")
            except Exception as e:
                logger.error(f"ACS MEDIA: Unable to acquire TTS synthesizer (run={run_id}): {e}")
                _lt_stop(latency_tool, "tts", ws, meta={"run_id": run_id, "mode": "acs", "error": "acquire_failed"})
                playback_status = "acquire_failed"
                _record_status(playback_status)
                return None

        try:
            logger.info(
                "ACS MEDIA: Starting TTS synthesis (run=%s, voice=%s, text_len=%s)",
                run_id,
                voice_to_use,
                len(text),
            )
            playback_status = "started"
            playback_task = asyncio.current_task()
            if main_event_loop and playback_task:
                main_event_loop.current_playback_task = playback_task
            try:
                pcm_bytes = await asyncio.to_thread(
                    synth.synthesize_to_pcm,
                    text,
                    voice_to_use,
                    TTS_SAMPLE_RATE_ACS,
                    style,
                    eff_rate,
                )
            except RuntimeError as synth_err:
                logger.warning(
                    "ACS MEDIA: Primary TTS failed (run=%s). Retrying without style/rate. error=%s",
                    run_id,
                    synth_err,
                )
                pcm_bytes = await asyncio.to_thread(
                    synth.synthesize_to_pcm,
                    text,
                    voice_to_use,
                    TTS_SAMPLE_RATE_ACS,
                    "",
                    "",
                )

            # Split into frames for ACS
            frames = SpeechSynthesizer.split_pcm_to_base64_frames(
                pcm_bytes, sample_rate=TTS_SAMPLE_RATE_ACS
            )

            if not frames and pcm_bytes:
                frame_size_bytes = int(0.02 * TTS_SAMPLE_RATE_ACS * 2)
                logger.warning(
                    "ACS MEDIA: Frame split returned no frames; padding and retrying (run=%s)",
                    run_id,
                )
                padded_pcm = pcm_bytes + b"\x00" * frame_size_bytes
                frames = SpeechSynthesizer.split_pcm_to_base64_frames(
                    padded_pcm, sample_rate=TTS_SAMPLE_RATE_ACS
                )

            frame_count = len(frames)
            estimated_duration = frame_count * 0.02
            total_bytes = len(pcm_bytes)
            logger.debug(
                "ACS MEDIA: Prepared frames (run=%s, frames=%s, bytes=%s, est_duration=%.2fs)",
                run_id,
                frame_count,
                total_bytes,
                estimated_duration,
            )

            sequence_id = 0
            for frame in frames:
                if not _ws_is_connected(ws):
                    logger.info(
                        "ACS MEDIA: WebSocket closing; stopping frame send (run=%s)",
                        run_id,
                    )
                    break
                lt = _get_connection_metadata(ws, "lt")
                greeting_ttfb_stopped = _get_connection_metadata(
                    ws, "_greeting_ttfb_stopped", False
                )

                if lt and not greeting_ttfb_stopped:
                    lt.stop("greeting_ttfb", ws.app.state.redis)
                    _set_connection_metadata(ws, "_greeting_ttfb_stopped", True)

                try:
                    await ws.send_json(
                        {
                            "kind": "AudioData",
                            "AudioData": {"data": frame, "sequenceId": sequence_id},
                            "StopAudio": None,
                        }
                    )
                    sequence_id += 1
                    await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    logger.info(
                        "ACS MEDIA: Frame loop cancelled (run=%s, seq=%s)",
                        run_id,
                        sequence_id,
                    )
                    playback_status = "cancelled"
                    _record_status(playback_status)
                    raise
                except Exception as e:
                    if not _ws_is_connected(ws):
                        logger.info(
                            "ACS MEDIA: WebSocket closed during frame send (run=%s)",
                            run_id,
                        )
                    else:
                        logger.error(
                            "Failed to send ACS audio frame (run=%s): %s | text_preview=%s",
                            run_id,
                            e,
                            (text[:40] + "...") if len(text) > 40 else text,
                        )
                    playback_status = "failed"
                    _record_status(playback_status)
                    break

            logger.info(
                "ACS MEDIA: Completed TTS synthesis (run=%s, frames=%s, bytes=%s, duration=%.2fs)",
                run_id,
                frame_count,
                total_bytes,
                estimated_duration,
            )

            if frames:
                if not _ws_is_connected(ws):
                    logger.debug(
                        "ACS MEDIA: WebSocket closing; skipping StopAudio send (run=%s)",
                        run_id,
                    )
                    playback_status = "interrupted"
                    _record_status(playback_status)
                else:
                    try:
                        await ws.send_json(
                            {"kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                        )
                        logger.debug(
                            "ACS MEDIA: Sent StopAudio after playback (run=%s)", run_id
                        )
                        playback_status = "completed"
                        _record_status(playback_status)
                    except Exception as e:
                        if not _ws_is_connected(ws):
                            logger.debug(
                                "ACS MEDIA: WebSocket closed before StopAudio send (run=%s)",
                                run_id,
                            )
                        else:
                            logger.warning(
                                "ACS MEDIA: Failed to send StopAudio (run=%s): %s",
                                run_id,
                                e,
                            )
                        playback_status = "interrupted"
                        _record_status(playback_status)
            else:
                playback_status = "no_audio"
                _record_status(playback_status)

        except asyncio.TimeoutError:
            logger.error(
                "ACS MEDIA: TTS synthesis timed out (run=%s, voice=%s, text_preview=%s)",
                run_id,
                voice_to_use,
                (text[:40] + "...") if len(text) > 40 else text,
            )
            frames = []
            playback_status = "timeout"
            _record_status(playback_status)
        except asyncio.CancelledError:
            logger.info(
                "ACS MEDIA: Playback cancelled by barge-in (run=%s)",
                run_id,
            )
            playback_status = "cancelled"
            _record_status(playback_status)
            raise
        except Exception as e:
            frames = []
            logger.error(
                "Failed to produce ACS audio (run=%s): %s | text_preview=%s",
                run_id,
                e,
                (text[:40] + "...") if len(text) > 40 else text,
            )
            playback_status = "failed"
            _record_status(playback_status)
        finally:
            if (
                main_event_loop
                and playback_task
                and main_event_loop.current_playback_task is playback_task
            ):
                main_event_loop.current_playback_task = None
            _lt_stop(
                latency_tool,
                "tts:send_frames",
                ws,
                meta={"run_id": run_id, "mode": "acs", "frames": len(frames)},
            )
            _lt_stop(
                latency_tool,
                "tts",
                ws,
                meta={"run_id": run_id, "mode": "acs", "voice": voice_to_use},
            )

            if temp_synth and synth:
                try:
                    await ws.app.state.tts_pool.release(synth)
                except Exception as e:
                    logger.error(f"Error releasing temporary ACS TTS synthesizer (run={run_id}): {e}")

        return None

    elif stream_mode == StreamMode.TRANSCRIPTION:
        # TRANSCRIPTION mode - queue with ACS caller
        acs_caller = ws.app.state.acs_caller
        if not acs_caller:
            _lt_stop(
                latency_tool,
                "tts",
                ws,
                meta={"run_id": run_id, "mode": "acs", "error": "no_acs_caller"},
            )
            logger.error("ACS caller not available for TRANSCRIPTION mode")
            playback_status = "no_caller"
            _record_status(playback_status)
            return None

        call_conn = _get_connection_metadata(ws, "call_conn")
        if not call_conn:
            _lt_stop(
                latency_tool,
                "tts",
                ws,
                meta={"run_id": run_id, "mode": "acs", "error": "no_call_connection"},
            )
            logger.error("Call connection not available")
            playback_status = "no_call_connection"
            _record_status(playback_status)
            return None

        # Queue with ACS
        task = asyncio.create_task(
            play_response_with_queue(acs_caller, call_conn, text, voice_name=voice_to_use)
        )

        _lt_stop(
            latency_tool,
            "tts",
            ws,
            meta={"run_id": run_id, "mode": "acs", "queued": True},
        )
        playback_status = "queued"
        _record_status(playback_status)

        return task

    else:
        logger.error(f"Unknown stream mode: {stream_mode}")
        playback_status = "invalid_mode"
        _record_status(playback_status)
        return None


async def push_final(
    ws: WebSocket,
    role: str,
    content: str,
    *,
    is_acs: bool = False,
) -> None:
    """Push final message (close bubble helper)."""
    try:
        envelope = {
            "type": "assistant_final",
            "content": content,
            "speaker": role,
            "sender": role,
            "message": content,
        }
        conn_id = None if is_acs else getattr(ws.state, "conn_id", None)
        await send_session_envelope(
            ws,
            envelope,
            session_id=getattr(ws.state, "session_id", None),
            conn_id=conn_id,
            event_label="assistant_final",
            broadcast_only=is_acs,
        )
        if is_acs:
            logger.debug(
                "ACS final message broadcast only: %s: %s...",
                role,
                content[:50],
            )
    except Exception as e:
        logger.error(f"Error pushing final message: {e}")


async def broadcast_message(
    connected_clients,
    message: str,
    sender: str = "system",
    app_state=None,
    session_id: str = None,
):
    """
    Session-safe broadcast message using ConnectionManager.

    This function requires session_id for proper session isolation.
    Messages will only be sent to connections within the specified session.

    Args:
        connected_clients: Legacy parameter (ignored for safety)
        message: Message content to broadcast
        sender: Message sender identifier
        app_state: Application state containing conn_manager
        session_id: REQUIRED - Session ID for proper isolation
    """
    if not app_state or not hasattr(app_state, "conn_manager"):
        raise ValueError("broadcast_message requires app_state with conn_manager")

    if not session_id:
        logger.error(
            "CRITICAL: broadcast_message called without session_id - this breaks session isolation!"
        )
        raise ValueError("session_id is required for session-safe broadcasting")

    envelope = make_status_envelope(message, sender=sender, session_id=session_id)

    sent_count = await app_state.conn_manager.broadcast_session(session_id, envelope)

    logger.info(
        f"Session-safe broadcast: {sender}: {message[:50]}... "
        f"(sent to {sent_count} clients in session {session_id})",
        extra={"session_id": session_id, "sender": sender, "sent_count": sent_count},
    )


# Re-export for convenience
__all__ = [
    "send_tts_audio",
    "send_response_to_acs",
    "push_final",
    "broadcast_message",
    "send_session_envelope",
    "get_connection_metadata",
]
