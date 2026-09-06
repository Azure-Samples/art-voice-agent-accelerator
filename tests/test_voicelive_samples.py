"""Regression coverage for service-managed interruption in the VoiceLive samples."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from azure.ai.voicelive.models import ServerEventType


@pytest.fixture(params=["helloworld.py", "voicelive_multiagent/test.py"])
def sample_assistant(request, tmp_path, monkeypatch):
    sample_path = Path(__file__).resolve().parents[1] / "samples" / "voice_live_sdk" / request.param
    monkeypatch.chdir(tmp_path)
    with (
        patch("os.chdir"),
        patch("dotenv.load_dotenv"),
        patch("logging.basicConfig"),
        patch("logging.getLogger"),
        patch("logging.FileHandler"),
    ):
        sample = runpy.run_path(str(sample_path))

    assistant = sample["BasicVoiceAssistant"](
        endpoint="https://example.services.ai.azure.com",
        credential=Mock(),
        model="gpt-realtime",
        voice="en-US-AvaNeural",
        instructions="You are a helpful assistant.",
    )
    assistant.connection = SimpleNamespace(
        response=SimpleNamespace(cancel=AsyncMock()),
        session=SimpleNamespace(update=AsyncMock()),
    )
    assistant.audio_processor = Mock()
    return assistant


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preceding_events",
    [
        [],
        [ServerEventType.RESPONSE_CREATED],
        [ServerEventType.RESPONSE_CREATED, ServerEventType.RESPONSE_DONE],
    ],
    ids=["idle", "responding", "completed"],
)
async def test_speech_started_clears_playback_without_cancelling(sample_assistant, preceding_events):
    for event_type in preceding_events:
        await sample_assistant._handle_event(SimpleNamespace(type=event_type))

    await sample_assistant._handle_event(
        SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED)
    )

    sample_assistant.audio_processor.skip_pending_audio.assert_called_once_with()
    sample_assistant.connection.response.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_session_keeps_service_managed_interruption(sample_assistant):
    await sample_assistant._setup_session()

    session = sample_assistant.connection.session.update.call_args.kwargs["session"].as_dict()
    assert session["turn_detection"]["type"] == "server_vad"
    assert session["turn_detection"].get("interrupt_response", True) is True


@pytest.mark.asyncio
async def test_audio_is_still_queued_for_playback(sample_assistant):
    await sample_assistant._handle_event(
        SimpleNamespace(type=ServerEventType.RESPONSE_AUDIO_DELTA, delta=b"\x00\x00")
    )

    sample_assistant.audio_processor.queue_audio.assert_called_once_with(b"\x00\x00")


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Unexpected error", "Cancellation failed: no active response"])
async def test_server_errors_are_reported(sample_assistant, capsys, message):
    await sample_assistant._handle_event(
        SimpleNamespace(type=ServerEventType.ERROR, error=SimpleNamespace(message=message))
    )

    assert f"Error: {message}" in capsys.readouterr().out
