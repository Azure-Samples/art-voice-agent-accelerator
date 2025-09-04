"""
Test DTMF validation failure cancellation logic.

This test verifies that calls are properly cancelled when DTMF validation fails.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.rtagent.backend.api.v1.handlers.dtmf_validation_lifecycle import (
    DTMFValidationLifecycle,
)
from apps.rtagent.backend.api.v1.events.types import CallEventContext


@pytest.fixture
def mock_context():
    """Create a mock CallEventContext for testing."""
    context = MagicMock(spec=CallEventContext)
    context.call_connection_id = "test-call-123"
    context.memo_manager = MagicMock()
    context.memo_manager.persist_to_redis_async = AsyncMock()
    context.redis_mgr = AsyncMock()
    context.acs_caller = MagicMock()
    context.websocket = MagicMock()
    return context


@pytest.mark.asyncio
async def test_aws_connect_validation_success_no_cancellation(mock_context):
    """Test that successful AWS Connect validation does NOT cancel the call."""
    # Arrange
    input_sequence = "123"
    expected_digits = "123"

    # Act
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        await DTMFValidationLifecycle._complete_aws_connect_validation(
            mock_context, input_sequence, expected_digits
        )

    # Assert - call should NOT be cancelled on success
    mock_cancel.assert_not_called()
    mock_context.memo_manager.set_context.assert_any_call("dtmf_validated", True)
    mock_context.memo_manager.set_context.assert_any_call(
        "dtmf_validation_gate_open", True
    )


@pytest.mark.asyncio
async def test_aws_connect_validation_failure_cancels_call(mock_context):
    """Test that failed AWS Connect validation cancels the call."""
    # Arrange
    input_sequence = "456"
    expected_digits = "123"

    # Act
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        await DTMFValidationLifecycle._complete_aws_connect_validation(
            mock_context, input_sequence, expected_digits
        )

    # Assert - call should be cancelled on failure
    mock_cancel.assert_called_once_with(mock_context)
    mock_context.memo_manager.set_context.assert_any_call("dtmf_validated", False)


@pytest.mark.asyncio
async def test_sequence_validation_failure_cancels_call(mock_context):
    """Test that failed sequence validation cancels the call."""
    # Arrange
    invalid_sequence = "12"  # Too short

    # Act
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        await DTMFValidationLifecycle._validate_sequence(mock_context, invalid_sequence)

    # Assert - call should be cancelled on failure
    mock_cancel.assert_called_once_with(mock_context)
    mock_context.memo_manager.update_context.assert_any_call("dtmf_validated", False)


@pytest.mark.asyncio
async def test_sequence_validation_success_no_cancellation(mock_context):
    """Test that successful sequence validation does NOT cancel the call."""
    # Arrange
    valid_sequence = "1234"  # Valid 4-digit PIN

    # Act
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        await DTMFValidationLifecycle._validate_sequence(mock_context, valid_sequence)

    # Assert - call should NOT be cancelled on success
    mock_cancel.assert_not_called()
    mock_context.memo_manager.update_context.assert_any_call("dtmf_validated", True)
    mock_context.memo_manager.update_context.assert_any_call(
        "dtmf_validation_gate_open", True
    )


@pytest.mark.asyncio
async def test_cancel_call_for_validation_failure_with_session_terminator(mock_context):
    """Test call cancellation using session terminator."""
    # Arrange
    mock_context.acs_caller.client = MagicMock()
    # Ensure websocket attribute exists and is truthy
    mock_context.websocket = MagicMock()

    # Act
    with patch(
        "apps.rtagent.backend.api.v1.handlers.dtmf_validation_lifecycle.terminate_session",
        new_callable=AsyncMock,
    ) as mock_terminate:
        await DTMFValidationLifecycle._cancel_call_for_validation_failure(mock_context)

    # Assert
    mock_terminate.assert_called_once()
    call_args = mock_terminate.call_args
    assert call_args.kwargs["ws"] == mock_context.websocket
    assert call_args.kwargs["is_acs"] is True
    assert call_args.kwargs["call_connection_id"] == "test-call-123"

    # Verify context updates
    mock_context.memo_manager.set_context.assert_any_call(
        "call_cancelled_dtmf_failure", True
    )
    mock_context.memo_manager.set_context.assert_any_call(
        "dtmf_validation_gate_open", False
    )

    # Verify Redis event publication
    mock_context.redis_mgr.publish_event_async.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_call_fallback_direct_hangup(mock_context):
    """Test call cancellation fallback when session terminator is not available."""
    # Arrange - no websocket available, simulate fallback
    mock_context.websocket = None
    mock_call_conn = MagicMock()
    mock_context.acs_caller.get_call_connection.return_value = mock_call_conn

    # Act
    await DTMFValidationLifecycle._cancel_call_for_validation_failure(mock_context)

    # Assert - should use direct hang_up as fallback
    mock_call_conn.hang_up.assert_called_once_with(is_for_everyone=True)


@pytest.mark.asyncio
async def test_public_cancel_method():
    """Test the public cancel_call_for_dtmf_failure method."""
    mock_context = MagicMock()

    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_private:
        await DTMFValidationLifecycle.cancel_call_for_dtmf_failure(mock_context)

    mock_private.assert_called_once_with(mock_context)
