"""
Azure Speech Recognition Module for Real-Time Voice Processing.

This module provides comprehensive streaming speech recognition capabilities using
the Azure Cognitive Services Speech SDK. It supports real-time audio processing
with advanced features including language detection, speaker diarization, and
neural audio processing for optimal voice agent performance.
It integrates with OpenTelemetry for observability, enabling detailed tracing and monitoring of the speech recognition process.
"""

import json
import os
from typing import Callable, List, Optional, Final

import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# OpenTelemetry imports for tracing
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Import centralized span attributes enum
from src.enums.monitoring import SpanAttr
from src.speech.auth_manager import SpeechTokenManager, get_speech_token_manager
from utils.ml_logging import get_logger

# Set up logger
logger = get_logger(__name__)

# Load environment variables from .env file
load_dotenv()


class StreamingSpeechRecognizerFromBytes:
    """
    Real-time streaming speech recognizer using Azure Speech SDK with advanced features.

    A comprehensive speech recognition engine that processes audio bytes in real-time
    using Azure Cognitive Services Speech SDK. Provides advanced features including
    automatic language detection, speaker diarization, neural audio processing,
    and comprehensive observability through OpenTelemetry tracing.

    This class is optimized for voice agent applications requiring low-latency
    speech recognition with high accuracy and advanced audio processing capabilities.

    Features:
        - Real-time streaming from PushAudioInputStream
        - Multi-format audio support (PCM, WebM, MP3, OGG)
        - Automatic language detection with configurable candidates
        - Speaker diarization for multi-speaker conversations
        - Neural audio front-end (noise suppression, AEC, AGC)
        - Voice activity detection with configurable timeouts
        - Semantic segmentation for improved sentence boundaries
        - Comprehensive error handling and recovery
        - OpenTelemetry tracing with Azure Monitor integration
        - Flexible authentication (API key or Default Credentials)

    Authentication Options:
        1. API Key: Traditional subscription key authentication
        2. Azure Default Credentials: Managed identity, service principal,
           or developer credentials for secure, keyless authentication

    Audio Processing Pipeline:
        1. Audio bytes written to PushAudioInputStream
        2. Optional neural front-end processing (noise reduction)
        3. Real-time speech recognition with language detection
        4. Optional speaker diarization for multi-speaker scenarios
        5. Continuous callbacks for partial and final results

    Observability:
        - Session-level spans for complete recognition sessions
        - Event tracking for audio chunks and recognition results
        - Application Map visualization as external service dependency
        - Call correlation across distributed voice agent components
        - Performance metrics and error tracking

    Attributes:
        key (Optional[str]): Azure Speech API key for authentication
        region (str): Azure region for Speech services
        candidate_languages (List[str]): Languages for auto-detection
        vad_silence_timeout_ms (int): Voice activity detection timeout
        audio_format (str): Audio format ("pcm" or "any")
        use_semantic (bool): Enable semantic segmentation
        call_connection_id (str): Call identifier for correlation
        enable_tracing (bool): Enable OpenTelemetry tracing

    Example:
        ```python
        # Initialize with comprehensive configuration
        recognizer = StreamingSpeechRecognizerFromBytes(
            key="your-speech-key",  # or None for Default Credentials
            region="eastus",
            candidate_languages=["en-US", "es-ES", "fr-FR"],
            vad_silence_timeout_ms=1000,
            audio_format="pcm",
            enable_neural_fe=True,
            enable_diarisation=True,
            speaker_count_hint=2,
            call_connection_id="call_123",
            enable_tracing=True
        )

        # Set up event callbacks
        def handle_partial(text, language, speaker_id):
            print(f"Partial ({language}): {text}")

        def handle_final(text, language, speaker_id):
            print(f"Final ({language}): {text}")

        recognizer.set_partial_result_callback(handle_partial)
        recognizer.set_final_result_callback(handle_final)

        # Start recognition session
        recognizer.start()

        # Process real-time audio stream
        try:
            for audio_chunk in audio_stream:
                recognizer.write_bytes(audio_chunk)
        finally:
            recognizer.stop()
            recognizer.close_stream()
        ```

    Note:
        For production deployments, Azure Default Credentials with managed
        identity is recommended over API keys for enhanced security.

    Raises:
        ValueError: If required configuration is missing or invalid
        Exception: If Azure authentication fails or Speech SDK errors occur
    """

    _DEFAULT_LANGS: Final[List[str]] = [
        "en-US",
        "es-ES",
        "fr-FR",
        "de-DE",
        "it-IT",
    ]

    def __init__(
        self,
        *,
        key: Optional[str] = None,
        region: Optional[str] = None,
        # Behaviour -----------------------------------------------------
        candidate_languages: List[str] | None = None,
        vad_silence_timeout_ms: int = 800,
        use_semantic_segmentation: bool = True,
        audio_format: str = "pcm",  # "pcm" | "any"
        # Advanced features --------------------------------------------
        enable_neural_fe: bool = False,
        enable_diarisation: bool = True,
        speaker_count_hint: int = 2,
        # Observability -------------------------------------------------
        call_connection_id: str | None = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize the streaming speech recognizer with comprehensive configuration.

        Creates a new speech recognizer instance with advanced audio processing
        capabilities, authentication options, and observability features for
        real-time voice agent applications.

        Args:
            key (Optional[str]): Azure Speech Services API key. If None, uses
                Azure Default Credentials (managed identity, service principal).
                For production, Default Credentials are recommended.
            region (Optional[str]): Azure region for Speech services (e.g., "eastus").
                Required for both API key and credential authentication.

        Behavior Configuration:
            candidate_languages (Optional[List[str]]): Languages for automatic
                detection. Defaults to ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"].
                More languages may impact recognition latency.
            vad_silence_timeout_ms (int): Voice activity detection silence timeout
                in milliseconds before finalizing recognition. Default: 800ms.
                Lower values = faster response, higher values = better accuracy.
            use_semantic_segmentation (bool): Enable semantic segmentation for
                improved sentence boundary detection. Default: True.
            audio_format (str): Audio input format. Options:
                - "pcm": Raw PCM 16kHz 16-bit mono audio
                - "any": Compressed formats (WebM, MP3, OGG) via GStreamer

        Advanced Features:
            enable_neural_fe (bool): Enable neural audio front-end processing
                including noise suppression, acoustic echo cancellation, and
                automatic gain control. Default: False. May increase latency.
            enable_diarisation (bool): Enable speaker diarization to identify
                different speakers in multi-speaker conversations. Default: True.
            speaker_count_hint (int): Hint for expected number of speakers
                (1-16). Helps optimize diarization accuracy. Default: 2.

        Observability:
            call_connection_id (Optional[str]): Unique identifier for call
                correlation in tracing and logging. If None, uses "unknown".
            enable_tracing (bool): Enable OpenTelemetry tracing with Azure
                Monitor integration for performance monitoring. Default: True.

        Attributes Initialized:
            - Authentication configuration and credentials
            - Audio processing parameters and feature flags
            - Callback handlers for recognition events
            - OpenTelemetry tracer for observability
            - Azure Speech SDK configuration

        Example:
            ```python
            # Production configuration with Default Credentials
            recognizer = StreamingSpeechRecognizerFromBytes(
                region="eastus",
                candidate_languages=["en-US", "es-ES"],
                vad_silence_timeout_ms=1000,
                enable_neural_fe=True,
                enable_diarisation=True,
                call_connection_id="call_abc123"
            )

            # Development configuration with API key
            recognizer = StreamingSpeechRecognizerFromBytes(
                key="your-speech-key",
                region="eastus",
                audio_format="any",  # Support compressed audio
                enable_tracing=True
            )
            ```

        Raises:
            ValueError: If region is missing when using Default Credentials,
                or if invalid audio_format is specified.
            Exception: If Azure authentication fails or Speech SDK initialization
                encounters errors.

        Note:
            The recognizer must be started with start() before processing audio.
            Authentication validation occurs during start(), not initialization.
        """
        self.key = key or os.getenv("AZURE_SPEECH_KEY")
        self.region = region or os.getenv("AZURE_SPEECH_REGION")
        self.candidate_languages = candidate_languages or self._DEFAULT_LANGS
        self.vad_silence_timeout_ms = vad_silence_timeout_ms
        self.audio_format = audio_format  # either "pcm" or "any"
        self.use_semantic = use_semantic_segmentation

        self.call_connection_id = call_connection_id or "unknown"
        self.enable_tracing = enable_tracing
        self._token_manager: Optional[SpeechTokenManager] = None

        self.partial_callback: Optional[Callable[[str, str, str | None], None]] = None
        self.final_callback: Optional[Callable[[str, str, str | None], None]] = None
        self.cancel_callback: Optional[
            Callable[[speechsdk.SessionEventArgs], None]
        ] = None

        # Advanced feature flags
        self._enable_neural_fe = enable_neural_fe
        self._enable_diarisation = enable_diarisation
        self._speaker_hint = max(0, min(speaker_count_hint, 16))

        self.push_stream = None
        self.speech_recognizer = None

        # Initialize tracing
        self.tracer = None
        self._session_span = None
        if self.enable_tracing:
            try:
                # Initialize Azure Monitor if not already done
                # init_logging_and_monitoring("speech_recognizer")
                self.tracer = trace.get_tracer(__name__)
                logger.debug("Azure Monitor tracing initialized for speech recognizer")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure Monitor tracing: {e}")
                self.enable_tracing = False

        self.cfg = self._create_speech_config()

    def set_call_connection_id(self, call_connection_id: str) -> None:
        """
        Update the call connection ID for correlation in tracing and logging.

        Sets or updates the call connection identifier used for correlating
        speech recognition operations across distributed voice agent components.
        This ID appears in OpenTelemetry traces and logs for end-to-end tracking.

        Args:
            call_connection_id (str): Unique identifier for the call or session.
                Typically provided by Azure Communication Services or your
                call management system.

        Example:
            ```python
            # Set ID from Azure Communication Services
            recognizer.set_call_connection_id("acs_call_123456")

            # Update ID during call transfer
            recognizer.set_call_connection_id("transferred_call_789")
            ```

        Note:
            This ID is used for correlation in Azure Monitor Application Map
            and distributed tracing. Changes take effect immediately for
            new spans and log entries.
        """
        self.call_connection_id = call_connection_id

    def _create_speech_config(self) -> speechsdk.SpeechConfig:
        """
        Create Azure Speech SDK configuration with authentication.

        Initializes the SpeechConfig using either API key authentication or
        Azure Default Credentials, following Azure security best practices
        for authentication in cloud environments.

        Authentication Methods:
            1. API Key: Uses subscription key and region (traditional method)
            2. Default Credentials: Uses managed identity, service principal,
               or developer credentials (recommended for production)

        Returns:
            speechsdk.SpeechConfig: Configured Speech SDK instance ready for
                use with recognition services.

        Environment Variables:
            - AZURE_SPEECH_KEY: API key for subscription-based auth
            - AZURE_SPEECH_REGION: Azure region for Speech services
            - AZURE_SPEECH_ENDPOINT: Custom endpoint URL (optional)

        Example:
            ```python
            # Internal method called during initialization
            config = recognizer._create_speech_config()
            ```

        Raises:
            ValueError: If region is missing when using Default Credentials,
                or if authentication token retrieval fails.
            Exception: If Azure authentication fails or Speech SDK configuration
                encounters errors.

        Note:
            For Default Credentials, the identity must have the "Cognitive
            Services User" RBAC role assigned for the Speech resource.
        """
        if self.key:
            # Use API key authentication if provided
            logger.info("Creating SpeechConfig with API key authentication")
            return speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        else:
            # Use Azure Default Credentials (managed identity, service principal, etc.)
            logger.debug("Creating SpeechConfig with Azure AD credentials")
            if not self.region:
                raise ValueError(
                    "Region must be specified when using Entra Credentials"
                )

            endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")
            if endpoint:
                # Use endpoint if provided
                speech_config = speechsdk.SpeechConfig(endpoint=endpoint)
            else:
                speech_config = speechsdk.SpeechConfig(region=self.region)

            # Set the authorization token
            try:
                token_manager = get_speech_token_manager()
                token_manager.apply_to_config(speech_config, force_refresh=True)
                self._token_manager = token_manager
                logger.debug(
                    "Successfully applied Azure AD token to SpeechConfig"
                )
            except Exception as e:
                logger.error(
                    f"Failed to apply Azure AD speech token: {e}. Ensure that the required RBAC role, such as 'Cognitive Services User', is assigned to your identity."
                )
                raise ValueError(
                    "Failed to authenticate with Azure Speech via Azure AD credentials"
                )

            return speech_config

    def refresh_authentication(self) -> bool:
        """Refresh authentication configuration when 401 errors occur.
        
        Returns:
            bool: True if authentication refresh succeeded, False otherwise.
        """
        try:
            logger.info(f"Refreshing authentication for call {self.call_connection_id}")
            if self.key:
                self.cfg = self._create_speech_config()
            else:
                self._ensure_auth_token(force_refresh=True)
            
            # Clear the current speech recognizer to force recreation with new config
            if self.speech_recognizer:
                self.speech_recognizer = None
                
            logger.info("Authentication refresh completed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh authentication: {e}")
            return False

    def _is_authentication_error(self, details) -> bool:
        """Check if cancellation details indicate a 401 authentication error.
        
        Args:
            details: Cancellation details from speech recognition event
            
        Returns:
            bool: True if this is a 401 authentication error, False otherwise.
        """
        if not details:
            return False
            
        error_details = getattr(details, 'error_details', '')
        if not error_details:
            return False
            
        # Check for 401 authentication error patterns
        auth_error_indicators = [
            "401",
            "Authentication error", 
            "WebSocket upgrade failed: Authentication error",
            "unauthorized",
            "Please check subscription information"
        ]
        
        return any(indicator.lower() in error_details.lower() for indicator in auth_error_indicators)

    def _ensure_auth_token(self, *, force_refresh: bool = False) -> None:
        """Ensure the Speech SDK config holds a valid Azure AD token."""
        if self.key:
            return

        if not self.cfg:
            self.cfg = self._create_speech_config()

        if not self._token_manager:
            self._token_manager = get_speech_token_manager()

        if not self.cfg:
            raise RuntimeError("Speech configuration unavailable for token refresh")

        self._token_manager.apply_to_config(self.cfg, force_refresh=force_refresh)

    def restart_recognition_after_auth_refresh(self) -> bool:
        """Restart speech recognition after authentication refresh.
        
        This method recreates the speech recognizer with fresh authentication
        and restarts the recognition session. It's typically called after
        a 401 authentication error has been detected and credentials refreshed.
        
        Returns:
            bool: True if restart succeeded, False otherwise.
        """
        try:
            logger.info("Restarting speech recognition with refreshed authentication")
            
            # Stop current recognition if still active
            if self.speech_recognizer:
                try:
                    self.speech_recognizer.stop_continuous_recognition_async().get()
                except Exception as e:
                    logger.debug(f"Error stopping previous recognizer: {e}")
                
            # Clear current recognizer
            self.speech_recognizer = None
            
            # Recreate and start recognition with new auth
            self.prepare_start()
            self.speech_recognizer.start_continuous_recognition_async().get()
            
            logger.info("Speech recognition restarted successfully with refreshed authentication")
            
            if self._session_span:
                self._session_span.add_event(
                    "recognition_restarted_after_auth_refresh",
                    {"restart_success": True}
                )
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart speech recognition after auth refresh: {e}")
            
            if self._session_span:
                self._session_span.add_event(
                    "recognition_restart_failed",
                    {"restart_success": False, "error": str(e)}
                )
                
            return False

    def set_partial_result_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Set callback function for partial (intermediate) recognition results.

        Registers a callback function that will be invoked whenever the speech
        recognizer produces partial recognition results during continuous
        recognition. Partial results provide real-time feedback as speech
        is being processed.

        Args:
            callback (Callable[[str, str], None]): Function to call with partial results.
                Function signature: callback(text, detected_language, speaker_id)
                - text (str): Partial recognized text (may change as more audio is processed)
                - detected_language (str): ISO language code (e.g., "en-US")
                - speaker_id (Optional[str]): Speaker identifier if diarization enabled

        Example:
            ```python
            def handle_partial_result(text, language, speaker_id):
                print(f"Partial ({language}): {text}")
                if speaker_id:
                    print(f"Speaker: {speaker_id}")

            recognizer.set_partial_result_callback(handle_partial_result)
            ```

        Note:
            Partial results are intermediate and may change as more audio
            is processed. Use final results for definitive text output.
            Callback is invoked from Speech SDK thread.
        """
        self.partial_callback = callback

    def set_final_result_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Set callback function for final recognition results.

        Registers a callback function that will be invoked when the speech
        recognizer produces final recognition results. Final results represent
        completed speech segments and are stable (won't change).

        Args:
            callback (Callable[[str, str], None]): Function to call with final results.
                Function signature: callback(text, detected_language, speaker_id)
                - text (str): Final recognized text (stable, won't change)
                - detected_language (str): ISO language code (e.g., "en-US")
                - speaker_id (Optional[str]): Speaker identifier if diarization enabled

        Example:
            ```python
            def handle_final_result(text, language, speaker_id):
                print(f"Final ({language}): {text}")
                # Process completed utterance
                process_user_input(text, language)

            recognizer.set_final_result_callback(handle_final_result)
            ```

        Note:
            Final results are triggered by voice activity detection silence
            timeouts or semantic segmentation boundaries. Callback is
            invoked from Speech SDK thread.
        """
        self.final_callback = callback

    def set_cancel_callback(
        self, callback: Callable[[speechsdk.SessionEventArgs], None]
    ) -> None:
        """
        Set callback function for cancellation and error events.

        Registers a callback function that will be invoked when speech recognition
        is canceled due to errors, network issues, or other exceptional conditions.
        This enables custom error handling and recovery logic.

        Args:
            callback (Callable[[speechsdk.SessionEventArgs], None]): Function to call
                when cancellation occurs. Receives SessionEventArgs with details
                about the cancellation reason and error information.

        Example:
            ```python
            def handle_cancellation(event_args):
                if event_args.result and event_args.result.cancellation_details:
                    details = event_args.result.cancellation_details
                    print(f"Recognition canceled: {details.reason}")
                    if details.error_details:
                        print(f"Error: {details.error_details}")

                    # Implement recovery logic
                    if details.reason == speechsdk.CancellationReason.Error:
                        restart_recognition()

            recognizer.set_cancel_callback(handle_cancellation)
            ```

        Note:
            Cancellation can occur due to network errors, authentication
            failures, quota exceeded, or service interruptions. Implement
            appropriate retry logic in the callback.
        """
        self.cancel_callback = callback

    def prepare_stream(self) -> None:
        """
        Initialize the audio input stream for speech recognition.

        Creates and configures a PushAudioInputStream based on the specified
        audio format. This stream will receive audio bytes for real-time
        speech recognition processing.

        Stream Formats:
            - PCM: Raw 16kHz 16-bit mono audio (uncompressed)
            - ANY: Compressed audio formats (WebM, MP3, OGG) via GStreamer

        Example:
            ```python
            # Prepare stream before starting recognition
            recognizer.prepare_stream()
            recognizer.start()

            # Now ready to receive audio bytes
            recognizer.write_bytes(audio_chunk)
            ```

        Raises:
            ValueError: If audio_format is not "pcm" or "any"

        Note:
            This method is called automatically by start() and prepare_start().
            Manual calls are only needed for advanced stream management scenarios.
        """
        if self.audio_format == "pcm":
            stream_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=16000, bits_per_sample=16, channels=1
            )
        elif self.audio_format == "any":
            stream_format = speechsdk.audio.AudioStreamFormat(
                compressed_stream_format=speechsdk.AudioStreamContainerFormat.ANY
            )
        else:
            raise ValueError(f"Unsupported audio_format: {self.audio_format}")

        self.push_stream = speechsdk.audio.PushAudioInputStream(
            stream_format=stream_format
        )

    def start(self) -> None:
        """
        Start continuous speech recognition with comprehensive tracing.

        Initializes and starts the speech recognition session with OpenTelemetry
        tracing for monitoring and debugging. Creates a session-level span that
        tracks the entire recognition lifecycle and integrates with Azure Monitor
        Application Map for service dependency visualization.

        Tracing Features:
            - Session-level span for complete recognition lifecycle
            - Call correlation with connection ID attributes
            - Azure Monitor Application Map integration
            - Service dependency visualization
            - Performance monitoring and error tracking

        Span Attributes:
            - rt.call.connection_id: Call correlation identifier
            - rt.session.id: Session identifier
            - ai.operation.id: Azure Monitor operation correlation
            - speech.region: Azure region for Speech services
            - peer.service: External service identification
            - server.address: Speech service endpoint
            - http.url: Recognition endpoint URL
            - speech.audio_format: Audio format configuration
            - speech.candidate_languages: Language detection settings

        Example:
            ```python
            # Start recognition with tracing
            recognizer.start()

            # Recognition is now active and ready for audio
            for audio_chunk in audio_stream:
                recognizer.write_bytes(audio_chunk)

            # Clean up
            recognizer.stop()
            ```

        Raises:
            Exception: If Speech SDK initialization fails, authentication
                errors occur, or network connectivity issues prevent startup.

        Note:
            This method blocks until the Speech SDK completes initialization.
            Recognition runs on background threads after successful startup.
            The session span remains active until stop() is called.
        """
        if self.enable_tracing and self.tracer:
            # Start a session-level span for the entire speech recognition session
            self._session_span = self.tracer.start_span(
                "speech_recognition_session", kind=SpanKind.CLIENT
            )

            # Set essential attributes using centralized enum and semantic conventions v1.27+
            self._session_span.set_attributes({
                "call_connection_id": self.call_connection_id,
                "session_id": self.call_connection_id,
                "ai.operation.id": self.call_connection_id,
                
                # Service and network identification
                "peer.service": "azure-cognitive-speech",
                "server.address": f"{self.region}.stt.speech.microsoft.com",
                "server.port": 443,
                "network.protocol.name": "websocket",
                "http.request.method": "POST",
                
                # Speech configuration
                "speech.audio_format": self.audio_format,
                "speech.candidate_languages": ",".join(self.candidate_languages),
                "speech.region": self.region,
            })

            # Make this span current for the duration of setup
            with trace.use_span(self._session_span):
                self._start_recognition()
        else:
            self._start_recognition()

    def _start_recognition(self) -> None:
        """
        Internal method to initialize and start the Speech SDK recognizer.

        Builds the complete Speech SDK recognizer configuration and starts
        continuous recognition in a single operation. This method handles
        the low-level SDK setup and network connection establishment.

        Process:
            1. Prepare audio stream and recognizer configuration
            2. Configure advanced features (neural FE, diarization)
            3. Set up language detection and recognition parameters
            4. Connect event callbacks for results and errors
            5. Start continuous recognition with network connection

        Logging:
            - Logs recognition startup with configuration details
            - Tracks session events in OpenTelemetry spans
            - Records successful initialization

        Raises:
            Exception: If Speech SDK fails to initialize or start recognition
                due to configuration errors, authentication issues, or network
                connectivity problems.

        Note:
            This method is called internally by start() and should not be
            called directly. Use start() for public API access.
        """
        logger.info("Starting recognition from byte stream…")

        self.prepare_start()
        self.speech_recognizer.start_continuous_recognition_async().get()

        logger.info("Recognition started.")
        if self._session_span:
            self._session_span.add_event("speech_recognition_started")

    def prepare_start(self) -> None:
        """
        Configure and prepare the Speech SDK recognizer with advanced features.

        Builds a complete Speech SDK recognizer instance with all configured
        features including neural front-end processing, speaker diarization,
        language detection, and semantic segmentation. This method handles
        the complex SDK configuration without starting network communication.

        Configuration Stages:
            1. SpeechConfig: Global properties and service settings
            2. Audio Stream: Format-specific input stream configuration
            3. Neural Audio Processing: Optional front-end enhancement
            4. Language Detection: Auto-detection configuration
            5. Recognizer Assembly: Complete recognizer with all features
            6. Callback Wiring: Event handler registration

        Advanced Features:
            - Neural Front-End: Noise suppression, AEC, AGC when enabled
            - Speaker Diarization: Multi-speaker identification and separation
            - Language Detection: Continuous auto-detection from candidates
            - Semantic Segmentation: Improved sentence boundary detection
            - VAD Configuration: Customizable silence timeout settings

        Audio Formats:
            - PCM: Raw 16kHz 16-bit mono for optimal performance
            - ANY: Compressed formats (WebM, MP3, OGG) via GStreamer

        Example:
            ```python
            # Internal method called by start()
            recognizer.prepare_start()
            # Recognizer is configured but not yet started
            ```

        Logging:
            Logs detailed configuration information including:
            - Audio format and processing options
            - Neural front-end and diarization settings
            - Language detection and VAD configuration
            - Callback registration status

        Note:
            This method prepares the recognizer but does not start recognition.
            Call speech_recognizer.start_continuous_recognition_async() after
            this method to begin processing audio.
        """
        logger.info(
            "Speech-SDK prepare_start – format=%s  neuralFE=%s  diar=%s",
            self.audio_format,
            self._enable_neural_fe,
            self._enable_diarisation,
        )

        self._ensure_auth_token()

        # ------------------------------------------------------------------ #
        # 1. SpeechConfig – global properties
        # ------------------------------------------------------------------ #
        speech_config = self.cfg

        if self.use_semantic:
            speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
            )

        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode, "Continuous"
        )

        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceResponse_StablePartialResultThreshold, "1"
        )

        # ── Speaker diarisation (if requested) ────────────────────────────
        if self._enable_diarisation:
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults,
                value="true",
            )
            # speech_config.set_property(
            #     speechsdk.PropertyId.SpeechServiceConnection_SpeakerDiarizationSpeakerCount,
            #     str(self._speaker_hint))

        # ------------------------------------------------------------------ #
        # 2. PushAudioInputStream – container vs. raw PCM
        # ------------------------------------------------------------------ #
        if self.audio_format == "pcm":
            stream_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=16000, bits_per_sample=16, channels=1
            )
        elif self.audio_format == "any":
            stream_format = speechsdk.audio.AudioStreamFormat(
                compressed_stream_format=speechsdk.AudioStreamContainerFormat.ANY
            )
        else:
            raise ValueError(f"Unsupported audio_format: {self.audio_format!r}")

        self.push_stream = speechsdk.audio.PushAudioInputStream(
            stream_format=stream_format
        )

        # ------------------------------------------------------------------ #
        # 3. Optional neural audio front-end
        # ------------------------------------------------------------------ #
        if self._enable_neural_fe:
            proc_opts = speechsdk.audio.AudioProcessingOptions(
                speechsdk.audio.AudioProcessingConstants.AUDIO_INPUT_PROCESSING_ENABLE_DEFAULT,
                speechsdk.audio.AudioProcessingConstants.AUDIO_INPUT_PROCESSING_MODE_DEFAULT,
            )
            audio_config = speechsdk.audio.AudioConfig(
                stream=self.push_stream, audio_processing_options=proc_opts
            )
        else:
            audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)

        # ------------------------------------------------------------------ #
        # 4. LID configuration
        # ------------------------------------------------------------------ #
        lid_cfg = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
            languages=self.candidate_languages
        )

        # ------------------------------------------------------------------ #
        # 5. Build recogniser (still no network traffic)
        # ------------------------------------------------------------------ #
        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            auto_detect_source_language_config=lid_cfg,
        )

        if not self.use_semantic:
            self.speech_recognizer.properties.set_property(
                speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs,
                str(self.vad_silence_timeout_ms),
            )

        # ------------------------------------------------------------------ #
        # 6. Wire callbacks / health telemetry
        # ------------------------------------------------------------------ #
        logger.debug(
            f"🔗 Setting up callbacks: partial={self.partial_callback is not None}, final={self.final_callback is not None}, cancel={self.cancel_callback is not None}"
        )

        if self.partial_callback:
            self.speech_recognizer.recognizing.connect(self._on_recognizing)
            logger.debug("✅ Connected partial callback (_on_recognizing)")
        if self.final_callback:
            self.speech_recognizer.recognized.connect(self._on_recognized)
            logger.debug("✅ Connected final callback (_on_recognized)")
        if self.cancel_callback:
            self.speech_recognizer.canceled.connect(self.cancel_callback)
            logger.debug("✅ Connected cancel callback")

        self.speech_recognizer.canceled.connect(self._on_canceled)
        self.speech_recognizer.session_stopped.connect(self._on_session_stopped)

        logger.info(
            "Speech-SDK ready " "(neuralFE=%s, diarisation=%s, speakers=%s)",
            self._enable_neural_fe,
            self._enable_diarisation,
            self._speaker_hint,
        )

    def write_bytes(self, audio_chunk: bytes) -> None:
        """
        Write audio bytes to the recognition stream for real-time processing.

        Feeds audio data to the Speech SDK's PushAudioInputStream for continuous
        speech recognition. Optimized for high-frequency calls with minimal
        overhead by using span events rather than per-chunk spans.

        Args:
            audio_chunk (bytes): Raw audio data to process. Format depends on
                the configured audio_format:
                - PCM: Raw 16kHz 16-bit mono audio bytes
                - ANY: Compressed audio data (WebM, MP3, OGG)

        Performance Considerations:
            - Avoids creating individual spans per chunk for optimal performance
            - Uses span events for coarse-grained visibility
            - Designed for high-frequency calls (100+ times per second)
            - Minimal overhead even with large audio streams

        Example:
            ```python
            # Real-time audio processing
            recognizer.start()

            for audio_chunk in audio_stream:
                recognizer.write_bytes(audio_chunk)

            recognizer.stop()
            ```

        Tracing:
            Adds lightweight events to the session span including:
            - Audio chunk size for throughput monitoring
            - Stream health indicators
            - No per-chunk spans to maintain performance

        Logging:
            - Debug logs for chunk size and stream status
            - Warning logs if stream is not initialized
            - Performance-optimized logging levels

        Note:
            The push_stream must be initialized (via start() or prepare_start())
            before calling this method. Audio chunks are queued and processed
            asynchronously by the Speech SDK.
        """
        logger.debug(
            f"write_bytes called: {len(audio_chunk)} bytes, has_push_stream={self.push_stream is not None}"
        )
        if self.push_stream:
            if self.enable_tracing and self._session_span:
                try:
                    self._session_span.add_event(
                        "audio_chunk", {"size": len(audio_chunk)}
                    )
                except Exception:
                    pass
            self.push_stream.write(audio_chunk)
            logger.debug(f"✅ Audio chunk written to push_stream")
        else:
            logger.warning(
                f"⚠️ write_bytes called but push_stream is None! {len(audio_chunk)} bytes discarded"
            )

    def stop(self) -> None:
        """
        Stop continuous speech recognition with graceful cleanup and tracing.

        Terminates the active speech recognition session asynchronously without
        blocking the calling thread. Properly finalizes OpenTelemetry tracing
        spans and ensures clean shutdown of Speech SDK resources.

        Cleanup Process:
            1. Add stop event to session span for tracking
            2. Initiate asynchronous recognition termination
            3. Finalize session span with success status
            4. Clean up tracing resources

        Behavior:
            - Non-blocking operation for responsive applications
            - Graceful termination of recognition processing
            - Proper span finalization for complete traces
            - Safe to call multiple times (idempotent)

        Example:
            ```python
            # Start recognition
            recognizer.start()

            # Process audio...
            for chunk in audio_stream:
                recognizer.write_bytes(chunk)

            # Stop when done
            recognizer.stop()
            recognizer.close_stream()  # Complete cleanup
            ```

        Tracing:
            - Adds "speech_recognition_stopping" event
            - Adds "speech_recognition_stopped" event
            - Sets span status to OK for successful completion
            - Ends session span to complete the trace

        Note:
            This method initiates shutdown but does not wait for completion.
            The Speech SDK handles final processing asynchronously. Call
            close_stream() after stop() for complete resource cleanup.
        """
        if self.speech_recognizer:
            # Add event to session span before stopping
            if self._session_span:
                self._session_span.add_event("speech_recognition_stopping")

            # Stop recognition asynchronously without blocking
            future = self.speech_recognizer.stop_continuous_recognition_async()
            logger.debug(
                "🛑 Speech recognition stop initiated asynchronously (non-blocking)"
            )
            logger.info("Recognition stopped.")

            # Finish session span if it's still active
            if self._session_span:
                self._session_span.add_event("speech_recognition_stopped")
                self._session_span.set_status(Status(StatusCode.OK))
                self._session_span.end()
                self._session_span = None

    def close_stream(self) -> None:
        """
        Close the audio input stream with final cleanup and tracing.

        Properly closes the PushAudioInputStream to release resources and
        signal end of audio input to the Speech SDK. Completes any remaining
        OpenTelemetry tracing activities for the session.

        Cleanup Activities:
            1. Add stream closing event to session span
            2. Close the PushAudioInputStream
            3. Add stream closed confirmation event
            4. End session span if still active
            5. Clean up tracing resources

        Resource Management:
            - Releases audio stream buffers and handles
            - Signals end-of-stream to Speech SDK
            - Completes any pending recognition operations
            - Frees memory and network resources

        Example:
            ```python
            try:
                recognizer.start()

                # Process audio stream
                for chunk in audio_stream:
                    recognizer.write_bytes(chunk)

            finally:
                # Always clean up resources
                recognizer.stop()
                recognizer.close_stream()
            ```

        Tracing:
            - Adds "audio_stream_closing" event
            - Adds "audio_stream_closed" event
            - Ends session span if not already completed
            - Ensures trace completion for monitoring

        Note:
            Call this method after stop() to ensure complete cleanup.
            Safe to call multiple times. The stream cannot be reused
            after closing - create a new recognizer instance if needed.
        """
        if self.push_stream:
            # Add event to session span before closing
            if self._session_span:
                self._session_span.add_event("audio_stream_closing")

            self.push_stream.close()

            # Final cleanup of session span if still active
            if self._session_span:
                self._session_span.add_event("audio_stream_closed")
                self._session_span.end()
                self._session_span = None

    @staticmethod
    def _extract_lang(evt) -> str:
        """
        Extract detected language from recognition event with fallback handling.

        Attempts to extract the detected language code from a speech recognition
        event using multiple fallback strategies to ensure reliable language
        detection regardless of the Language Identification (LID) mode.

        Args:
            evt: Speech recognition event containing language detection results

        Returns:
            str: ISO language code (e.g., "en-US") or empty string if detection
                fails. Empty string signals the caller to use default language.

        Detection Priority:
            1. evt.result.language: Direct language field (Continuous LID mode)
            2. AutoDetectSourceLanguageResult: Property-based detection
            3. Empty string: Fallback when detection fails

        Example:
            ```python
            # Internal usage in event handlers
            detected_lang = StreamingSpeechRecognizerFromBytes._extract_lang(event)
            if not detected_lang:
                detected_lang = "en-US"  # Use default
            ```

        Note:
            This static method is used internally by recognition event handlers
            to provide consistent language detection across different LID modes
            and Speech SDK versions.
        """
        if getattr(evt.result, "language", None):
            return evt.result.language

        prop = evt.result.properties.get(
            speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult,
            "",
        )
        if prop:
            return prop

        return ""

    def _extract_speaker_id(self, evt):
        """
        Extract speaker identifier from diarization results in recognition event.

        Parses the JSON result property to extract speaker identification
        information when speaker diarization is enabled. This enables
        multi-speaker conversation tracking and attribution.

        Args:
            evt: Speech recognition event potentially containing diarization data

        Returns:
            Optional[str]: Speaker identifier string (e.g., "0", "1") if
                diarization is active and speaker detected, None otherwise.

        JSON Structure:
            The Speech SDK provides diarization results in the JsonResult
            property as a nested JSON structure containing SpeakerId field
            when speaker diarization is enabled.

        Example:
            ```python
            # Internal usage in event handlers
            speaker_id = recognizer._extract_speaker_id(event)
            if speaker_id:
                print(f"Speaker {speaker_id}: {text}")
            ```

        Error Handling:
            - Returns None if JSON parsing fails
            - Returns None if SpeakerId field is missing
            - Returns None if diarization is disabled
            - Graceful handling of malformed JSON

        Note:
            Speaker IDs are typically numeric strings ("0", "1", "2") assigned
            by the diarization algorithm. The same speaker may receive different
            IDs across different recognition sessions.
        """
        blob = evt.result.properties.get(
            speechsdk.PropertyId.SpeechServiceResponse_JsonResult, ""
        )
        if blob:
            try:
                return str(json.loads(blob).get("SpeakerId"))
            except Exception:
                pass
        return None

    # callbacks → wrap user callbacks with tracing
    def _on_recognizing(self, evt: speechsdk.SpeechRecognitionEventArgs) -> None:
        """
        Handle partial recognition results with comprehensive tracing and logging.

        Processes intermediate speech recognition results during continuous
        recognition, providing real-time feedback for voice applications.
        Creates detailed traces for monitoring and debugging partial results.

        Args:
            evt (speechsdk.SpeechRecognitionEventArgs): Recognition event containing
                partial text, language detection, and optional speaker information.

        Processing Pipeline:
            1. Extract partial text and language from event
            2. Extract speaker ID if diarization is enabled
            3. Create tracing span for partial recognition
            4. Add session events for monitoring
            5. Invoke user callback with results

        Tracing Attributes:
            - speech.result.type: "partial" for intermediate results
            - speech.result.text_length: Character count for throughput analysis
            - speech.detected_language: Auto-detected language code
            - rt.call.connection_id: Call correlation identifier

        Example:
            ```python
            # Set callback to receive partial results
            def handle_partial(text, language, speaker_id):
                print(f"Partial ({language}): {text}")

            recognizer.set_partial_result_callback(handle_partial)
            ```

        Callback Signature:
            callback(text, detected_language, speaker_id)
            - text (str): Partial recognized text (may change)
            - detected_language (str): ISO language code
            - speaker_id (Optional[str]): Speaker identifier if available

        Performance:
            - Optimized for high-frequency calls
            - Lightweight span creation
            - Debug-level logging to minimize overhead
            - Efficient language detection extraction

        Note:
            Partial results are intermediate and may change as more audio
            is processed. They provide real-time feedback but should not
            be used for final text processing.
        """
        txt = evt.result.text
        speaker_id = self._extract_speaker_id(evt)

        # Extract language outside the tracing block to avoid scope issues
        detected = (
            speechsdk.AutoDetectSourceLanguageResult(evt.result).language
            or self.candidate_languages[0]
        )

        logger.debug(
            f"🔍 _on_recognizing called: text='{txt}', detected_lang='{detected}', has_callback={self.partial_callback is not None}"
        )

        if txt and self.partial_callback:
            # Create a span for partial recognition
            if self.enable_tracing and self.tracer:
                with self.tracer.start_as_current_span(
                    "speech_partial_recognition",
                    kind=SpanKind.CLIENT,
                    attributes={
                        "speech.result.type": "partial",
                        "speech.result.text_length": len(txt),
                        "rt.call.connection_id": self.call_connection_id,
                    },
                ) as span:
                    span.set_attribute("speech.detected_language", detected)

                    # Add event to session span
                    if self._session_span:
                        self._session_span.add_event(
                            "partial_recognition_received",
                            {"text_length": len(txt), "detected_language": detected},
                        )

            logger.debug(
                f"Calling partial_callback with: '{txt}', '{detected}', '{speaker_id}'"
            )
            self.partial_callback(txt, detected, speaker_id)
        elif txt:
            logger.debug(f"⚠️ Got text but no partial_callback: '{txt}'")
        else:
            logger.debug(f"🔇 Empty text in recognizing event")

    def _on_recognized(self, evt: speechsdk.SpeechRecognitionEventArgs) -> None:
        """
        Handle final recognition results with comprehensive tracing and processing.

        Processes completed speech recognition results representing finalized
        speech segments. Creates detailed traces and invokes user callbacks
        for stable recognition results that won't change.

        Args:
            evt (speechsdk.SpeechRecognitionEventArgs): Recognition event containing
                final text, language detection, result reason, and metadata.

        Processing Pipeline:
            1. Validate recognition success (RecognizedSpeech reason)
            2. Extract final text and detected language
            3. Create comprehensive tracing span
            4. Add detailed session events with text preview
            5. Invoke user callback with stable results

        Result Validation:
            Only processes events with ResultReason.RecognizedSpeech to ensure
            valid speech was detected (not silence, noise, or errors).

        Tracing Attributes:
            - speech.result.type: "final" for completed results
            - speech.result.text_length: Character count for analysis
            - speech.detected_language: Auto-detected language code
            - speech.result.reason: Recognition result status
            - rt.call.connection_id: Call correlation identifier

        Session Events:
            - final_recognition_received: Tracks completed recognitions
            - text_length: Character count for throughput monitoring
            - detected_language: Language detection results
            - text_preview: First 50 characters for debugging

        Example:
            ```python
            # Set callback to receive final results
            def handle_final(text, language, speaker_id):
                print(f"Final ({language}): {text}")
                process_user_input(text, language)

            recognizer.set_final_result_callback(handle_final)
            ```

        Callback Signature:
            callback(text, detected_language, speaker_id)
            - text (str): Final recognized text (stable)
            - detected_language (str): ISO language code
            - speaker_id (Optional[str]): Speaker identifier if available

        Note:
            Final results are triggered by voice activity detection silence
            timeouts or semantic segmentation boundaries. These results are
            stable and suitable for downstream processing.
        """
        logger.debug(
            f"🔍 _on_recognized called: reason={evt.result.reason}, text='{evt.result.text}', has_callback={self.final_callback is not None}"
        )

        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            detected_lang = (
                speechsdk.AutoDetectSourceLanguageResult(evt.result).language
                or self.candidate_languages[0]
            )

            logger.debug(
                f"🔍 Recognition successful: text='{evt.result.text}', detected_lang='{detected_lang}'"
            )

            if self.enable_tracing and self.tracer and evt.result.text:
                with self.tracer.start_as_current_span(
                    "speech_final_recognition",
                    kind=SpanKind.CLIENT,
                    attributes={
                        "speech.result.type": "final",
                        "speech.result.text_length": len(evt.result.text),
                        "speech.detected_language": detected_lang,
                        "rt.call.connection_id": self.call_connection_id,
                        "speech.result.reason": str(evt.result.reason),
                    },
                ) as span:
                    # Add event to session span
                    if self._session_span:
                        self._session_span.add_event(
                            "final_recognition_received",
                            {
                                "text_length": len(evt.result.text),
                                "detected_language": detected_lang,
                                "text_preview": (
                                    evt.result.text[:50] + "..."
                                    if len(evt.result.text) > 50
                                    else evt.result.text
                                ),
                            },
                        )

            if self.final_callback and evt.result.text:
                logger.debug(
                    f"Calling final_callback with: '{evt.result.text}', '{detected_lang}'"
                )
                self.final_callback(evt.result.text, detected_lang)
            elif evt.result.text:
                logger.debug(
                    f"⚠️ Got final text but no final_callback: '{evt.result.text}'"
                )
        else:
            logger.debug(
                f"🚫 Recognition result reason not RecognizedSpeech: {evt.result.reason}"
            )

    def _on_canceled(self, evt: speechsdk.SessionEventArgs) -> None:
        """
        Handle cancellation events with comprehensive error tracking and recovery.

        Processes speech recognition cancellation events caused by errors,
        network issues, authentication failures, or service interruptions.
        Provides detailed error information and tracing for debugging and
        monitoring purposes.

        Args:
            evt (speechsdk.SessionEventArgs): Cancellation event containing
                error details, reason codes, and diagnostic information.

        Error Processing:
            1. Log cancellation event with details
            2. Set error status on session span
            3. Extract detailed cancellation information
            4. Add comprehensive error events to span
            5. Enable error analysis and recovery

        Common Cancellation Reasons:
            - EndOfStream: Normal end of audio input
            - CancelledByUser: Intentional cancellation
            - Error: Network, authentication, or service errors
            - BadRequest: Invalid configuration or parameters

        Tracing Integration:
            - Sets span status to ERROR with description
            - Adds recognition_canceled event with details
            - Adds cancellation_details event with reason and error
            - Enables Application Map error visualization

        Example Error Handling:
            ```python
            def handle_cancellation(event_args):
                if event_args.result.cancellation_details:
                    details = event_args.result.cancellation_details
                    if details.reason == speechsdk.CancellationReason.Error:
                        # Implement retry logic
                        logger.error(f"Recognition error: {details.error_details}")
                        schedule_retry()

            recognizer.set_cancel_callback(handle_cancellation)
            ```

        Recovery Strategies:
            - Network errors: Implement exponential backoff retry
            - Authentication errors: Refresh tokens and reconnect
            - Quota errors: Implement rate limiting and delays
            - Service errors: Switch to backup regions if available

        Note:
            Cancellation events often indicate recoverable conditions.
            Implement appropriate retry logic in custom cancel callbacks
            for robust voice applications.
        """
        logger.warning("Recognition canceled: %s", evt)

        # Add error event to session span
        if self._session_span:
            self._session_span.set_status(
                Status(StatusCode.ERROR, "Recognition canceled")
            )
            self._session_span.add_event(
                "recognition_canceled", {"event_details": str(evt)}
            )

        if evt.result and evt.result.cancellation_details:
            details = evt.result.cancellation_details
            error_msg = f"Reason: {details.reason}, Error: {details.error_details}"
            
            # Check for 401 authentication error and attempt refresh
            if self._is_authentication_error(details):
                logger.warning(f"Authentication error detected in speech recognition: {details.error_details}")
                
                if self._session_span:
                    self._session_span.add_event(
                        "recognition_authentication_error",
                        {"error_details": details.error_details}
                    )
                
                # Try to refresh authentication
                if self.refresh_authentication():
                    logger.info("Authentication refreshed successfully for speech recognition")
                    
                    if self._session_span:
                        self._session_span.add_event(
                            "recognition_authentication_refreshed",
                            {"refresh_success": True}
                        )
                        
                    # Attempt automatic restart with refreshed credentials
                    if self.restart_recognition_after_auth_refresh():
                        logger.info("Speech recognition automatically restarted with refreshed credentials")
                        return  # Exit early on successful restart
                    else:
                        logger.warning("Automatic restart failed - manual restart required")
                else:
                    logger.error("Failed to refresh authentication for speech recognition")
                    
                    if self._session_span:
                        self._session_span.add_event(
                            "recognition_authentication_refresh_failed",
                            {"refresh_success": False}
                        )
            
            logger.warning(error_msg)

            # Add detailed error information to span
            if self._session_span:
                self._session_span.add_event(
                    "cancellation_details",
                    {
                        "cancellation_reason": str(details.reason),
                        "error_details": details.error_details,
                    },
                )

    def _on_session_stopped(self, evt: speechsdk.SessionEventArgs) -> None:
        """
        Handle session stopped events with final cleanup and tracing completion.

        Processes the session stopped event that signals the end of a speech
        recognition session. Performs final cleanup of tracing resources and
        ensures proper session lifecycle completion.

        Args:
            evt (speechsdk.SessionEventArgs): Session event containing information
                about the session termination.

        Cleanup Activities:
            1. Log session termination
            2. Add session stopped event to span
            3. Set final span status to OK (successful completion)
            4. End session span to complete tracing
            5. Clean up tracing resources

        Session Lifecycle:
            Session stopped events occur when:
            - Recognition is explicitly stopped via stop()
            - End of audio stream is reached
            - Session timeout is exceeded
            - Unrecoverable errors force termination

        Tracing Completion:
            - Adds "speech_session_stopped" event
            - Sets span status to OK for normal termination
            - Ends session span to complete the trace
            - Clears span reference for cleanup

        Example:
            ```python
            # Session lifecycle
            recognizer.start()          # Session begins
            # ... process audio ...
            recognizer.stop()           # Session stopping
            # _on_session_stopped called # Session ended
            ```

        Integration:
            This method works with Azure Monitor Application Map to:
            - Complete service dependency traces
            - Provide session duration metrics
            - Enable end-to-end call correlation
            - Support distributed tracing across services

        Note:
            This method is called automatically by the Speech SDK and
            should not be invoked directly. It ensures proper cleanup
            regardless of how the session ends (normal or error).
        """
        logger.info("Session stopped.")

        # Add event to session span and finish it
        if self._session_span:
            self._session_span.add_event("speech_session_stopped")
            self._session_span.set_status(Status(StatusCode.OK))
            self._session_span.end()
            self._session_span = None
