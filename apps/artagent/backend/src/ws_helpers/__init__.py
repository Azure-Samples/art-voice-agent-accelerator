"""
WebSocket Helpers
=================

Utilities for WebSocket messaging across transports.

Quick Reference:
----------------

SENDING TO UI (Dashboard/Frontend):
    # Final user transcript (broadcast to all session connections)
    await send_user_transcript(ws, text, session_id=sid, broadcast_only=True)

    # Partial/interim transcript
    await send_user_partial_transcript(ws, text, session_id=sid)

    # Generic session envelope
    await send_session_envelope(ws, envelope, session_id=sid, broadcast_only=True)

SENDING TTS AUDIO:
    # Browser - sends raw PCM frames
    await send_tts_audio(text, ws)

    # ACS - sends base64-wrapped JSON frames
    await send_response_to_acs(ws, text, blocking=True)

BUILDING ENVELOPES (envelopes.py):
    make_envelope(etype, sender, payload, topic, session_id)
    make_status_envelope(message, sender, session_id)
    make_event_envelope(event_type, event_data, sender)

BARGE-IN (barge_in.py):
    BargeInController - manages interruption detection for browser transport

Important: For ACS calls, always use broadcast_only=True because the ACS
WebSocket is separate from the dashboard relay WebSocket.
"""
