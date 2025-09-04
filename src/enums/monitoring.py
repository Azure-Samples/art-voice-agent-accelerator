from enum import Enum


# Span attribute keys for Azure App Insights OpenTelemetry logging
class SpanAttr(str, Enum):
    CORRELATION_ID = "correlation.id"
    CALL_CONNECTION_ID = "call.connection.id"
    SESSION_ID = "session.id"
    # deepcode ignore NoHardcodedCredentials: This is not a credential, but an attribute label used for Azure App Insights OpenTelemetry logging.
    USER_ID = "user.id"
    OPERATION_NAME = "operation.name"
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    STATUS_CODE = "status.code"
    ERROR_TYPE = "error.type"
    ERROR_MESSAGE = "error.message"
    TRACE_ID = "trace.id"
    SPAN_ID = "span.id"

    # Azure Communication Services specific attributes
    ACS_TARGET_NUMBER = "acs.target_number"
    ACS_SOURCE_NUMBER = "acs.source_number"
    ACS_STREAM_MODE = "acs.stream_mode"
    ACS_CALL_CONNECTION_ID = "acs.call_connection_id"

    # Text-to-Speech specific attributes
    TTS_AUDIO_SIZE_BYTES = "tts.audio.size_bytes"
    TTS_FRAME_COUNT = "tts.frame.count"
    TTS_FRAME_SIZE_BYTES = "tts.frame.size_bytes"
    TTS_SAMPLE_RATE = "tts.sample_rate"
    TTS_VOICE = "tts.voice"
    TTS_TEXT_LENGTH = "tts.text.length"
    TTS_OUTPUT_FORMAT = "tts.output.format"

    # WebSocket specific attributes
    WS_OPERATION_TYPE = "ws.operation_type"
    WS_TEXT_LENGTH = "ws.text_length"
    WS_TEXT_PREVIEW = "ws.text_preview"
    WS_STATE = "ws.state"
    WS_STREAM_MODE = "ws.stream_mode"
    WS_BLOCKING = "ws.blocking"
    WS_ROLE = "ws.role"
    WS_CONTENT_LENGTH = "ws.content_length"
    WS_IS_ACS = "ws.is_acs"
