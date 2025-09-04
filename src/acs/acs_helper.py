import asyncio
import logging
import os

from aiohttp import web
from azure.communication.callautomation import (
    AudioFormat,
    AzureBlobContainerRecordingStorage,
    CallAutomationClient,
    CallConnectionClient,
    MediaStreamingAudioChannelType,
    MediaStreamingContentType,
    MediaStreamingOptions,
    PhoneNumberIdentifier,
    RecordingChannel,
    RecordingContent,
    RecordingFormat,
    StreamingTransportType,
    TranscriptionOptions,
)
from azure.communication.identity import CommunicationIdentityClient
from azure.core.exceptions import HttpResponseError
from utils.azure_auth import get_credential, ManagedIdentityCredential
from azure.communication.callautomation import CallConnectionProperties
from datetime import datetime, timedelta

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from src.enums.stream_modes import StreamMode
from utils.ml_logging import get_logger

logger = get_logger("src.acs")
tracer = trace.get_tracer(__name__)


def _endpoint_host_from_client(client: CallAutomationClient) -> str:
    try:
        endpoint = getattr(getattr(client, "_config", None), "endpoint", None)
        if endpoint:
            return str(endpoint).replace("https://", "").replace("http://", "")
    except Exception:
        pass
    return "acs.communication.azure.com"


async def wait_for_call_connected(
    call_conn: CallConnectionClient,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.01,  # Poll every 10ms for low latency
) -> CallConnectionProperties:
    """
    Block until the call reaches the **Connected** state.
    """
    deadline = datetime.utcnow() + timedelta(seconds=timeout)

    while True:
        time = datetime.utcnow()
        logger.info("🕐 Waiting for call to connect...")
        try:
            props: CallConnectionProperties = call_conn.get_call_properties()
            state = str(props.call_connection_state).lower()

            if state == "connected":
                logger.info("☎️ Call %s is now connected", props.call_connection_id)
                return props

            if datetime.utcnow() >= deadline:
                raise TimeoutError(
                    f"Call {props.call_connection_id} not connected after {timeout}s."
                )

        except Exception as e:
            logger.warning(f"Error getting call properties: {e}")
            if datetime.utcnow() >= deadline:
                raise TimeoutError(
                    f"Call not connected after {timeout}s due to errors."
                )

        time_end = datetime.utcnow() - time
        logger.info(f"🕐 Waited {time_end.total_seconds()}s for call to connect...")
        await asyncio.sleep(poll_interval)


class AcsCaller:
    """
    Azure Communication Services call automation helper.
    """

    def __init__(
        self,
        source_number: str,
        callback_url: str,
        recording_callback_url: str = None,
        websocket_url: str = None,
        acs_connection_string: str = None,
        acs_endpoint: str = None,
        cognitive_services_endpoint: str = None,
        speech_recognition_model_endpoint_id: str = None,
        recording_configuration: dict = None,
        recording_storage_container_url: str = None,
    ):
        # Required
        if not (acs_connection_string or acs_endpoint):
            raise ValueError("Provide either acs_connection_string or acs_endpoint")

        if not source_number:
            raise ValueError(
                "No source_number provided. You must purchase and configure an Azure Communication Services phone number. "
                "Set the number in your environment as ACS_SOURCE_PHONE_NUMBER. "
                "See: https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/telephony/get-phone-number?tabs=windows&pivots=platform-azcli"
            )
        self.source_number = source_number
        self.callback_url = callback_url
        self.cognitive_services_endpoint = cognitive_services_endpoint
        self.speech_recognition_model_endpoint_id = speech_recognition_model_endpoint_id

        # Recording Settings
        if not recording_callback_url:
            recording_callback_url = callback_url
        self.recording_callback_url = recording_callback_url
        self.recording_configuration = recording_configuration or {}
        self.recording_storage_container_url = recording_storage_container_url

        # Live Transcription Settings (ACS <--> STT/TTS)
        self.transcription_opts = (
            TranscriptionOptions(
                transport_url=websocket_url,
                transport_type=StreamingTransportType.WEBSOCKET,
                locale="en-US",
                start_transcription=True,
                enable_intermediate_results=True,
            )
            if websocket_url
            else None
        )

        self.media_streaming_options = MediaStreamingOptions(
            transport_url=websocket_url,
            transport_type=StreamingTransportType.WEBSOCKET,
            content_type=MediaStreamingContentType.AUDIO,
            audio_channel_type=MediaStreamingAudioChannelType.UNMIXED,
            start_media_streaming=True,
            enable_bidirectional=True,
            enable_dtmf_tones=True,
            audio_format=AudioFormat.PCM16_K_MONO,  # Ensure this matches what your STT expects
        )

        # Initialize ACS client with proper authentication
        try:
            if acs_connection_string:
                logger.info("Using ACS connection string for authentication")
                self.client = CallAutomationClient.from_connection_string(
                    acs_connection_string
                )
            else:
                if not acs_endpoint:
                    raise ValueError(
                        "acs_endpoint is required when not using connection string"
                    )

                logger.info("Using managed identity for ACS authentication")

                # No need to create tokens via CommunicationIdentityClient
                if "AZURE_CLIENT_ID" in os.environ:
                    credentials = self._create_identity_and_get_token(acs_endpoint)
                else:
                    # Use system-assigned managed identity
                    credentials = get_credential()

                self.client = CallAutomationClient(
                    endpoint=acs_endpoint, credential=credentials
                )

        except Exception as e:
            logger.error(f"Failed to initialize ACS client: {e}")
            if "managed identity" in str(
                e
            ).lower() or "CredentialUnavailableError" in str(e):
                logger.error("Managed identity is not available in this environment.")
                logger.error("Either:")
                logger.error("1. Use ACS_CONNECTION_STRING instead of managed identity")
                logger.error(
                    "2. Ensure managed identity is enabled for this App Service"
                )
                logger.error(
                    "3. Set AZURE_CLIENT_ID if using user-assigned managed identity"
                )
            raise

        # Validate configuration
        self._validate_configuration(websocket_url, acs_connection_string, acs_endpoint)
        logger.info("AcsCaller initialized")

    def _create_identity_and_get_token(self, resource_endpoint):
        client = CommunicationIdentityClient(resource_endpoint, get_credential())

        user = client.create_user()
        token_response = client.get_token(user, scopes=["voip"])

        return token_response

    def _validate_configuration(
        self, websocket_url: str, acs_connection_string: str, acs_endpoint: str
    ):
        """Validate configuration and log warnings for common misconfigurations."""
        # Log configuration status
        if websocket_url:
            logger.info(f"Transcription transport_url (WebSocket): {websocket_url}")
        else:
            logger.warning("No websocket_url provided for transcription transport")

        if not self.source_number:
            logger.warning("ACS source_number is not set")

        if not self.callback_url:
            logger.warning("ACS callback_url is not set")

        if not (acs_connection_string or acs_endpoint):
            logger.warning("Neither ACS connection string nor endpoint is set")

        if not self.cognitive_services_endpoint:
            logger.warning(
                "No cognitive_services_endpoint provided (TTS/STT may not work)"
            )

        if not self.recording_storage_container_url:
            logger.warning(
                "No recording_storage_container_url provided (recordings may not be saved)"
            )

    async def initiate_call(
        self, target_number: str, stream_mode: StreamMode = StreamMode.MEDIA
    ) -> dict:
        """Start a new call with live transcription over websocket."""
        call = self.client
        src = PhoneNumberIdentifier(self.source_number)
        dest = PhoneNumberIdentifier(target_number)

        try:
            logger.info(f"Initiating call from {self.source_number} to {target_number}")
            logger.debug(f"Stream mode: {stream_mode}")
            logger.debug(f"Transcription options: {self.transcription_opts}")
            logger.debug(f"Media streaming options: {self.media_streaming_options}")
            logger.debug(
                f"Cognitive services endpoint: {self.cognitive_services_endpoint}"
            )
            logger.debug(f"Callback URL: {self.callback_url}")

            # Determine which capabilities to enable based on stream_mode
            transcription = None
            cognitive_services_endpoint = None
            media_streaming = None

            if stream_mode == StreamMode.TRANSCRIPTION:
                transcription = self.transcription_opts
                cognitive_services_endpoint = self.cognitive_services_endpoint

            if stream_mode == StreamMode.MEDIA or stream_mode == StreamMode.VOICE_LIVE:
                media_streaming = self.media_streaming_options

            # Default to transcription if no valid mode specified
            if stream_mode not in [
                StreamMode.TRANSCRIPTION,
                StreamMode.MEDIA,
                StreamMode.VOICE_LIVE,
            ]:
                logger.warning(
                    f"Invalid stream_mode '{stream_mode}', defaulting to transcription"
                )
                transcription = self.transcription_opts

            logger.debug(
                "Creating call to %s via callback %s", target_number, self.callback_url
            )

            endpoint_host = _endpoint_host_from_client(call)
            with tracer.start_as_current_span(
                "Azure.Communication.CallAutomation.CreateCall",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "azure-communication-services",
                    "net.peer.name": endpoint_host,
                },
            ):
                result = call.create_call(
                    target_participant=dest,
                    source_caller_id_number=src,
                    callback_url=self.callback_url,
                    cognitive_services_endpoint=cognitive_services_endpoint,
                    transcription=transcription,
                    media_streaming=media_streaming,
                )

            logger.info("Call created: %s", result.call_connection_id)
            return {"status": "created", "call_id": result.call_connection_id}

        except HttpResponseError as e:
            logger.error("ACS call failed [%s]: %s", e.status_code, e.message)
            raise
        except Exception:
            logger.exception("Unexpected error in initiate_call")
            raise

    async def answer_incoming_call(
        self,
        incoming_call_context: str,
        redis_mgr=None,
        stream_mode: StreamMode = StreamMode.MEDIA,
    ) -> object:
        """
        Answer an incoming call and set up live transcription.
        """
        try:
            logger.debug(f"Answering incoming call: {incoming_call_context}")
            transcription = None
            cognitive_services_endpoint = None
            media_streaming = None

            if stream_mode == StreamMode.TRANSCRIPTION:
                transcription = self.transcription_opts
                cognitive_services_endpoint = self.cognitive_services_endpoint

            if stream_mode == StreamMode.MEDIA or stream_mode == StreamMode.VOICE_LIVE:
                media_streaming = self.media_streaming_options

            # Default to transcription if no valid mode specified
            if stream_mode not in [
                StreamMode.TRANSCRIPTION,
                StreamMode.MEDIA,
                StreamMode.VOICE_LIVE,
            ]:
                logger.warning(
                    f"Invalid stream_mode '{stream_mode}', defaulting to transcription"
                )
                transcription = self.transcription_opts

            endpoint_host = _endpoint_host_from_client(self.client)
            with tracer.start_as_current_span(
                "Azure.Communication.CallAutomation.AnswerCall",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "azure-communication-services",
                    "net.peer.name": endpoint_host,
                },
            ):
                result = self.client.answer_call(
                    incoming_call_context=incoming_call_context,
                    callback_url=self.callback_url,
                    cognitive_services_endpoint=cognitive_services_endpoint,
                    transcription=transcription,
                    media_streaming=media_streaming,
                )

            logger.info(f"Incoming call answered: {result.call_connection_id}")
            return result

        except HttpResponseError as e:
            logger.error(
                f"Failed to answer call [status: {e.status_code}]: {e.message}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error answering call: {e}", exc_info=True)
            raise

    def get_call_connection(self, call_connection_id: str) -> CallConnectionClient:
        """
        Retrieve the CallConnectionClient for the given call_connection_id.
        """
        try:
            return self.client.get_call_connection(call_connection_id)
        except Exception as e:
            logger.error(f"Error retrieving CallConnectionClient: {e}", exc_info=True)
            return None

    def start_recording(self, server_call_id: str):
        """
        Start recording the call.
        """
        try:
            endpoint_host = _endpoint_host_from_client(self.client)
            with tracer.start_as_current_span(
                "Azure.Communication.CallAutomation.StartRecording",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "azure-communication-services",
                    "net.peer.name": endpoint_host,
                },
            ):
                self.client.start_recording(
                    server_call_id=server_call_id,
                    recording_state_callback_url=self.recording_callback_url,
                    recording_content_type=RecordingContent.AUDIO,
                    recording_channel_type=RecordingChannel.UNMIXED,
                    recording_format_type=RecordingFormat.WAV,
                    recording_storage=AzureBlobContainerRecordingStorage(
                        container_url=self.recording_storage_container_url,
                    ),
                )
            logger.info(f"Started recording for call {server_call_id}")
        except Exception as e:
            logger.error(f"Error starting recording for call {server_call_id}: {e}")

    def stop_recording(self, server_call_id: str):
        """
        Stop recording the call.
        """
        try:
            endpoint_host = _endpoint_host_from_client(self.client)
            with tracer.start_as_current_span(
                "Azure.Communication.CallAutomation.StopRecording",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "azure-communication-services",
                    "net.peer.name": endpoint_host,
                },
            ):
                self.client.stop_recording(server_call_id=server_call_id)
            logger.info(f"Stopped recording for call {server_call_id}")
        except Exception as e:
            logger.error(f"Error stopping recording for call {server_call_id}: {e}")
