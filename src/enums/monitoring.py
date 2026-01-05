from enum import Enum


# Span attribute keys for Azure App Insights OpenTelemetry logging
class SpanAttr(str, Enum):
    """
    Standardized span attribute keys for OpenTelemetry tracing.

    These attributes follow OpenTelemetry semantic conventions and are optimized
    for Azure Application Insights Application Map visualization.

    Attribute Categories:
    - Core: Basic correlation and identification
    - Application Map: Required for proper dependency visualization
    - GenAI: OpenTelemetry GenAI semantic conventions for LLM observability
    - Speech: Azure Speech Services metrics
    - ACS: Azure Communication Services
    - WebSocket: Real-time communication tracking
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # CORE ATTRIBUTES - Basic correlation and identification
    # ═══════════════════════════════════════════════════════════════════════════
    CORRELATION_ID = "correlation.id"
    CALL_CONNECTION_ID = "call.connection.id"
    SESSION_ID = "session.id"
    # deepcode ignore NoHardcodedCredentials: This is not a credential, but an attribute label
    USER_ID = "user.id"
    OPERATION_NAME = "operation.name"
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    STATUS_CODE = "status.code"
    ERROR_TYPE = "error.type"
    ERROR_MESSAGE = "error.message"
    TRACE_ID = "trace.id"
    SPAN_ID = "span.id"

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION MAP ATTRIBUTES - Required for App Insights dependency visualization
    # ═══════════════════════════════════════════════════════════════════════════
    # These create edges (connectors) between nodes in Application Map
    PEER_SERVICE = "peer.service"  # Target service name (creates edge)
    SERVER_ADDRESS = "server.address"  # Target hostname/IP
    SERVER_PORT = "server.port"  # Target port
    NET_PEER_NAME = "net.peer.name"  # Legacy peer name (backwards compat)
    DB_SYSTEM = "db.system"  # Database type (redis, cosmosdb, etc.)
    DB_OPERATION = "db.operation"  # Database operation (GET, SET, query)
    DB_NAME = "db.name"  # Database/container name
    HTTP_METHOD = "http.method"  # HTTP method (GET, POST, etc.)
    HTTP_URL = "http.url"  # Full request URL
    HTTP_STATUS_CODE = "http.status_code"  # Response status code

    # ═══════════════════════════════════════════════════════════════════════════
    # GENAI SEMANTIC CONVENTIONS - OpenTelemetry GenAI standard attributes
    # See: https://opentelemetry.io/docs/specs/semconv/gen-ai/
    # ═══════════════════════════════════════════════════════════════════════════
    # Provider & Operation
    GENAI_SYSTEM = "gen_ai.system"  # Deprecated, use GENAI_PROVIDER_NAME
    GENAI_PROVIDER_NAME = "gen_ai.provider.name"  # e.g., "azure.ai.openai"
    GENAI_OPERATION_NAME = "gen_ai.operation.name"  # e.g., "chat", "embeddings"

    # Request attributes
    GENAI_REQUEST_MODEL = "gen_ai.request.model"  # Requested model name
    GENAI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"  # Max tokens requested
    GENAI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    GENAI_REQUEST_TOP_P = "gen_ai.request.top_p"
    GENAI_REQUEST_SEED = "gen_ai.request.seed"
    GENAI_REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
    GENAI_REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"

    # Response attributes
    GENAI_RESPONSE_MODEL = "gen_ai.response.model"  # Actual model used
    GENAI_RESPONSE_ID = "gen_ai.response.id"  # Response identifier
    GENAI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"  # e.g., ["stop"]

    # Token usage
    GENAI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"  # Prompt tokens
    GENAI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"  # Completion tokens

    # Tool/Function calling
    GENAI_TOOL_NAME = "gen_ai.tool.name"  # Tool being executed
    GENAI_TOOL_CALL_ID = "gen_ai.tool.call.id"  # Unique tool call ID
    GENAI_TOOL_TYPE = "gen_ai.tool.type"  # function, extension, datastore

    # Timing metrics
    GENAI_CLIENT_OPERATION_DURATION = "gen_ai.client.operation.duration"
    GENAI_SERVER_TIME_TO_FIRST_TOKEN = "gen_ai.server.time_to_first_token"

    # ── Responses Endpoint & Advanced Model Support ──────────────────────────
    # OpenAI /responses endpoint specific attributes (for o-reasoning/gpt-5)
    GENAI_ENDPOINT_TYPE = "gen_ai.endpoint.type"  # "chat" or "responses"
    GENAI_REASONING_TOKENS = "gen_ai.usage.reasoning_tokens"  # Reasoning tokens used
    GENAI_REASONING_EFFORT = "gen_ai.request.reasoning_effort"  # "low", "medium", "high"
    GENAI_MIN_P = "gen_ai.request.min_p"  # Minimum probability threshold
    GENAI_TYPICAL_P = "gen_ai.request.typical_p"  # Typical sampling parameter
    GENAI_VERBOSITY = "gen_ai.request.verbosity"  # Output verbosity level (0-2)
    GENAI_MODEL_VERSION = "gen_ai.response.model_version"  # Model version string
    GENAI_SYSTEM_FINGERPRINT = "gen_ai.response.system_fingerprint"  # System config fingerprint
    GENAI_INCLUDE_REASONING = "gen_ai.request.include_reasoning"  # Whether reasoning is included

    # ═══════════════════════════════════════════════════════════════════════════
    # SPEECH SERVICES ATTRIBUTES - Azure Cognitive Services Speech
    # ═══════════════════════════════════════════════════════════════════════════
    # Speech-to-Text (STT)
    SPEECH_STT_LANGUAGE = "speech.stt.language"
    SPEECH_STT_RECOGNITION_DURATION = "speech.stt.recognition_duration"
    SPEECH_STT_CONFIDENCE = "speech.stt.confidence"
    SPEECH_STT_TEXT_LENGTH = "speech.stt.text_length"
    SPEECH_STT_RESULT_REASON = "speech.stt.result_reason"

    # Text-to-Speech (TTS)
    SPEECH_TTS_VOICE = "speech.tts.voice"
    SPEECH_TTS_LANGUAGE = "speech.tts.language"
    SPEECH_TTS_SYNTHESIS_DURATION = "speech.tts.synthesis_duration"
    SPEECH_TTS_AUDIO_SIZE_BYTES = "speech.tts.audio_size_bytes"
    SPEECH_TTS_TEXT_LENGTH = "speech.tts.text_length"
    SPEECH_TTS_OUTPUT_FORMAT = "speech.tts.output_format"
    SPEECH_TTS_SAMPLE_RATE = "speech.tts.sample_rate"
    SPEECH_TTS_FRAME_COUNT = "speech.tts.frame_count"

    # Legacy TTS attributes (for backwards compatibility)
    TTS_AUDIO_SIZE_BYTES = "tts.audio.size_bytes"
    TTS_FRAME_COUNT = "tts.frame.count"
    TTS_FRAME_SIZE_BYTES = "tts.frame.size_bytes"
    TTS_SAMPLE_RATE = "tts.sample_rate"
    TTS_VOICE = "tts.voice"
    TTS_TEXT_LENGTH = "tts.text.length"
    TTS_OUTPUT_FORMAT = "tts.output.format"

    # ═══════════════════════════════════════════════════════════════════════════
    # CONVERSATION TURN ATTRIBUTES - Per-turn latency tracking
    # ═══════════════════════════════════════════════════════════════════════════
    TURN_ID = "turn.id"
    TURN_NUMBER = "turn.number"
    TURN_USER_INTENT_PREVIEW = "turn.user_intent_preview"
    TURN_USER_SPEECH_DURATION = "turn.user_speech_duration"

    # Latency breakdown (all in milliseconds)
    TURN_STT_LATENCY_MS = "turn.stt.latency_ms"  # STT: speech recognition time
    TURN_LLM_TTFB_MS = "turn.llm.ttfb_ms"  # LLM: time to first token
    TURN_LLM_TOTAL_MS = "turn.llm.total_ms"  # LLM: total inference time
    TURN_TTS_TTFB_MS = "turn.tts.ttfb_ms"  # TTS: time to first audio chunk
    TURN_TTS_TOTAL_MS = "turn.tts.total_ms"  # TTS: total synthesis time
    TURN_TOTAL_LATENCY_MS = "turn.total_latency_ms"  # End-to-end turn latency
    TURN_TRANSPORT_TYPE = "turn.transport_type"

    # Token counts (from LLM inference) - duplicated from GenAI for direct access
    TURN_LLM_INPUT_TOKENS = "turn.llm.input_tokens"  # Prompt/input tokens
    TURN_LLM_OUTPUT_TOKENS = "turn.llm.output_tokens"  # Completion/output tokens
    TURN_LLM_TOKENS_PER_SEC = "turn.llm.tokens_per_sec"  # Generation throughput

    # ═══════════════════════════════════════════════════════════════════════════
    # AZURE COMMUNICATION SERVICES ATTRIBUTES
    # ═══════════════════════════════════════════════════════════════════════════
    ACS_TARGET_NUMBER = "acs.target_number"
    ACS_SOURCE_NUMBER = "acs.source_number"
    ACS_STREAM_MODE = "acs.stream_mode"
    ACS_CALL_CONNECTION_ID = "acs.call_connection_id"
    ACS_OPERATION = "acs.operation"

    # ═══════════════════════════════════════════════════════════════════════════
    # WEBSOCKET ATTRIBUTES - Real-time communication tracking
    # ═══════════════════════════════════════════════════════════════════════════
    WS_OPERATION_TYPE = "ws.operation_type"
    WS_TEXT_LENGTH = "ws.text_length"
    WS_TEXT_PREVIEW = "ws.text_preview"
    WS_STATE = "ws.state"
    WS_STREAM_MODE = "ws.stream_mode"
    WS_BLOCKING = "ws.blocking"
    WS_ROLE = "ws.role"
    WS_CONTENT_LENGTH = "ws.content_length"
    WS_IS_ACS = "ws.is_acs"


# ═══════════════════════════════════════════════════════════════════════════════
# PEER SERVICE CONSTANTS - Standard values for Application Map edges
# ═══════════════════════════════════════════════════════════════════════════════
class PeerService:
    """
    Standard peer.service values for Application Map dependency visualization.

    Use these constants when setting SpanAttr.PEER_SERVICE to ensure consistent
    node naming in Application Insights Application Map.
    """

    AZURE_OPENAI = "azure.ai.openai"
    AZURE_SPEECH = "azure.speech"
    AZURE_COMMUNICATION = "azure.communication"
    AZURE_MANAGED_REDIS = "azure-managed-redis"
    REDIS = "redis"
    COSMOSDB = "cosmosdb"
    HTTP = "http"


class GenAIProvider:
    """
    Standard gen_ai.provider.name values per OpenTelemetry GenAI conventions.
    """

    AZURE_OPENAI = "azure.ai.openai"
    OPENAI = "openai"
    AZURE_SPEECH = "azure.speech"  # Custom for speech services
    ANTHROPIC = "anthropic"
    AWS_BEDROCK = "aws.bedrock"


class GenAIOperation:
    """
    Standard gen_ai.operation.name values per OpenTelemetry GenAI conventions.
    """

    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    TEXT_COMPLETION = "text_completion"
    EXECUTE_TOOL = "execute_tool"
    CREATE_AGENT = "create_agent"
    INVOKE_AGENT = "invoke_agent"
