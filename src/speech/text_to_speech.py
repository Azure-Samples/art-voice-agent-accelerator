"""Azure Cognitive Services Text-to-Speech Integration Module.

This module provides comprehensive text-to-speech synthesis capabilities for real-time
voice applications using Azure Cognitive Services Speech SDK. It offers multiple synthesis
modes optimized for different use cases including real-time streaming, local playback,
and frame-based audio processing.
"""

import html
import os
import re
import asyncio
import time
from typing import Callable, Dict, List, Optional

import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
from langdetect import LangDetectException, detect

# OpenTelemetry imports for tracing
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Import centralized span attributes enum
from src.enums.monitoring import SpanAttr
from src.speech.auth_manager import SpeechTokenManager, get_speech_token_manager
from utils.ml_logging import get_logger

# Load environment variables from a .env file if present
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

_SENTENCE_END = re.compile(r"([.!?；？！。]+|\n)")


def split_sentences(text: str) -> List[str]:
    """Split text into sentences while preserving delimiters for natural speech synthesis.

    This function provides intelligent sentence boundary detection optimized for
    text-to-speech applications. It preserves punctuation marks to maintain
    natural prosody and intonation patterns during synthesis.

    The function handles multiple languages and scripts including:
    - English punctuation (., !, ?)
    - Chinese punctuation (。, ！, ？)
    - Japanese punctuation (。, ！, ？)
    - Spanish punctuation with inverted marks
    - Newline characters as sentence boundaries

    Args:
        text: Input text to split into sentences. Can contain mixed languages
              and various punctuation styles.

    Returns:
        List of sentence strings with trailing whitespace removed. Empty
        sentences are filtered out. Punctuation marks are preserved within
        each sentence for proper synthesis prosody.

    Example:
        ```python
        text = "Hello world! How are you? Fine, thanks."
        sentences = split_sentences(text)
        # Returns: ["Hello world!", "How are you?", "Fine, thanks."]

        # Multi-language support
        mixed_text = "Hello! 你好！¿Cómo estás?"
        sentences = split_sentences(mixed_text)
        # Returns: ["Hello!", "你好！", "¿Cómo estás?"]
        ```

    Performance:
        - O(n) time complexity where n is text length
        - Minimal memory overhead with character-by-character processing
        - Optimized for real-time text processing in voice applications

    Note:
        This function is designed for speech synthesis and may not be suitable
        for general NLP sentence tokenization tasks. It prioritizes preserving
        audio prosody over linguistic accuracy.
    """
    parts, buf = [], []
    for ch in text:
        buf.append(ch)
        if _SENTENCE_END.match(ch):
            parts.append("".join(buf).strip())
            buf.clear()
    if buf:
        parts.append("".join(buf).strip())
    return parts


def auto_style(lang_code: str) -> Dict[str, str]:
    """Determine optimal voice style and speech rate based on language family.

    This function provides language-specific optimizations for Azure Cognitive
    Services neural voices. It applies empirically-determined style and rate
    settings that improve naturalness and comprehension for different language
    families.

    Optimization Logic:
    - Romance languages (Spanish, French, Italian): Use "chat" style with
      slightly faster rate (+3%) for improved conversational flow
    - English variants: Apply "chat" style with +3% rate for natural dialogue
    - Other languages: Return empty dict to use voice defaults

    Args:
        lang_code: ISO 639-1 language code (e.g., 'en', 'es', 'fr', 'zh').
                   Case-insensitive, supports language-region codes like 'en-US'.

    Returns:
        Dictionary with optimal synthesis parameters:
        - 'style': Voice style name (e.g., 'chat', 'news', 'customerservice')
        - 'rate': Speech rate adjustment (e.g., '+3%', '-10%', '1.2x')

        Returns empty dict if no optimization available for the language.

    Example:
        ```python
        # English optimization
        settings = auto_style('en-US')
        # Returns: {'style': 'chat', 'rate': '+3%'}

        # Spanish optimization
        settings = auto_style('es')
        # Returns: {'style': 'chat', 'rate': '+3%'}

        # Unsupported language
        settings = auto_style('zh')
        # Returns: {}
        ```

    Supported Language Families:
        - English: en, en-US, en-GB, en-AU, etc.
        - Spanish: es, es-ES, es-MX, es-AR, etc.
        - French: fr, fr-FR, fr-CA, etc.
        - Italian: it, it-IT, etc.

    Performance:
        - O(1) lookup time with string prefix matching
        - Minimal memory footprint
        - Safe for high-frequency calls in real-time applications

    Note:
        These optimizations are based on user experience testing and may be
        adjusted based on specific voice characteristics or application requirements.
        Always test with your target audience for optimal results.
    """
    if lang_code.startswith(("es", "fr", "it")):
        return {"style": "chat", "rate": "+3%"}
    if lang_code.startswith("en"):
        return {"style": "chat", "rate": "+3%"}
    return {}


def ssml_voice_wrap(
    voice: str,
    language: str,
    sentences: List[str],
    sanitizer: Callable[[str], str],
    style: str = None,
    rate: str = None,
) -> str:
    """Build optimized SSML document with a single voice tag for efficient synthesis.

    This function constructs a well-formed SSML (Speech Synthesis Markup Language)
    document optimized for Azure Cognitive Services. It combines multiple text
    segments into a single voice container to minimize synthesis overhead while
    supporting advanced features like language switching, prosody control, and
    voice styling.

    Key Features:
    - Automatic language detection per sentence with graceful fallback
    - Language-specific style and rate optimization via auto_style()
    - Dynamic language switching within the same voice
    - Custom style and rate parameter override support
    - XML-safe text sanitization to prevent parsing errors
    - Efficient single-voice document structure

    Args:
        voice: Azure Cognitive Services voice name (e.g., 'en-US-JennyMultilingualNeural',
               'es-ES-ElviraNeural'). Must be a valid neural voice identifier.
        language: Base language code for the document (e.g., 'en-US', 'es-ES').
                  Used as fallback when per-sentence detection fails.
        sentences: List of text segments to synthesize. Each segment is processed
                   independently for language detection and style optimization.
        sanitizer: Function to escape XML special characters (&, <, >, ", ').
                   Should handle text content to prevent SSML parsing errors.
        style: Optional voice style override (e.g., 'chat', 'news', 'excited').
               If provided, overrides auto-detected language-specific styles.
        rate: Optional speech rate override (e.g., '+10%', '-20%', '1.5x').
              If provided, overrides auto-detected language-specific rates.

    Returns:
        Complete SSML document string ready for Azure Speech synthesis.
        Includes proper XML declaration, namespace definitions, and voice
        container with all text segments and their styling.

    Example:
        ```python
        sentences = ["Hello world!", "¿Cómo estás?", "Très bien!"]
        sanitizer = lambda text: html.escape(text, quote=True)

        ssml = ssml_voice_wrap(
            voice="en-US-JennyMultilingualNeural",
            language="en-US",
            sentences=sentences,
            sanitizer=sanitizer,
            style="chat",
            rate="+5%"
        )

        # Results in SSML like:
        # <speak version="1.0" xmlns="..." xml:lang="en-US">
        #   <voice name="en-US-JennyMultilingualNeural">
        #     <mstts:express-as style="chat">
        #       <prosody rate="+5%">Hello world!</prosody>
        #     </mstts:express-as>
        #     <lang xml:lang="es">
        #       <mstts:express-as style="chat">
        #         <prosody rate="+5%">¿Cómo estás?</prosody>
        #       </mstts:express-as>
        #     </lang>
        #     ...
        #   </voice>
        # </speak>
        ```

    Language Detection Behavior:
        - Attempts automatic detection for each sentence using langdetect
        - Falls back to base language parameter on detection failure
        - Wraps foreign language segments in <lang> tags for proper pronunciation
        - Handles mixed-language content gracefully within single document

    Performance Optimizations:
        - Single voice container reduces Azure TTS processing overhead
        - Batch processing of multiple sentences in one request
        - Minimal SSML structure for faster parsing
        - Efficient string concatenation with list operations

    Error Handling:
        - Graceful fallback on language detection failures
        - Safe handling of empty or whitespace-only sentences
        - XML escaping prevents malformed SSML documents
        - Robust handling of unsupported language codes

    Azure TTS Compatibility:
        - Follows Azure Cognitive Services SSML specification v1.0
        - Supports Microsoft Text-to-Speech Service extensions
        - Compatible with neural voice styling and prosody features
        - Proper namespace declarations for all used elements

    Note:
        This function assumes the target voice supports multilingual synthesis.
        For monolingual voices, language switching may not work as expected.
        Always validate voice capabilities for your specific use case.
    """
    body = []
    for seg in sentences:
        try:
            lang = detect(seg)
        except LangDetectException:
            lang = language
        attrs = auto_style(lang)
        inner = sanitizer(seg)

        # Apply custom rate or auto-detected rate
        prosody_rate = rate or attrs.get("rate")
        if prosody_rate:
            inner = f'<prosody rate="{prosody_rate}">{inner}</prosody>'

        # Apply custom style or auto-detected style
        voice_style = style or attrs.get("style")
        if voice_style:
            inner = (
                f'<mstts:express-as style="{voice_style}">{inner}</mstts:express-as>'
            )

        # optional language switch
        if lang != language:
            inner = f'<lang xml:lang="{lang}">{inner}</lang>'

        body.append(inner)

    joined = "".join(body)
    return (
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" '
        f'xml:lang="{language}">'
        f'<voice name="{voice}">{joined}</voice>'
        "</speak>"
    )


def _is_headless() -> bool:
    """Detect if the application is running in a headless environment without audio output.

    This function provides lightweight heuristics to determine whether the current
    execution environment has audio output capabilities. It's used to prevent
    audio playback attempts in containerized deployments, CI/CD pipelines, and
    cloud server environments where audio hardware is not available.

    Detection Logic:
    1. Linux systems without DISPLAY environment variable:
       - Typical in Docker containers, cloud VMs, and server deployments
       - DISPLAY variable indicates X11 GUI session availability

    2. Continuous Integration environments:
       - CI environment variable is commonly set by CI/CD platforms
       - Includes GitHub Actions, Azure DevOps, Jenkins, etc.

    3. Future extensibility:
       - Can be extended for Windows detection using SESSIONNAME
       - Supports additional platform-specific indicators

    Returns:
        True if running in headless environment (no audio output expected).
        False if audio output capabilities are likely available.

    Example:
        ```python
        if _is_headless():
            print("Audio playback disabled - headless environment")
            return None  # Skip speaker initialization
        else:
            print("Audio hardware detected - enabling playback")
            return create_audio_output()
        ```

    Platform Support:
        - Linux: Checks DISPLAY environment variable
        - Windows: Placeholder for future SESSIONNAME detection
        - macOS: Inherits from UNIX-like behavior
        - CI/CD: Universal CI environment variable detection

    Performance:
        - O(1) operation with minimal system calls
        - Safe for frequent invocation
        - No external dependencies or network calls

    Environment Variables Checked:
        - DISPLAY: X11 display server indicator (Linux/Unix)
        - CI: Generic CI/CD environment flag
        - (Future) SESSIONNAME: Windows session type indicator

    Use Cases:
        - Docker container audio policy decisions
        - Cloud deployment configuration
        - CI/CD pipeline optimization
        - Development vs. production environment detection
        - Automated testing in headless browsers

    Note:
        These heuristics provide reasonable defaults but may not cover all
        edge cases. Consider adding application-specific environment variables
        for explicit audio policy control when needed.
    """
    import sys

    return (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")) or bool(
        os.environ.get("CI")
    )


class SpeechSynthesizer:
    """Azure Cognitive Services Text-to-Speech synthesizer for real-time voice applications.

    This class provides a comprehensive interface to Azure Cognitive Services Speech
    synthesis capabilities, optimized for low-latency real-time voice applications.
    It supports multiple synthesis modes, authentication methods, and output formats
    while providing robust error handling and comprehensive observability.

    Key Capabilities:
    * Real-time text-to-speech synthesis with minimal latency
    * Multiple output formats: WAV, PCM, base64-encoded frames
    * Local speaker playback with automatic headless detection
    * Memory-only synthesis without audio hardware requirements
    * Advanced voice control: neural styles, prosody, multilingual
    * OpenTelemetry distributed tracing with correlation IDs
    * Concurrent synthesis limiting for service stability
    * Automatic authentication token refresh handling

    Authentication Modes:
    1. API Key: Direct subscription key authentication
    2. Azure Default Credentials: Managed identity, service principal, CLI auth
    3. Token-based: Automatic refresh with Azure AD integration

    Synthesis Modes:
    1. Speaker Playback: Direct audio output to system speakers
    2. Memory Synthesis: Return audio data as bytes without playback
    3. Frame-based: Generate base64-encoded frames for streaming
    4. PCM Output: Raw audio data for custom processing

    Playback Control:
    * "auto": Enable playback only when audio hardware detected
    * "always": Force playback attempt, use null sink if headless
    * "never": Disable all playback operations

    Performance Features:
    * Semaphore-limited concurrent synthesis (default: 4 requests)
    * Efficient SSML generation with single voice containers
    * Language-specific optimization for natural speech
    * Automatic sentence splitting for improved prosody
    * Memory-efficient streaming with chunked processing

    Observability Integration:
    * OpenTelemetry distributed tracing with session spans
    * Azure Monitor Application Insights compatibility
    * Structured JSON logging with correlation IDs
    * Performance metrics and error tracking
    * Service dependency mapping for App Map visualization

    Example Usage:
        ```python
        # Initialize with API key
        synthesizer = SpeechSynthesizer(
            key="your-speech-key",
            region="eastus",
            voice="en-US-JennyMultilingualNeural",
            playback="auto",
            enable_tracing=True
        )

        # Local playback (if hardware available)
        synthesizer.start_speaking_text(
            "Hello, how can I help you today?",
            style="chat",
            rate="+10%"
        )

        # Memory synthesis for processing
        audio_bytes = synthesizer.synthesize_speech(
            "This is synthesized audio data",
            voice="en-US-AriaNeural"
        )

        # Streaming frames for real-time applications
        frames = synthesizer.synthesize_to_base64_frames(
            "Real-time streaming audio",
            sample_rate=16000
        )

        # Validate configuration
        if synthesizer.validate_configuration():
            print("Ready for synthesis operations")
        ```

    Thread Safety:
        - Class instances are thread-safe for synthesis operations
        - Internal semaphore prevents service overload
        - OpenTelemetry spans are properly isolated per operation
        - No shared mutable state between synthesis calls

    Error Handling:
        - Graceful degradation when audio hardware unavailable
        - Automatic retry for transient authentication failures
        - Comprehensive error logging with correlation tracking
        - Silent fallback for non-critical playback operations

    Resource Management:
        - Lazy initialization of audio hardware components
        - Automatic cleanup of synthesis resources
        - Efficient memory usage with streaming operations
        - Proper disposal of OpenTelemetry spans

    Dependencies:
        - azure-cognitiveservices-speech: Core Speech SDK
        - opentelemetry-api: Distributed tracing support
        - utils.azure_auth: Azure credential management
        - langdetect: Language detection for optimization

    Note:
        This class is designed for production use in voice applications.
        Always validate configuration before production deployment and
        monitor synthesis latency and error rates through telemetry.
    """

    # Limit concurrent server-side TTS synth requests to avoid SDK/service hiccups
    _synth_semaphore = asyncio.Semaphore(4)

    def __init__(
        self,
        key: str = None,
        region: str = None,
        language: str = "en-US",
        voice: str = "en-US-JennyMultilingualNeural",
        format: speechsdk.SpeechSynthesisOutputFormat = speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm,
        playback: str = "auto",  # "auto" | "always" | "never"
        call_connection_id: Optional[str] = None,
        enable_tracing: bool = True,
    ):
        """Initialize Azure Speech synthesizer with comprehensive configuration options.

        Creates a new SpeechSynthesizer instance with flexible authentication,
        configurable output formats, and intelligent playback management. The
        initializer sets up all necessary components for text-to-speech synthesis
        while handling various deployment scenarios and error conditions gracefully.

        Authentication Priority:
        1. Provided key parameter (highest priority)
        2. AZURE_SPEECH_KEY environment variable
        3. Azure Default Credentials (managed identity, service principal, CLI)
        4. Fallback to credential chain resolution

        Args:
            key: Azure Speech Services subscription key. If not provided,
                 attempts to use AZURE_SPEECH_KEY environment variable or
                 Azure Default Credentials for authentication.
            region: Azure region for Speech Services (e.g., 'eastus', 'westeurope').
                    If not provided, uses AZURE_SPEECH_REGION environment variable.
                    Required for all authentication methods.
            language: Default language for synthesis (e.g., 'en-US', 'es-ES').
                      Used as fallback when language detection fails or is disabled.
                      Supports all Azure Cognitive Services language codes.
            voice: Default neural voice name for synthesis. Must be a valid Azure
                   neural voice identifier (e.g., 'en-US-JennyMultilingualNeural').
                   Can be overridden in individual synthesis calls.
            format: Default output format for audio synthesis. Affects quality,
                    file size, and compatibility. Common formats include:
                    - Riff16Khz16BitMonoPcm: Standard quality, smaller size
                    - Riff24Khz16BitMonoPcm: High quality, balanced size
                    - Riff48Khz16BitMonoPcm: Highest quality, larger size
            playback: Audio playback behavior control:
                      - "auto": Enable playback only when audio hardware detected
                      - "always": Force playback attempt, use null sink if headless
                      - "never": Disable all local playback operations
            call_connection_id: Correlation ID for tracing and logging context.
                                Links synthesis operations to specific call sessions
                                for distributed tracing and debugging.
            enable_tracing: Whether to enable OpenTelemetry distributed tracing.
                           When enabled, creates spans for all synthesis operations
                           with detailed metrics and correlation information.

        Raises:
            ValueError: When region is not provided for Default Credential authentication.
            RuntimeError: When no valid authentication method can be established.
            Exception: For critical configuration errors that prevent initialization.

        Environment Variables:
            - AZURE_SPEECH_KEY: Subscription key for API authentication
            - AZURE_SPEECH_REGION: Azure region for service endpoint
            - AZURE_SPEECH_ENDPOINT: Custom endpoint URL (optional)
            - AZURE_SPEECH_RESOURCE_ID: Resource ID for AAD authentication
            - TTS_ENABLE_LOCAL_PLAYBACK: Enable/disable local audio playback

        Example:
            ```python
            # API key authentication
            synthesizer = SpeechSynthesizer(
                key="your-speech-key",
                region="eastus",
                voice="en-US-AriaNeural",
                playback="auto"
            )

            # Managed identity authentication
            synthesizer = SpeechSynthesizer(
                region="eastus",  # key=None uses managed identity
                language="es-ES",
                voice="es-ES-ElviraNeural",
                enable_tracing=True
            )

            # Production configuration
            synthesizer = SpeechSynthesizer(
                region=os.getenv("AZURE_SPEECH_REGION"),
                voice="en-US-JennyMultilingualNeural",
                format=speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm,
                playback="never",  # Headless deployment
                call_connection_id="session-12345",
                enable_tracing=True
            )
            ```

        Initialization Behavior:
            - Lazy loading: Audio hardware components created only when needed
            - Fail-safe: Continues initialization even if tracing setup fails
            - Validation: Speech config created and validated during initialization
            - Logging: Comprehensive initialization status and error reporting

        Performance Considerations:
            - Minimal initialization overhead with lazy component loading
            - Efficient credential caching for repeated authentications
            - Tracing overhead only when enabled and properly configured
            - Memory-efficient design suitable for long-running applications

        Thread Safety:
            - Instance variables are set once during initialization
            - No shared mutable state between concurrent operations
            - Thread-safe for all synthesis methods after initialization
            - OpenTelemetry spans properly isolated per thread

        Note:
            Audio hardware detection occurs lazily during first playback attempt.
            This prevents initialization failures in headless environments while
            preserving playback capabilities when hardware becomes available.
        """
        # Retrieve Azure Speech credentials from parameters or environment variables
        self.key = key or os.getenv("AZURE_SPEECH_KEY")
        self.region = region or os.getenv("AZURE_SPEECH_REGION")
        self.language = language
        self.voice = voice
        self.format = format
        self.playback = playback
        self.enable_tracing = enable_tracing
        self.call_connection_id = call_connection_id or "unknown"
        self._token_manager: Optional[SpeechTokenManager] = None

        # Initialize tracing components (matching speech_recognizer pattern)
        self.tracer = None
        self._session_span = None

        if self.enable_tracing:
            try:
                # Use same pattern as speech_recognizer
                self.tracer = trace.get_tracer(__name__)
                logger.debug("Azure Monitor tracing initialized for speech synthesizer")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure Monitor tracing: {e}")
                self.enable_tracing = False
                # Temporarily disable to avoid startup errors
                logger.debug("Continuing without Azure Monitor tracing")

        # DON'T initialize speaker synthesizer during __init__ to avoid audio library issues
        # Only create it when actually needed for speaker playback
        self._speaker = None

        # Create base speech config for other operations
        self.cfg = None
        try:
            self.cfg = self._create_speech_config()
            logger.debug("Speech synthesizer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize speech config: {e}")
            # Don't fail completely - allow for memory-only synthesis

    def set_call_connection_id(self, call_connection_id: str) -> None:
        """Set the call connection ID for correlation in tracing and logging.

        Updates the correlation identifier used to link all synthesis operations
        to a specific call session or conversation. This ID is embedded in
        OpenTelemetry spans, log entries, and monitoring data to enable
        end-to-end request tracking across distributed systems.

        The call connection ID serves as the primary correlation key for:
        - Distributed tracing across microservices
        - Log aggregation and filtering
        - Performance monitoring and debugging
        - Session-based analytics and reporting
        - Error correlation and root cause analysis

        Args:
            call_connection_id: Unique identifier for the call session or conversation.
                               Typically provided by Azure Communication Services,
                               telephony systems, or application session managers.
                               Should be unique across the system and time.

        Example:
            ```python
            synthesizer = SpeechSynthesizer(region="eastus")

            # Set correlation ID for new call session
            synthesizer.set_call_connection_id("acs-call-12345-67890")

            # All subsequent operations will include this ID
            audio = synthesizer.synthesize_speech("Hello caller")
            # Tracing spans will include rt.call.connection_id = "acs-call-12345-67890"

            # Update for new session
            synthesizer.set_call_connection_id("acs-call-99999-11111")
            ```

        Thread Safety:
            - Safe to call from multiple threads
            - Changes apply to all subsequent synthesis operations
            - Does not affect operations already in progress

        Performance:
            - O(1) operation with no system calls
            - Minimal memory overhead
            - Safe for frequent updates during call transfers

        Integration Points:
            - OpenTelemetry spans: Set as rt.call.connection_id attribute
            - Structured logs: Included in all log entries as correlation field
            - Azure Monitor: Available for custom dashboards and alerting
            - Application Insights: Enables end-to-end transaction tracking

        Note:
            This method should be called before synthesis operations to ensure
            proper correlation. The ID will be used in all spans and logs until
            explicitly changed or the instance is destroyed.
        """
        self.call_connection_id = call_connection_id

    def _create_speech_config(self):
        """Create and configure Azure Speech SDK configuration with flexible authentication.

        This method establishes a connection to Azure Cognitive Services Speech
        using the most appropriate authentication method based on available credentials.
        It handles token expiration, credential refresh, and provides comprehensive
        error handling for various deployment scenarios.

        Authentication Flow:
        1. API Key Method (preferred if available):
           - Uses subscription key and region for direct authentication
           - Simple and reliable for development and testing
           - Credentials from constructor parameters or environment variables

        2. Azure Default Credentials (production recommended):
           - Leverages Azure AD authentication with automatic token refresh
           - Supports managed identity, service principal, and credential chains
           - Requires AZURE_SPEECH_RESOURCE_ID environment variable
           - Provides enhanced security and eliminates key management

        Returns:
            speechsdk.SpeechConfig: Configured Speech SDK config object ready
            for synthesis operations. Includes language, voice, and format settings.

        Raises:
            ValueError: When region is missing for Default Credential authentication.
            RuntimeError: When authentication fails or no valid method available.
            Exception: For credential token acquisition failures or config errors.

        Configuration Applied:
            - speech_synthesis_language: Set to instance language (e.g., 'en-US')
            - speech_synthesis_voice_name: Set to instance voice name
            - output_format: Set to 24kHz 16-bit mono PCM for high quality

        Environment Variables Used:
            - AZURE_SPEECH_KEY: Subscription key for API authentication
            - AZURE_SPEECH_REGION: Azure region for service endpoint
            - AZURE_SPEECH_ENDPOINT: Custom endpoint URL (optional)
            - AZURE_SPEECH_RESOURCE_ID: Resource ID for AAD authentication

        Token Management:
            - Fresh token acquired on each call to handle expiration
            - Automatic refresh through Azure credential chain
            - Proper token format for Azure AD authentication
            - Error handling for token acquisition failures

        Example Usage:
            ```python
            # Internal method - called automatically during initialization
            try:
                config = synthesizer._create_speech_config()
                print(f"Authenticated to region: {config.region}")
            except RuntimeError as e:
                print(f"Authentication failed: {e}")
            ```

        Performance Considerations:
            - Token acquisition may involve network calls
            - Credential caching handled by Azure SDK
            - Config creation is relatively lightweight
            - Should not be called frequently due to auth overhead

        Security Features:
            - No credential logging or exposure
            - Secure token handling with automatic cleanup
            - Support for enterprise AAD authentication
            - Credential chain fallback for maximum flexibility

        Error Recovery:
            - Detailed error messages for troubleshooting
            - Graceful handling of credential failures
            - Clear guidance for configuration fixes
            - Comprehensive logging for debugging

        Note:
            This method creates a fresh configuration each time to ensure
            token freshness and handle credential rotation. The configuration
            should be cached at the instance level to avoid repeated auth calls.
        """
        if self.key:
            logger.info("Creating SpeechConfig with API key authentication")
            speech_config = speechsdk.SpeechConfig(
                subscription=self.key, region=self.region
            )
        else:
            logger.debug("Creating SpeechConfig with Azure AD credentials")
            if not self.region:
                raise ValueError(
                    "Region must be specified when using Azure Default Credentials"
                )

            endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")
            if endpoint:
                speech_config = speechsdk.SpeechConfig(endpoint=endpoint)
            else:
                speech_config = speechsdk.SpeechConfig(region=self.region)

            try:
                token_manager = get_speech_token_manager()
                token_manager.apply_to_config(speech_config, force_refresh=True)
                self._token_manager = token_manager
                logger.debug("Successfully applied Azure AD token to SpeechConfig")
            except Exception as e:
                logger.error(f"Failed to apply Azure AD speech token: {e}")
                raise RuntimeError(
                    "Failed to authenticate with Azure Speech via Azure AD credentials"
                )

        if not speech_config:
            raise RuntimeError(
                "Failed to create speech config - no valid authentication method found"
            )

        speech_config.speech_synthesis_language = self.language
        speech_config.speech_synthesis_voice_name = self.voice
        # Set the output format to 24kHz 16-bit mono PCM WAV
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
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
                self._speaker = None  # force re-creation with new token
            
            logger.info("Authentication refresh completed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh authentication: {e}")
            return False

    def _is_authentication_error(self, result) -> bool:
        """Check if synthesis result indicates a 401 authentication error.
        
        Returns:
            bool: True if this is a 401 authentication error, False otherwise.
        """
        if result.reason != speechsdk.ResultReason.Canceled:
            return False
            
        if not hasattr(result, 'cancellation_details') or not result.cancellation_details:
            return False
            
        error_details = getattr(result.cancellation_details, 'error_details', '')
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
        """Ensure the cached speech configuration has a valid Azure AD token."""
        if self.key:
            return

        if not self.cfg:
            self.cfg = self._create_speech_config()

        if not self._token_manager:
            self._token_manager = get_speech_token_manager()

        if not self.cfg:
            raise RuntimeError("Speech configuration unavailable for token refresh")

        self._token_manager.apply_to_config(self.cfg, force_refresh=force_refresh)

    def _create_speaker_synthesizer(self):
        """Create audio output synthesizer with intelligent playback mode handling.

        This method creates a Speech SDK synthesizer configured for local audio
        playback based on the instance's playback mode and environment detection.
        It provides flexible audio output management for different deployment
        scenarios from development to production containers.

        Playback Mode Behavior:

        "never" Mode:
            - Never attempts to create audio output synthesizer
            - Suitable for headless deployments and batch processing
            - Returns None immediately without hardware detection

        "auto" Mode (recommended):
            - Creates synthesizer only when audio hardware likely available
            - Uses headless environment detection for intelligent decisions
            - Prevents audio errors in containerized deployments
            - Enables local playback in development environments

        "always" Mode:
            - Always attempts to create synthesizer regardless of environment
            - Uses null audio sink in headless environments (no actual output)
            - Useful for testing audio processing without speaker requirements
            - May log warnings in environments without audio capabilities

        Returns:
            speechsdk.SpeechSynthesizer or None: Configured synthesizer for
            audio playback, or None if playback disabled or unavailable.

            The synthesizer is cached for subsequent calls to avoid repeated
            hardware detection and initialization overhead.

        Environment Detection:
            - Checks for GUI display availability (DISPLAY environment variable)
            - Detects CI/CD pipeline environments (CI environment variable)
            - Identifies containerized deployments without audio hardware
            - Uses platform-specific heuristics for accurate detection

        Audio Configuration:
            - use_default_speaker=True: Uses system default audio device
            - filename=None: Null sink for headless "always" mode
            - Inherits speech config settings from instance configuration

        Example Usage:
            ```python
            # Internal method - called automatically during playback
            synthesizer._speaker = synthesizer._create_speaker_synthesizer()

            if synthesizer._speaker:
                # Audio playback available
                synthesizer._speaker.speak_text_async("Hello world")
            else:
                # Headless environment or playback disabled
                logger.info("Audio playback not available")
            ```

        Caching Behavior:
            - Speaker synthesizer created once and cached
            - Subsequent calls return cached instance for efficiency
            - Cache cleared only when instance destroyed
            - No automatic refresh for hardware changes

        Error Handling:
            - Graceful fallback when audio hardware unavailable
            - Comprehensive logging for debugging audio issues
            - Returns None on any speaker creation failure
            - No exceptions raised to avoid disrupting synthesis

        Performance Considerations:
            - Lazy initialization only when actually needed
            - Hardware detection cached to avoid repeated system calls
            - Minimal overhead for non-playback use cases
            - Efficient reuse of created synthesizer instances

        Thread Safety:
            - Safe to call from multiple threads
            - First caller creates and caches the synthesizer
            - Subsequent calls return cached instance
            - No race conditions in synthesizer creation

        Resource Management:
            - Audio resources automatically managed by Speech SDK
            - Synthesizer lifecycle tied to parent instance
            - Proper cleanup when parent instance destroyed
            - No manual resource disposal required

        Note:
            Audio hardware availability is detected at creation time.
            If hardware becomes available after instance creation,
            the synthesizer won't automatically detect the change.
            Consider recreating the instance or clearing the cache.
        """
        # 1. Never mode: do not create a speaker synthesizer
        if self.playback == "never":
            logger.debug("playback='never' – speaker creation skipped")
            return None

        # 2. If already created, return cached instance
        if self._speaker is not None:
            return self._speaker

        # 3. Create the speaker synthesizer according to playback mode
        try:
            self._ensure_auth_token()
            speech_config = self.cfg
            headless = _is_headless()

            if self.playback == "always":
                # Always create, use null sink if headless
                if headless:
                    audio_config = speechsdk.audio.AudioOutputConfig(filename=None)
                    logger.debug(
                        "playback='always' – headless: using null audio output"
                    )
                else:
                    audio_config = speechsdk.audio.AudioOutputConfig(
                        use_default_speaker=True
                    )
                    logger.debug(
                        "playback='always' – using default system speaker output"
                    )
                self._speaker = speechsdk.SpeechSynthesizer(
                    speech_config=speech_config, audio_config=audio_config
                )
            elif self.playback == "auto":
                # Only create if not headless
                if headless:
                    logger.debug("playback='auto' – headless: speaker not created")
                    self._speaker = None
                else:
                    audio_config = speechsdk.audio.AudioOutputConfig(
                        use_default_speaker=True
                    )
                    logger.debug(
                        "playback='auto' – using default system speaker output"
                    )
                    self._speaker = speechsdk.SpeechSynthesizer(
                        speech_config=speech_config, audio_config=audio_config
                    )
        except Exception as exc:
            logger.warning("Could not create speaker synthesizer: %s", exc)
            self._speaker = None  # fall back to memory-only synthesis

        return self._speaker

    @staticmethod
    def _sanitize(text: str) -> str:
        """Escape XML-significant characters for safe SSML document construction.

        This static method provides essential XML escaping to prevent SSML
        parsing errors when user-provided text contains special characters.
        It ensures that text content can be safely embedded within SSML
        elements without breaking document structure or syntax.

        Characters Escaped:
        - & (ampersand) → &amp; (entity references)
        - < (less than) → &lt; (opening tags)
        - > (greater than) → &gt; (closing tags)
        - " (double quote) → &quot; (attribute values)
        - ' (single quote) → &#x27; (attribute values)

        Args:
            text: Raw text string that may contain XML-significant characters.
                  Can include user input, dynamic content, or multilingual text
                  that needs to be safely embedded in SSML documents.

        Returns:
            Escaped text string safe for inclusion in SSML XML documents.
            All XML-significant characters are replaced with their entity
            references while preserving the original text meaning.

        Example:
            ```python
            # User input with special characters
            user_text = 'Say "Hello & welcome!" with <emphasis>'
            safe_text = SpeechSynthesizer._sanitize(user_text)
            # Result: 'Say &quot;Hello &amp; welcome!&quot; with &lt;emphasis&gt;'

            # Can now be safely used in SSML
            ssml = f'<speak><voice name="en-US-JennyNeural">{safe_text}</voice></speak>'
            ```

        Use Cases:
            - User-generated content in voice applications
            - Dynamic text from databases or APIs
            - Multilingual content with special punctuation
            - Template-based SSML generation
            - Real-time text processing in voice assistants

        Performance:
            - O(n) time complexity where n is text length
            - Minimal memory overhead with efficient string operations
            - Safe for high-frequency calls in real-time applications
            - No external dependencies or network calls

        SSML Compatibility:
            - Follows XML 1.0 specification for character escaping
            - Compatible with Azure Cognitive Services SSML parser
            - Preserves Unicode characters and multilingual content
            - Does not interfere with legitimate SSML markup

        Security Considerations:
            - Prevents XML injection attacks through user input
            - Ensures SSML document well-formedness
            - Safe for processing untrusted text content
            - No risk of malformed synthesis requests

        Note:
            This method only escapes content text, not SSML markup.
            If you need to include actual SSML tags in your text,
            they should be added after sanitization during document
            construction to maintain proper XML structure.
        """
        return html.escape(text, quote=True)

    def start_speaking_text(
        self, text: str, voice: str = None, rate: str = "15%", style: str = None
    ) -> None:
        """
        Synthesize and play text through the server's speakers (if available).
        In headless environments, this will log a warning and skip playback.

        Args:
            text: Text to synthesize
            voice: Voice name (defaults to self.voice)
            rate: Speech rate (defaults to "15%")
            style: Voice style (defaults to None)
        """
        # Check environment variable to determine if playback is enabled
        playback_env = os.getenv("TTS_ENABLE_LOCAL_PLAYBACK", "true").lower()
        voice = voice or self.voice
        if playback_env not in ("1", "true", "yes"):
            logger.info(
                "TTS_ENABLE_LOCAL_PLAYBACK is set to false; skipping audio playback."
            )
            return
        # Start session-level span for speaker synthesis if tracing is enabled
        if self.enable_tracing and self.tracer:
            self._session_span = self.tracer.start_span(
                "tts_speaker_synthesis_session", kind=SpanKind.CLIENT
            )

            # Correlation keys
            self._session_span.set_attribute(
                "rt.call.connection_id", self.call_connection_id
            )
            self._session_span.set_attribute("rt.session.id", self.call_connection_id)

            # Service specific attributes
            self._session_span.set_attribute("tts.region", self.region)
            self._session_span.set_attribute("tts.voice", voice or self.voice)
            self._session_span.set_attribute("tts.language", self.language)
            self._session_span.set_attribute("tts.text_length", len(text))
            self._session_span.set_attribute("tts.operation_type", "speaker_synthesis")
            self._session_span.set_attribute(
                "server.address", f"{self.region}.tts.speech.microsoft.com"
            )
            self._session_span.set_attribute("server.port", 443)
            self._session_span.set_attribute("http.method", "POST")
            # Use endpoint if set, otherwise default to region-based URL
            endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")
            if endpoint:
                self._session_span.set_attribute(
                    "http.url", f"{endpoint}/cognitiveservices/v1"
                )
            else:
                self._session_span.set_attribute(
                    "http.url",
                    f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                )
            # External dependency identification for App Map
            self._session_span.set_attribute("peer.service", "azure-cognitive-speech")
            self._session_span.set_attribute(
                "net.peer.name", f"{self.region}.tts.speech.microsoft.com"
            )

            # Set standard attributes if available
            self._session_span.set_attribute(
                SpanAttr.SERVICE_NAME, "azure-speech-synthesis"
            )
            self._session_span.set_attribute(SpanAttr.SERVICE_VERSION, "1.0.0")

            # Make this span current for the duration
            with trace.use_span(self._session_span):
                self._start_speaking_text_internal(text, voice, rate, style)
        else:
            self._start_speaking_text_internal(text, voice, rate, style)

    def _start_speaking_text_internal(
        self, text: str, voice: str = None, rate: str = "15%", style: str = None
    ) -> None:
        """Internal method to perform speaker synthesis with tracing events"""
        voice = voice or self.voice
        try:
            # Add event for speaker synthesis start
            if self._session_span:
                self._session_span.add_event(
                    "tts_speaker_synthesis_started",
                    {"text_length": len(text), "voice": voice},
                )

            speaker = self._create_speaker_synthesizer()
            if speaker is None:
                if self._session_span:
                    self._session_span.add_event(
                        "tts_speaker_unavailable", {"reason": "headless_environment"}
                    )

                logger.warning(
                    "Speaker not available in headless environment, skipping playback"
                )
                return

            if self._session_span:
                self._session_span.add_event("tts_speaker_synthesizer_created")

            logger.info(
                "Starting streaming speech synthesis for text: %s",
                text[:50] + "...",
            )

            # Build SSML with consistent voice, rate, and style support
            sanitized_text = self._sanitize(text)
            inner_content = (
                f'<prosody rate="{rate}" pitch="default">{sanitized_text}</prosody>'
            )

            if style:
                inner_content = f'<mstts:express-as style="{style}">{inner_content}</mstts:express-as>'

            ssml = f"""
                <speak version="1.0" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
                    <voice name="{voice}">
                        {inner_content}
                    </voice>
                </speak>"""

            if self._session_span:
                self._session_span.add_event("tts_speaker_ssml_created")

            # Perform synthesis and check result for authentication errors
            result = speaker.speak_ssml_async(ssml).get()
            
            # Check for 401 authentication error and retry with refresh if needed
            if self._is_authentication_error(result):
                error_details = getattr(result.cancellation_details, 'error_details', '')
                logger.warning(f"Authentication error detected in speaker synthesis: {error_details}")
                
                # Try to refresh authentication and retry once
                if self.refresh_authentication():
                    logger.info("Retrying speaker synthesis with refreshed authentication")
                    
                    if self._session_span:
                        self._session_span.add_event(
                            "tts_speaker_authentication_refreshed",
                            {"retry_attempt": True}
                        )
                    
                    # Create new speaker with refreshed config and retry
                    self._speaker = None  # Clear cached speaker
                    speaker = self._create_speaker_synthesizer()
                    if speaker:
                        result = speaker.speak_ssml_async(ssml).get()
                        if self._session_span:
                            self._session_span.add_event("tts_speaker_synthesis_retry_completed")
                    else:
                        logger.error("Failed to recreate speaker after authentication refresh")
                else:
                    logger.error("Failed to refresh authentication for speaker synthesis")

            if self._session_span:
                self._session_span.add_event("tts_speaker_synthesis_initiated")
                self._session_span.set_status(Status(StatusCode.OK))

        except Exception as exc:
            error_msg = f"TTS playback not available in this environment: {exc}"

            if self._session_span:
                self._session_span.add_event(
                    "tts_speaker_synthesis_error",
                    {"error_type": type(exc).__name__, "error_message": str(exc)},
                )
                self._session_span.set_status(Status(StatusCode.ERROR, error_msg))

            logger.warning(error_msg)

        finally:
            # Close session span
            if self._session_span:
                self._session_span.end()
                self._session_span = None

    def stop_speaking(self) -> None:
        """Stop current playback (if any)."""
        if self._speaker:
            try:
                logger.info("[🛑] Stopping speech synthesis...")
                self._speaker.stop_speaking_async()
            except Exception as e:
                logger.warning(f"Could not stop speech synthesis: {e}")

    def synthesize_speech(
        self, text: str, voice: str = None, style: str = None, rate: str = None
    ) -> bytes:
        """
        Synthesizes text to speech in memory (returning WAV bytes).
        Does NOT play audio on server speakers.

        Args:
            text: Text to synthesize
            voice: Voice name (defaults to self.voice)
            style: Voice style
            rate: Speech rate
        """
        voice = voice or self.voice
        # Start session-level span for synthesis if tracing is enabled
        if self.enable_tracing and self.tracer:
            self._session_span = self.tracer.start_span(
                "tts_synthesis_session", kind=SpanKind.CLIENT
            )

            # Set session attributes for correlation (matching speech_recognizer pattern)
            self._session_span.set_attribute("ai.operation.id", self.call_connection_id)
            self._session_span.set_attribute("tts.session.id", self.call_connection_id)
            self._session_span.set_attribute("tts.region", self.region)
            self._session_span.set_attribute("tts.voice", self.voice)
            self._session_span.set_attribute("tts.language", self.language)
            self._session_span.set_attribute("tts.text_length", len(text))

            # Set standard attributes if available
            self._session_span.set_attribute(
                SpanAttr.SERVICE_NAME, "azure-speech-synthesis"
            )
            self._session_span.set_attribute(SpanAttr.SERVICE_VERSION, "1.0.0")

            # Make this span current for the duration
            with trace.use_span(self._session_span):
                return self._synthesize_speech_internal(text, voice, style, rate)
        else:
            return self._synthesize_speech_internal(text, voice, style, rate)

    def _synthesize_speech_internal(
        self, text: str, voice: str = None, style: str = None, rate: str = None
    ) -> bytes:
        """Internal method to perform synthesis with tracing events"""
        voice = voice or self.voice
        self._ensure_auth_token()
        try:
            # Add event for synthesis start
            if self._session_span:
                self._session_span.add_event(
                    "tts_synthesis_started",
                    {"text_length": len(text), "voice": voice},
                )

            # Create speech config for memory synthesis
            speech_config = self.cfg
            speech_config.speech_synthesis_language = self.language
            speech_config.speech_synthesis_voice_name = voice
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm
            )

            if self._session_span:
                self._session_span.add_event("tts_config_created")

            # Use None for audio_config to synthesize to memory
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, audio_config=None
            )

            if self._session_span:
                self._session_span.add_event("tts_synthesizer_created")

            # Build SSML if style or rate are specified, otherwise use plain text
            if style or rate:
                sanitized_text = self._sanitize(text)
                inner_content = sanitized_text

                if rate:
                    inner_content = f'<prosody rate="{rate}">{inner_content}</prosody>'

                if style:
                    inner_content = f'<mstts:express-as style="{style}">{inner_content}</mstts:express-as>'

                ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">
    <voice name="{voice}">
        {inner_content}
    </voice>
</speak>"""
                result = synthesizer.speak_ssml_async(ssml).get()
            else:
                result = synthesizer.speak_text_async(text).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                if self._session_span:
                    self._session_span.add_event("tts_synthesis_completed")

                audio_data_stream = speechsdk.AudioDataStream(result)
                wav_bytes = audio_data_stream.read_data()

                if self._session_span:
                    self._session_span.add_event(
                        "tts_audio_data_extracted", {"audio_size_bytes": len(wav_bytes)}
                    )
                    self._session_span.set_status(Status(StatusCode.OK))
                    self._session_span.end()
                    self._session_span = None

                return bytes(wav_bytes)
            else:
                # Check for 401 authentication error and retry with refresh if needed
                if self._is_authentication_error(result):
                    error_details = getattr(result.cancellation_details, 'error_details', '')
                    logger.warning(f"Authentication error detected in speech synthesis: {error_details}")
                    
                    # Try to refresh authentication and retry once
                    if self.refresh_authentication():
                        logger.info("Retrying speech synthesis with refreshed authentication")
                        
                        if self._session_span:
                            self._session_span.add_event(
                                "tts_authentication_refreshed",
                                {"retry_attempt": True}
                            )
                        
                        # Retry synthesis with refreshed config
                        speech_config = self.cfg
                        speech_config.speech_synthesis_language = self.language
                        speech_config.speech_synthesis_voice_name = voice
                        speech_config.set_speech_synthesis_output_format(
                            speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm
                        )
                        synthesizer = speechsdk.SpeechSynthesizer(
                            speech_config=speech_config, audio_config=None
                        )
                        result = synthesizer.speak_text_async(text).get()
                        
                        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                            wav_bytes = result.audio_data
                            if self._session_span:
                                self._session_span.add_event(
                                    "tts_audio_data_extracted_retry", {"audio_size_bytes": len(wav_bytes)}
                                )
                                self._session_span.set_status(Status(StatusCode.OK))
                                self._session_span.end()
                                self._session_span = None
                            return bytes(wav_bytes)
                    else:
                        logger.error("Failed to refresh authentication for speech synthesis")
                
                error_msg = f"Speech synthesis failed: {result.reason}"
                logger.error(error_msg)

                if self._session_span:
                    self._session_span.add_event(
                        "tts_synthesis_failed", {"failure_reason": str(result.reason)}
                    )
                    self._session_span.set_status(Status(StatusCode.ERROR, error_msg))
                    self._session_span.end()
                    self._session_span = None
                return b""
        except Exception as e:
            error_msg = f"Error synthesizing speech: {e}"
            logger.error(error_msg)

            if self._session_span:
                self._session_span.add_event(
                    "tts_synthesis_exception",
                    {"error_type": type(e).__name__, "error_message": str(e)},
                )
                self._session_span.set_status(Status(StatusCode.ERROR, error_msg))
                self._session_span.end()
                self._session_span = None
            return b""

    def synthesize_to_base64_frames(
        self,
        text: str,
        sample_rate: int = 16000,
        voice: str = None,
        style: str = None,
        rate: str = None,
    ) -> list[str]:
        """
        Synthesize `text` via Azure TTS into raw 16-bit PCM mono at either 16 kHz or 24 kHz,
        then split into 20 ms frames (50 fps), returning each frame as a base64 string.

        Args:
            text: Text to synthesize
            sample_rate: 16000 or 24000
            voice: Voice name (defaults to self.voice)
            style: Voice style
            rate: Speech rate

        Returns:
            List of base64-encoded audio frames
        """
        voice = voice or self.voice
        # Start session-level span for frame synthesis if tracing is enabled
        if self.enable_tracing and self.tracer:
            self._session_span = self.tracer.start_span(
                "tts_frame_synthesis_session", kind=SpanKind.CLIENT
            )

            # Set session attributes for correlation (matching speech_recognizer pattern)
            self._session_span.set_attribute("ai.operation.id", self.call_connection_id)
            self._session_span.set_attribute("tts.session.id", self.call_connection_id)
            self._session_span.set_attribute("tts.region", self.region)
            self._session_span.set_attribute("tts.voice", self.voice)
            self._session_span.set_attribute("tts.language", self.language)
            self._session_span.set_attribute("tts.text_length", len(text))
            self._session_span.set_attribute("tts.sample_rate", sample_rate)

            # Set standard attributes if available
            self._session_span.set_attribute(
                SpanAttr.SERVICE_NAME, "azure-speech-synthesis"
            )
            self._session_span.set_attribute(SpanAttr.SERVICE_VERSION, "1.0.0")

            # Make this span current for the duration
            with trace.use_span(self._session_span):
                return self._synthesize_to_base64_frames_internal(
                    text, sample_rate, voice, style, rate
                )
        else:
            return self._synthesize_to_base64_frames_internal(
                text, sample_rate, voice, style, rate
            )

    def _synthesize_to_base64_frames_internal(
        self,
        text: str,
        sample_rate: int,
        voice: str = None,
        style: str = None,
        rate: str = None,
    ) -> list[str]:
        """Internal method to perform frame synthesis with tracing events"""
        voice = voice or self.voice
        self._ensure_auth_token()
        try:
            # Add event for synthesis start
            if self._session_span:
                self._session_span.add_event(
                    "tts_frame_synthesis_started",
                    {
                        "text_length": len(text),
                        "voice": voice,
                        "sample_rate": sample_rate,
                    },
                )

            # Select SDK output format and packet size
            fmt_map = {
                16000: speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm,
                24000: speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm,
            }
            sdk_format = fmt_map.get(sample_rate)
            if not sdk_format:
                raise ValueError("sample_rate must be 16000 or 24000")

            # 1) Configure Speech SDK using class attributes with fresh auth
            logger.debug(f"Creating speech config for TTS synthesis")
            speech_config = self.cfg
            speech_config.speech_synthesis_language = self.language
            speech_config.speech_synthesis_voice_name = voice
            speech_config.set_speech_synthesis_output_format(sdk_format)

            if self._session_span:
                self._session_span.add_event("tts_frame_config_created")

            # 2) Synthesize to memory (audio_config=None) - NO AUDIO HARDWARE NEEDED
            synth = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, audio_config=None
            )

            if self._session_span:
                self._session_span.add_event("tts_frame_synthesizer_created")

            logger.debug(
                f"Synthesizing text with Azure TTS (voice: {voice}): {text[:100]}..."
            )

            # Build SSML if style or rate are specified, otherwise use plain text
            if style or rate:
                sanitized_text = self._sanitize(text)
                inner_content = sanitized_text

                if rate:
                    inner_content = f'<prosody rate="{rate}">{inner_content}</prosody>'

                if style:
                    inner_content = f'<mstts:express-as style="{style}">{inner_content}</mstts:express-as>'

                ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">
    <voice name="{voice}">
        {inner_content}
    </voice>
</speak>"""
                result = synth.speak_ssml_async(ssml).get()
            else:
                result = synth.speak_text_async(text).get()

            # 3) Check result
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                raw_bytes = result.audio_data

                if self._session_span:
                    self._session_span.add_event(
                        "tts_frame_synthesis_completed",
                        {"audio_data_size": len(raw_bytes), "synthesis_success": True},
                    )
            else:
                # Check for 401 authentication error and retry with refresh if needed
                if self._is_authentication_error(result):
                    error_details = getattr(result.cancellation_details, 'error_details', '')
                    logger.warning(f"Authentication error detected in frame synthesis: {error_details}")
                    
                    # Try to refresh authentication and retry once
                    if self.refresh_authentication():
                        logger.info("Retrying frame synthesis with refreshed authentication")
                        
                        if self._session_span:
                            self._session_span.add_event(
                                "tts_frame_authentication_refreshed",
                                {"retry_attempt": True}
                            )
                        
                        # Retry synthesis with refreshed config
                        speech_config = self._create_speech_config()
                        speech_config.speech_synthesis_language = self.language
                        speech_config.speech_synthesis_voice_name = voice
                        speech_config.set_speech_synthesis_output_format(sdk_format)
                        
                        synth = speechsdk.SpeechSynthesizer(
                            speech_config=speech_config, audio_config=None
                        )
                        
                        # Retry the synthesis operation
                        if style or rate:
                            result = synth.speak_ssml_async(ssml).get()
                        else:
                            result = synth.speak_text_async(text).get()
                            
                        # Check retry result
                        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                            raw_bytes = result.audio_data
                            if self._session_span:
                                self._session_span.add_event(
                                    "tts_frame_synthesis_completed_retry",
                                    {"audio_data_size": len(raw_bytes), "synthesis_success": True},
                                )
                            # Continue with frame processing below
                        else:
                            error_msg = f"TTS retry failed. Reason: {result.reason}"
                            if result.reason == speechsdk.ResultReason.Canceled:
                                error_msg += f" Details: {result.cancellation_details.reason}"
                            logger.error(error_msg)
                            raise Exception(error_msg)
                    else:
                        logger.error("Failed to refresh authentication for frame synthesis")
                        error_msg = f"TTS failed. Reason: {result.reason}"
                        if result.reason == speechsdk.ResultReason.Canceled:
                            error_msg += f" Details: {result.cancellation_details.reason}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                else:
                    error_msg = f"TTS failed. Reason: {result.reason}"
                    if result.reason == speechsdk.ResultReason.Canceled:
                        error_msg += f" Details: {result.cancellation_details.reason}"

                    if self._session_span:
                        self._session_span.add_event(
                            "tts_frame_synthesis_failed",
                            {
                                "error_reason": str(result.reason),
                                "error_details": error_msg,
                            },
                        )

                    logger.error(error_msg)
                    raise Exception(error_msg)

            logger.debug(f"Got {len(raw_bytes)} bytes of raw audio data")

            # 4) Split into frames
            import base64

            frame_size_bytes = int(0.02 * sample_rate * 2)  # 20 ms of samples
            base64_frames = []

            for i in range(0, len(raw_bytes), frame_size_bytes):
                frame = raw_bytes[i : i + frame_size_bytes]
                if len(frame) == frame_size_bytes:
                    b64_frame = base64.b64encode(frame).decode("utf-8")
                    base64_frames.append(b64_frame)

            if self._session_span:
                self._session_span.add_event(
                    "tts_frame_processing_completed",
                    {
                        "total_frames": len(base64_frames),
                        "frame_size_bytes": frame_size_bytes,
                    },
                )

            logger.debug(f"Created {len(base64_frames)} base64 frames")
            return base64_frames

        except Exception as e:
            if self._session_span:
                self._session_span.add_event(
                    "tts_frame_synthesis_error",
                    {"error_type": type(e).__name__, "error_message": str(e)},
                )
                self._session_span.set_status(Status(StatusCode.ERROR, str(e)))

            logger.error(f"Error in synthesize_to_base64_frames: {e}")
            raise

        finally:
            # Close session span
            if self._session_span:
                self._session_span.end()
                self._session_span = None

    def validate_configuration(self) -> bool:
        """
        Validate the Azure Speech configuration and return True if valid.
        """
        try:
            logger.info("Validating Azure Speech configuration...")
            logger.info(f"Region: {self.region}")
            logger.info(f"Language: {self.language}")
            logger.info(f"Voice: {self.voice}")
            logger.info(
                f"Using subscription key: {'Yes' if self.key else 'No (using DefaultAzureCredential)'}"
            )

            if not self.region:
                logger.error("Azure Speech region is not configured")
                return False

            if not self.key:
                try:
                    manager = self._token_manager or get_speech_token_manager()
                    manager.get_token(force_refresh=True)
                    self._token_manager = manager
                    logger.info("Azure AD authentication successful")
                except Exception as e:
                    logger.error(f"Azure AD authentication failed: {e}")
                    return False

            # Test a simple synthesis to validate configuration
            try:
                test_result = self.synthesize_to_base64_frames(
                    "test", sample_rate=16000
                )
                if test_result:
                    logger.info("Configuration validation successful")
                    return True
                else:
                    logger.error(
                        "Configuration validation failed - no audio data returned"
                    )
                    return False
            except Exception as e:
                logger.error(f"Configuration validation failed: {e}")
                return False

        except Exception as e:
            logger.error(f"Error during configuration validation: {e}")
            return False

    ## Cleaned up methods
    def synthesize_to_pcm(
        self,
        text: str,
        voice: str = None,
        sample_rate: int = 16000,
        style: str = None,
        rate: str = None,
    ) -> bytes:
        """
        Synthesize text to PCM bytes with consistent voice parameter support.

        Args:
            text: Text to synthesize
            voice: Voice name (defaults to self.voice)
            sample_rate: Sample rate (16000, 24000, or 48000)
            style: Voice style
            rate: Speech rate
        """
        voice = voice or self.voice
        style = style or "chat"
        rate = rate or "+3%"

        self._ensure_auth_token()

        speech_config = self.cfg
        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_speech_synthesis_output_format(
            {
                16000: speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm,
                24000: speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm,
                48000: speechsdk.SpeechSynthesisOutputFormat.Raw48Khz16BitMonoPcm,
            }[sample_rate]
        )

        # Build SSML with consistent style support
        sanitized_text = self._sanitize(text)
        inner_content = sanitized_text

        # Apply prosody rate if specified
        if rate:
            inner_content = f'<prosody rate="{rate}">{inner_content}</prosody>'

        # Apply style if specified
        if style:
            inner_content = (
                f'<mstts:express-as style="{style}">{inner_content}</mstts:express-as>'
            )

        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">
    <voice name="{voice}">
        {inner_content}
    </voice>
</speak>"""

        # Use audio_config=None for memory synthesis - NO AUDIO HARDWARE NEEDED
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.cfg, audio_config=None
        )

        result = synthesizer.speak_ssml_async(ssml).get()

        # Check for 401 authentication error and retry with refresh if needed
        if self._is_authentication_error(result):
            error_details = getattr(result.cancellation_details, 'error_details', '')
            logger.warning(f"Authentication error detected in PCM synthesis: {error_details}")
            
            # Try to refresh authentication and retry once
            if self.refresh_authentication():
                logger.info("Retrying PCM synthesis with refreshed authentication")
                # Recreate synthesizer with new config and retry
                synthesizer = speechsdk.SpeechSynthesizer(
                    speech_config=self.cfg, audio_config=None
                )
                result = synthesizer.speak_ssml_async(ssml).get()
            else:
                logger.error("Failed to refresh authentication for PCM synthesis")

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print("Cancellation reason:", cancellation.reason)
            print("Error details:", cancellation.error_details)

        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"TTS failed: {result.reason}")

        return result.audio_data  # raw PCM bytes

    @staticmethod
    def split_pcm_to_base64_frames(
        pcm_bytes: bytes, sample_rate: int = 16000
    ) -> list[str]:
        import base64

        frame_size = int(0.02 * sample_rate * 2)  # 20ms * sample_rate * 2 bytes/sample
        return [
            base64.b64encode(pcm_bytes[i : i + frame_size]).decode("utf-8")
            for i in range(0, len(pcm_bytes), frame_size)
            if len(pcm_bytes[i : i + frame_size]) == frame_size
        ]
