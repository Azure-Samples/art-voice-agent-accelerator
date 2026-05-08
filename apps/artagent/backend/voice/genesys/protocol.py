"""
Genesys AudioHook v2 Protocol
===============================

Implements the Genesys Cloud AudioConnector AudioHook v2 protocol for
WebSocket-based real-time audio streaming.

Protocol overview:
    - Client (Genesys) sends: open, close, ping, playback_started,
      playback_completed, dtmf, error, update, discarded, resumed, paused
    - Server sends: opened, closed, pong, disconnect, event, pause,
      resume, reconnect, updated
    - Binary frames carry µ-law 8kHz audio in both directions
    - Sequence numbers tracked on both sides for ordering

Reference: https://developer.genesys.cloud/devapps/audiohook/
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger("genesys.protocol")


# ═══════════════════════════════════════════════════════════════════════════════
# Protocol Constants
# ═══════════════════════════════════════════════════════════════════════════════

PROTOCOL_VERSION = "2"

# Client → Server message types
CLIENT_MSG_OPEN = "open"
CLIENT_MSG_CLOSE = "close"
CLIENT_MSG_PING = "ping"
CLIENT_MSG_PLAYBACK_STARTED = "playback_started"
CLIENT_MSG_PLAYBACK_COMPLETED = "playback_completed"
CLIENT_MSG_DTMF = "dtmf"
CLIENT_MSG_ERROR = "error"
CLIENT_MSG_UPDATE = "update"
CLIENT_MSG_PAUSED = "paused"
CLIENT_MSG_RESUMED = "resumed"
CLIENT_MSG_DISCARDED = "discarded"

# Server → Client message types
SERVER_MSG_OPENED = "opened"
SERVER_MSG_CLOSED = "closed"
SERVER_MSG_PONG = "pong"
SERVER_MSG_DISCONNECT = "disconnect"
SERVER_MSG_EVENT = "event"
SERVER_MSG_PAUSE = "pause"
SERVER_MSG_RESUME = "resume"
SERVER_MSG_RECONNECT = "reconnect"
SERVER_MSG_UPDATED = "updated"

# Disconnect reasons
DISCONNECT_COMPLETED = "completed"
DISCONNECT_UNAUTHORIZED = "unauthorized"
DISCONNECT_ERROR = "error"

# Supported media format
SUPPORTED_FORMAT = "PCMU"
SUPPORTED_RATE = 8000


class GenesysProtocol:
    """Manages AudioHook v2 protocol state and message construction.

    Handles sequence number tracking, message validation, and serialization
    for the Genesys AudioConnector WebSocket protocol.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._server_seq = 0
        self._client_seq = 0
        self._conversation_id: str | None = None
        self._organization_id: str | None = None
        self._input_variables: dict[str, str] = {}
        self._selected_media: dict[str, Any] | None = None

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def organization_id(self) -> str | None:
        return self._organization_id

    @property
    def input_variables(self) -> dict[str, str]:
        return self._input_variables

    # ─────────────────────────────────────────────────────────────────────────
    # Inbound message processing
    # ─────────────────────────────────────────────────────────────────────────

    def validate_message(self, raw: str) -> dict[str, Any] | None:
        """Parse and validate an inbound client message.

        Returns the parsed message dict, or None if validation fails.
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[GenesysProtocol] Failed to parse JSON message")
            return None

        msg_type = msg.get("type")
        msg_seq = msg.get("seq")
        msg_serverseq = msg.get("serverseq", 0)
        msg_id = msg.get("id")

        # Validate sequence numbers
        if msg_seq is not None and msg_seq != self._client_seq + 1:
            logger.warning(
                "[GenesysProtocol] Invalid client seq: got %s, expected %s",
                msg_seq,
                self._client_seq + 1,
            )
            return None

        if msg_serverseq is not None and msg_serverseq > self._server_seq:
            logger.warning(
                "[GenesysProtocol] Invalid server seq reference: %s > %s",
                msg_serverseq,
                self._server_seq,
            )
            return None

        # Validate session ID
        if msg_id and msg_id != self.session_id:
            logger.warning(
                "[GenesysProtocol] Session ID mismatch: got %s, expected %s",
                msg_id,
                self.session_id,
            )
            return None

        # Update client sequence
        if msg_seq is not None:
            self._client_seq = msg_seq

        return msg

    def process_open(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Process an 'open' message and extract session parameters.

        Returns the selected media parameter or None if no compatible format.
        """
        params = msg.get("parameters", {})
        self._conversation_id = params.get("conversationId")
        self._organization_id = params.get("organizationId")
        self._input_variables = params.get("inputVariables", {})

        media_list = params.get("media", [])
        for media in media_list:
            if media.get("format") == SUPPORTED_FORMAT and media.get("rate") == SUPPORTED_RATE:
                self._selected_media = media
                logger.info(
                    "[GenesysProtocol] Session opened | conversation=%s org=%s media=%s",
                    self._conversation_id,
                    self._organization_id,
                    json.dumps(media),
                )
                return media

        logger.warning("[GenesysProtocol] No supported media format found in open message")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Outbound message construction
    # ─────────────────────────────────────────────────────────────────────────

    def _create_server_message(self, msg_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Create a server message with proper sequencing."""
        self._server_seq += 1
        return {
            "version": PROTOCOL_VERSION,
            "id": self.session_id,
            "type": msg_type,
            "seq": self._server_seq,
            "clientseq": self._client_seq,
            "parameters": parameters,
        }

    def create_opened(self, media: dict[str, Any]) -> dict[str, Any]:
        """Create 'opened' response confirming media selection."""
        return self._create_server_message(SERVER_MSG_OPENED, {"media": [media]})

    def create_pong(self) -> dict[str, Any]:
        """Create 'pong' keep-alive response."""
        return self._create_server_message(SERVER_MSG_PONG, {})

    def create_closed(self) -> dict[str, Any]:
        """Create 'closed' acknowledgment."""
        return self._create_server_message(SERVER_MSG_CLOSED, {})

    def create_updated(self) -> dict[str, Any]:
        """Create 'updated' acknowledgment."""
        return self._create_server_message(SERVER_MSG_UPDATED, {})

    def create_disconnect(
        self,
        reason: str = DISCONNECT_COMPLETED,
        info: str = "",
        output_variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create 'disconnect' message to end the session."""
        params: dict[str, Any] = {"reason": reason}
        if info:
            params["info"] = info
        if output_variables:
            params["outputVariables"] = output_variables
        return self._create_server_message(SERVER_MSG_DISCONNECT, params)

    def create_event(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        """Create 'event' message with entity list."""
        return self._create_server_message(SERVER_MSG_EVENT, {"entities": entities})

    def create_barge_in_event(self) -> dict[str, Any]:
        """Create barge-in event to signal user interruption."""
        return self.create_event([{"type": "barge_in", "data": {}}])

    def create_transcript_event(
        self,
        transcript: str,
        channel: str = "external",
        is_final: bool = True,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Create transcript event for speech recognition results."""
        entity = {
            "type": "transcript",
            "data": {
                "id": str(uuid.uuid4()),
                "channel": channel,
                "isFinal": is_final,
                "alternatives": [
                    {
                        "confidence": confidence,
                        "interpretations": [
                            {"type": "normalized", "transcript": transcript},
                        ],
                    },
                ],
            },
        }
        return self.create_event([entity])

    def create_bot_turn_response(
        self,
        disposition: str = "match",
        text: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        """Create bot_turn_response event."""
        data: dict[str, Any] = {"disposition": disposition}
        if text is not None:
            data["text"] = text
        if confidence is not None:
            data["confidence"] = confidence
        return self.create_event([{"type": "bot_turn_response", "data": data}])
