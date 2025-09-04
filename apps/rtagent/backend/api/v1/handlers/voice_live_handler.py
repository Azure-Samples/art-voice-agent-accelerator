"""
 Voice Live Handler
========================

A simplified handler for Azure AI Speech Live Voice API integration that follows
the media.py expected interface pattern with start() and stop() methods.

This implementation is based on the official Azure Voice Live quickstart pattern
and integrates with the existing media pipeline.
"""

import os
import uuid
import json
import asyncio
import base64
import logging
import threading
import time
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Union, Literal, Optional, Set, Callable, Awaitable
from typing_extensions import AsyncIterator, TypedDict, Required
from websockets.asyncio.client import connect as ws_connect
from websockets.asyncio.client import ClientConnection as AsyncWebsocket
from websockets.asyncio.client import HeadersLike
from websockets.typing import Data
from websockets.exceptions import WebSocketException
from azure.core.credentials_async import AsyncTokenCredential
from utils.azure_auth import get_credential
from utils.ml_logging import get_logger

logger = get_logger("api.v1.handlers.voice_live_handler")

AUDIO_SAMPLE_RATE = 24000
AudioTimestampTypes = Literal["word"]


class AzureDeepNoiseSuppression(TypedDict, total=False):
    type: Literal["azure_deep_noise_suppression"]


class ServerEchoCancellation(TypedDict, total=False):
    type: Literal["server_echo_cancellation"]


class AzureSemanticDetection(TypedDict, total=False):
    model: Literal["semantic_detection_v1"]
    threshold: float
    timeout: float


EOUDetection = AzureSemanticDetection


class AzureSemanticVAD(TypedDict, total=False):
    type: Literal["azure_semantic_vad"]
    end_of_utterance_detection: EOUDetection
    threshold: float
    silence_duration_ms: int
    prefix_padding_ms: int


class Animation(TypedDict, total=False):
    outputs: Set[Literal["blendshapes", "viseme_id", "emotion"]]


class Session(TypedDict, total=False):
    voice: Dict[str, Union[str, float]]
    turn_detection: Union[AzureSemanticVAD]
    input_audio_noise_reduction: AzureDeepNoiseSuppression
    input_audio_echo_cancellation: ServerEchoCancellation
    animation: Animation
    output_audio_timestamp_types: Set[AudioTimestampTypes]


class SessionUpdateEventParam(TypedDict, total=False):
    type: Literal["session.update"]
    session: Required[Session]
    event_id: str


class AsyncVoiceLiveSessionResource:
    def __init__(self, connection: "AsyncVoiceLiveConnection") -> None:
        self._connection = connection

    async def update(
        self,
        *,
        session: Session,
        event_id: str | None = None,
    ) -> None:
        param: SessionUpdateEventParam = {
            "type": "session.update",
            "session": session,
            "event_id": event_id or str(uuid.uuid4()),
        }
        data = json.dumps(param)
        await self._connection.send(data)


class AsyncVoiceLiveConnection:
    session: AsyncVoiceLiveSessionResource
    _connection: AsyncWebsocket

    def __init__(self, url: str, additional_headers: HeadersLike) -> None:
        self._url = url
        self._additional_headers = additional_headers
        self._connection = None
        self.session = AsyncVoiceLiveSessionResource(self)

    async def __aenter__(self) -> "AsyncVoiceLiveConnection":
        try:
            self._connection = await ws_connect(
                self._url, additional_headers=self._additional_headers
            )
        except WebSocketException as e:
            raise ValueError(f"Failed to establish a WebSocket connection: {e}")
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def __aiter__(self) -> AsyncIterator[Data]:
        async for data in self._connection:
            yield data

    async def recv(self) -> Data:
        return await self._connection.recv()

    async def send(self, message: Data) -> None:
        await self._connection.send(message)


class AsyncAzureVoiceLive:
    def __init__(
        self,
        *,
        azure_endpoint: str | None = None,
        api_version: str | None = "2025-05-01-preview",
        api_key: str | None = None,
        azure_ad_token_credential: AsyncTokenCredential | None = None,
    ) -> None:
        if azure_endpoint is None:
            azure_endpoint = os.environ.get("AZURE_VOICE_LIVE_ENDPOINT")

        if azure_endpoint is None:
            raise ValueError(
                "Must provide the 'azure_endpoint' argument, or the 'AZURE_VOICE_LIVE_ENDPOINT' environment variable"
            )

        if api_key is None and azure_ad_token_credential is None:
            api_key = os.environ.get("AZURE_VOICE_LIVE_API_KEY")

        if api_key is None and azure_ad_token_credential is None:
            azure_ad_token_credential = get_credential()

        if api_key and azure_ad_token_credential:
            raise ValueError(
                "Duplicating credentials. Please pass one of 'api_key' and 'azure_ad_token_credential'"
            )

        self._api_key = api_key
        self._azure_endpoint = azure_endpoint
        self._api_version = api_version
        self._azure_ad_token_credential = azure_ad_token_credential
        self._connection = None

    def get_token(self) -> str:
        if self._azure_ad_token_credential:
            scopes = "https://cognitiveservices.azure.com/.default"
            token = self._azure_ad_token_credential.get_token(scopes)
            return token.token
        else:
            return None

    async def connect(self, model: str) -> AsyncVoiceLiveConnection:
        if self._connection is not None:
            raise ValueError("Already connected to the Azure Voice Agent service.")
        if not model:
            raise ValueError("Model name is required.")
        if not isinstance(model, str):
            raise TypeError(
                f"The 'model' parameter must be of type 'str', but got {type(model).__name__}."
            )

        url = f"{self._azure_endpoint.rstrip('/')}/voice-agent/realtime?api-version={self._api_version}&model={model}"
        url = url.replace("https://", "wss://")

        auth_header = {}
        if self._azure_ad_token_credential:
            token = self.get_token()
            auth_header = {"Authorization": f"Bearer {token}"}
        elif self._api_key:
            auth_header = {"api-key": self._api_key}

        request_id = uuid.uuid4()
        headers = {"x-ms-client-request-id": str(request_id), **auth_header}

        self._connection = AsyncVoiceLiveConnection(
            url,
            additional_headers=headers,
        )
        return self._connection


class VoiceLiveHandler:
    """
    Simplified Voice Live handler following the media.py interface pattern.

    Provides start() and stop() methods as expected by the media pipeline,
    and manages Azure Voice Live API connections using the quickstart pattern.
    """

    def __init__(
        self,
        session_id: str,
        websocket,
        azure_endpoint: str,
        model_name: str = "gpt-4o-mini",
        orchestrator: Optional[Callable] = None,
    ):
        self.session_id = session_id
        self.websocket = websocket
        self.azure_endpoint = azure_endpoint
        self.model_name = model_name
        self.orchestrator = orchestrator

        # Connection state
        self.voice_live_client = None
        self.voice_live_connection = None
        self.is_running = False

        # Audio format configuration from metadata
        self.audio_format = "pcm"  # Default
        self.sample_rate = 16000  # Default
        self.channels = 1  # Default

        # Background tasks
        self.receive_task = None

        logger.info(f"VoiceLiveHandler initialized for session {session_id}")

    async def start(self) -> None:
        """
        Start the voice live handler.

        Expected by media.py - initializes Azure Voice Live connection and starts processing tasks.
        """
        try:
            logger.info(f"Starting voice live handler for session {self.session_id}")

            # Create Azure Voice Live client
            self.voice_live_client = AsyncAzureVoiceLive(
                azure_endpoint=self.azure_endpoint,
                azure_ad_token_credential=get_credential(),
            )

            # Connect to Azure Voice Live API
            self.voice_live_connection = await self.voice_live_client.connect(
                model=self.model_name
            )

            # Start connection
            logger.info(
                f"Establishing Azure Voice Live WebSocket connection for session {self.session_id}"
            )
            try:
                await self.voice_live_connection.__aenter__()
                logger.info(
                    f"Azure Voice Live WebSocket connection established for session {self.session_id}"
                )

                # Verify connection state
                if (
                    hasattr(self.voice_live_connection, "_connection")
                    and self.voice_live_connection._connection
                ):
                    logger.info(
                        f"WebSocket connection object verified for session {self.session_id}"
                    )
                else:
                    logger.warning(
                        f"WebSocket connection object not properly initialized for session {self.session_id}"
                    )

            except Exception as conn_error:
                logger.error(
                    f"Failed to establish Azure Voice Live connection for session {self.session_id}: {conn_error}"
                )
                raise

            # Configure session
            await self._configure_session()

            # Start background tasks
            self.is_running = True
            # Only start receive task - sending is handled by media.py loop calling handle_audio_data
            logger.info(f"Starting receive task for session {self.session_id}")
            self.receive_task = asyncio.create_task(self._receive_audio_loop())
            logger.info(f"Receive task started for session {self.session_id}")

            # Give the receive task a moment to start
            await asyncio.sleep(0.1)

            logger.info(
                f"Voice live handler started successfully for session {self.session_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to start voice live handler for session {self.session_id}: {e}"
            )
            await self.stop()
            raise

    async def stop(self) -> None:
        """
        Stop the voice live handler.

        Expected by media.py - cleans up connections and stops processing tasks.
        """
        try:
            logger.info(f"Stopping voice live handler for session {self.session_id}")

            # Stop processing
            self.is_running = False

            # Cancel background tasks
            if self.receive_task and not self.receive_task.done():
                self.receive_task.cancel()
                try:
                    await self.receive_task
                except asyncio.CancelledError:
                    pass

            # Close Azure Voice Live connection
            if self.voice_live_connection:
                await self.voice_live_connection.__aexit__(None, None, None)
                self.voice_live_connection = None

            self.voice_live_client = None

            logger.info(
                f"Voice live handler stopped successfully for session {self.session_id}"
            )

        except Exception as e:
            logger.error(
                f"Error stopping voice live handler for session {self.session_id}: {e}"
            )

    async def handle_audio_data(self, message_data) -> None:
        """
        Handle incoming messages from the client.

        This method can be called by the media pipeline to send various message types to Azure Voice Live.
        Supports AudioData, AudioMetadata, and DTMF messages.

        IMPORTANT: This method must never block to avoid blocking the media processing loop.
        """
        # Basic communication tracking
        # if isinstance(message_data, str) and len(message_data) > 50:
        #     logger.info(f"📨 Session {self.session_id}: Received {len(message_data)} char message")

        if not self.is_running:
            logger.warning(
                f"Received message while handler not running in session {self.session_id}"
            )
            return

        if not self.voice_live_connection:
            logger.warning(
                f"Received message while voice live connection not available in session {self.session_id}"
            )
            return

        try:
            # Handle different input formats
            if isinstance(message_data, str):
                # Parse JSON message structure
                try:
                    message = json.loads(message_data)
                    message_kind = message.get("kind", "unknown")

                    # Track message types
                    if message_kind == "AudioData":
                        logger.info(f"Session {self.session_id}: Processing audio data")
                    elif message_kind == "AudioMetadata":
                        logger.info(
                            f"📋 Session {self.session_id}: Processing audio metadata"
                        )

                    # Use asyncio.create_task to ensure these don't block the main processing loop
                    if message_kind == "AudioData" and "audioData" in message:
                        asyncio.create_task(self._handle_audio_data_message(message))
                    elif message_kind == "AudioMetadata":
                        asyncio.create_task(
                            self._handle_audio_metadata_message(message)
                        )
                    elif message_kind == "DtmfTone" and "dtmfTone" in message:
                        asyncio.create_task(self._handle_dtmf_message(message))
                    else:
                        logger.warning(
                            f"Unknown message kind '{message_kind}' in session {self.session_id}"
                        )
                        return

                except json.JSONDecodeError:
                    # If it's not JSON, treat as raw text/data
                    logger.warning(
                        f"Failed to parse JSON message in session {self.session_id}"
                    )
                    return

            elif isinstance(message_data, bytes):
                # Handle raw audio bytes
                asyncio.create_task(self._handle_raw_audio_bytes(message_data))
            else:
                logger.warning(
                    f"Unsupported message_data type: {type(message_data)} in session {self.session_id}"
                )
                return

        except Exception as e:
            logger.error(f"Error handling message in session {self.session_id}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _handle_audio_data_message(self, message: dict) -> None:
        """Handle AudioData messages."""
        try:
            # Check connection state first
            if (
                not self.voice_live_connection
                or not self.voice_live_connection._connection
            ):
                logger.warning(
                    f"Voice Live connection not available for session {self.session_id}"
                )
                return

            # Check if connection is already closed
            if (
                hasattr(self.voice_live_connection._connection, "closed")
                and self.voice_live_connection._connection.closed
            ):
                logger.info(
                    f"Voice Live connection already closed for session {self.session_id}"
                )
                self.is_running = False
                return

            audio_data = message["audioData"]["data"]
            # The data is already base64 encoded
            audio_b64 = audio_data

            # DEBUG: Log audio data details
            try:
                audio_bytes = base64.b64decode(audio_b64)
                # Simple audio tracking
                logger.info(
                    f"Session {self.session_id}: Sending {len(audio_bytes)} byte audio chunk to Azure"
                )
            except Exception as decode_error:
                logger.warning(
                    f"[AUDIO DEBUG] Session {self.session_id}: Could not decode audio data for size calculation: {decode_error}"
                )

            # Send to Azure Voice Live API with better error handling
            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": audio_b64,
                "event_id": str(uuid.uuid4()),
            }

            try:
                await self.voice_live_connection.send(json.dumps(audio_event))
                logger.debug(
                    f"[AUDIO SEND] Session {self.session_id}: Successfully sent audio chunk to Azure Voice Live"
                )
            except Exception as send_error:
                error_msg = str(send_error).lower()

                # Handle normal WebSocket closure gracefully
                if (
                    "received 1000 (ok)" in error_msg
                    or "connectionclosedok" in error_msg
                ):
                    logger.info(
                        f"Azure Voice Live connection closed normally for session {self.session_id}"
                    )
                    self.is_running = False
                    return  # Don't raise exception for normal closure
                elif "close frame" in error_msg or "connectionclosed" in error_msg:
                    logger.warning(
                        f"Azure Voice Live connection closed unexpectedly for session {self.session_id}: {send_error}"
                    )
                    self.is_running = False
                    return  # Don't raise exception, just stop processing
                else:
                    logger.error(
                        f"WebSocket send error for session {self.session_id}: {send_error}"
                    )
                    raise send_error

        except KeyError as e:
            logger.error(
                f"Missing audio data in message for session {self.session_id}: {e}"
            )
        except Exception as e:
            logger.error(
                f"Error handling audio data message in session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _handle_audio_metadata_message(self, message: dict) -> None:
        """Handle AudioMetadata messages and extract audio format configuration."""
        try:
            start_time = asyncio.get_event_loop().time()
            logger.info(
                f"Received audio metadata in session {self.session_id}: {message}"
            )

            # Extract audio configuration from metadata payload
            payload = message.get("payload", {})
            if payload:
                self.audio_format = payload.get("format", "pcm")
                self.sample_rate = payload.get("rate", 16000)
                self.channels = payload.get("channels", 1)

                logger.info(
                    f"Updated audio config for session {self.session_id}: format={self.audio_format}, rate={self.sample_rate}, channels={self.channels}"
                )

            # Trigger greeting when call starts (metadata received)
            await self._send_greeting()

            end_time = asyncio.get_event_loop().time()
            processing_time = (end_time - start_time) * 1000  # Convert to milliseconds
            logger.info(
                f"Processed audio metadata for session {self.session_id} in {processing_time:.2f}ms"
            )

        except Exception as e:
            logger.error(
                f"Error handling audio metadata message in session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _send_greeting(self) -> None:
        """Send greeting message to Azure Voice Live to have the agent speak."""
        try:
            if (
                not self.voice_live_connection
                or not self.voice_live_connection._connection
            ):
                logger.warning(
                    f"Cannot send greeting - Voice Live connection not available for session {self.session_id}"
                )
                return

            # Check if connection is already closed
            if (
                hasattr(self.voice_live_connection._connection, "closed")
                and self.voice_live_connection._connection.closed
            ):
                logger.warning(
                    f"Cannot send greeting - Voice Live connection already closed for session {self.session_id}"
                )
                return

            # Get greeting from orchestrator if available
            greeting_text = "Hello! I'm your AI assistant. How can I help you today?"
            # if self.orchestrator:
            #     try:

            #         if greeting_response:
            #             greeting_text = greeting_response
            #     except Exception as e:
            #         logger.warning(f"Failed to get greeting from orchestrator for session {self.session_id}: {e}")

            # logger.info(f"[GREETING SEND] Session {self.session_id}: Sending greeting message to Azure Voice Live")

            # Send greeting message to Azure Voice Live
            greeting_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": greeting_text}],
                },
                "event_id": str(uuid.uuid4()),
            }

            await self.voice_live_connection.send(json.dumps(greeting_event))
            logger.info(
                f"[GREETING SENT] Session {self.session_id}: Successfully sent greeting: '{greeting_text}'"
            )

        except Exception as e:
            logger.error(f"Error sending greeting for session {self.session_id}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _handle_dtmf_message(self, message: dict) -> None:
        """Handle DTMF tone messages."""
        try:
            dtmf_data = message["dtmfTone"]
            tone = dtmf_data.get("tone")
            duration = dtmf_data.get("duration")

            logger.info(
                f"Received DTMF tone '{tone}' (duration: {duration}ms) in session {self.session_id}"
            )

            # Send DTMF information to Azure Voice Live API
            # This could be used for interactive voice response scenarios
            dtmf_event = {
                "type": "input_dtmf.append",
                "tone": tone,
                "duration": duration,
                "event_id": str(uuid.uuid4()),
            }

            await self.voice_live_connection.send(json.dumps(dtmf_event))

            # Also send to client via WebSocket for potential UI updates
            if self.websocket:
                client_message = {
                    "type": "dtmf",
                    "tone": tone,
                    "duration": duration,
                    "session_id": self.session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await self.websocket.send_text(json.dumps(client_message))

        except Exception as e:
            logger.error(
                f"Error handling DTMF message in session {self.session_id}: {e}"
            )

    async def _handle_raw_audio_bytes(self, audio_bytes: bytes) -> None:
        """Handle raw audio bytes."""
        try:
            # Check connection state first
            if (
                not self.voice_live_connection
                or not self.voice_live_connection._connection
            ):
                logger.warning(
                    f"Voice Live connection not available for raw audio in session {self.session_id}"
                )
                return

            # Check if connection is already closed
            if (
                hasattr(self.voice_live_connection._connection, "closed")
                and self.voice_live_connection._connection.closed
            ):
                logger.info(
                    f"Voice Live connection already closed for raw audio in session {self.session_id}"
                )
                self.is_running = False
                return

            # DEBUG: Log raw audio details
            logger.debug(
                f"[RAW AUDIO DEBUG] Session {self.session_id}: Received raw audio of {len(audio_bytes)} bytes"
            )

            # Calculate approximate duration for PCM audio
            bytes_per_sample = 2  # 16-bit PCM
            samples = len(audio_bytes) // bytes_per_sample
            duration_ms = (samples / self.sample_rate) * 1000
            logger.debug(
                f"[RAW AUDIO DEBUG] Session {self.session_id}: Raw audio duration ~{duration_ms:.1f}ms at {self.sample_rate}Hz"
            )

            # Convert raw audio bytes to base64
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            # Send to Azure Voice Live API
            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": audio_b64,
                "event_id": str(uuid.uuid4()),
            }

            try:
                await self.voice_live_connection.send(json.dumps(audio_event))
                logger.debug(
                    f"[RAW AUDIO SEND] Session {self.session_id}: Successfully sent raw audio to Azure Voice Live"
                )
            except Exception as send_error:
                error_msg = str(send_error).lower()

                # Handle normal WebSocket closure gracefully
                if (
                    "received 1000 (ok)" in error_msg
                    or "connectionclosedok" in error_msg
                ):
                    logger.info(
                        f"Azure Voice Live connection closed normally for raw audio in session {self.session_id}"
                    )
                    self.is_running = False
                    return  # Don't raise exception for normal closure
                elif "close frame" in error_msg or "connectionclosed" in error_msg:
                    logger.warning(
                        f"Azure Voice Live connection closed unexpectedly for raw audio in session {self.session_id}: {send_error}"
                    )
                    self.is_running = False
                    return  # Don't raise exception, just stop processing
                else:
                    logger.error(
                        f"WebSocket send error for raw audio in session {self.session_id}: {send_error}"
                    )
                    raise send_error

        except Exception as e:
            logger.error(
                f"Error handling raw audio bytes in session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _configure_session(self) -> None:
        """Configure the Azure Voice Live session."""
        try:
            self.system_prompt = (
                "Greet the user warmly and ask how you can assist them today."
            )
            session_config = {
                "modalities": ["text", "audio"],
                "instructions": self.system_prompt,
                "turn_detection": {
                    "type": "azure_semantic_vad",
                    "threshold": 0.3,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 500,
                    "end_of_utterance_detection": {
                        "model": "semantic_detection_v1",
                        "threshold": 0.01,
                        "timeout": 2,
                    },
                },
                "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
                "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
                "voice": {
                    "name": "en-US-Ava:DragonHDLatestNeural",
                    "type": "azure-standard",
                    "temperature": 0.8,
                },
                # Enable transcription to receive transcription.completed events
                "input_audio_transcription": {"model": "whisper-1"},
            }

            logger.info(
                f"Sending session configuration for {self.session_id}: {session_config}"
            )
            await self.voice_live_connection.session.update(session=session_config)
            logger.info(
                f"Session configuration sent successfully for {self.session_id}"
            )

        except Exception as e:
            logger.error(f"Failed to configure session {self.session_id}: {e}")
            raise

    async def _receive_audio_loop(self) -> None:
        """Background task to receive audio responses from Azure Voice Live."""
        logger.info(f"Starting receive audio loop for session {self.session_id}")
        try:
            async for raw_event in self.voice_live_connection:
                if not self.is_running:
                    logger.info(
                        f"Receive loop stopping - handler not running for session {self.session_id}"
                    )
                    break

                logger.debug(
                    f"Received event from Azure Voice Live for session {self.session_id}: {raw_event[:100]}..."
                )

                try:
                    event = json.loads(raw_event)
                    await self._handle_voice_live_event(event)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode event: {e}")
                except Exception as e:
                    logger.error(f"Error handling voice live event: {e}")

        except WebSocketException as e:
            logger.error(
                f"WebSocket error in receive loop for session {self.session_id}: {e}"
            )
        except Exception as e:
            logger.error(
                f"Error in receive audio loop for session {self.session_id}: {e}"
            )
        finally:
            logger.info(f"Receive audio loop ended for session {self.session_id}")

    async def _handle_voice_live_event(self, event: dict) -> None:
        """Handle events from Azure Voice Live API."""
        event_type = event.get("type", "")
        event_id = event.get("event_id", "unknown")

        logger.debug(
            f"[EVENT CALLBACK] Session {self.session_id}: Received '{event_type}' event (ID: {event_id})"
        )

        if event_type == "response.audio.delta":
            logger.debug(
                f"[AUDIO RESPONSE CALLBACK] Session {self.session_id}: Processing audio delta"
            )
            await self._handle_audio_response(event)
        elif event_type == "response.text.delta":
            text_delta = event.get("delta", "")
            logger.debug(
                f"[TEXT RESPONSE CALLBACK] Session {self.session_id}: Processing text delta: '{text_delta}'"
            )
            await self._handle_text_response(event)
        elif event_type == "input_audio_buffer.speech_started":
            logger.info(
                f"[SPEECH DETECTION] Session {self.session_id}: Speech started - user began speaking"
            )
        elif event_type == "input_audio_buffer.speech_stopped":
            logger.info(
                f"[SPEECH DETECTION] Session {self.session_id}: Speech stopped - user finished speaking"
            )
        elif event_type == "conversation.item.input_audio_transcription.completed":
            logger.debug(
                f"[TRANSCRIPTION CALLBACK] Session {self.session_id}: Processing transcription completion"
            )
            await self._handle_transcription_completed(event)
        elif event_type == "response.done":
            logger.info(
                f"[RESPONSE COMPLETE] Session {self.session_id}: Full response completed"
            )
        elif event_type == "session.created":
            logger.info(
                f"[SESSION EVENT] Session {self.session_id}: Session created successfully"
            )
        elif event_type == "session.updated":
            logger.info(
                f"[SESSION EVENT] Session {self.session_id}: Session configuration updated"
            )
        elif event_type == "conversation.item.created":
            logger.debug(
                f"[CONVERSATION EVENT] Session {self.session_id}: Conversation item created"
            )
        elif event_type == "input_audio_buffer.committed":
            logger.debug(
                f"[AUDIO BUFFER] Session {self.session_id}: Audio buffer committed"
            )
        elif event_type == "input_audio_buffer.cleared":
            logger.debug(
                f"[AUDIO BUFFER] Session {self.session_id}: Audio buffer cleared"
            )
        elif event_type == "response.created":
            logger.debug(
                f"[RESPONSE EVENT] Session {self.session_id}: Response generation started"
            )
        elif event_type == "response.output_item.added":
            logger.debug(
                f"[RESPONSE EVENT] Session {self.session_id}: Output item added to response"
            )
        elif event_type == "response.output_item.done":
            logger.debug(
                f"[RESPONSE EVENT] Session {self.session_id}: Output item completed"
            )
        elif event_type == "response.content_part.added":
            logger.debug(
                f"[RESPONSE EVENT] Session {self.session_id}: Content part added"
            )
        elif event_type == "response.content_part.done":
            logger.debug(
                f"[RESPONSE EVENT] Session {self.session_id}: Content part completed"
            )
        elif event_type == "response.audio_transcript.delta":
            transcript = event.get("delta", "")
            logger.debug(
                f"[AUDIO TRANSCRIPT] Session {self.session_id}: AI is saying: '{transcript}'"
            )
        elif event_type == "response.audio_transcript.done":
            logger.debug(
                f"[AUDIO TRANSCRIPT] Session {self.session_id}: AI transcript completed"
            )
        elif event_type == "error":
            logger.error(
                f"[ERROR EVENT] Session {self.session_id}: Processing error event"
            )
            await self._handle_error_event(event)
        else:
            logger.debug(
                f"[UNHANDLED EVENT] Session {self.session_id}: '{event_type}' - {json.dumps(event, indent=2) if logger.isEnabledFor(logging.DEBUG) else 'Enable DEBUG logging for full event details'}"
            )

    async def _handle_audio_response(self, event: dict) -> None:
        """Handle audio response from Azure Voice Live and format for ACS WebSocket."""
        try:
            audio_delta = event.get("delta", "")
            if audio_delta and self.websocket:
                # DEBUG: Log outgoing audio details
                try:
                    original_bytes = base64.b64decode(audio_delta)
                    logger.debug(
                        f"[AUDIO OUT] Session {self.session_id}: Received {len(original_bytes)} bytes from Azure Voice Live (24kHz)"
                    )
                except Exception:
                    logger.debug(
                        f"[AUDIO OUT] Session {self.session_id}: Received audio delta (decode failed for size calc)"
                    )

                # Resample audio from 24kHz (Azure Voice Live) to match ACS expected rate
                resampled_audio = await self._resample_audio_for_acs(audio_delta)

                # Format audio response in ACS-expected format
                acs_audio_message = {
                    "kind": "AudioData",
                    "audioData": {
                        "data": resampled_audio,  # Base64 encoded resampled audio data
                        "silent": False,  # Audio contains actual speech
                        "timestamp": time.time(),  # Unix timestamp
                    },
                }

                logger.debug(
                    f"[AUDIO OUT] Session {self.session_id}: Sending resampled audio to client WebSocket"
                )
                await self.websocket.send_text(json.dumps(acs_audio_message))

        except Exception as e:
            logger.error(
                f"Error handling audio response in session {self.session_id}: {e}"
            )

    async def _resample_audio_for_acs(self, audio_b64: str) -> str:
        """Resample audio from Azure Voice Live (24kHz) to ACS expected rate (16kHz)."""
        try:
            # Decode base64 audio data
            audio_bytes = base64.b64decode(audio_b64)

            # Azure Voice Live outputs 24kHz 16-bit PCM, ACS expects 16kHz
            source_rate = 24000
            target_rate = self.sample_rate  # From ACS metadata (16000)

            if source_rate == target_rate:
                # No resampling needed
                return audio_b64

            # Convert bytes to numpy array (16-bit PCM)
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

            #  resampling using numpy interpolation
            # Calculate the resampling ratio
            resample_ratio = target_rate / source_rate  # 16000/24000 = 0.667

            # Create new sample indices
            original_length = len(audio_np)
            new_length = int(original_length * resample_ratio)

            # Use linear interpolation to resample
            original_indices = np.arange(original_length)
            new_indices = np.linspace(0, original_length - 1, new_length)
            resampled_audio = np.interp(
                new_indices, original_indices, audio_np.astype(np.float32)
            )

            # Convert back to int16 and then to bytes
            resampled_int16 = resampled_audio.astype(np.int16)
            resampled_bytes = resampled_int16.tobytes()

            # Encode back to base64
            resampled_b64 = base64.b64encode(resampled_bytes).decode("utf-8")

            logger.debug(
                f"Resampled audio from {source_rate}Hz to {target_rate}Hz for session {self.session_id} "
                f"(original: {len(audio_bytes)} bytes, resampled: {len(resampled_bytes)} bytes)"
            )

            return resampled_b64

        except Exception as e:
            logger.error(f"Error resampling audio for session {self.session_id}: {e}")
            # Return original audio if resampling fails
            return audio_b64

    async def _handle_text_response(self, event: dict) -> None:
        """Handle text response from Azure Voice Live."""
        try:
            text_delta = event.get("delta", "")
            if text_delta and self.websocket:
                logger.info(
                    f"[AI TEXT RESPONSE] Session {self.session_id}: AI responding with text: '{text_delta}'"
                )

                # Format text response - could be used for transcription display
                # ACS might not expect this format, but useful for debugging
                text_message = {
                    "kind": "TextData",
                    "textData": {
                        "text": text_delta,
                        "role": "assistant",
                        "timestamp": time.time(),
                    },
                }

                logger.debug(
                    f"[TEXT OUT] Session {self.session_id}: Sending text response to client WebSocket"
                )
                await self.websocket.send_text(json.dumps(text_message))

        except Exception as e:
            logger.error(
                f"Error handling text response in session {self.session_id}: {e}"
            )

    async def _handle_error_event(self, event: dict) -> None:
        """Handle error events from Azure Voice Live."""
        error_details = event.get("error", {})
        error_type = error_details.get("type", "Unknown")
        error_message = error_details.get("message", "No message provided")

        logger.error(f"Azure Voice Live error: {error_type} - {error_message}")

        if self.websocket:
            # Format error in ACS-style structure
            error_msg = {
                "kind": "ErrorData",
                "errorData": {
                    "code": error_type,
                    "message": error_message,
                    "timestamp": time.time(),
                },
            }

            try:
                await self.websocket.send_text(json.dumps(error_msg))
            except Exception as e:
                logger.error(f"Failed to send error message to client: {e}")

    async def _handle_transcription_completed(self, event: dict) -> None:
        """Handle transcription completed events and route through orchestrator if available."""
        try:
            transcript_text = event.get("transcript", "")
            if not transcript_text:
                logger.warning(
                    f"[TRANSCRIPTION] Session {self.session_id}: Received transcription event with no text"
                )
                return

            # logger.info(f"[TRANSCRIPTION RECEIVED] Session {self.session_id}: User said: '{transcript_text}'")

            # DEBUG: Log full transcription event details
            logger.debug(
                f"[TRANSCRIPTION DEBUG] Session {self.session_id}: Full event data: {json.dumps(event, indent=2)}"
            )

            # # If orchestrator is available, route conversation through it
            # if self.orchestrator:
            #     await self._process_with_orchestrator(transcript_text)
            # else:
            #     # Log that we're using Azure Voice Live's built-in conversation handling
            #     logger.info(f"No orchestrator configured, using Azure Voice Live built-in conversation handling for session {self.session_id}")

        except Exception as e:
            logger.error(
                f"Error handling transcription completion in session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _process_with_orchestrator(self, user_message: str) -> None:
        """Process user message through the orchestrator and send response to Azure Voice Live."""
        try:
            logger.info(
                f"Processing message through orchestrator for session {self.session_id}: '{user_message}'"
            )

            # Get response from orchestrator
            try:
                # This depends on your orchestrator's interface - adjust as needed
                response = await self.orchestrator.process_message(
                    user_message, session_id=self.session_id
                )
                if not response:
                    logger.warning(
                        f"Orchestrator returned empty response for session {self.session_id}"
                    )
                    return

            except Exception as e:
                logger.error(
                    f"Error getting response from orchestrator for session {self.session_id}: {e}"
                )
                # Fall back to default response
                response = "I'm sorry, I'm having trouble processing your request right now. Please try again."

            # Send orchestrator response to Azure Voice Live for TTS
            await self._send_orchestrator_response(response)

        except Exception as e:
            logger.error(
                f"Error processing message with orchestrator in session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _send_orchestrator_response(self, response_text: str) -> None:
        """Send orchestrator response to Azure Voice Live for text-to-speech conversion."""
        try:
            if (
                not self.voice_live_connection
                or not self.voice_live_connection._connection
            ):
                logger.warning(
                    f"Cannot send orchestrator response - Voice Live connection not available for session {self.session_id}"
                )
                return

            # Check if connection is already closed
            if (
                hasattr(self.voice_live_connection._connection, "closed")
                and self.voice_live_connection._connection.closed
            ):
                logger.warning(
                    f"Cannot send orchestrator response - Voice Live connection already closed for session {self.session_id}"
                )
                return

            # Send response message to Azure Voice Live for TTS
            response_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": response_text}],
                },
                "event_id": str(uuid.uuid4()),
            }

            await self.voice_live_connection.send(json.dumps(response_event))
            logger.info(
                f"Sent orchestrator response to Azure Voice Live for session {self.session_id}: '{response_text}'"
            )

            # Also trigger response generation
            generate_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio"],
                    "instructions": "Please provide a natural, conversational response based on the assistant message.",
                },
                "event_id": str(uuid.uuid4()),
            }

            await self.voice_live_connection.send(json.dumps(generate_event))
            logger.info(
                f"Triggered response generation for orchestrator response in session {self.session_id}"
            )

        except Exception as e:
            logger.error(
                f"Error sending orchestrator response for session {self.session_id}: {e}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
