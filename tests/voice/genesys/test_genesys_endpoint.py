"""Endpoint-level tests for the Genesys AudioHook v2 WebSocket route.

These exercise the *real* FastAPI WebSocket endpoint
(``/api/v1/genesys/stream``) end-to-end via Starlette's ``TestClient`` — the
WebSocket handshake, subprotocol negotiation, and the open→opened transaction —
without requiring the private Azure backend. The only thing stubbed is the
VoiceLive connection itself (``_connect_voicelive``), so we can assert that a
Genesys *connection probe* never allocates VoiceLive resources while a real
conversation does.

This is the integration counterpart to ``test_genesys_protocol.py`` and directly
validates the fix for the IBM AudioConnector activation failure.

Reference: https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from apps.artagent.backend.api.v1.endpoints.genesys import router
from apps.artagent.backend.voice.genesys.handler import GenesysVoiceLiveHandler
from apps.artagent.backend.voice.genesys.protocol import NULL_UUID

SESSION_ID = "62780b08-3a9d-43b0-9d74-4aa5745fa633"

PROBE_MEDIA = [
    {"type": "audio", "format": "PCMU", "channels": ["external", "internal"], "rate": 8000},
    {"type": "audio", "format": "PCMU", "channels": ["external"], "rate": 8000},
    {"type": "audio", "format": "PCMU", "channels": ["internal"], "rate": 8000},
]

REAL_MEDIA = [
    {"type": "audio", "format": "PCMU", "channels": ["external"], "rate": 8000},
]


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/genesys")
    return app


def _open_message(*, conversation_id: str, media: list[dict], seq: int = 1) -> dict:
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


def _close_message(seq: int = 2) -> dict:
    return {
        "version": "2",
        "id": SESSION_ID,
        "type": "close",
        "seq": seq,
        "serverseq": 1,
        "position": "PT1S",
        "parameters": {},
    }


@pytest.fixture()
def client():
    return TestClient(_build_app())


# ── Connection probe (the IBM activation path) ───────────────────────────────


def test_connection_probe_completes_without_allocating_voicelive(client):
    """A null-UUID probe must get a conformant ``opened`` and never touch VoiceLive."""
    with patch.object(
        GenesysVoiceLiveHandler, "_connect_voicelive", new_callable=AsyncMock
    ) as mock_connect, patch.object(
        GenesysVoiceLiveHandler, "_websocket_open", new_callable=PropertyMock, return_value=True
    ):
        with client.websocket_connect(
            "/api/v1/genesys/stream",
            headers={"audiohook-session-id": SESSION_ID},
        ) as ws:
            ws.send_text(json.dumps(_open_message(conversation_id=NULL_UUID, media=PROBE_MEDIA)))
            opened = json.loads(ws.receive_text())

            assert opened["type"] == "opened"
            assert opened["id"] == SESSION_ID
            assert opened["parameters"]["startPaused"] is False
            assert opened["parameters"]["media"][0]["format"] == "PCMU"

            # The whole point of the fix: a probe must NOT spin up VoiceLive.
            mock_connect.assert_not_awaited()

            # Probe then closes; server must answer with closed.
            ws.send_text(json.dumps(_close_message()))
            closed = json.loads(ws.receive_text())
            assert closed["type"] == "closed"


def test_real_conversation_open_allocates_voicelive(client):
    """A real (non-null) conversationId must still drive a VoiceLive connection."""
    with patch.object(
        GenesysVoiceLiveHandler, "_connect_voicelive", new_callable=AsyncMock
    ) as mock_connect, patch.object(
        GenesysVoiceLiveHandler, "_websocket_open", new_callable=PropertyMock, return_value=True
    ):
        with client.websocket_connect(
            "/api/v1/genesys/stream",
            headers={"audiohook-session-id": SESSION_ID},
        ) as ws:
            ws.send_text(
                json.dumps(
                    _open_message(
                        conversation_id="11111111-2222-3333-4444-555555555555",
                        media=REAL_MEDIA,
                    )
                )
            )
            opened = json.loads(ws.receive_text())
            assert opened["type"] == "opened"

        mock_connect.assert_awaited_once()


# ── WebSocket subprotocol negotiation (RFC 6455 conformance) ─────────────────


def test_no_subprotocol_selected_when_client_offers_none(client):
    """Genesys offers no subprotocol; the server must not force one."""
    with patch.object(
        GenesysVoiceLiveHandler, "_websocket_open", new_callable=PropertyMock, return_value=True
    ):
        with client.websocket_connect(
            "/api/v1/genesys/stream",
            headers={"audiohook-session-id": SESSION_ID},
        ) as ws:
            assert getattr(ws, "accepted_subprotocol", None) is None


def test_subprotocol_mirrored_only_when_offered(client):
    """If a client offers ``audiohook`` the server may echo exactly that token."""
    with patch.object(
        GenesysVoiceLiveHandler, "_websocket_open", new_callable=PropertyMock, return_value=True
    ):
        with client.websocket_connect(
            "/api/v1/genesys/stream",
            headers={"audiohook-session-id": SESSION_ID},
            subprotocols=["audiohook"],
        ) as ws:
            assert getattr(ws, "accepted_subprotocol", None) == "audiohook"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
