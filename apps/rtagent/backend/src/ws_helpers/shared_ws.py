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
import json
import uuid
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from config import (
    ACS_STREAMING_MODE,
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


def _get_connection_metadata(ws: WebSocket, key: str, default=None):
    """Helper to get metadata from connection manager safely."""
    try:
        conn_id = getattr(ws.state, "conn_id", None)
        if conn_id and hasattr(ws.app.state, "conn_manager"):
            connection = ws.app.state.conn_manager._conns.get(conn_id)
            if connection and connection.meta.handler:
                return connection.meta.handler.get(key, default)
    except Exception:
        pass
    return default


def _set_connection_metadata(ws: WebSocket, key: str, value):
    """Helper to set metadata in connection manager safely."""
    try:
        conn_id = getattr(ws.state, "conn_id", None)
        if conn_id and hasattr(ws.app.state, "conn_manager"):
            connection = ws.app.state.conn_manager._conns.get(conn_id)
            if connection and connection.meta.handler:
                connection.meta.handler[key] = value
    except Exception:
        pass


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
        _set_connection_metadata(ws, "is_synthesizing", True)
        _set_connection_metadata(ws, "audio_playing", True)
        # Reset any stale cancel request from prior barge-ins
        try:
            _set_connection_metadata(ws, "tts_cancel_requested", False)
        except Exception:
            pass

        # Use voice settings
        voice_to_use = voice_name or GREETING_VOICE_TTS
        style = voice_style or "conversational"
        eff_rate = rate or "medium"

        logger.debug(
            f"TTS synthesis: voice={voice_to_use}, style={style}, rate={eff_rate} (run={run_id})"
        )

        # Synthesize audio
        pcm_bytes = synth.synthesize_to_pcm(
            text=text,
            voice=voice_to_use,
            sample_rate=TTS_SAMPLE_RATE_UI,
            style=style,
            rate=eff_rate,
        )

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
                if _get_connection_metadata(ws, "tts_cancel_requested", False):
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
    run_id = str(uuid.uuid4())[:8]
    voice_to_use = voice_name or GREETING_VOICE_TTS
    style = voice_style or "conversational"
    eff_rate = rate or "medium"
    frames: list[str] = []
    synth = None
    temp_synth = False

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
                return None

        try:
            logger.info(
                "ACS MEDIA: Starting TTS synthesis (run=%s, voice=%s, text_len=%s)",
                run_id,
                voice_to_use,
                len(text),
            )
            synth_future = asyncio.to_thread(
                synth.synthesize_to_pcm,
                text,
                voice_to_use,
                TTS_SAMPLE_RATE_ACS,
                style,
                eff_rate,
            )
            pcm_bytes = await asyncio.wait_for(synth_future, timeout=6.0)

            # Split into frames for ACS
            frames = SpeechSynthesizer.split_pcm_to_base64_frames(
                pcm_bytes, sample_rate=TTS_SAMPLE_RATE_ACS
            )

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
                            "AudioData": {"data": frame},
                            "StopAudio": None,
                        }
                    )
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
                    break

            logger.info(
                "ACS MEDIA: Completed TTS synthesis (run=%s, frames=%s)",
                run_id,
                len(frames),
            )

            if frames:
                if not _ws_is_connected(ws):
                    logger.debug(
                        "ACS MEDIA: WebSocket closing; skipping StopAudio send (run=%s)",
                        run_id,
                    )
                else:
                    try:
                        await ws.send_json(
                            {"kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                        )
                        logger.debug(
                            "ACS MEDIA: Sent StopAudio after playback (run=%s)", run_id
                        )
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

        except asyncio.TimeoutError:
            logger.error(
                "ACS MEDIA: TTS synthesis timed out (run=%s, voice=%s, text_preview=%s)",
                run_id,
                voice_to_use,
                (text[:40] + "...") if len(text) > 40 else text,
            )
            frames = []
        except Exception as e:
            frames = []
            logger.error(
                "Failed to produce ACS audio (run=%s): %s | text_preview=%s",
                run_id,
                e,
                (text[:40] + "...") if len(text) > 40 else text,
            )
        finally:
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

        return task

    else:
        logger.error(f"Unknown stream mode: {stream_mode}")
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
        if is_acs:
            # For ACS, just log - the call flow handles final messages
            logger.debug(f"ACS final message: {role}: {content[:50]}...")
        else:
            # For browser, send final message
            await ws.send_json(
                {
                    "type": "assistant_final",
                    "content": content,
                    "speaker": role,
                }
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
]
