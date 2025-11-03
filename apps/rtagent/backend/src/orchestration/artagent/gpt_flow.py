from __future__ import annotations

"""OpenAI streaming + tool-call orchestration layer with explicit rate-limit visibility
and controllable retries.

Public API
----------
process_gpt_response() – Stream completions, emit TTS chunks, run tools.
"""

import asyncio
import json
import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

from fastapi import WebSocket
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from urllib.parse import urlparse

from config import (
    AZURE_OPENAI_CHAT_DEPLOYMENT_ID,
    AZURE_OPENAI_ENDPOINT,
    TTS_END,
)
from apps.rtagent.backend.src.agents.artagent.tool_store.tool_registry import (
    available_tools as DEFAULT_TOOLS,
)
from apps.rtagent.backend.src.agents.artagent.tool_store.tools_helper import (
    function_mapping,
    push_tool_end,
    push_tool_start,
)
from apps.rtagent.backend.src.helpers import add_space
from src.aoai.client import client as default_aoai_client, create_azure_openai_client
from apps.rtagent.backend.src.ws_helpers.shared_ws import (
    broadcast_message,
    get_connection_metadata,
    push_final,
    send_response_to_acs,
    send_session_envelope,
    send_tts_audio,
)
from apps.rtagent.backend.src.ws_helpers.envelopes import make_assistant_streaming_envelope
from utils.ml_logging import get_logger
from utils.trace_context import create_trace_context
from apps.rtagent.backend.src.utils.tracing import (
    create_service_handler_attrs,
    create_service_dependency_attrs)
from utils.ml_logging import get_logger
from utils.trace_context import create_trace_context

if TYPE_CHECKING:  # pragma: no cover – typing-only import
    from src.stateful.state_managment import MemoManager  # noqa: F401

# ---------------------------------------------------------------------------
# Logging / Tracing
# ---------------------------------------------------------------------------
logger = get_logger("orchestration.gpt_flow")
tracer = trace.get_tracer(__name__)

_GPT_FLOW_TRACING = os.getenv("GPT_FLOW_TRACING", "true").lower() == "true"
_STREAM_TRACING = os.getenv("STREAM_TRACING", "false").lower() == "true"  # High freq

JSONDict = Dict[str, Any]


# ---------------------------------------------------------------------------
# Retry / Rate-limit configuration
# ---------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


AOAI_RETRY_MAX_ATTEMPTS: int = int(os.getenv("AOAI_RETRY_MAX_ATTEMPTS", "4"))
AOAI_RETRY_BASE_DELAY_SEC: float = _env_float("AOAI_RETRY_BASE_DELAY_SEC", 0.5)
AOAI_RETRY_MAX_DELAY_SEC: float = _env_float("AOAI_RETRY_MAX_DELAY_SEC", 8.0)
AOAI_RETRY_BACKOFF_FACTOR: float = _env_float("AOAI_RETRY_BACKOFF_FACTOR", 2.0)
AOAI_RETRY_JITTER_SEC: float = _env_float("AOAI_RETRY_JITTER_SEC", 0.2)


@dataclass
class RateLimitInfo:
    """
    Structured snapshot of AOAI limit/trace headers.

    :param request_id: x-request-id from AOAI.
    :param retry_after: Parsed retry-after seconds if present.
    :param region: x-ms-region if present.
    :param remaining_requests: Remaining request quota in the current window.
    :param remaining_tokens: Remaining token quota in the current window.
    :param reset_requests: Reset time for request window (seconds or epoch if provided).
    :param reset_tokens: Reset time for token window (seconds or epoch if provided).
    :param limit_requests: Request limit of the window if provided.
    :param limit_tokens: Token limit of the window if provided.
    """
    request_id: Optional[str] = None
    retry_after: Optional[float] = None
    region: Optional[str] = None
    remaining_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None
    reset_requests: Optional[str] = None
    reset_tokens: Optional[str] = None
    limit_requests: Optional[int] = None
    limit_tokens: Optional[int] = None


def _parse_int(val: Optional[str]) -> Optional[int]:
    try:
        return int(val) if val is not None and val != "" else None
    except Exception:
        return None


def _parse_float(val: Optional[str]) -> Optional[float]:
    try:
        return float(val) if val is not None and val != "" else None
    except Exception:
        return None


def _extract_headers(container: Any) -> Dict[str, str]:
    """
    Best-effort header extraction from various SDK response/exception shapes.

    We try the following in order:
      - container.headers
      - container.response.headers
      - container.http_response.headers
      - container._response.headers  (fallback)
    """
    cand_attrs = ("headers", "response", "http_response", "_response")
    headers: Optional[Dict[str, str]] = None

    if hasattr(container, "headers") and isinstance(container.headers, dict):
        headers = container.headers

    if headers is None:
        for attr in cand_attrs:
            obj = getattr(container, attr, None)
            if obj is None:
                continue
            maybe = getattr(obj, "headers", None)
            if isinstance(maybe, dict):
                headers = maybe
                break
            if callable(getattr(obj, "headers", None)):
                try:
                    h = obj.headers()
                    if isinstance(h, dict):
                        headers = h
                        break
                except Exception:
                    continue

    if headers is None:
        logger.warning("No headers could be extracted from container", extra={"container_type": type(container).__name__})

    return headers or {}


def _rate_limit_from_headers(headers: Dict[str, str]) -> RateLimitInfo:
    """
    Parse AOAI rate-limit and tracing headers into RateLimitInfo.
    """
    h = {k.lower(): v for k, v in headers.items()}

    info = RateLimitInfo(
        request_id=h.get("x-request-id") or h.get("x-ms-request-id"),
        retry_after=_parse_float(h.get("retry-after")),
        region=h.get("x-ms-region") or h.get("azureml-model-deployment"),
        remaining_requests=_parse_int(
            h.get("x-ratelimit-remaining-requests") or h.get("ratelimit-remaining-requests")
        ),
        remaining_tokens=_parse_int(
            h.get("x-ratelimit-remaining-tokens") or h.get("ratelimit-remaining-tokens")
        ),
        reset_requests=h.get("x-ratelimit-reset-requests") or h.get("ratelimit-reset-requests"),
        reset_tokens=h.get("x-ratelimit-reset-tokens") or h.get("ratelimit-reset-tokens"),
        limit_requests=_parse_int(
            h.get("x-ratelimit-limit-requests") or h.get("ratelimit-limit-requests")
        ),
        limit_tokens=_parse_int(
            h.get("x-ratelimit-limit-tokens") or h.get("ratelimit-limit-tokens")
        ),
    )
    return info


def _log_rate_limit(prefix: str, info: RateLimitInfo) -> None:
    """
    Emit a single structured log line describing current limit state.
    """
    logger.info(
        "%s | req_id=%s region=%s rem_req=%s rem_tok=%s lim_req=%s lim_tok=%s reset_req=%s reset_tok=%s retry_after=%s",
        prefix,
        info.request_id,
        info.region,
        info.remaining_requests,
        info.remaining_tokens,
        info.limit_requests,
        info.limit_tokens,
        info.reset_requests,
        info.reset_tokens,
        info.retry_after,
        extra={
            "aoai_request_id": info.request_id,
            "aoai_region": info.region,
            "aoai_remaining_requests": info.remaining_requests,
            "aoai_remaining_tokens": info.remaining_tokens,
            "aoai_limit_requests": info.limit_requests,
            "aoai_limit_tokens": info.limit_tokens,
            "aoai_reset_requests": info.reset_requests,
            "aoai_reset_tokens": info.reset_tokens,
            "aoai_retry_after": info.retry_after,
            "event_type": "rate_limit_status",
            "prefix": prefix
        }
    )


def _set_span_rate_limit(span, info: RateLimitInfo) -> None:
    """
    Attach rate-limit attributes to the active span.
    """
    if not span:
        return
    span.set_attribute("aoai.request_id", info.request_id or "")
    span.set_attribute("aoai.region", info.region or "")
    if info.remaining_requests is not None:
        span.set_attribute("aoai.ratelimit.remaining_requests", info.remaining_requests)
    if info.remaining_tokens is not None:
        span.set_attribute("aoai.ratelimit.remaining_tokens", info.remaining_tokens)
    if info.limit_requests is not None:
        span.set_attribute("aoai.ratelimit.limit_requests", info.limit_requests)
    if info.limit_tokens is not None:
        span.set_attribute("aoai.ratelimit.limit_tokens", info.limit_tokens)
    if info.retry_after is not None:
        span.set_attribute("aoai.retry_after", info.retry_after)
    if info.reset_requests:
        span.set_attribute("aoai.reset_requests", info.reset_requests)
    if info.reset_tokens:
        span.set_attribute("aoai.reset_tokens", info.reset_tokens)


def _inspect_client_retry_settings(client: Any) -> None:
    """
    Log the SDK client's built-in retry behavior if discoverable.

    Many OpenAI/AzureOpenAI client versions expose a 'max_retries' property.
    """
    try:
        max_retries = getattr(client, "max_retries", None)
        transport = getattr(client, "transport", None)
        logger.info("AOAI SDK retry: max_retries=%s transport=%s", max_retries, type(transport).__name__ if transport else None)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Latency tool helpers (No-ops if ws.state.lt is missing)
# ---------------------------------------------------------------------------
class _NoOpLatency:
    def start(self, *_args, **_kwargs):
        return None

    def stop(self, *_args, **_kwargs):
        return None

    def mark(self, *_args, **_kwargs):
        return None


def _lt(ws: WebSocket):
    try:
        return getattr(ws.state, "lt", _NoOpLatency())
    except Exception:
        return _NoOpLatency()


def _log_latency_stop(name: str, dur: Any) -> None:
    try:
        if isinstance(dur, (int, float)):
            logger.info("[Latency] %s: %.3f ms", name, float(dur))
        else:
            logger.info("[Latency] %s stopped", name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Error helpers (status + header summary for logs)
# ---------------------------------------------------------------------------
def _extract_status_from_exc(exc: Exception) -> Optional[int]:
    for attr in ("status", "status_code", "http_status", "statusCode"):
        try:
            v = getattr(exc, attr, None)
            if isinstance(v, int):
                return v
        except Exception:
            pass
    for attr in ("response", "http_response", "_response"):
        try:
            obj = getattr(exc, attr, None)
            if obj is None:
                continue
            v = getattr(obj, "status_code", None)
            if isinstance(v, int):
                return v
            v = getattr(obj, "status", None)
            if isinstance(v, int):
                return v
        except Exception:
            pass
    try:
        s = str(exc)
        for token in ("429", "500", "502", "503", "504", "400", "401", "403", "404"):
            if token in s:
                return int(token)
    except Exception:
        pass
    return None


def _summarize_headers(headers: Dict[str, str]) -> str:
    keys = [
        "x-request-id",
        "x-ms-request-id",
        "x-ms-region",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "retry-after",
    ]
    low = {k.lower(): v for k, v in headers.items()}
    pick = {k: low.get(k) for k in keys if low.get(k) is not None}
    return json.dumps(pick)


# ---------------------------------------------------------------------------
# Voice + sender helpers (UNCHANGED)
# ---------------------------------------------------------------------------
def _get_agent_voice_config(
    cm: "MemoManager",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Retrieve agent voice config from memory manager.

    :param cm: The active MemoManager instance for conversation state.
    :return: (voice_name, voice_style, voice_rate) or (None, None, None).
    """
    if cm is None:
        logger.warning("MemoManager is None, using default voice configuration")
        return None, None, None

    try:
        voice_name = cm.get_value_from_corememory("current_agent_voice")
        voice_style = cm.get_value_from_corememory("current_agent_voice_style", "chat")
        voice_rate = cm.get_value_from_corememory("current_agent_voice_rate", "+3%")
        return voice_name, voice_style, voice_rate
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to get agent voice config: %s", exc)
        return None, None, None


def _get_agent_sender_name(cm: "MemoManager", *, include_autoauth: bool = True) -> str:
    """
    Resolve the visible sender name for dashboard/UI.

    :param cm: MemoManager instance for reading conversation context.
    :param include_autoauth: When True, map active_agent=='AutoAuth' to 'Auth Agent'.
    :return: Human-friendly speaker label for display.
    """
    try:
        active_agent = cm.get_value_from_corememory("active_agent") if cm else None
        authenticated = cm.get_value_from_corememory("authenticated") if cm else False

        if active_agent == "Claims":
            return "Claims Specialist"
        if active_agent == "General":
            return "General Info"
        if include_autoauth and active_agent == "AutoAuth":
            return "Auth Agent"
        if not authenticated:
            return "Auth Agent"
        return "Assistant"
    except Exception:
        return "Assistant"


# ---------------------------------------------------------------------------
# Emission helpers (UNCHANGED)
# ---------------------------------------------------------------------------
async def _emit_streaming_text(
    text: str,
    ws: WebSocket,
    is_acs: bool,
    cm: "MemoManager",
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Emit one assistant text chunk via either ACS or WebSocket + TTS.

    :param text: The text chunk to emit to client.
    :param ws: Active WebSocket connection instance.
    :param is_acs: Whether to route via Azure Communication Services.
    :param cm: MemoManager for voice config and speaker labels.
    :param call_connection_id: Optional correlation ID for tracing.
    :param session_id: Optional session ID for tracing correlation.
    :raises: Re-raises any exceptions from TTS or ACS emission.
    """
    voice_name, voice_style, voice_rate = _get_agent_voice_config(cm)

    if _STREAM_TRACING:
        span_attrs = create_service_handler_attrs(
            service_name="gpt_flow",
            call_connection_id=call_connection_id,
            session_id=session_id,
            operation="emit_streaming_text",
            text_length=len(text),
            is_acs=is_acs,
            chunk_type="streaming_text",
        )
        with tracer.start_as_current_span(
            "gpt_flow.emit_streaming_text", attributes=span_attrs
        ) as span:
            try:
                playback_status = "completed"
                if is_acs:
                    span.set_attribute("output_channel", "acs")
                    await send_response_to_acs(
                        ws,
                        text,
                        latency_tool=_lt(ws),
                        voice_name=voice_name,
                        voice_style=voice_style,
                        rate=voice_rate,
                    )
                    playback_status = get_connection_metadata(
                        ws, "acs_last_playback_status", "completed"
                    )
                else:
                    span.set_attribute("output_channel", "websocket_tts")
                    await send_tts_audio(
                        text,
                        ws,
                        latency_tool=_lt(ws),
                        voice_name=voice_name,
                        voice_style=voice_style,
                        rate=voice_rate,
                    )
                envelope = make_assistant_streaming_envelope(
                    content=text,
                    sender=_get_agent_sender_name(cm, include_autoauth=True),
                    session_id=session_id,
                )
                envelope["speaker"] = envelope.get("sender")
                envelope["message"] = text  # Legacy compatibility for dashboards
                conn_id = None if is_acs else getattr(ws.state, "conn_id", None)
                await send_session_envelope(
                    ws,
                    envelope,
                    session_id=session_id,
                    conn_id=conn_id,
                    event_label="assistant_streaming",
                    broadcast_only=is_acs,
                )

                span.add_event(
                    "text_emitted",
                    {
                        "text_length": len(text),
                        "output_channel": "acs" if is_acs else "websocket",
                        "acs.playback_status": playback_status,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                span.record_exception(exc)
                logger.exception("Failed to emit streaming text")
                raise
    else:
        playback_status = "completed"
        if is_acs:
            await send_response_to_acs(
                ws,
                text,
                latency_tool=_lt(ws),
                voice_name=voice_name,
                voice_style=voice_style,
                rate=voice_rate,
            )
            playback_status = get_connection_metadata(
                ws, "acs_last_playback_status", "completed"
            )
        else:
            await send_tts_audio(
                text,
                ws,
                latency_tool=_lt(ws),
                voice_name=voice_name,
                voice_style=voice_style,
                rate=voice_rate,
            )

        envelope = make_assistant_streaming_envelope(
            content=text,
            sender=_get_agent_sender_name(cm, include_autoauth=True),
            session_id=session_id,
        )
        envelope["speaker"] = envelope.get("sender")
        envelope["message"] = text  # Legacy compatibility for dashboards
        conn_id = None if is_acs else getattr(ws.state, "conn_id", None)
        await send_session_envelope(
            ws,
            envelope,
            session_id=session_id,
            conn_id=conn_id,
            event_label="assistant_streaming",
            broadcast_only=is_acs,
        )


async def _broadcast_dashboard(
    ws: WebSocket,
    cm: "MemoManager",
    message: str,
    *,
    include_autoauth: bool,
) -> None:
    """Broadcast a message to the relay dashboard with correct speaker label."""
    try:
        sender = _get_agent_sender_name(cm, include_autoauth=include_autoauth)
        
        session_id = (
            cm.session_id
            or getattr(ws.state, "session_id", None)
            or getattr(ws.state, "call_connection_id", None)
            or ws.headers.get("x-session-id")
            or ws.headers.get("x-call-connection-id")
            or "unknown"
        )
        
        logger.info(
            "🎯 dashboard_broadcast: sender='%s' include_autoauth=%s msg='%s...' session_id='%s'",
            sender,
            include_autoauth,
            message[:50],
            session_id,
        )
        
        # SESSION-SAFE: Use session-specific broadcasting instead of topic-based
        await broadcast_message(None, message, sender, app_state=ws.app.state, session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to broadcast dashboard message: %s", exc)


# ---------------------------------------------------------------------------
# Chat + streaming helpers – with explicit retry & header capture
# ---------------------------------------------------------------------------
def _validate_conversation_history(history: List[JSONDict], agent_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate conversation history for OpenAI API compliance.
    
    Checks for common conversation integrity issues that cause OpenAI API errors:
    - Orphaned tool calls (assistant with tool_calls but no tool responses)
    - Invalid message sequences
    - Malformed tool call structures
    
    Args:
        history: List of conversation messages
        agent_name: Name of the agent for logging context
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not history:
        return True, None
        
    # Track tool calls that need responses
    pending_tool_calls = {}
    
    for i, msg in enumerate(history):
        role = msg.get("role")
        
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # Register tool calls that need responses
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict) and "id" in tool_call:
                        pending_tool_calls[tool_call["id"]] = i
                        
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id and tool_call_id in pending_tool_calls:
                # Mark tool call as resolved
                del pending_tool_calls[tool_call_id]
    
    # Check for orphaned tool calls
    if pending_tool_calls:
        orphaned_ids = list(pending_tool_calls.keys())
        error_msg = f"Orphaned tool calls detected: {orphaned_ids}"
        logger.error(
            "Conversation history validation failed for agent %s: %s",
            agent_name,
            error_msg,
            extra={
                "agent_name": agent_name,
                "orphaned_tool_calls": orphaned_ids,
                "history_length": len(history),
                "event_type": "conversation_validation_error"
            }
        )
        return False, error_msg
    
    logger.debug(
        "Conversation history validation passed for agent %s: %d messages",
        agent_name,
        len(history),
        extra={
            "agent_name": agent_name,
            "history_length": len(history),
            "event_type": "conversation_validation_success"
        }
    )
    return True, None


def _repair_conversation_history(history: List[JSONDict], agent_name: str) -> List[JSONDict]:
    """
    Attempt to repair conversation history by adding missing tool responses.
    
    This is a recovery mechanism to prevent conversation corruption from
    causing cascading failures.
    
    Args:
        history: Original conversation history
        agent_name: Name of the agent for logging context
        
    Returns:
        List[JSONDict]: Repaired conversation history
    """
    repaired_history = history.copy()
    pending_tool_calls = {}
    
    # Identify orphaned tool calls
    for i, msg in enumerate(history):
        role = msg.get("role")
        
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict) and "id" in tool_call:
                        pending_tool_calls[tool_call["id"]] = tool_call
                        
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id and tool_call_id in pending_tool_calls:
                del pending_tool_calls[tool_call_id]
    
    # Add synthetic tool responses for orphaned tool calls
    if pending_tool_calls:
        logger.warning(
            "Repairing conversation history for agent %s: adding %d synthetic tool responses",
            agent_name,
            len(pending_tool_calls),
            extra={
                "agent_name": agent_name,
                "orphaned_count": len(pending_tool_calls),
                "event_type": "conversation_history_repair"
            }
        )
        
        for tool_call_id, tool_call in pending_tool_calls.items():
            synthetic_response = {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": tool_call.get("function", {}).get("name", "unknown_tool"),
                "content": json.dumps({
                    "error": "Tool execution was interrupted",
                    "message": "The previous tool execution was interrupted. Please try again.",
                    "synthetic_response": True
                }),
            }
            repaired_history.append(synthetic_response)
    
    return repaired_history


def _build_completion_kwargs(
    *,
    history: List[JSONDict],
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    tools: Optional[List[JSONDict]],
) -> JSONDict:
    """
    Build Azure OpenAI chat-completions kwargs.

    :param history: List of conversation messages for chat context.
    :param model_id: Azure OpenAI model deployment identifier.
    :param temperature: Sampling temperature for response generation.
    :param top_p: Nucleus sampling parameter for response diversity.
    :param max_tokens: Maximum number of tokens to generate.
    :param tools: Optional list of tool definitions for function calling.
    :return: Dict suitable for az_openai_client.chat.completions.create.
    """
    return {
        "stream": True,
        "messages": history,
        "model": model_id,
        "max_completion_tokens": max_tokens,
        # "temperature": temperature,
        # "top_p": top_p,
        "tools": tools or [],
        "tool_choice": "auto" if (tools or []) else "none",
    }


class _ToolCallState:
    """Minimal state carrier for a single tool call parsed from stream deltas."""
    def __init__(self) -> None:
        self.started: bool = False
        self.name: str = ""
        self.call_id: str = ""
        self.args_json: str = ""


async def _openai_stream_with_retry(
    chat_kwargs: Dict[str, Any],
    *,
    model_id: str,
    dep_span,  # active OTEL span for dependency call
    session_id: Optional[str] = None,
    client: Optional[Any] = None,
    refresh_client_cb: Optional[Callable[[], Awaitable[Any]]] = None,
) -> Tuple[Iterable[Any], RateLimitInfo]:
    """
    Invoke AOAI streaming with explicit retry and capture rate-limit headers.
    
    Uses session-specific client from pool to eliminate
    resource contention and improve concurrent session throughput.

    We try the SDK's streaming-response context (if present) to access headers.
    Falls back to normal `.create(**kwargs)`.

    If a refresh callback is provided and we encounter a 401 status code,
    the callback is invoked to rebuild the client and the request is retried
    immediately without consuming a normal retry attempt.
    """
    aoai_client = client or default_aoai_client
    _inspect_client_retry_settings(aoai_client)

    attempts = 0
    last_info = RateLimitInfo()
    aoai_host = urlparse(AZURE_OPENAI_ENDPOINT).netloc or "api.openai.azure.com"

    logger.info(
        "Starting AOAI stream request: model=%s host=%s max_attempts=%d",
        model_id,
        aoai_host,
        AOAI_RETRY_MAX_ATTEMPTS,
        extra={
            "model_id": model_id,
            "aoai_host": aoai_host,
            "max_attempts": AOAI_RETRY_MAX_ATTEMPTS,
            "session_id": session_id,
            "client_type": type(aoai_client).__name__,
            "event_type": "aoai_stream_start"
        }
    )

    while True:
        attempts += 1
        logger.info(
            "AOAI stream attempt %d/%d",
            attempts,
            AOAI_RETRY_MAX_ATTEMPTS,
            extra={
                "attempt": attempts,
                "max_attempts": AOAI_RETRY_MAX_ATTEMPTS,
                "session_id": session_id,
                "event_type": "aoai_stream_attempt"
            }
        )

        try:
            with_stream_ctx = getattr(
                aoai_client.chat.completions, "with_streaming_response", None
            )

            if callable(with_stream_ctx):
                ctx = with_stream_ctx.create(**chat_kwargs)
                with ctx as resp_ctx:
                    headers = _extract_headers(resp_ctx)
                    last_info = _rate_limit_from_headers(headers)
                    _log_rate_limit("AOAI stream started", last_info)
                    _set_span_rate_limit(dep_span, last_info)
                    dep_span.add_event("openai_stream_started", {"attempt": attempts})

                    logger.info(
                        "AOAI stream successful on attempt %d",
                        attempts,
                        extra={
                            "attempt": attempts,
                            "success": True,
                            "session_id": session_id,
                            "event_type": "aoai_stream_success"
                        }
                    )

                    response_stream = resp_ctx
                    return response_stream, last_info
            else:
                response_stream = aoai_client.chat.completions.create(**chat_kwargs)
                dep_span.add_event("openai_stream_started", {"attempt": attempts})
                logger.info(
                    "AOAI stream successful on attempt %d (no headers available)",
                    attempts,
                    extra={
                        "attempt": attempts,
                        "success": True,
                        "headers_available": False,
                        "session_id": session_id,
                        "event_type": "aoai_stream_success"
                    }
                )
                return response_stream, last_info

        except Exception as exc:  # noqa: BLE001
            # Try to log status + request-id + header snapshot every time (incl. 429)
            headers = _extract_headers(exc)
            last_info = _rate_limit_from_headers(headers)
            status = _extract_status_from_exc(exc)

            logger.error(
                "AOAI stream error attempt=%s/%s status=%s req_id=%s retry_after=%s headers=%s exc=%s",
                attempts,
                AOAI_RETRY_MAX_ATTEMPTS,
                status,
                last_info.request_id,
                last_info.retry_after,
                _summarize_headers({k.lower(): v for k, v in headers.items()}),
                repr(exc),
                extra={"http_status": status, "aoai_request_id": last_info.request_id, "event_type": "aoai_stream_error"}
            )

            _log_rate_limit("AOAI error", last_info)
            _set_span_rate_limit(dep_span, last_info)

            if status == 401 and refresh_client_cb is not None:
                dep_span.add_event(
                    "openai_auth_refresh_start",
                    {"attempt": attempts, "session_id": session_id},
                )
                logger.warning(
                    "AOAI authentication failed (401); refreshing client",
                    extra={
                        "attempt": attempts,
                        "session_id": session_id,
                        "event_type": "aoai_auth_refresh_start",
                    },
                )
                try:
                    refreshed_client = await refresh_client_cb()
                    if refreshed_client is not None:
                        aoai_client = refreshed_client
                        dep_span.add_event(
                            "openai_auth_refresh_success",
                            {"attempt": attempts, "session_id": session_id},
                        )
                        logger.info(
                            "AOAI client refreshed after 401",
                            extra={
                                "attempt": attempts,
                                "session_id": session_id,
                                "event_type": "aoai_auth_refresh_success",
                            },
                        )
                        attempts -= 1
                        continue
                    dep_span.add_event(
                        "openai_auth_refresh_noop",
                        {"attempt": attempts, "session_id": session_id},
                    )
                    logger.error(
                        "Refresh callback returned no client after 401",
                        extra={
                            "attempt": attempts,
                            "session_id": session_id,
                            "event_type": "aoai_auth_refresh_failure",
                        },
                    )
                except Exception as refresh_exc:  # noqa: BLE001
                    dep_span.add_event(
                        "openai_auth_refresh_failure",
                        {
                            "attempt": attempts,
                            "session_id": session_id,
                            "error_type": type(refresh_exc).__name__,
                        },
                    )
                    logger.error(
                        "AOAI client refresh failed after 401: %s",
                        refresh_exc,
                        extra={
                            "attempt": attempts,
                            "session_id": session_id,
                            "event_type": "aoai_auth_refresh_failure",
                        },
                    )

            # Decide on retry
            should_retry, reason = _should_retry(exc)
            dep_span.add_event(
                "openai_stream_exception",
                {"attempt": attempts, "retry": should_retry, "reason": reason, "status": status},
            )

            if not should_retry or attempts >= AOAI_RETRY_MAX_ATTEMPTS:
                dep_span.record_exception(exc)
                dep_span.set_attribute("retry.exhausted", True)
                raise

            delay = _compute_delay(last_info, attempts)
            dep_span.set_attribute("retry.delay_sec", delay)
            logger.info(
                "Retrying AOAI stream in %.2f seconds (attempt %d/%d)",
                delay, attempts, AOAI_RETRY_MAX_ATTEMPTS,
                extra={"delay_seconds": delay, "attempt": attempts, "event_type": "aoai_stream_retry_delay"}
            )
            await asyncio.sleep(delay)


def _should_retry(exc: Exception) -> Tuple[bool, str]:
    """
    Classify whether an exception should be retried.

    :return: (should_retry, reason)
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    logger.error(
        "AOAI Exception Analysis: type=%s message='%s'",
        type(exc).__name__,
        str(exc)[:200],
        extra={
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "event_type": "aoai_exception_analysis"
        }
    )

    retryable_names = (
        "ratelimit", "timeout", "apitimeout", "serviceunavailable",
        "apierror", "apistatuserror", "httpresponseerror", "httpserror",
        "badgateway", "gatewaytimeout", "too many requests", "connectionerror",
    )
    if any(k in name for k in retryable_names) or any(k in msg for k in retryable_names):
        return True, f"retryable:{name}"

    for code in ("429", "502", "503", "504"):
        if code in msg:
            return True, f"http:{code}"

    return False, f"non-retryable:{name}"


def _compute_delay(info: RateLimitInfo, attempts: int) -> float:
    """
    Compute next sleep duration using Retry-After when present,
    otherwise exponential backoff with jitter.
    """
    if info.retry_after is not None and info.retry_after >= 0:
        base = float(info.retry_after)
    else:
        base = AOAI_RETRY_BASE_DELAY_SEC * (AOAI_RETRY_BACKOFF_FACTOR ** (attempts - 1))
    base = min(base, AOAI_RETRY_MAX_DELAY_SEC)
    jitter = random.uniform(0, AOAI_RETRY_JITTER_SEC)
    return base + jitter


async def _consume_openai_stream(
    response_stream: Any,
    ws: WebSocket,
    is_acs: bool,
    cm: "MemoManager",
    call_connection_id: Optional[str],
    session_id: Optional[str],
) -> Tuple[str, _ToolCallState]:
    """
    Consume the AOAI stream, emitting TTS chunks as punctuation arrives.

    :param response_stream: Azure OpenAI streaming response object or ctx.
    :param ws: WebSocket connection for client communication.
    :param is_acs: Flag indicating Azure Communication Services pathway.
    :param cm: MemoManager instance for conversation state.
    :param call_connection_id: Optional correlation ID for tracing.
    :param session_id: Optional session ID for tracing correlation.
    :return: (full_assistant_text, tool_call_state)
    """
    collected: List[str] = []
    final_chunks: List[str] = []
    tool = _ToolCallState()

    # TTFB ends on first delta; then we time the stream consume
    lt = _lt(ws)
    first_seen = False
    consume_started = False

    for chunk in response_stream:
        if not first_seen:
            first_seen = True
            try:
                dur = lt.stop("aoai:ttfb")
                _log_latency_stop("aoai:ttfb", dur)
            except Exception:
                pass
            try:
                lt.start("aoai:consume")
                consume_started = True
            except Exception:
                consume_started = False

        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta

        # Tool-call aggregation
        if getattr(delta, "tool_calls", None):
            tc = delta.tool_calls[0]
            tool.call_id = tc.id or tool.call_id
            tool.name = getattr(tc.function, "name", None) or tool.name
            tool.args_json += getattr(tc.function, "arguments", None) or ""
            if not tool.started:
                tool.started = True
            continue

        # Text streaming (flush on boundaries in TTS_END)
        if getattr(delta, "content", None):
            collected.append(delta.content)
            if delta.content in TTS_END:
                streaming = add_space("".join(collected).strip())
                logger.info("process_gpt_response – streaming text chunk: %s", streaming)
                await _emit_streaming_text(
                    streaming, ws, is_acs, cm, call_connection_id, session_id
                )
                final_chunks.append(streaming)
                collected.clear()

    # Handle trailing content
    if collected:
        pending = "".join(collected).strip()
        if pending:
            await _emit_streaming_text(
                pending, ws, is_acs, cm, call_connection_id, session_id
            )
            final_chunks.append(pending)

    if consume_started:
        try:
            dur = lt.stop("aoai:consume")
            _log_latency_stop("aoai:consume", dur)
        except Exception:
            pass

    return "".join(final_chunks).strip(), tool


# ---------------------------------------------------------------------------
# Main orchestration entry – now calls the retry/limit-aware streamer
# ---------------------------------------------------------------------------
async def process_gpt_response(  # noqa: PLR0913
    cm: "MemoManager",
    user_prompt: str,
    ws: WebSocket,
    *,
    agent_name: str,
    is_acs: bool = False,
    model_id: str = AZURE_OPENAI_CHAT_DEPLOYMENT_ID,
    temperature: float = 0.5,
    top_p: float = 1.0,
    max_tokens: int = 4096,
    available_tools: Optional[List[Dict[str, Any]]] = None,
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Stream a chat completion, emitting TTS and handling tool calls.

    This function fetches and streams a GPT response with explicit
    rate-limit visibility and controllable retry. It logs AOAI headers,
    sets tracing attributes, and continues into the tool-call flow.

    :param cm: Active MemoManager instance for conversation state.
    :param user_prompt: The raw user prompt string input.
    :param ws: WebSocket connection to the client.
    :param agent_name: Identifier used to fetch agent-specific chat history.
    :param is_acs: Flag indicating Azure Communication Services pathway.
    :param model_id: Azure OpenAI deployment ID for model selection.
    :param temperature: Sampling temperature for response generation.
    :param top_p: Nucleus sampling value for response diversity.
    :param max_tokens: Maximum tokens for the completion response.
    :param available_tools: Tool definitions to expose, defaults to DEFAULT_TOOLS.
    :param call_connection_id: ACS call connection ID for tracing correlation.
    :param session_id: Session ID for tracing correlation.
    :return: Optional tool result dictionary if a tool was executed, None otherwise.
    :raises Exception: Propagates critical errors after retries are exhausted.
    """
    # Build history and tools
    agent_history: List[JSONDict] = cm.get_history(agent_name)
    agent_history.append({"role": "user", "content": user_prompt})
    tool_set = available_tools or DEFAULT_TOOLS

    logger.info(
        "Starting GPT response processing: agent=%s model=%s prompt_len=%d tools=%d",
        agent_name,
        model_id,
        len(user_prompt) if user_prompt else 0,
        len(tool_set),
        extra={
            "agent_name": agent_name,
            "model_id": model_id,
            "prompt_length": len(user_prompt) if user_prompt else 0,
            "tools_count": len(tool_set),
            "is_acs": is_acs,
            "call_connection_id": call_connection_id,
            "session_id": session_id,
            "event_type": "gpt_flow_start"
        }
    )

    # Create handler span for GPT flow service
    span_attrs = create_service_handler_attrs(
        service_name="gpt_flow",
        call_connection_id=call_connection_id,
        session_id=session_id,
        operation="process_response",
        agent_name=agent_name,
        model_id=model_id,
        is_acs=is_acs,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools_available=len(tool_set),
        prompt_length=len(user_prompt) if user_prompt else 0,
    )

    with tracer.start_as_current_span("gpt_flow.process_response", attributes=span_attrs) as span:
        chat_kwargs = _build_completion_kwargs(
            history=agent_history,
            model_id=model_id,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tool_set,
        )
        span.set_attribute("chat.history_length", len(agent_history))

        # Dependency span for AOAI
        azure_openai_attrs = create_service_dependency_attrs(
            source_service="gpt_flow",
            target_service="azure_openai",
            call_connection_id=call_connection_id,
            session_id=session_id,
            operation="stream_completion",
            model=model_id,
            stream=True,
        )
        host = urlparse(AZURE_OPENAI_ENDPOINT).netloc or "api.openai.azure.com"

        tool_state = _ToolCallState()
        last_rate_info = RateLimitInfo()

        lt = _lt(ws)
        # Total timer for AOAI path
        try:
            lt.start("aoai:total")
        except Exception:
            pass

        try:
            with tracer.start_as_current_span(
                "gpt_flow.stream_completion",
                kind=SpanKind.CLIENT,
                attributes={
                    **azure_openai_attrs,
                    "peer.service": "azure-openai",
                    "server.address": host,
                    "server.port": 443,
                    "http.method": "POST",
                    "http.url": f"https://{host}/openai/deployments/{model_id}/chat/completions",
                    "pipeline.stage": "orchestrator -> aoai",
                    "retry.max_attempts": AOAI_RETRY_MAX_ATTEMPTS,
                    "retry.base_delay": AOAI_RETRY_BASE_DELAY_SEC,
                    "retry.max_delay": AOAI_RETRY_MAX_DELAY_SEC,
                    "retry.backoff_factor": AOAI_RETRY_BACKOFF_FACTOR,
                    "retry.jitter": AOAI_RETRY_JITTER_SEC,
                },
            ) as dep_span:
                # Start TTFB just before issuing the stream call
                try:
                    lt.start("aoai:ttfb")
                except Exception:
                    pass

                aoai_manager = getattr(ws.app.state, "aoai_client_manager", None)

                if aoai_manager is not None:
                    aoai_client = await aoai_manager.get_client(session_id=session_id)
                    setattr(ws.app.state, "aoai_client", aoai_client)

                    async def refresh_client_cb() -> Any:
                        refreshed = await aoai_manager.refresh_after_auth_failure(session_id=session_id)
                        setattr(ws.app.state, "aoai_client", refreshed)
                        return refreshed

                else:
                    aoai_client = getattr(ws.app.state, "aoai_client", default_aoai_client)

                    async def refresh_client_cb() -> Any:
                        new_client = await asyncio.to_thread(create_azure_openai_client)
                        setattr(ws.app.state, "aoai_client", new_client)
                        return new_client

                response_stream, last_rate_info = await _openai_stream_with_retry(
                    chat_kwargs,
                    model_id=model_id,
                    dep_span=dep_span,
                    session_id=session_id,
                    client=aoai_client,
                    refresh_client_cb=refresh_client_cb,
                )

                # Consume the stream and emit chunks
                full_text, tool_state = await _consume_openai_stream(
                    response_stream, ws, is_acs, cm, call_connection_id, session_id
                )

                dep_span.set_attribute("tool_call_detected", tool_state.started)
                if tool_state.started:
                    dep_span.set_attribute("tool_name", tool_state.name)

        except Exception as exc:  # noqa: BLE001
            # Ensure timers stop on all error paths
            try:
                dur = lt.stop("aoai:ttfb")
                _log_latency_stop("aoai:ttfb", dur)
            except Exception:
                pass
            try:
                dur = lt.stop("aoai:consume")
                _log_latency_stop("aoai:consume", dur)
            except Exception:
                pass
            try:
                dur = lt.stop("aoai:total")
                _log_latency_stop("aoai:total", dur)
            except Exception:
                pass

            _log_rate_limit("AOAI final failure", last_rate_info)
            span.record_exception(exc)

            # Extra explicit error log incl. 429, request-id, headers
            headers = _extract_headers(exc)
            info = _rate_limit_from_headers(headers)
            status = _extract_status_from_exc(exc)
            logger.error(
                "AOAI streaming failed status=%s req_id=%s headers=%s exc=%s",
                status,
                info.request_id,
                _summarize_headers({k.lower(): v for k, v in headers.items()}),
                repr(exc),
                extra={"http_status": status, "aoai_request_id": info.request_id, "event_type": "gpt_flow_failure"}
            )
            raise

        finally:
            try:
                dur = lt.stop("aoai:total")
                _log_latency_stop("aoai:total", dur)
            except Exception:
                pass

        # Finalize assistant text
        if full_text:
            agent_history.append({"role": "assistant", "content": full_text})
            await push_final(
                ws,
                _get_agent_sender_name(cm, include_autoauth=True),
                full_text,
                is_acs=is_acs,
            )
            await _broadcast_dashboard(ws, cm, full_text, include_autoauth=False)
            span.set_attribute("response.length", len(full_text))

        # Handle follow-up tool call (if any)
        if tool_state.started:
            span.add_event(
                "tool_execution_starting",
                {"tool_name": tool_state.name, "tool_id": tool_state.call_id},
            )

            agent_history.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_state.call_id,
                            "type": "function",
                            "function": {
                                "name": tool_state.name,
                                "arguments": tool_state.args_json,
                            },
                        }
                    ],
                }
            )
            result = await _handle_tool_call(
                tool_state.name,
                tool_state.call_id,
                tool_state.args_json,
                cm,
                ws,
                agent_name,
                is_acs,
                model_id,
                temperature,
                top_p,
                max_tokens,
                tool_set,
                call_connection_id,
                session_id,
            )
            if result is not None:
                async def persist_tool_results() -> None:
                    cm.persist_tool_output(tool_state.name, result)
                    if isinstance(result, dict) and "slots" in result:
                        cm.update_slots(result["slots"])

                asyncio.create_task(persist_tool_results())
                span.set_attribute("tool.execution_success", True)
                span.add_event("tool_execution_completed", {"tool_name": tool_state.name})
            return result

        span.set_attribute("completion_type", "text_only")
        return None


# ---------------------------------------------------------------------------
# Tool handling (UNCHANGED)
# ---------------------------------------------------------------------------
async def _handle_tool_call(  # noqa: PLR0913
    tool_name: str,
    tool_id: str,
    args: str,
    cm: "MemoManager",
    ws: WebSocket,
    agent_name: str,
    is_acs: bool,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    available_tools: List[Dict[str, Any]],
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a tool with conversation history integrity protection.
    
    This function now implements transaction-like behavior to prevent
    conversation history corruption that leads to OpenAI API errors.

    :param tool_name: Name of the tool function to execute.
    :param tool_id: Unique identifier for this tool call instance.
    :param args: JSON string containing tool function arguments.
    :param cm: MemoManager instance for conversation state.
    :param ws: WebSocket connection for client communication.
    :param agent_name: Identifier for the calling agent context.
    :param is_acs: Flag indicating Azure Communication Services pathway.
    :param model_id: Azure OpenAI model deployment identifier.
    :param temperature: Sampling temperature for follow-up responses.
    :param top_p: Nucleus sampling value for follow-up responses.
    :param max_tokens: Maximum tokens for follow-up completions.
    :param available_tools: List of available tool definitions.
    :param call_connection_id: Optional correlation ID for tracing.
    :param session_id: Optional session ID for tracing correlation.
    :return: Parsed result dictionary from the tool execution.
    :raises ValueError: If tool_name does not exist in function_mapping.
    """
    logger.info(
        "Starting tool execution: tool=%s id=%s args_len=%d",
        tool_name,
        tool_id,
        len(args) if args else 0,
        extra={
            "tool_name": tool_name,
            "tool_id": tool_id,
            "args_length": len(args) if args else 0,
            "agent_name": agent_name,
            "is_acs": is_acs,
            "event_type": "tool_execution_start"
        }
    )

    with create_trace_context(
        name="gpt_flow.handle_tool_call",
        call_connection_id=call_connection_id,
        session_id=session_id,
        metadata={
            "tool_name": tool_name,
            "tool_id": tool_id,
            "agent_name": agent_name,
            "is_acs": is_acs,
            "args_length": len(args) if args else 0,
        },
    ) as trace_ctx:
        # Get conversation history for tool execution
        agent_history = cm.get_history(agent_name)
        
        try:
            params: JSONDict = json.loads(args or "{}")
        except json.JSONDecodeError as json_exc:
            # JSON parsing failure - maintain conversation integrity
            trace_ctx.set_attribute("error", f"Invalid JSON args: {json_exc}")
            logger.error(
                "Invalid JSON in tool args: tool=%s, args=%s, error=%s",
                tool_name,
                args[:200] if args else "None",
                json_exc,
                extra={
                    "tool_name": tool_name,
                    "args_preview": args[:200] if args else "None",
                    "error_type": "json_decode_error",
                    "event_type": "tool_execution_error"
                }
            )
            # Add error tool response to prevent OpenAI "orphaned tool call" errors
            agent_history.append(
                {
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({
                        "error": "Invalid tool arguments format",
                        "message": "The tool arguments could not be parsed. Please try again."
                    }),
                }
            )
            raise ValueError(f"Invalid JSON arguments for tool '{tool_name}': {json_exc}")
        
        fn = function_mapping.get(tool_name)
        if fn is None:
            trace_ctx.set_attribute("error", f"Unknown tool '{tool_name}'")
            logger.error(
                "Unknown tool requested: %s",
                tool_name,
                extra={
                    "tool_name": tool_name,
                    "available_tools": list(function_mapping.keys()),
                    "event_type": "tool_execution_error"
                }
            )
            # Add error tool response to prevent OpenAI "orphaned tool call" errors
            agent_history.append(
                {
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({
                        "error": "Unknown tool",
                        "message": f"Tool '{tool_name}' is not available. Available tools: {list(function_mapping.keys())}"
                    }),
                }
            )
            raise ValueError(f"Unknown tool '{tool_name}'")

        trace_ctx.set_attribute("tool.parameters_count", len(params))
        call_short_id = uuid.uuid4().hex[:8]
        trace_ctx.set_attribute("tool.call_id", call_short_id)

        await push_tool_start(ws, call_short_id, tool_name, params, is_acs=is_acs, session_id=session_id)
        trace_ctx.add_event("tool_start_pushed", {"call_id": call_short_id})

        with create_trace_context(
            name=f"gpt_flow.execute_tool.{tool_name}",
            call_connection_id=call_connection_id,
            session_id=session_id,
            metadata={"tool_name": tool_name, "call_id": call_short_id, "parameters": params},
        ) as exec_ctx:
            t0 = time.perf_counter()
            result = None
            elapsed_ms = 0
            
            try:
                result_raw = await fn(params)
                elapsed_ms = (time.perf_counter() - t0) * 1000

                exec_ctx.set_attribute("execution.duration_ms", elapsed_ms)
                exec_ctx.set_attribute("execution.success", True)

                result: JSONDict = (
                    json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                )
                exec_ctx.set_attribute("result.type", type(result).__name__)

                logger.info(
                    "Tool execution successful: tool=%s duration=%.2fms result_type=%s",
                    tool_name,
                    elapsed_ms,
                    type(result).__name__,
                    extra={
                        "tool_name": tool_name,
                        "execution_duration_ms": elapsed_ms,
                        "result_type": type(result).__name__,
                        "success": True,
                        "event_type": "tool_execution_success"
                    }
                )
                
                # Add successful tool response to prevent conversation corruption
                agent_history.append(
                    {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(result),
                    }
                )
                
            except Exception as tool_exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                exec_ctx.set_attribute("execution.duration_ms", elapsed_ms)
                exec_ctx.set_attribute("execution.success", False)
                exec_ctx.record_exception(tool_exc)

                logger.error(
                    "Tool execution failed: tool=%s duration=%.2fms error=%s",
                    tool_name,
                    elapsed_ms,
                    str(tool_exc),
                    extra={
                        "tool_name": tool_name,
                        "execution_duration_ms": elapsed_ms,
                        "error_type": type(tool_exc).__name__,
                        "error_message": str(tool_exc),
                        "success": False,
                        "event_type": "tool_execution_error"
                    }
                )
                
                # Add error tool response to prevent OpenAI "orphaned tool call" errors
                # This is the #1 cause of conversation corruption and 400 API errors
                error_result = {
                    "error": type(tool_exc).__name__,
                    "message": "Tool execution failed. Please try again or contact support.",
                    "details": str(tool_exc)[:500]  # Truncate long error messages
                }
                
                agent_history.append(
                    {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(error_result),
                    }
                )
                
                # Use error result for push_tool_end
                result = error_result
                
                # Still push tool_end with error status
                await push_tool_end(
                    ws,
                    call_short_id,
                    tool_name,
                    "error",
                    elapsed_ms,
                    error=str(tool_exc),
                    is_acs=is_acs,
                    session_id=session_id,
                )
                trace_ctx.add_event("tool_end_pushed", {"elapsed_ms": elapsed_ms, "status": "error"})

                if is_acs:
                    await _broadcast_dashboard(ws, cm, f"🛠️ {tool_name} ❌", include_autoauth=False)

                # CRITICAL: Don't re-raise the exception to prevent conversation corruption
                # Instead, proceed with the error result and let GPT handle the error response
                logger.warning(
                    "Tool execution completed with error, continuing with error result to maintain conversation integrity",
                    extra={
                        "tool_name": tool_name,
                        "error_handled": True,
                        "event_type": "tool_error_recovery"
                    }
                )

        # Only push success tool_end if execution was successful (no error in result)
        if elapsed_ms > 0 and result and (not isinstance(result, dict) or not result.get("error")):
            await push_tool_end(
                ws,
                call_short_id,
                tool_name,
                "success",
                elapsed_ms,
                result=result,
                is_acs=is_acs,
                session_id=session_id,
            )
            trace_ctx.add_event("tool_end_pushed", {"elapsed_ms": elapsed_ms, "status": "success"})

            if is_acs:
                await _broadcast_dashboard(ws, cm, f"🛠️ {tool_name} ✔️", include_autoauth=False)

        logger.info(
            "Starting tool follow-up: tool=%s",
            tool_name,
            extra={"tool_name": tool_name, "event_type": "tool_followup_start"}
        )

        trace_ctx.add_event("starting_tool_followup")

        # Skip follow-up completions when the tool signals session termination (e.g., voicemail)
        should_terminate = False
        if isinstance(result, dict):
            if result.get("terminate_session") or result.get("voicemail_detected"):
                should_terminate = True
            elif isinstance(result.get("data"), dict):
                data = result["data"]
                if data.get("terminate_session") or data.get("voicemail_detected"):
                    should_terminate = True

        if should_terminate:
            trace_ctx.add_event("tool_requested_termination", {"tool_name": tool_name})
            logger.info(
                "Tool %s requested session termination; skipping follow-up completion.",
                tool_name,
                extra={"tool_name": tool_name, "event_type": "tool_termination"},
            )
            trace_ctx.set_attribute("tool.execution_complete", True)
            return result or {}

        # Validate conversation history before follow-up
        try:
            await _process_tool_followup(
                cm,
                ws,
                agent_name,
                is_acs,
                model_id,
                temperature,
                top_p,
                max_tokens,
                available_tools,
                call_connection_id,
                session_id,
            )
        except Exception as followup_exc:
            logger.error(
                "Tool follow-up failed: tool=%s error=%s",
                tool_name,
                followup_exc,
                extra={
                    "tool_name": tool_name,
                    "followup_error": str(followup_exc),
                    "event_type": "tool_followup_error"
                },
                exc_info=True
            )
            # Don't propagate follow-up errors to prevent cascading failures
            
        trace_ctx.set_attribute("tool.execution_complete", True)
        return result or {}


async def _process_tool_followup(  # noqa: PLR0913
    cm: "MemoManager",
    ws: WebSocket,
    agent_name: str,
    is_acs: bool,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    available_tools: List[Dict[str, Any]],
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Invoke GPT once more after tool execution (no new user input).

    :param cm: MemoManager instance for conversation state.
    :param ws: WebSocket connection for client communication.
    :param agent_name: Identifier for the calling agent context.
    :param is_acs: Flag indicating Azure Communication Services pathway.
    :param model_id: Azure OpenAI model deployment identifier.
    :param temperature: Sampling temperature for follow-up responses.
    :param top_p: Nucleus sampling value for follow-up responses.
    :param max_tokens: Maximum tokens for follow-up completions.
    :param available_tools: List of available tool definitions.
    :param call_connection_id: Optional correlation ID for tracing.
    :param session_id: Optional session ID for tracing correlation.
    """
    with create_trace_context(
        name="gpt_flow.tool_followup",
        call_connection_id=call_connection_id,
        session_id=session_id,
        metadata={
            "agent_name": agent_name,
            "model_id": model_id,
            "is_acs": is_acs,
            "followup_type": "post_tool_execution",
        },
    ) as trace_ctx:
        trace_ctx.add_event("starting_followup_completion")
        await process_gpt_response(
            cm,
            "",  # No new user prompt.
            ws,
            agent_name=agent_name,
            is_acs=is_acs,
            model_id=model_id,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            available_tools=available_tools,
            call_connection_id=call_connection_id,
            session_id=session_id,
        )
        trace_ctx.add_event("followup_completion_finished")
