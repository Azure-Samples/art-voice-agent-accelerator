"""Unit tests for the Genesys AudioHook v2 protocol layer.

These are the first automated tests for the Genesys connector. They guard the
regressions found while debugging an IBM AudioConnector integration that failed
Genesys's activation connection probe:

* Connection-probe detection (null-UUID conversationId).
* ``opened`` message conformance — should carry ``startPaused`` to match the
  AudioHook v2 'opened' schema example (the field is optional per the schema).
* Media selection / open-transaction handling.
* Sequence-number + session-id validation.

Reference: https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices
"""

from __future__ import annotations

import json

import pytest

from apps.artagent.backend.voice.genesys.protocol import (
    NULL_UUID,
    GenesysProtocol,
)

SESSION_ID = "62780b08-3a9d-43b0-9d74-4aa5745fa633"

EXTERNAL_MEDIA = {
    "type": "audio",
    "format": "PCMU",
    "channels": ["external"],
    "rate": 8000,
}


def _open_message(
    *,
    conversation_id: str,
    media: list[dict] | None = None,
    seq: int = 1,
) -> dict:
    """Build an AudioHook 'open' message matching Genesys's wire format."""
    if media is None:
        media = [dict(EXTERNAL_MEDIA)]
    return {
        "version": "2",
        "id": SESSION_ID,
        "type": "open",
        "seq": seq,
        "serverseq": 0,
        "position": "PT0S",
        "parameters": {
            "organizationId": "aec04f7c-8108-4e07-a9d6-67a8d5df7b3e",
            "conversationId": conversation_id,
            "participant": {"id": conversation_id, "ani": "", "aniName": "", "dnis": ""},
            "media": media,
        },
    }


# ── Connection-probe detection ──────────────────────────────────────────────


def test_connection_probe_detected_for_null_uuid():
    proto = GenesysProtocol(SESSION_ID)
    probe = _open_message(
        conversation_id=NULL_UUID,
        media=[
            {"type": "audio", "format": "PCMU", "channels": ["external", "internal"], "rate": 8000},
            {"type": "audio", "format": "PCMU", "channels": ["external"], "rate": 8000},
            {"type": "audio", "format": "PCMU", "channels": ["internal"], "rate": 8000},
        ],
    )
    assert proto.is_connection_probe(probe) is True


def test_real_conversation_is_not_a_probe():
    proto = GenesysProtocol(SESSION_ID)
    real = _open_message(conversation_id="11111111-2222-3333-4444-555555555555")
    assert proto.is_connection_probe(real) is False


def test_missing_conversation_id_is_not_a_probe():
    proto = GenesysProtocol(SESSION_ID)
    assert proto.is_connection_probe({"parameters": {}}) is False
    assert proto.is_connection_probe({}) is False


def test_probe_offering_full_media_list_still_selects_supported_format():
    """The probe sends a *full* media list (not empty); process_open must match it."""
    proto = GenesysProtocol(SESSION_ID)
    probe = _open_message(
        conversation_id=NULL_UUID,
        media=[
            {"type": "audio", "format": "PCMU", "channels": ["external", "internal"], "rate": 8000},
            {"type": "audio", "format": "PCMU", "channels": ["external"], "rate": 8000},
        ],
    )
    selected = proto.process_open(probe)
    assert selected is not None
    assert selected["format"] == "PCMU"
    assert selected["rate"] == 8000


# ── opened message conformance ──────────────────────────────────────────────


def test_opened_includes_start_paused_false_by_default():
    proto = GenesysProtocol(SESSION_ID)
    opened = proto.create_opened(dict(EXTERNAL_MEDIA))
    assert opened["type"] == "opened"
    assert opened["version"] == "2"
    assert opened["id"] == SESSION_ID  # server must echo the client's session id
    assert opened["parameters"]["startPaused"] is False
    assert opened["parameters"]["media"] == [EXTERNAL_MEDIA]


def test_opened_can_start_paused():
    proto = GenesysProtocol(SESSION_ID)
    opened = proto.create_opened(dict(EXTERNAL_MEDIA), start_paused=True)
    assert opened["parameters"]["startPaused"] is True


# ── open-transaction media selection ────────────────────────────────────────


def test_process_open_selects_pcmu_8khz():
    proto = GenesysProtocol(SESSION_ID)
    selected = proto.process_open(_open_message(conversation_id=NULL_UUID))
    assert selected == EXTERNAL_MEDIA


def test_process_open_rejects_unsupported_format():
    proto = GenesysProtocol(SESSION_ID)
    msg = _open_message(
        conversation_id=NULL_UUID,
        media=[{"type": "audio", "format": "L16", "channels": ["external"], "rate": 16000}],
    )
    assert proto.process_open(msg) is None


def test_process_open_with_empty_media_returns_none():
    proto = GenesysProtocol(SESSION_ID)
    msg = _open_message(conversation_id=NULL_UUID, media=[])
    assert proto.process_open(msg) is None


# ── sequence + session-id validation ────────────────────────────────────────


def test_validate_message_rejects_session_id_mismatch():
    proto = GenesysProtocol(SESSION_ID)
    foreign = _open_message(conversation_id=NULL_UUID)
    foreign["id"] = "deadbeef-0000-0000-0000-000000000000"
    assert proto.validate_message(json.dumps(foreign)) is None


def test_validate_message_accepts_matching_id_and_tracks_seq():
    proto = GenesysProtocol(SESSION_ID)
    parsed = proto.validate_message(json.dumps(_open_message(conversation_id=NULL_UUID, seq=1)))
    assert parsed is not None
    # opened should mirror the just-received client seq
    opened = proto.create_opened(dict(EXTERNAL_MEDIA))
    assert opened["clientseq"] == 1
    assert opened["seq"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
