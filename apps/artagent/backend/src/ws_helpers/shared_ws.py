"""
shared_ws.py
============
WebSocket helpers for both realtime and ACS routers:

    • send_tts_audio        – browser TTS
    • send_response_to_acs  – phone-call TTS
    • push_final            – "close bubble" helper
    • broadcast_message     – relay to /relay dashboards

LEGACY STATUS:
--------------
This file contains legacy TTS code paths that are being phased out.
New code should use:
  - apps.artagent.backend.voice.tts.TTSPlayback for TTS
  - ConversationTurnSpan for telemetry tracking

These functions now use OpenTelemetry decorators for telemetry.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from typing import Any

from apps.artagent.backend.registries.agentstore.loader import build_agent_summaries
from apps.artagent.backend.src.services.acs.acs_helpers import play_response_with_queue
from apps.artagent.backend.src.services.speech_services import SpeechSynthesizer
from apps.artagent.backend.src.ws_helpers.envelopes import (
    make_envelope,
    make_event_envelope,
    make_status_envelope,
)
from config import (
    ACS_STREAMING_MODE,
    DEFAULT_VOICE_RATE,
    DEFAULT_VOICE_STYLE,
    GREETING_VOICE_TTS,
    TTS_SAMPLE_RATE_ACS,
    TTS_SAMPLE_RATE_UI,
)
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from src.enums.stream_modes import StreamMode
from utils.ml_logging import get_logger
from utils.telemetry_decorators import trace_speech, add_speech_tts_metrics

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


def _ws_is_connected(ws: WebSocket) -> bool:
    """Return True if both client and application states are active."""
    return (
        ws.client_state == WebSocketState.CONNECTED
        and ws.application_state == WebSocketState.CONNECTED
    )


async def send_user_transcript(
    ws: WebSocket,
    text: str,
    *,
    session_id: str | None = None,
    conn_id: str | None = None,
    broadcast_only: bool = False,
    turn_id: str | None = None,
    active_agent: str | None = None,
    active_agent_label: str | None = None,
) -> None:
    """Emit a user transcript using the standard session envelope.

    Aligns ACS transcripts with the realtime conversation flow so dashboards
    and the UI render user bubbles consistently.
    """
    payload_session_id = session_id or getattr(ws.state, "session_id", None)
    resolved_conn = conn_id or getattr(ws.state, "conn_id", None)

    payload_data = {
        "type": "user",
        "sender": "User",
        "message": text,
        "content": text,
        "streaming": False,
        "status": "completed",
        "turn_id": turn_id,
        "response_id": turn_id,
    }
    if active_agent:
        payload_data["active_agent"] = active_agent
        payload_data["active_agent_label"] = active_agent_label

    envelope_payload = make_envelope(
        etype="event",
        sender="User",
        payload=payload_data,
        topic="session",
        session_id=payload_session_id,
    )

    await send_session_envelope(
        ws,
        envelope_payload,
        session_id=payload_session_id,
        conn_id=resolved_conn,
        event_label="user_transcript",
        broadcast_only=broadcast_only,
    )


async def send_user_partial_transcript(
    ws: WebSocket,
    text: str,
    *,
    language: str | None = None,
    speaker_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Emit partial user speech updates for ACS parity with realtime."""
    payload_session_id = session_id or getattr(ws.state, "session_id", None)

    partial_payload = {
        "type": "streaming",
        "streaming_type": "stt_partial",
        "content": text,
        "language": language,
        "speaker_id": speaker_id,
        "session_id": payload_session_id,
        "is_final": False,
    }

    envelope = make_event_envelope(
        event_type="stt_partial",
        event_data=partial_payload,
        sender="STT",
        topic="session",
        session_id=payload_session_id,
    )

    await send_session_envelope(
        ws,
        envelope,
        session_id=payload_session_id,
        conn_id=None,
        event_label="user_transcript_partial",
        broadcast_only=True,
    )


async def send_agent_inventory(
    app_state,
    *,
    session_id: str,
    call_id: str | None = None,
) -> bool:
    """Send a lightweight agent/tool snapshot to dashboards for a session."""
    if not app_state or not hasattr(app_state, "conn_manager"):
        return False

    agents = getattr(app_state, "unified_agents", {}) or {}
    summaries = getattr(app_state, "agent_summaries", None) or build_agent_summaries(agents)
    start_agent = getattr(app_state, "start_agent", None)
    scenario = getattr(app_state, "scenario", None)
    scenario_name = getattr(scenario, "name", None) if scenario else None
    handoff_map = getattr(app_state, "handoff_map", {}) or {}

    payload = {
        "type": "agent_inventory",
        "event_type": "agent_inventory",
        "source": "unified",
        "scenario": scenario_name,
        "start_agent": start_agent,
        "agent_count": len(summaries),
        "agents": summaries,
        "handoff_map": handoff_map,
    }

    envelope = make_envelope(
        etype="event",
        sender="System",
        payload=payload,
        topic="dashboard",
        session_id=session_id,
        call_id=call_id,
    )

    try:
        await broadcast_session_envelope(
            app_state,
            envelope,
            session_id=session_id,
            event_label="agent_inventory",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Failed to broadcast agent inventory",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return False


async def send_session_envelope(
    ws: WebSocket,
    envelope: dict[str, Any],
    *,
    session_id: str | None = None,
    conn_id: str | None = None,
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

    if manager and resolved_session_id and broadcast_only:
        try:
            sent = await broadcast_session_envelope(
                ws.app.state,
                envelope,
                session_id=resolved_session_id,
                event_label=event_label,
            )
            if sent:
                return True
            logger.debug(
                "Session broadcast delivered no envelopes",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Session broadcast failed",
                extra={
                    "session_id": resolved_session_id,
                    "conn_id": resolved_conn_id,
                    "event": event_label,
                    "error": str(exc),
                },
            )

    if manager and resolved_conn_id and not broadcast_only:
        try:
            sent = await manager.send_to_connection(resolved_conn_id, envelope)
            if sent:
                try:
                    await manager.publish_session_envelope(
                        resolved_session_id, envelope, event_label=event_label
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Distributed publish failed after direct send",
                        extra={
                            "session_id": resolved_session_id,
                            "conn_id": resolved_conn_id,
                            "event": event_label,
                            "error": str(exc),
                        },
                    )
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
                    await broadcast_session_envelope(
                        ws.app.state,
                        envelope,
                        session_id=resolved_session_id,
                        event_label=event_label,
                    )
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


@trace_speech(operation="tts.browser_send")
async def send_tts_audio(
    text: str,
    ws: WebSocket,
    voice_name: str | None = None,
    voice_style: str | None = None,
    rate: str | None = None,
    on_first_audio: Callable[[], None] | None = None,
) -> None:
    """Send TTS audio to browser WebSocket client with optimized pool management."""
    run_id = str(uuid.uuid4())[:8]

    # Use dedicated TTS client per session
    synth = None
    client_tier = None
    temp_synth = False
    session_id = getattr(ws.state, "session_id", None)
    cancel_event: asyncio.Event | None = _get_connection_metadata(ws, "tts_cancel_event")

    voice_to_use = voice_name or GREETING_VOICE_TTS
    style = voice_style or "conversational"
    eff_rate = rate or "medium"

    try:
        (
            synth,
            client_tier,
        ) = await ws.app.state.tts_pool.acquire_for_session(session_id)
        logger.debug(
            f"[PERF] Using dedicated TTS client for session {session_id} (tier={client_tier.value}, run={run_id})"
        )
    except Exception as e:
        logger.error(f"[PERF] Failed to get dedicated TTS client (run={run_id}): {e}")

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
        prepared_voices: set[tuple[str, str, str]] = getattr(synth, "_prepared_voices", None)
        if prepared_voices is None:
            prepared_voices = set()
            synth._prepared_voices = prepared_voices

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
                    await asyncio.wait_for(loop.run_in_executor(None, warm_partial), timeout=4.0)
                prepared_voices.add(warm_signature)
                logger.debug(
                    "[%s] Warmed TTS voice=%s style=%s rate=%s (run=%s)",
                    session_id,
                    voice_to_use,
                    style,
                    eff_rate,
                    run_id,
                )
            except TimeoutError:
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
        cancel_wait: asyncio.Task[None] | None = None

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

        # Record TTS metrics
        add_speech_tts_metrics(
            voice=voice_to_use,
            audio_size_bytes=len(pcm_bytes),
            text_length=len(text),
            sample_rate=TTS_SAMPLE_RATE_UI,
        )

        # Signal first audio available
        if on_first_audio:
            try:
                on_first_audio()
            except Exception as e:
                logger.warning(f"on_first_audio callback failed: {e}")

        # Split into frames
        frames = SpeechSynthesizer.split_pcm_to_base64_frames(
            pcm_bytes, sample_rate=TTS_SAMPLE_RATE_UI
        )
        logger.debug(f"TTS frames prepared: {len(frames)} (run={run_id})")

        for i, frame in enumerate(frames):
            # Barge-in: stop sending frames immediately if a cancel is requested
            try:
                cancel_triggered = _get_connection_metadata(ws, "tts_cancel_requested", False)
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
                logger.debug("WebSocket closing during browser frame send (run=%s)", run_id)
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
                logger.error(f"Failed to send audio frame {i} (run={run_id}): {e}")
                break

        logger.debug(f"TTS complete: {len(frames)} frames sent (run={run_id})")

    except Exception as e:
        logger.error(f"TTS synthesis failed (run={run_id}): {e}")
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
                # Use release_for_session with None to clear state before discard
                await ws.app.state.tts_pool.release_for_session(None, synth)
                logger.debug(f"[PERF] Released temporary TTS client back to pool (run={run_id})")
            except Exception as e:
                logger.error(f"Error releasing temporary TTS synthesizer (run={run_id}): {e}")


@trace_speech(operation="tts.acs_send")
async def send_response_to_acs(
    ws: WebSocket,
    text: str,
    *,
    blocking: bool = False,
    stream_mode: StreamMode = ACS_STREAMING_MODE,
    voice_name: str | None = None,
    voice_style: str | None = None,
    rate: str | None = None,
    on_first_audio: Callable[[], None] | None = None,
) -> asyncio.Task | None:
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
    playback_task: asyncio.Task | None = None

    acs_handler = getattr(ws, "_acs_media_handler", None)
    if acs_handler:
        main_event_loop = getattr(acs_handler, "main_event_loop", None)

    if stream_mode == StreamMode.MEDIA:
        synth = _get_connection_metadata(ws, "tts_client")
        if not synth:
            try:
                synth = await ws.app.state.tts_pool.acquire()
                temp_synth = True
                logger.warning("ACS MEDIA: Temporarily acquired TTS synthesizer from pool")
            except Exception as e:
                logger.error(f"ACS MEDIA: Unable to acquire TTS synthesizer (run={run_id}): {e}")
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
        except Exception as e:
            logger.error(
                "Failed to produce ACS audio (run=%s): %s | text_preview=%s",
                run_id,
                e,
                (text[:40] + "...") if len(text) > 40 else text,
            )
            playback_status = "failed"
            _record_status(playback_status)
            if temp_synth and synth:
                try:
                    await ws.app.state.tts_pool.release(synth)
                except Exception as release_exc:
                    logger.error(
                        f"Error releasing temporary ACS TTS synthesizer (run={run_id}): {release_exc}"
                    )
            return None

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

        if not frames:
            playback_status = "no_audio"
            _record_status(playback_status)
            if temp_synth and synth:
                try:
                    await ws.app.state.tts_pool.release(synth)
                except Exception as release_exc:
                    logger.error(
                        f"Error releasing temporary ACS TTS synthesizer (run={run_id}): {release_exc}"
                    )
            return None
        # Record TTS metrics
        add_speech_tts_metrics(
            voice=voice_to_use,
            audio_size_bytes=len(pcm_bytes),
            text_length=len(text),
            sample_rate=TTS_SAMPLE_RATE_ACS,
        )

        # Signal first audio available (frames prepared)
        if on_first_audio:
            try:
                on_first_audio()
            except Exception as e:
                logger.warning(f"on_first_audio callback failed: {e}")

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
        pcm_bytes = None

        class _NullAsyncLock:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        playback_lock = getattr(main_event_loop, "playback_lock", None) if main_event_loop else None
        lock_cm = playback_lock if playback_lock is not None else _NullAsyncLock()

        async def _stream_frames() -> None:
            nonlocal frames, playback_status, synth, temp_synth
            async with lock_cm:
                playback_task_local = asyncio.current_task()
                if main_event_loop and playback_task_local:
                    main_event_loop.current_playback_task = playback_task_local
                try:
                    playback_status = "started"
                    _record_status(playback_status)
                    sequence_id = 0
                    for frame in frames:
                        # Check for barge-in cancellation request
                        if _get_connection_metadata(ws, "tts_cancel_requested", False):
                            logger.info(
                                "ACS MEDIA: Barge-in detected; stopping frame send (run=%s, seq=%s)",
                                run_id,
                                sequence_id,
                            )
                            playback_status = "barge_in"
                            _record_status(playback_status)
                            break

                        if not _ws_is_connected(ws):
                            logger.info(
                                "ACS MEDIA: WebSocket closing; stopping frame send (run=%s)",
                                run_id,
                            )
                            playback_status = "interrupted"
                            _record_status(playback_status)
                            break

                        try:
                            await ws.send_json(
                                {
                                    "kind": "AudioData",
                                    "AudioData": {"data": frame, "sequenceId": sequence_id},
                                    "StopAudio": None,
                                }
                            )
                            sequence_id += 1
                            # Reduced pacing: send frames faster than real-time.
                            # ACS buffers frames and plays at 20ms rate internally.
                            # 5ms gives ~4x speedup while maintaining order.
                            await asyncio.sleep(0.005)
                        except asyncio.CancelledError:
                            logger.info(
                                "ACS MEDIA: Frame loop cancelled (run=%s, seq=%s)",
                                run_id,
                                sequence_id,
                            )
                            playback_status = "cancelled"
                            _record_status(playback_status)
                            raise
                        except Exception as frame_exc:
                            if not _ws_is_connected(ws):
                                logger.info(
                                    "ACS MEDIA: WebSocket closed during frame send (run=%s)",
                                    run_id,
                                )
                            else:
                                logger.error(
                                    "Failed to send ACS audio frame (run=%s, seq=%s): %s",
                                    run_id,
                                    sequence_id,
                                    frame_exc,
                                )
                            playback_status = "failed"
                            _record_status(playback_status)
                            break
                    else:
                        # All frames sent successfully
                        # NOTE: Do NOT send StopAudio here - it clears the ACS buffer
                        # and would cut off audio from subsequent chunks in a streaming response.
                        # StopAudio should only be sent on barge-in or at the very end of a response.
                        playback_status = "completed"
                        _record_status(playback_status)
                finally:
                    if (
                        main_event_loop
                        and playback_task_local
                        and main_event_loop.current_playback_task is playback_task_local
                    ):
                        main_event_loop.current_playback_task = None
                    if temp_synth and synth:
                        try:
                            # Use release_for_session with None to clear state
                            await ws.app.state.tts_pool.release_for_session(None, synth)
                        except Exception as release_exc:
                            logger.error(
                                f"Error releasing temporary ACS TTS synthesizer (run={run_id}): {release_exc}"
                            )

        _record_status("queued")
        stream_task = asyncio.create_task(_stream_frames())

        if blocking:
            await stream_task
            return None
        return stream_task

    elif stream_mode == StreamMode.TRANSCRIPTION:
        # TRANSCRIPTION mode - queue with ACS caller
        acs_caller = ws.app.state.acs_caller
        if not acs_caller:
            logger.error("ACS caller not available for TRANSCRIPTION mode")
            playback_status = "no_caller"
            _record_status(playback_status)
            return None

        call_conn = _get_connection_metadata(ws, "call_conn")
        if not call_conn:
            logger.error("Call connection not available")
            playback_status = "no_call_connection"
            _record_status(playback_status)
            return None

        # Queue with ACS
        task = asyncio.create_task(
            play_response_with_queue(acs_caller, call_conn, text, voice_name=voice_to_use)
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
    Session-safe broadcast helper (deprecated).

    Constructs a status envelope and delegates to broadcast_session_envelope so
    downstream consumers always receive structured payloads.
    """
    if not app_state or not hasattr(app_state, "conn_manager"):
        raise ValueError("broadcast_message requires app_state with conn_manager")

    if not session_id:
        logger.error(
            "CRITICAL: broadcast_message called without session_id - this breaks session isolation!"
        )
        raise ValueError("session_id is required for session-safe broadcasting")

    envelope = make_status_envelope(message, sender=sender, session_id=session_id)

    sent_count = await broadcast_session_envelope(
        app_state,
        envelope,
        session_id=session_id,
        event_label="legacy_status",
    )

    logger.info(
        "Session-safe broadcast",
        extra={
            "session_id": session_id,
            "sender": sender,
            "sent_count": sent_count,
            "preview": message[:50],
        },
    )


async def broadcast_session_envelope(
    app_state,
    envelope: dict[str, Any],
    *,
    session_id: str | None = None,
    event_label: str = "unspecified",
) -> int:
    """
    Broadcast a fully constructed envelope to all connections in a session.

    Args:
        app_state: FastAPI application state containing the connection manager.
        envelope: Pre-built message envelope to send.
        session_id: Optional override for the target session.
        event_label: Log-friendly label describing the envelope.

    Returns:
        int: Number of connections the envelope was delivered to.
    """
    if not app_state or not hasattr(app_state, "conn_manager"):
        raise ValueError("broadcast_session_envelope requires app_state with conn_manager")

    target_session = session_id or envelope.get("session_id")
    if not target_session:
        raise ValueError("session_id must be provided for envelope broadcasts")

    sent_count = await app_state.conn_manager.broadcast_session(
        target_session,
        envelope,
    )

    try:
        await app_state.conn_manager.publish_session_envelope(
            target_session,
            envelope,
            event_label=event_label,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Distributed broadcast publish failed",
            extra={
                "session_id": target_session,
                "event": event_label,
                "error": str(exc),
            },
        )

    logger.debug(
        "Session envelope broadcast",
        extra={
            "session_id": target_session,
            "event": event_label,
            "sent_count": sent_count,
            "envelope_type": envelope.get("type"),
            "sender": envelope.get("sender"),
        },
    )
    return sent_count


# =============================================================================
# Unified ACS TTS Queue
# =============================================================================


def queue_acs_tts(
    ws: WebSocket,
    text: str,
    *,
    voice_name: str | None = None,
    voice_style: str | None = None,
    rate: str | None = None,
    stream_mode: StreamMode | None = None,
    is_greeting: bool = False,
) -> asyncio.Task:
    """
    Queue TTS playback for ACS with proper serialization.

    ALL ACS TTS should go through this function to ensure sequential playback.
    Uses the acs_playback_tail task chain to prevent overlapping audio.

    Args:
        ws: WebSocket connection
        text: Text to synthesize and play
        voice_name: Optional voice override
        voice_style: Optional style override
        rate: Optional rate override
        stream_mode: Optional stream mode override
        is_greeting: Whether this is a greeting (for logging)

    Returns:
        The queued task (for optional awaiting)
    """
    previous_task: asyncio.Task | None = getattr(ws.state, "acs_playback_tail", None)
    effective_stream_mode = stream_mode or getattr(ws.state, "stream_mode", ACS_STREAMING_MODE)
    label = "greeting" if is_greeting else "response"

    async def _runner(prior: asyncio.Task | None) -> None:
        current_task = asyncio.current_task()

        # Wait for previous chunk to fully complete (synthesis + streaming)
        if prior:
            try:
                await prior
            except asyncio.CancelledError:
                # Barge-in cancelled previous - stop the chain
                logger.debug("ACS TTS queue: prior task cancelled, stopping chain")
                return
            except Exception as prior_exc:
                logger.warning("ACS TTS queue: prior task failed: %s", prior_exc)

        # Check if cancelled before starting
        cancel_requested = getattr(ws.state, "tts_cancel_requested", False)
        if cancel_requested:
            logger.debug("ACS TTS queue: skipping %s (cancel requested)", label)
            return

        try:
            logger.debug("ACS TTS queue: playing %s (len=%d)", label, len(text))
            # Use blocking=True: waits for synthesis AND all frames to stream.
            # This ensures no overlap between chunks.
            await send_response_to_acs(
                ws,
                text,
                blocking=True,
                voice_name=voice_name,
                voice_style=voice_style,
                rate=rate,
                stream_mode=effective_stream_mode,
            )
        except asyncio.CancelledError:
            logger.debug("ACS TTS queue: %s cancelled (barge-in)", label)
        except Exception as playback_exc:
            logger.exception("ACS TTS queue: %s failed", label, exc_info=playback_exc)
        finally:
            tail_now: asyncio.Task | None = getattr(ws.state, "acs_playback_tail", None)
            if tail_now is current_task:
                ws.state.acs_playback_tail = None

    next_task = asyncio.create_task(_runner(previous_task), name=f"acs_tts_{label}")
    ws.state.acs_playback_tail = next_task
    return next_task


async def queue_acs_tts_blocking(
    ws: WebSocket,
    text: str,
    *,
    voice_name: str | None = None,
    voice_style: str | None = None,
    rate: str | None = None,
    stream_mode: StreamMode | None = None,
    is_greeting: bool = False,
) -> None:
    """
    Queue TTS playback for ACS and wait for it to complete.

    Same as queue_acs_tts but awaits the task.
    Use this for greetings where you need to wait for completion.
    """
    task = queue_acs_tts(
        ws,
        text,
        voice_name=voice_name,
        voice_style=voice_style,
        rate=rate,
        stream_mode=stream_mode,
        is_greeting=is_greeting,
    )
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("ACS TTS blocking: task cancelled")
    except Exception as e:
        logger.warning("ACS TTS blocking: task failed: %s", e)


# Re-export for convenience
__all__ = [
    "send_tts_audio",
    "send_response_to_acs",
    "queue_acs_tts",
    "queue_acs_tts_blocking",
    "push_final",
    "broadcast_message",
    "broadcast_session_envelope",
    "send_session_envelope",
    "get_connection_metadata",
    "send_agent_inventory",
]
