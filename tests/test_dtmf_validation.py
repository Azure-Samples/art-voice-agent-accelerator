# Ensure telemetry is disabled for unit tests to avoid the ProxyLogger/resource issue
import os

# Disable cloud telemetry so utils/ml_logging avoids attaching OpenTelemetry LoggingHandler.
# This must be set before importing modules that call get_logger() at import time.
os.environ.setdefault("DISABLE_CLOUD_TELEMETRY", "true")
# Also ensure Application Insights connection string is not set (prevents other code paths)
os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

import asyncio
import json
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from apps.rtagent.backend.api.v1.handlers.dtmf_validation_lifecycle import (
    DTMFValidationLifecycle,
)


class DummyMemo:
    def __init__(self):
        self._d = {}

    def get_context(self, k, default=None):
        return self._d.get(k, default)

    def update_context(self, k, v):
        self._d[k] = v

    def set_context(self, k, v):
        self._d[k] = v

    async def persist_to_redis_async(self, redis_mgr):
        pass


class FakeAuthService:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    async def validate_pin(self, call_id, phone, pin):
        self.calls.append((call_id, phone, pin))
        # small delay to emulate I/O
        await asyncio.sleep(0.01)
        return {"ok": self.ok, "user_id": "u1"} if self.ok else {"ok": False}


@pytest.mark.asyncio
async def test_validate_sequence_success():
    """Test successful DTMF sequence validation using centralized logic."""
    memo = DummyMemo()

    context = SimpleNamespace(
        call_connection_id="call-1",
        memo_manager=memo,
        redis_mgr=AsyncMock(),
        clients=None,
        acs_caller=None,
    )

    # Mock the cancellation method to ensure it's not called on success
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        # Test a valid 4-digit sequence
        await DTMFValidationLifecycle._validate_sequence(context, "1234")

    # Assert success case
    assert memo.get_context("dtmf_validated") is True
    assert memo.get_context("entered_pin") == "1234"
    assert memo.get_context("dtmf_validation_gate_open") is True
    mock_cancel.assert_not_called()


@pytest.mark.asyncio
async def test_validate_sequence_failure():
    """Test failed DTMF sequence validation using centralized logic."""
    memo = DummyMemo()

    context = SimpleNamespace(
        call_connection_id="call-2",
        memo_manager=memo,
        redis_mgr=AsyncMock(),
        clients=None,
        acs_caller=None,
    )

    # Mock the cancellation method to verify it's called on failure
    with patch.object(
        DTMFValidationLifecycle, "_cancel_call_for_validation_failure"
    ) as mock_cancel:
        # Test an invalid sequence (too short)
        await DTMFValidationLifecycle._validate_sequence(context, "12")

    # Assert failure case
    assert memo.get_context("dtmf_validated") is False
    assert memo.get_context("entered_pin") is None
    # Verify call cancellation was triggered
    mock_cancel.assert_called_once_with(context)
