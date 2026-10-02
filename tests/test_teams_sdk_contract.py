"""Verify Teams support using the actual SDK serializer, with a network-free transport."""

import inspect
import json

import pytest
from azure.communication.callautomation import (
    AudioFormat,
    CallAutomationClient,
    MediaStreamingAudioChannelType,
    MediaStreamingContentType,
    MediaStreamingOptions,
    MicrosoftTeamsAppIdentifier,
    PhoneNumberIdentifier,
    StreamingTransportType,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.pipeline.transport import HttpTransport


class RequestCaptured(Exception):
    pass


class CaptureTransport(HttpTransport):
    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        self.body = json.loads(request.body)
        raise RequestCaptured()


def test_sdk_serializes_teams_source_without_standalone_caller_id():
    if "teams_app_source" not in inspect.signature(CallAutomationClient.create_call).parameters:
        pytest.skip("Teams requires a supported SDK; local SDK must expose teams_app_source")
    transport = CaptureTransport()
    client = CallAutomationClient(
        "https://example.communication.azure.com",
        AzureKeyCredential("YQ=="),
        transport=transport,
        retry_total=0,
    )
    with pytest.raises(RequestCaptured):
        client.create_call(
            target_participant=PhoneNumberIdentifier("+15551234567"),
            callback_url="https://example.invalid/callbacks",
            teams_app_source=MicrosoftTeamsAppIdentifier(
                "11111111-2222-3333-4444-555555555555"
            ),
            media_streaming=MediaStreamingOptions(
                transport_url="wss://example.invalid/media",
                transport_type=StreamingTransportType.WEBSOCKET,
                content_type=MediaStreamingContentType.AUDIO,
                audio_channel_type=MediaStreamingAudioChannelType.UNMIXED,
                enable_bidirectional=True,
                audio_format=AudioFormat.PCM16_K_MONO,
            ),
        )
    assert transport.body["teamsAppSource"]["appId"] == "11111111-2222-3333-4444-555555555555"
    assert "sourceCallerIdNumber" not in transport.body
    assert transport.body["mediaStreamingOptions"]["enableBidirectional"] is True
