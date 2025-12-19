"""Quick verification tests for MemoManager optimizations."""

from unittest.mock import MagicMock

import pytest
from src.stateful.state_managment import MemoManager


def test_memomanager_init_basic():
    """Test basic MemoManager initialization."""
    mm = MemoManager()
    assert mm.session_id is not None
    assert len(mm.session_id) > 0


def test_memomanager_init_with_session_id():
    """Test MemoManager with explicit session_id."""
    mm = MemoManager(session_id="test123")
    assert mm.session_id == "test123"


def test_context_get_set():
    """Test context operations work."""
    mm = MemoManager(session_id="ctx-test")
    mm.set_context("mykey", "myvalue")
    assert mm.get_context("mykey") == "myvalue"


def test_tts_interrupt():
    """Test TTS interrupt flag (simplified key)."""
    mm = MemoManager(session_id="tts-test")
    assert mm.is_tts_interrupted() is False
    mm.set_tts_interrupted(True)
    assert mm.is_tts_interrupted() is True
    mm.set_tts_interrupted(False)
    assert mm.is_tts_interrupted() is False


def test_from_redis_with_manager_loads_data():
    """Test from_redis_with_manager actually loads data from Redis."""
    mock_redis = MagicMock()
    mock_redis.get_session_data.return_value = {
        "corememory": '{"loaded_key": "loaded_value"}',
        "chat_history": "{}",
    }

    mm = MemoManager.from_redis_with_manager("session456", mock_redis)

    # Should store the redis manager reference
    assert mm._redis_manager == mock_redis

    # Should have loaded the data
    assert mm.get_context("loaded_key") == "loaded_value"

    # Should have called get_session_data (with session: prefix)
    mock_redis.get_session_data.assert_called_once_with("session:session456")


def test_no_auto_refresh_attributes():
    """Verify auto_refresh code was removed - these attributes should not exist."""
    mm = MemoManager()
    # These attributes were removed as dead code
    assert not hasattr(mm, "auto_refresh_interval")
    assert not hasattr(mm, "last_refresh_time")
    assert not hasattr(mm, "_refresh_task")
    # These methods were removed
    assert not hasattr(mm, "enable_auto_refresh")
    assert not hasattr(mm, "disable_auto_refresh")
    assert not hasattr(mm, "_auto_refresh_loop")


def test_pending_persist_task_initialized():
    """Verify _pending_persist_task attribute exists for lifecycle management."""
    mm = MemoManager()
    assert hasattr(mm, "_pending_persist_task")
    assert mm._pending_persist_task is None


def test_cancel_pending_persist_no_task():
    """cancel_pending_persist returns False when no task is pending."""
    mm = MemoManager()
    assert mm.cancel_pending_persist() is False


@pytest.mark.asyncio
async def test_persist_background_creates_task():
    """persist_background creates and tracks the task."""
    mock_redis = MagicMock()
    mock_redis.set_session_data = MagicMock(return_value=None)

    mm = MemoManager(session_id="task-test", redis_mgr=mock_redis)

    # Initially no task
    assert mm._pending_persist_task is None

    # Call persist_background
    await mm.persist_background()

    # Task should be created
    assert mm._pending_persist_task is not None

    # Wait for task to complete
    await mm._pending_persist_task


@pytest.mark.asyncio
async def test_persist_background_deduplication():
    """persist_background cancels previous task before creating new one."""
    import asyncio

    mock_redis = MagicMock()

    # Simulate slow persist
    async def slow_persist(*args, **kwargs):
        await asyncio.sleep(10)

    mock_redis.set_session_data = slow_persist

    mm = MemoManager(session_id="dedup-test", redis_mgr=mock_redis)

    # Start first persist (will hang due to slow mock)
    await mm.persist_background()
    first_task = mm._pending_persist_task
    assert first_task is not None

    # Start second persist - should cancel first
    await mm.persist_background()
    second_task = mm._pending_persist_task

    # Let cancellation propagate
    await asyncio.sleep(0.01)

    # First task should be cancelled
    assert first_task.cancelled() or first_task.done()
    # Second task should be different
    assert second_task is not first_task

    # Cleanup
    mm.cancel_pending_persist()


@pytest.mark.asyncio
async def test_cancel_pending_persist_with_active_task():
    """cancel_pending_persist cancels an active task and returns True."""
    import asyncio

    mock_redis = MagicMock()

    async def slow_persist(*args, **kwargs):
        await asyncio.sleep(10)

    mock_redis.set_session_data = slow_persist

    mm = MemoManager(session_id="cancel-test", redis_mgr=mock_redis)

    # Start persist
    await mm.persist_background()
    task = mm._pending_persist_task
    assert task is not None
    assert not task.done()

    # Cancel should return True
    result = mm.cancel_pending_persist()
    assert result is True

    # Task should be cancelled
    await asyncio.sleep(0.01)  # Let cancellation propagate
    assert task.cancelled() or task.done()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
