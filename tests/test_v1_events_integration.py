"""
Comprehensive tests for V1 Events Integration and Hybrid Architecture
====================================================================

Tests the integration between:
- ACS Lifecycle Handler (simplified for ACS operations)
- V1 Event System (centralized business logic)
- REST Endpoints (event emission)
- Event Handlers (business logic processing)
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from azure.core.messaging import CloudEvent
from datetime import datetime

# Import the modules we're testing
from apps.rtagent.backend.api.v1.events.processor import (
    CallEventProcessor,
    reset_call_event_processor,
)
from apps.rtagent.backend.api.v1.events.handlers import CallEventHandlers
from apps.rtagent.backend.api.v1.events.types import (
    CallEventContext,
    ACSEventTypes,
    V1EventTypes,
)
from apps.rtagent.backend.api.v1.events.registration import register_default_handlers
from apps.rtagent.backend.api.v1.handlers.acs_call_lifecycle import ACSLifecycleHandler


class TestV1EventsIntegration:
    """Test the integrated V1 events system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset processor before each test."""
        reset_call_event_processor()

    @pytest.fixture
    def mock_redis_mgr(self):
        """Mock Redis manager."""
        return MagicMock()

    @pytest.fixture
    def mock_acs_caller(self):
        """Mock ACS caller."""
        mock_caller = AsyncMock()
        mock_caller.initiate_call.return_value = {
            "status": "created",
            "call_id": "test_call_123",
        }
        mock_caller.answer_incoming_call.return_value = MagicMock(
            call_connection_id="test_call_456"
        )
        return mock_caller

    @pytest.fixture
    def mock_memo_manager(self):
        """Mock memo manager."""
        mock_memo = MagicMock()
        mock_memo.get_context.return_value = None
        return mock_memo

    @pytest.fixture
    def sample_call_event_context(self, mock_memo_manager, mock_redis_mgr):
        """Create sample call event context."""
        event = CloudEvent(
            source="azure.communication.callautomation",
            type=ACSEventTypes.CALL_CONNECTED,
            data={
                "callConnectionId": "test_call_123",
                "callConnectionProperties": {
                    "connectedTime": datetime.utcnow().isoformat() + "Z"
                },
            },
        )

        return CallEventContext(
            event=event,
            call_connection_id="test_call_123",
            event_type=ACSEventTypes.CALL_CONNECTED,
            memo_manager=mock_memo_manager,
            redis_mgr=mock_redis_mgr,
        )

    async def test_event_processor_registration(self):
        """Test that handlers can be registered and retrieved."""
        processor = CallEventProcessor()

        async def dummy_handler(context: CallEventContext):
            pass

        # Register handler
        processor.register_handler(ACSEventTypes.CALL_CONNECTED, dummy_handler)

        # Check stats
        stats = processor.get_stats()
        assert stats["handlers_registered"] == 1
        assert ACSEventTypes.CALL_CONNECTED in stats["event_types"]

    async def test_default_handlers_registration(self):
        """Test that default handlers are registered correctly."""
        register_default_handlers()

        from apps.rtagent.backend.api.v1.events.processor import (
            get_call_event_processor,
        )

        processor = get_call_event_processor()

        stats = processor.get_stats()

        # Should have handlers for V1 events and ACS events
        assert stats["handlers_registered"] > 0
        assert V1EventTypes.CALL_INITIATED in stats["event_types"]
        assert ACSEventTypes.CALL_CONNECTED in stats["event_types"]

    async def test_call_initiated_handler(
        self, sample_call_event_context, mock_memo_manager
    ):
        """Test call initiated event handler."""
        # Modify context for call initiated event
        sample_call_event_context.event_type = V1EventTypes.CALL_INITIATED
        sample_call_event_context.event.data = {
            "callConnectionId": "test_call_123",
            "target_number": "+1234567890",
            "api_version": "v1",
        }

        # Call handler
        await CallEventHandlers.handle_call_initiated(sample_call_event_context)

        # Verify memo manager was updated
        mock_memo_manager.update_context.assert_called()

        # Check specific calls
        calls = mock_memo_manager.update_context.call_args_list
        call_args = {call[0][0]: call[0][1] for call in calls}

        assert call_args["call_initiated_via"] == "api"
        assert call_args["api_version"] == "v1"
        assert call_args["call_direction"] == "outbound"
        assert call_args["target_number"] == "+1234567890"

    async def test_call_connected_handler(self, sample_call_event_context):
        """Test call connected event handler."""
        # Mock clients for broadcast
        mock_clients = [MagicMock(), MagicMock()]
        sample_call_event_context.clients = mock_clients

        with patch(
            "apps.rtagent.backend.api.v1.events.handlers.broadcast_message"
        ) as mock_broadcast:
            await CallEventHandlers.handle_call_connected(sample_call_event_context)

            # Verify broadcast was called
            mock_broadcast.assert_called_once()

            # Check broadcast message
            broadcast_args = mock_broadcast.call_args[0]
            message_data = json.loads(broadcast_args[1])

            assert message_data["type"] == "call_connected"
            assert message_data["call_connection_id"] == "test_call_123"

    async def test_webhook_events_router(self, sample_call_event_context):
        """Test webhook events router delegates to specific handlers."""
        sample_call_event_context.event_type = V1EventTypes.WEBHOOK_EVENTS

        with patch.object(CallEventHandlers, "handle_call_connected") as mock_handle:
            # Set the original event type in context
            sample_call_event_context.event_type = ACSEventTypes.CALL_CONNECTED

            await CallEventHandlers.handle_webhook_events(sample_call_event_context)

            # Verify the specific handler was called
            mock_handle.assert_called_once_with(sample_call_event_context)

    async def test_acs_lifecycle_handler_event_emission(
        self, mock_acs_caller, mock_redis_mgr
    ):
        """Test that ACS lifecycle handler emits events correctly."""
        handler = ACSLifecycleHandler()

        with patch.object(handler, "_emit_call_event") as mock_emit:
            result = await handler.start_outbound_call(
                acs_caller=mock_acs_caller,
                target_number="+1234567890",
                redis_mgr=mock_redis_mgr,
            )

            # Verify call was successful
            assert result["status"] == "success"
            assert result["callId"] == "test_call_123"

            # Verify event was emitted
            mock_emit.assert_called_once()
            emit_args = mock_emit.call_args[0]

            assert emit_args[0] == "V1.Call.Initiated"  # event_type
            assert emit_args[1] == "test_call_123"  # call_connection_id
            assert emit_args[2]["target_number"] == "+1234567890"  # data

    async def test_process_call_events_delegation(self, mock_redis_mgr):
        """Test that process_call_events delegates to V1 event system."""
        handler = ACSLifecycleHandler()

        # Mock request object
        mock_request = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.redis = mock_redis_mgr

        # Create mock events
        mock_events = [
            MagicMock(
                type=ACSEventTypes.CALL_CONNECTED,
                data={"callConnectionId": "test_call_123"},
            )
        ]

        with patch(
            "apps.rtagent.backend.api.v1.events.processor.get_call_event_processor"
        ) as mock_get_processor:
            mock_processor = AsyncMock()
            mock_processor.process_events.return_value = {
                "status": "success",
                "processed": 1,
                "failed": 0,
            }
            mock_get_processor.return_value = mock_processor

            result = await handler.process_call_events(mock_events, mock_request)

            # Verify delegation occurred
            assert result["status"] == "success"
            assert result["processing_system"] == "events_v1"
            assert result["processed_events"] == 1

            # Verify processor was called
            mock_processor.process_events.assert_called_once()

    async def test_event_context_data_extraction(self):
        """Test event context data extraction methods."""
        # Test with dict data
        event = CloudEvent(
            source="test",
            type="test.event",
            data={"field1": "value1", "field2": "value2"},
        )

        context = CallEventContext(
            event=event, call_connection_id="test_123", event_type="test.event"
        )

        # Test get_event_data
        data = context.get_event_data()
        assert data["field1"] == "value1"
        assert data["field2"] == "value2"

        # Test get_event_field
        assert context.get_event_field("field1") == "value1"
        assert context.get_event_field("nonexistent", "default") == "default"

    async def test_event_context_json_data_extraction(self):
        """Test event context with JSON string data."""
        json_data = json.dumps({"callConnectionId": "test_123", "status": "connected"})

        event = CloudEvent(source="test", type="test.event", data=json_data)

        context = CallEventContext(
            event=event, call_connection_id="test_123", event_type="test.event"
        )

        data = context.get_event_data()
        assert data["callConnectionId"] == "test_123"
        assert data["status"] == "connected"

    async def test_processor_error_isolation(self):
        """Test that one failing handler doesn't stop others."""
        processor = CallEventProcessor()

        # Create handlers - one that fails, one that succeeds
        async def failing_handler(context: CallEventContext):
            raise Exception("Handler failed")

        async def succeeding_handler(context: CallEventContext):
            pass

        # Register both handlers for same event type
        processor.register_handler(ACSEventTypes.CALL_CONNECTED, failing_handler)
        processor.register_handler(ACSEventTypes.CALL_CONNECTED, succeeding_handler)

        # Create test event
        event = CloudEvent(
            source="test",
            type=ACSEventTypes.CALL_CONNECTED,
            data={"callConnectionId": "test_123"},
        )

        # Mock request state
        mock_state = MagicMock()

        # Process event - should not raise exception
        result = await processor.process_events([event], mock_state)

        # Should indicate partial success
        assert result["processed"] == 1  # One event processed
        assert "failed" in result or "status" in result  # Some indication of issues

    async def test_active_call_tracking(self):
        """Test that processor tracks active calls correctly."""
        processor = CallEventProcessor()

        # Mock request state
        mock_state = MagicMock()

        # Create call connected event
        connected_event = CloudEvent(
            source="test",
            type=ACSEventTypes.CALL_CONNECTED,
            data={"callConnectionId": "test_123"},
        )

        await processor.process_events([connected_event], mock_state)

        # Should track the active call
        active_calls = processor.get_active_calls()
        assert "test_123" in active_calls

        # Create call disconnected event
        disconnected_event = CloudEvent(
            source="test",
            type=ACSEventTypes.CALL_DISCONNECTED,
            data={"callConnectionId": "test_123"},
        )

        await processor.process_events([disconnected_event], mock_state)

        # Should no longer track the call
        active_calls = processor.get_active_calls()
        assert "test_123" not in active_calls


class TestEndToEndIntegration:
    """Test end-to-end integration of the hybrid architecture."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset processor before each test."""
        reset_call_event_processor()

    async def test_outbound_call_flow(self):
        """Test complete outbound call flow through hybrid architecture."""

        # 1. Setup mocks
        mock_acs_caller = AsyncMock()
        mock_acs_caller.initiate_call.return_value = {
            "status": "created",
            "call_id": "test_call_outbound",
        }

        mock_redis_mgr = MagicMock()

        # 2. Register handlers
        register_default_handlers()

        # 3. Initiate call through lifecycle handler
        handler = ACSLifecycleHandler()

        with patch.object(handler, "_emit_call_event") as mock_emit:
            result = await handler.start_outbound_call(
                acs_caller=mock_acs_caller,
                target_number="+1234567890",
                redis_mgr=mock_redis_mgr,
            )

        # 4. Verify ACS operation succeeded
        assert result["status"] == "success"
        assert result["callId"] == "test_call_outbound"

        # 5. Verify event was emitted for business logic
        mock_emit.assert_called_once()
        emit_args = mock_emit.call_args[0]
        assert emit_args[0] == "V1.Call.Initiated"
        assert emit_args[1] == "test_call_outbound"

    async def test_webhook_processing_flow(self):
        """Test webhook event processing through the events system."""

        # 1. Register handlers
        register_default_handlers()

        # 2. Create mock webhook events
        webhook_events = [
            CloudEvent(
                source="azure.communication.callautomation",
                type=ACSEventTypes.CALL_CONNECTED,
                data={"callConnectionId": "webhook_call_123"},
            ),
            CloudEvent(
                source="azure.communication.callautomation",
                type=ACSEventTypes.PARTICIPANTS_UPDATED,
                data={
                    "callConnectionId": "webhook_call_123",
                    "participants": [
                        {"identifier": {"phoneNumber": {"value": "+1234567890"}}}
                    ],
                },
            ),
        ]

        # 3. Mock request state
        mock_state = MagicMock()
        mock_state.redis = MagicMock()

        # 4. Process through event system
        from apps.rtagent.backend.api.v1.events.processor import (
            get_call_event_processor,
        )

        processor = get_call_event_processor()

        result = await processor.process_events(webhook_events, mock_state)

        # 5. Verify processing
        assert result["processed"] == 2
        assert result["failed"] == 0

    async def test_error_handling_consistency(self):
        """Test that errors are handled consistently across the system."""

        # 1. Test ACS operation error
        mock_acs_caller = AsyncMock()
        mock_acs_caller.initiate_call.side_effect = Exception("ACS Error")

        handler = ACSLifecycleHandler()

        with pytest.raises(Exception):  # Should propagate as HTTPException
            await handler.start_outbound_call(
                acs_caller=mock_acs_caller,
                target_number="+1234567890",
                redis_mgr=MagicMock(),
            )

        # 2. Test event processing error
        register_default_handlers()

        # Create malformed event
        bad_event = CloudEvent(source="test", type="Unknown.Event.Type", data=None)

        from apps.rtagent.backend.api.v1.events.processor import (
            get_call_event_processor,
        )

        processor = get_call_event_processor()

        # Should handle gracefully without raising
        result = await processor.process_events([bad_event], MagicMock())
        assert "status" in result


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
