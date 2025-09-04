# apps/rtagent/backend/src/lva/base.py
from __future__ import annotations

import base64
import json
import os
import time
import uuid
import queue
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from utils.ml_logging import get_logger

# Load environment variables from .env file
load_dotenv()

from .transport import WebSocketTransport
from .audio_io import MicSource, SpeakerSink, pcm_to_base64

logger = get_logger(__name__)

# ── SIMPLIFIED CONFIGURATION MATCHING WORKING NOTEBOOK ──────────────────────────────
DEFAULT_API_VERSION: str = "2025-05-01-preview"
DEFAULT_SAMPLE_RATE_HZ = 24_000
DEFAULT_CHUNK_MS = 20


@dataclass(frozen=True)
class LvaModel:
    """
    Model configuration for Azure Voice Live API.
    
    :param deployment_id: Voice Live model deployment (e.g., 'gpt-4o', 'gpt-4o-realtime-preview').
    """
    deployment_id: str


@dataclass(frozen=True)
class LvaAgentBinding:
    """
    Agent Service binding configuration.
    
    :param agent_id: Azure AI Agent ID to bind the session to.
    :param project_name: Project name (required for agent connections).
    """
    agent_id: str
    project_name: str


@dataclass(frozen=True)
class LvaSessionCfg:
    """
    Voice/VAD/noise/echo configuration applied via session.update.
    
    :param voice_name: TTS voice name.
    :param voice_temperature: Voice randomness (0.0-1.0).
    :param vad_threshold: VAD sensitivity (0.0-1.0).
    :param vad_prefix_ms: VAD prefix padding (ms).
    :param vad_silence_ms: VAD silence duration (ms).
    """
    voice_name: str = "en-US-Ava:DragonHDLatestNeural"
    voice_temperature: float = 0.8
    vad_threshold: float = 0.5
    vad_prefix_ms: int = 300
    vad_silence_ms: int = 1000


class AzureLiveVoiceAgent:
    """
    Live Voice Agent using Azure Voice Live API with Azure AI Agent Service.
    
    This implementation follows the working pattern from the notebook that successfully
    connects to Azure Voice Live API using simplified authentication and agent binding.
    
    Key features:
    - Simplified authentication with token fallback to API key
    - Direct agent binding via environment variables
    - Real-time audio processing with proper session management
    """

    def __init__(
        self,
        *,
        model: LvaModel,
        binding: LvaAgentBinding,
        session: Optional[LvaSessionCfg] = None,
    ) -> None:
        """
        Initialize Azure Live Voice Agent with simplified configuration.
        
        This follows the working pattern from the notebook that successfully authenticates
        and connects to Azure Voice Live API.
        
        Args:
            model: Model configuration (deployment_id)
            binding: Agent binding configuration (agent_id, project_name)
            session: Optional session configuration for voice/VAD settings
        """
        self._model = model
        self._binding = binding
        self._session = session or LvaSessionCfg()
        
        # Get configuration from environment (matching your .env file)
        self._endpoint = os.getenv("AZURE_VOICE_LIVE_ENDPOINT")
        self._api_key = os.getenv("AZURE_VOICE_LIVE_API_KEY")
        self._api_version = os.getenv("AZURE_VOICE_LIVE_API_VERSION", DEFAULT_API_VERSION)
        
        if not self._endpoint:
            raise ValueError("AZURE_VOICE_LIVE_ENDPOINT environment variable is required")
        
        # Setup authentication - prefer token with API key fallback (matches notebook pattern)
        self._auth_method = None
        
        # Try token-based authentication first
        try:
            credential = DefaultAzureCredential()
            token = credential.get_token("https://ai.azure.com/.default")
            self._auth_headers = {
                "Authorization": f"Bearer {token.token}",
                "x-ms-client-request-id": str(uuid.uuid4())
            }
            self._auth_method = "token"
            logger.info("Using token-based authentication")
        except Exception as e:
            logger.warning(f"Token authentication failed: {e}")
            if self._api_key:
                self._auth_headers = {
                    "api-key": self._api_key,
                    "x-ms-client-request-id": str(uuid.uuid4())
                }
                self._auth_method = "api_key"
                logger.info("Using API key authentication")
            else:
                raise ValueError("Both token authentication failed and AZURE_VOICE_LIVE_API_KEY is not set")
        
        # Build WebSocket URL (matches working notebook pattern)
        azure_ws_endpoint = self._endpoint.rstrip('/').replace("https://", "wss://")
        
        # Get additional authentication token for agent access
        try:
            agent_token = credential.get_token("https://ai.azure.com/.default")
        except Exception as e:
            logger.warning(f"Failed to get agent token: {e}")
            # Fallback to the same voice token
            agent_token = token
        
        # Agent connection URL with project name, agent ID, and agent access token
        self._url = (
            f"{azure_ws_endpoint}/voice-live/realtime"
            f"?api-version={self._api_version}"
            f"&agent-project-name={self._binding.project_name}"
            f"&agent-id={self._binding.agent_id}"
            f"&agent-access-token={agent_token.token}"
        )
        
        logger.info(f"Azure Live Voice Agent initialized")
        logger.info(f"  - Endpoint: {self._endpoint}")
        logger.info(f"  - Model: {self._model.deployment_id}")
        logger.info(f"  - Authentication: {self._auth_method}")
        logger.info(f"  - Agent ID: {self._binding.agent_id}")
        logger.info(f"  - Project: {self._binding.project_name}")
        
        # Initialize WebSocket transport
        self._ws = WebSocketTransport(self._url, self._auth_headers)
        
        # Audio I/O setup
        self._src = MicSource(sample_rate=DEFAULT_SAMPLE_RATE_HZ)
        self._sink = SpeakerSink(sample_rate=DEFAULT_SAMPLE_RATE_HZ)
        self._frames = int(DEFAULT_SAMPLE_RATE_HZ * (DEFAULT_CHUNK_MS / 1000))

    def _session_update(self) -> Dict[str, Any]:
        """
        Build session.update configuration for Azure Voice Live API.
        
        This matches the working pattern from the notebook with proper voice,
        VAD, noise reduction, and echo cancellation settings.
        
        Returns:
            Dict containing session.update payload
        """
        return {
            "type": "session.update",
            "session": {
                # Turn detection (VAD) configuration
                "turn_detection": {
                    "type": "azure_semantic_vad",
                    "threshold": self._session.vad_threshold,
                    "prefix_padding_ms": self._session.vad_prefix_ms,
                    "silence_duration_ms": self._session.vad_silence_ms,
                },
                
                # Audio input configuration
                "input_audio_format": "pcm16",
                "input_audio_noise_reduction": {
                    "type": "azure_deep_noise_suppression"
                },
                "input_audio_echo_cancellation": {
                    "type": "server_echo_cancellation"
                },
                
                # Audio output configuration  
                "output_audio_format": "pcm16",
                
                # Voice configuration
                "voice": {
                    "name": self._session.voice_name,
                    "type": "azure-standard",
                    "temperature": self._session.voice_temperature,
                },
            },
            "event_id": str(uuid.uuid4())
        }

    def _handle_event(self, raw: str) -> None:
        """
        Handle Voice Live events with simplified processing.
        
        This follows the working notebook pattern for event handling.
        
        Args:
            raw: Raw JSON event string from WebSocket
        """
        try:
            evt = json.loads(raw)
        except Exception:
            logger.exception("Event parse failed")
            return

        event_type = evt.get("type", "")
        
        # Session events
        if event_type == "session.created":
            session_id = evt.get("session", {}).get("id", "")
            logger.info(f"Session created: {session_id}")
            
        elif event_type == "session.updated":
            logger.info("Session configuration updated")
            
        # Audio events
        elif event_type == "response.audio.delta":
            try:
                delta = evt.get("delta", "")
                if delta:
                    audio_bytes = base64.b64decode(delta)
                    self._sink.write(audio_bytes)
            except Exception as e:
                logger.warning(f"Audio delta processing failed: {e}")
                
        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = evt.get("transcript", "")
            if transcript:
                logger.info(f"User said: {transcript}")
                
        elif event_type == "response.audio_transcript.done":
            transcript = evt.get("transcript", "")
            if transcript:
                logger.info(f"Agent said: {transcript}")
                
        # Error events
        elif event_type == "error":
            error_info = evt.get("error", {})
            error_type = error_info.get("type", "unknown")
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Voice Live API error [{error_type}]: {error_message}")
            
        else:
            # Log other events for debugging
            logger.debug(f"Received event: {event_type}")

    def connect(self) -> None:
        """
        Connect to Azure Voice Live API WebSocket.
        
        This establishes the connection and sends the initial session configuration.
        """
        try:
            self._ws.connect()
            logger.info("Connected to Azure Voice Live API")
            
            # Send session configuration
            session_config = self._session_update()
            self._ws.send_dict(session_config)
            logger.info("Session configuration sent")
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    def run(self) -> None:
        """
        Start the main audio streaming loop.
        
        This connects to the service, starts audio I/O, and handles real-time
        bidirectional audio streaming with proper event processing.
        """
        try:
            # Connect to the service
            self.connect()
            
            # Start audio I/O
            self._src.start()
            self._sink.start()
            
            logger.info("Starting audio streaming loop")
            
            try:
                while True:
                    # Send microphone audio to the service
                    pcm = self._src.read(self._frames)
                    if pcm is not None and len(pcm) > 0:
                        audio_message = {
                            "type": "input_audio_buffer.append",
                            "audio": pcm_to_base64(pcm),
                            "event_id": str(uuid.uuid4())
                        }
                        self._ws.send_dict(audio_message)
                    
                    # Process incoming events (non-blocking)
                    raw_event = self._ws.recv(timeout_s=0.01)
                    if raw_event:
                        self._handle_event(raw_event)
                        
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
            except Exception as e:
                logger.exception(f"Audio streaming loop failed: {e}")
                raise
                
        finally:
            # Cleanup
            try:
                self._src.stop()
                self._sink.stop()
                self._ws.close()
                logger.info("Audio streaming stopped and connections closed")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")

    def send_text(self, text: str) -> None:
        """
        Send a text message to the agent.
        
        Args:
            text: Text message to send
        """
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}]
            },
            "event_id": str(uuid.uuid4())
        }
        self._ws.send_dict(message)
        logger.info(f"Sent text message: {text}")

    def close(self) -> None:
        """Close the connection and cleanup resources."""
        try:
            self._src.stop()
            self._sink.stop()
            self._ws.close()
            logger.info("Azure Live Voice Agent connection closed")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    @property
    def url(self) -> str:
        """Get the WebSocket URL for debugging."""
        return self._url
    
    @property 
    def auth_method(self) -> str:
        """Get the authentication method used."""
        return self._auth_method or "unknown"
