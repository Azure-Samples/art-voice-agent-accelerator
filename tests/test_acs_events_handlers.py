"""
Test ACS Events Handler Functionality
=====================================

Focused tests for the refactored ACS events handling.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apps.artagent.backend.api.v1.events.handlers import CallEventHandlers
from apps.artagent.backend.api.v1.events.types import (
    ACSEventTypes,
    CallEventContext,
    V1EventTypes,
)
from azure.core.messaging import CloudEvent


class TestCallEventHandlers:
    """Test individual event handlers."""

    @pytest.fixture
    def mock_context(self):
        """Create mock call event context."""
        event = CloudEvent(
            source="test",
            type=ACSEventTypes.CALL_CONNECTED,
            data={"callConnectionId": "test_123"},
        )

        context = CallEventContext(
            event=event,
            call_connection_id="test_123",
            event_type=ACSEventTypes.CALL_CONNECTED,
        )
        context.memo_manager = MagicMock()
        context.clients = []

        # Stub ACS caller connection with participants list
        call_conn = MagicMock()
        call_conn.list_participants.return_value = [
            SimpleNamespace(
                identifier=SimpleNamespace(kind="phone_number", properties={"value": "+1234567890"})
            ),
            SimpleNamespace(identifier=SimpleNamespace(kind="communicationUser", properties={})),
        ]

        acs_caller = MagicMock()
        acs_caller.get_call_connection.return_value = call_conn
        context.acs_caller = acs_caller

        # App state with redis manager stub
        redis_mgr = SimpleNamespace(get_value_async=AsyncMock(return_value=None))
        context.redis_mgr = redis_mgr
        context.app_state = SimpleNamespace(redis=redis_mgr, conn_manager=None)
        return context

    @patch("apps.artagent.backend.api.v1.events.handlers.logger")
    async def test_handle_call_initiated(self, mock_logger, mock_context):
        """Test call initiated handler."""
        mock_context.event_type = V1EventTypes.CALL_INITIATED
        mock_context.event.data = {
            "callConnectionId": "test_123",
            "target_number": "+1234567890",
            "api_version": "v1",
        }

        await CallEventHandlers.handle_call_initiated(mock_context)

        # Verify context updates
        assert mock_context.memo_manager.update_context.called
        calls = mock_context.memo_manager.update_context.call_args_list

        # Extract all calls as dict
        updates = {call[0][0]: call[0][1] for call in calls}

        assert updates["call_initiated_via"] == "api"
        assert updates["api_version"] == "v1"
        assert updates["call_direction"] == "outbound"

    @patch("apps.artagent.backend.api.v1.events.acs_events.logger")
    async def test_handle_inbound_call_received(self, mock_logger, mock_context):
        """Test inbound call received handler."""
        mock_context.event_type = V1EventTypes.INBOUND_CALL_RECEIVED
        mock_context.event.data = {
            "callConnectionId": "test_123",
            "from": {"kind": "phoneNumber", "phoneNumber": {"value": "+1987654321"}},
        }

        await CallEventHandlers.handle_inbound_call_received(mock_context)

        # Verify context updates
        calls = mock_context.memo_manager.update_context.call_args_list
        updates = {call[0][0]: call[0][1] for call in calls}

        assert updates["call_direction"] == "inbound"
        assert updates["caller_id"] == "+1987654321"

    # @patch("apps.artagent.backend.api.v1.events.acs_events.logger")
    # async def test_handle_call_connected_with_broadcast(
    #     self, mock_logger, mock_context
    # ):
    #     """Test call connected handler with WebSocket broadcast."""
    #     with patch(
    #         "apps.artagent.backend.api.v1.events.acs_events.broadcast_session_envelope"
    #     ) as mock_broadcast, patch(
    #         "apps.artagent.backend.api.v1.events.acs_events.DTMFValidationLifecycle.setup_aws_connect_validation_flow",
    #         new=AsyncMock(),
    #     ) as mock_dtmf:
    #         await CallEventHandlers.handle_call_connected(mock_context)

    #         if events_handlers.DTMF_VALIDATION_ENABLED:
    #             mock_dtmf.assert_awaited()
    #         else:
    #             mock_dtmf.assert_not_awaited()
    #         assert mock_broadcast.await_count == 2

    #         status_call = mock_broadcast.await_args_list[0]
    #         event_call = mock_broadcast.await_args_list[1]

    #         status_envelope = status_call.args[1]
    #         assert status_envelope["type"] == "status"
    #         assert status_envelope["payload"]["message"].startswith("📞 Call connected")
    #         assert status_call.kwargs["session_id"] == "test_123"

    #         event_envelope = event_call.args[1]
    #         assert event_envelope["type"] == "event"
    #         assert event_envelope["payload"]["event_type"] == "call_connected"
    #         assert event_envelope["payload"]["call_connection_id"] == "test_123"
    #         assert event_call.kwargs["session_id"] == "test_123"

    @patch("apps.artagent.backend.api.v1.events.acs_events.logger")
    async def test_handle_dtmf_tone_received(self, mock_logger, mock_context):
        """Test DTMF tone handling."""
        mock_context.event_type = ACSEventTypes.DTMF_TONE_RECEIVED
        mock_context.event.data = {
            "callConnectionId": "test_123",
            "tone": "5",
            "sequenceId": 1,
        }

        # Mock current sequence
        mock_context.memo_manager.get_context.return_value = "123"

        await CallEventHandlers.handle_dtmf_tone_received(mock_context)

        # Should update DTMF sequence
        mock_context.memo_manager.update_context.assert_called()

    async def test_extract_caller_id_phone_number(self):
        """Test caller ID extraction from phone number."""
        caller_info = {"kind": "phoneNumber", "phoneNumber": {"value": "+1234567890"}}

        caller_id = CallEventHandlers._extract_caller_id(caller_info)
        assert caller_id == "+1234567890"

    async def test_extract_caller_id_raw_id(self):
        """Test caller ID extraction from raw ID."""
        caller_info = {"kind": "other", "rawId": "user@domain.com"}

        caller_id = CallEventHandlers._extract_caller_id(caller_info)
        assert caller_id == "user@domain.com"

    async def test_extract_caller_id_fallback(self):
        """Test caller ID extraction fallback."""
        caller_info = {}

        caller_id = CallEventHandlers._extract_caller_id(caller_info)
        assert caller_id == "unknown"

    @patch(
        "apps.artagent.backend.api.v1.events.acs_events.broadcast_session_envelope",
        new_callable=AsyncMock,
    )
    async def test_call_transfer_accepted_envelope(self, mock_broadcast, mock_context):
        mock_context.event_type = ACSEventTypes.CALL_TRANSFER_ACCEPTED
        mock_context.event.data = {
            "callConnectionId": "test_123",
            "operationContext": "route-42",
            "targetParticipant": {"rawId": "sip:agent@example.com"},
        }

        with patch.object(
            CallEventHandlers,
            "_broadcast_session_event_envelope",
            new_callable=AsyncMock,
        ) as mock_event:
            await CallEventHandlers.handle_call_transfer_accepted(mock_context)

        assert mock_broadcast.await_count == 1
        status_envelope = mock_broadcast.await_args.kwargs["envelope"]
        assert status_envelope["payload"]["label"] == "Transfer Accepted"
        assert "Call transfer accepted" in status_envelope["payload"]["message"]

        mock_event.assert_awaited()
        assert mock_event.await_args.kwargs["event_type"] == "call_transfer_accepted"

    @patch(
        "apps.artagent.backend.api.v1.events.acs_events.broadcast_session_envelope",
        new_callable=AsyncMock,
    )
    async def test_call_transfer_failed_envelope(self, mock_broadcast, mock_context):
        mock_context.event_type = ACSEventTypes.CALL_TRANSFER_FAILED
        mock_context.event.data = {
            "callConnectionId": "test_123",
            "operationContext": "route-42",
            "targetParticipant": {"phoneNumber": {"value": "+1234567890"}},
            "resultInformation": {"message": "Busy"},
        }

        with patch.object(
            CallEventHandlers,
            "_broadcast_session_event_envelope",
            new_callable=AsyncMock,
        ) as mock_event:
            await CallEventHandlers.handle_call_transfer_failed(mock_context)

        assert mock_broadcast.await_count == 1
        status_envelope = mock_broadcast.await_args.kwargs["envelope"]
        assert status_envelope["payload"]["label"] == "Transfer Failed"
        assert "Call transfer failed" in status_envelope["payload"]["message"]
        assert "Busy" in status_envelope["payload"]["message"]

        mock_event.assert_awaited()
        assert mock_event.await_args.kwargs["event_type"] == "call_transfer_failed"


class TestEventProcessingFlow:
    """Test event processing flow."""

    @patch("apps.artagent.backend.api.v1.events.handlers.logger")
    async def test_webhook_event_routing(self, mock_logger):
        """Test webhook event router."""
        event = CloudEvent(
            source="test",
            type=ACSEventTypes.CALL_CONNECTED,
            data={"callConnectionId": "test_123"},
        )

        context = CallEventContext(
            event=event,
            call_connection_id="test_123",
            event_type=ACSEventTypes.CALL_CONNECTED,
        )

        with patch.object(CallEventHandlers, "handle_call_connected") as mock_handler:
            await CallEventHandlers.handle_webhook_events(context)
            mock_handler.assert_called_once_with(context)

    @patch("apps.artagent.backend.api.v1.events.handlers.logger")
    async def test_unknown_event_type_handling(self, mock_logger):
        """Test handling of unknown event types."""
        event = CloudEvent(
            source="test",
            type="Unknown.Event.Type",
            data={"callConnectionId": "test_123"},
        )

        context = CallEventContext(
            event=event, call_connection_id="test_123", event_type="Unknown.Event.Type"
        )

        # Should handle gracefully without error
        await CallEventHandlers.handle_webhook_events(context)

        # No specific handler should be called for unknown type
        # This should just log and continue


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
