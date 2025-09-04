"""
ACS Lifecycle Handler - Clean & Simple Implementation
==================================================

Azure Communication Services lifecycle management with simplified tracing.

This handler provides call lifecycle operations with:
- Pluggable orchestrator support for conversation engines
- Clean tracing and observability patterns
- Backward compatibility with existing call operations
- Simple error handling and logging
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, List
from datetime import datetime

from azure.core.exceptions import HttpResponseError
from azure.core.messaging import CloudEvent
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from config import (
    ACS_STREAMING_MODE,
    GREETING,
    GREETING_VOICE_TTS,
)
from apps.rtagent.backend.src.ws_helpers.shared_ws import broadcast_message

from src.enums.stream_modes import StreamMode
from src.stateful.state_managment import MemoManager

from utils.ml_logging import get_logger

# V1 API specific imports
from .acs_media_lifecycle import ACSMediaHandler
from ..events import get_call_event_processor
from ..dependencies.orchestrator import get_orchestrator


logger = get_logger("v1.api.handlers.acs_lifecycle")
tracer = trace.get_tracer(__name__)


def safe_set_span_attributes(span, attributes: dict) -> None:
    """
    Safely set OpenTelemetry span attributes without raising exceptions.

    Defensive method that validates span state and recording status before
    attempting to set attributes. Prevents span operation failures from
    disrupting call processing in production environments.

    Args:
        span: OpenTelemetry span instance to update.
        attributes: Dictionary of attribute key-value pairs to set on the span.

    Note:
        Logs debug messages on failure but does not raise exceptions to
        maintain system stability when tracing is misconfigured.
    """
    try:
        if span and span.is_recording():
            span.set_attributes(attributes)
    except Exception as e:
        logger.debug(f"Failed to set span attributes: {e}")


def _safe_get_event_data(event: CloudEvent) -> Dict[str, Any]:
    """
    Safely extract data from CloudEvent object as a dictionary.

    CloudEvent.data can be various types (dict, str, bytes, etc.). This function
    ensures consistent dictionary access regardless of the original data format,
    with comprehensive error handling for malformed event data.

    Args:
        event: CloudEvent object from Azure Communication Services.

    Returns:
        Dict[str, Any]: Dictionary containing event data, empty dict if
        parsing fails or data format is unsupported.

    Note:
        Handles JSON strings, byte arrays, and object attributes gracefully.
        Returns empty dictionary as fallback to prevent downstream errors.
    """
    try:
        data = event.data

        # If already a dictionary, return as-is
        if isinstance(data, dict):
            return data

        # If string, try to parse as JSON
        if isinstance(data, str):
            return json.loads(data)

        # If bytes, decode and parse as JSON
        if isinstance(data, bytes):
            return json.loads(data.decode("utf-8"))

        # For other types, try to convert to dict if it has dict-like attributes
        if hasattr(data, "__dict__"):
            return data.__dict__

        # Last resort: return empty dict
        logger.warning(
            f"Unexpected CloudEvent data type: {type(data)}, returning empty dict"
        )
        return {}

    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
        logger.error(
            f"Error parsing CloudEvent data: {e}, data type: {type(event.data)}"
        )
        return {}


def _get_event_field(event: CloudEvent, field_name: str, default: Any = None) -> Any:
    """
    Safely extract a specific field from CloudEvent data with fallback handling.

    Convenience method that combines event data extraction with field access,
    providing consistent error handling and default value support for
    CloudEvent field processing.

    Args:
        event: CloudEvent object containing the data to extract from.
        field_name: Name of the field to extract from the event data.
        default: Default value to return if field is not found or extraction fails.

    Returns:
        Any: Field value if found, otherwise the default value.
    """
    data = _safe_get_event_data(event)
    return data.get(field_name, default)


class ACSLifecycleHandler:
    """
    Azure Communication Services call lifecycle manager.

    Provides call lifecycle operations with:
    - Pluggable orchestrator support for different conversation engines
    - Clean tracing and observability
    - Outbound/inbound call management
    - Event processing with backward compatibility
    """

    def __init__(self):
        """
        Initialize ACS lifecycle handler.
        """
        self.logger = get_logger("api.v1.handlers.acs_lifecycle")

    async def _emit_call_event(
        self,
        event_type: str,
        call_connection_id: str,
        data: Dict[str, Any],
        redis_mgr=None,
    ) -> None:
        """
        Emit a call event through the V1 event system for asynchronous processing.

        Creates and processes CloudEvent instances through the call event processor
        to enable decoupled call lifecycle management. Provides error isolation
        to prevent event processing failures from disrupting call operations.

        Args:
            event_type: Type of event to emit (e.g., 'call.initiated', 'call.ended').
            call_connection_id: Unique call connection identifier for event correlation.
            data: Additional event data payload to include with the base call information.
            redis_mgr: Redis manager instance for state access during event processing.

        Note:
            Uses mock request state for event processing to maintain compatibility
            with existing event processor interfaces while supporting new lifecycle patterns.
        """
        try:
            from azure.core.messaging import CloudEvent
            from ..events import get_call_event_processor

            # Create mock request state for event processing
            class MockRequestState:
                def __init__(self, redis_mgr):
                    self.redis = redis_mgr
                    self.acs_caller = None
                    self.clients = []

            # Create CloudEvent
            cloud_event = CloudEvent(
                source="api/v1/lifecycle",
                type=event_type,
                data={"callConnectionId": call_connection_id, **data},
            )

            # Process through event system
            processor = get_call_event_processor()
            await processor.process_events([cloud_event], MockRequestState(redis_mgr))

        except Exception as e:
            self.logger.error(f"Failed to emit call event {event_type}: {e}")

    async def start_outbound_call(
        self,
        acs_caller,
        target_number: str,
        redis_mgr,
        call_id: str = None,
        browser_session_id: str = None,  # NEW: Browser session ID for UI coordination
    ) -> Dict[str, Any]:
        """
        Initiate an outbound call with orchestrator support.

        :param acs_caller: The ACS caller instance
        :param target_number: The phone number to call (E.164 format)
        :type target_number: str
        :param redis_mgr: Redis manager instance for state persistence
        :param call_id: Optional call ID for tracking (auto-generated if None)
        :type call_id: str
        :param browser_session_id: Browser session ID for UI/ACS coordination
        :type browser_session_id: str
        :return: Call initiation result
        :rtype: Dict[str, Any]
        :raises HTTPException: When ACS caller is not initialized or call fails
        """

        if not acs_caller:
            raise HTTPException(503, "ACS Caller not initialised")

        with tracer.start_as_current_span(
            "v1.acs_lifecycle.start_outbound_call",
            kind=SpanKind.SERVER,
            attributes={
                "call.target_number": target_number,
                "call.id": call_id or "auto_generated",
                "call.direction": "outbound",
                "api.version": "v1",
            },
        ) as span:
            try:
                logger.info(f"Starting outbound call to {target_number} ")

                start_time = time.perf_counter()
                result = await acs_caller.initiate_call(
                    target_number, stream_mode=ACS_STREAMING_MODE
                )
                latency = time.perf_counter() - start_time

                safe_set_span_attributes(
                    span,
                    {
                        "call.initiation_latency_ms": latency * 1000,
                        "call.result_status": result.get("status"),
                    },
                )

                if result.get("status") != "created":
                    span.set_status(Status(StatusCode.ERROR, "Call initiation failed"))
                    logger.error(f"❌ Call initiation failed: {result}")
                    return {"status": "failed", "message": "Call initiation failed"}

                call_id = result["call_id"]
                safe_set_span_attributes(
                    span,
                    {
                        "call.connection.id": call_id,
                        "call.success": True,
                        "browser.session_id": browser_session_id,
                    },
                )

                # Store browser session ID mapping for media endpoint coordination
                if browser_session_id and redis_mgr:
                    try:
                        # Store the mapping: call_connection_id -> browser_session_id
                        # This enables the media endpoint to use the browser's session ID
                        await redis_mgr.set_value_async(
                            f"call_session_map:{call_id}",
                            browser_session_id,
                            ttl_seconds=3600,  # Expire after 1 hour
                        )
                        logger.info(
                            f"🔗 Stored session mapping: {call_id} -> {browser_session_id}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store session mapping: {e}")

                # Emit call initiated event for business logic processing
                await self._emit_call_event(
                    "V1.Call.Initiated",
                    call_id,
                    {
                        "target_number": target_number,
                        "api_version": "v1",
                        "call_direction": "outbound",
                        "initiated_at": datetime.utcnow().isoformat() + "Z",
                        "browser_session_id": browser_session_id,  # Include in event data
                    },
                    redis_mgr,
                )

                span.set_status(Status(StatusCode.OK))
                logger.info(
                    f"✅ Call initiated successfully: {call_id} (latency: {latency:.3f}s)"
                )

                return {
                    "status": "success",
                    "message": "Call initiated",
                    "callId": call_id,
                    "initiated_at": datetime.utcnow().isoformat() + "Z",
                }

            except (HttpResponseError, RuntimeError) as exc:
                safe_set_span_attributes(
                    span,
                    {
                        "error.type": type(exc).__name__,
                        "error.message": str(exc),
                    },
                )
                span.set_status(Status(StatusCode.ERROR, f"ACS error: {exc}"))
                logger.error(f"❌ ACS error during call initiation: {exc}")

                raise HTTPException(
                    500,
                    detail={
                        "error": str(exc),
                        "target_number": target_number,
                        "call_id": call_id,
                    },
                ) from exc

            except Exception as exc:
                safe_set_span_attributes(
                    span,
                    {
                        "error.type": type(exc).__name__,
                        "error.message": str(exc),
                    },
                )
                span.set_status(Status(StatusCode.ERROR, f"Unexpected error: {exc}"))
                logger.error(f"❌ Unexpected error during call initiation: {exc}")

                raise HTTPException(
                    400,
                    detail={
                        "error": str(exc),
                        "target_number": target_number,
                        "call_id": call_id,
                    },
                ) from exc

    async def accept_inbound_call(
        self,
        request_body: Dict[str, Any],
        acs_caller,
    ) -> JSONResponse:
        """
        Accept and process inbound call events.

        Handles Event Grid subscription validation and incoming calls with
        simplified logic and V1 API migration standards.

        :param request_body: Event Grid request body containing events
        :type request_body: Dict[str, Any]
        :param acs_caller: The ACS caller instance for call operations
        :return: Validation response or call acceptance status
        :rtype: JSONResponse
        :raises HTTPException: When ACS caller is not initialized or processing fails
        """
        if not acs_caller:
            raise HTTPException(503, "ACS Caller not initialised")

        with tracer.start_as_current_span(
            "v1.acs_lifecycle.accept_inbound_call",
            kind=SpanKind.SERVER,
            attributes={
                "events.count": len(request_body),
                "api.version": "v1",
            },
        ) as span:
            try:
                logger.info(f"🏠 Processing {len(request_body)} inbound events")

                for event in request_body:
                    event_type = event.get("eventType")
                    event_data = event.get("data", {})

                    if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
                        return await self._handle_subscription_validation(
                            event_data, span
                        )
                    elif event_type == "Microsoft.Communication.IncomingCall":
                        return await self._handle_incoming_call(
                            event_data, acs_caller, span
                        )
                    else:
                        logger.info(f"📝 Ignoring unhandled event type: {event_type}")

                # If no events were processed, return success
                safe_set_span_attributes(
                    span, {"operation.result": "no_processable_events"}
                )
                span.set_status(Status(StatusCode.OK))
                return JSONResponse({"status": "no events processed"}, status_code=200)

            except HTTPException:
                raise
            except Exception as exc:
                safe_set_span_attributes(
                    span,
                    {
                        "error.type": type(exc).__name__,
                        "error.message": str(exc),
                    },
                )
                span.set_status(Status(StatusCode.ERROR, f"Unexpected error: {exc}"))
                logger.error(f"❌ Error processing inbound call: {exc}")
                raise HTTPException(400, "Invalid request body") from exc

    async def _handle_subscription_validation(
        self, event_data: Dict[str, Any], span
    ) -> JSONResponse:
        """
        Handle Event Grid subscription validation.

        :param event_data: Event data containing validation code
        :type event_data: Dict[str, Any]
        :param span: OpenTelemetry span for tracing
        :return: JSON response with validation code
        :rtype: JSONResponse
        :raises HTTPException: When validation code is missing
        """
        validation_code = event_data.get("validationCode")

        if not validation_code:
            safe_set_span_attributes(span, {"validation.error": "missing_code"})
            span.set_status(Status(StatusCode.ERROR, "Validation code not found"))
            raise HTTPException(400, "Validation code not found in event data")

        safe_set_span_attributes(span, {"validation.success": True})
        span.set_status(Status(StatusCode.OK))
        logger.info("✅ Event Grid subscription validation successful")

        return JSONResponse({"validationResponse": validation_code}, status_code=200)

    async def _handle_incoming_call(
        self, event_data: Dict[str, Any], acs_caller, span
    ) -> JSONResponse:
        """
        Handle incoming call event.

        :param event_data: Event data containing call information
        :type event_data: Dict[str, Any]
        :param acs_caller: ACS caller instance for call operations
        :param span: OpenTelemetry span for tracing
        :return: JSON response with call acceptance status
        :rtype: JSONResponse
        :raises HTTPException: When call context is missing or call answering fails
        """
        # Extract caller information
        caller_info = event_data.get("from", {})
        caller_id = self._extract_caller_id(caller_info)
        incoming_call_context = event_data.get("incomingCallContext")

        if not incoming_call_context:
            safe_set_span_attributes(span, {"call.error": "missing_context"})
            span.set_status(Status(StatusCode.ERROR, "Missing incoming call context"))
            raise HTTPException(400, "Missing incoming call context")

        safe_set_span_attributes(
            span,
            {
                "call.caller_id": caller_id,
                "call.direction": "inbound",
                "call.from.kind": caller_info.get("kind"),
            },
        )

        logger.info(f"Answering incoming call from {caller_id}")

        # Answer the call
        start_time = time.perf_counter()
        answer_result = await acs_caller.answer_incoming_call(
            incoming_call_context=incoming_call_context,
            stream_mode=ACS_STREAMING_MODE,
        )
        latency = time.perf_counter() - start_time

        if not answer_result:
            safe_set_span_attributes(span, {"call.answer_failed": True})
            span.set_status(Status(StatusCode.ERROR, "Failed to answer call"))
            raise HTTPException(500, "Failed to answer incoming call")

        call_connection_id = getattr(answer_result, "call_connection_id", None)
        if call_connection_id:
            safe_set_span_attributes(
                span,
                {
                    "call.connection.id": call_connection_id,
                    "call.answer_latency_ms": latency * 1000,
                    "call.answered": True,
                },
            )

            logger.info(
                f"✅ Call answered successfully: {call_connection_id} (latency: {latency:.3f}s)"
            )
        else:
            logger.warning("⚠️ Call answered but no connection ID available")

        span.set_status(Status(StatusCode.OK))
        return JSONResponse(
            {
                "status": "call answered",
                "call_connection_id": call_connection_id,
                "caller_id": caller_id,
                "answered_at": datetime.utcnow().isoformat() + "Z",
            },
            status_code=200,
        )

    def _extract_caller_id(self, caller_info: Dict[str, Any]) -> str:
        """
        Extract caller ID from caller information.

        :param caller_info: Caller information dictionary
        :type caller_info: Dict[str, Any]
        :return: Caller ID string
        :rtype: str
        """
        if caller_info.get("kind") == "phoneNumber":
            return caller_info.get("phoneNumber", {}).get("value", "unknown")
        return caller_info.get("rawId", "unknown")

    async def process_call_events(
        self,
        events: list,
        request,
    ) -> Dict[str, str]:
        """
        Process runtime call events through the V1 event system.

        This method delegates ALL event processing to the events system for
        consistent handling of all ACS webhook events.

        :param events: List of ACS webhook events to process
        :type events: list
        :param request: FastAPI request object containing app state dependencies
        :return: Processing status and metadata
        :rtype: Dict[str, str]
        """
        from ..events import get_call_event_processor, register_default_handlers
        from azure.core.messaging import CloudEvent

        with tracer.start_as_current_span(
            "v1.acs_lifecycle.process_call_events",
            kind=SpanKind.SERVER,
            attributes={
                "events.count": len(events),
                "api.version": "v1",
                "processing.delegated_to": "events_system",
            },
        ) as span:
            for idx, event in enumerate(events):
                call_connection_id = _get_event_field(event, "callConnectionId")
                safe_set_span_attributes(
                    span,
                    {
                        f"event.{idx}.type": getattr(event, "type", "Unknown"),
                        f"event.{idx}.call_connection_id": call_connection_id,
                    },
                )

            try:
                # Ensure handlers are registered
                register_default_handlers()

                # Get processor and convert events to CloudEvents
                processor = get_call_event_processor()
                cloud_events = []

                for event in events:
                    if isinstance(event, CloudEvent):
                        cloud_events.append(event)
                    elif hasattr(event, "type") and hasattr(event, "data"):
                        # Convert ACS event object to CloudEvent
                        cloud_event = CloudEvent(
                            source="azure.communication.callautomation",
                            type=event.type,
                            data=event.data,
                        )
                        cloud_events.append(cloud_event)
                    elif isinstance(event, dict):
                        # Convert dict to CloudEvent
                        event_type = event.get("eventType") or event.get(
                            "type", "Unknown"
                        )
                        cloud_event = CloudEvent(
                            source="azure.communication.callautomation",
                            type=event_type,
                            data=event.get("data", event),
                        )
                        cloud_events.append(cloud_event)

                # Delegate to events system
                result = await processor.process_events(cloud_events, request.app.state)

                safe_set_span_attributes(
                    span,
                    {
                        "events.processed": result.get("processed", 0),
                        "events.failed": result.get("failed", 0),
                        "delegation.success": True,
                    },
                )

                logger.info(f"✅ Delegated {len(events)} events to V1 events system")

                # Return legacy-compatible response
                return {
                    "status": result.get("status", "success"),
                    "message": f"Processed {result.get('processed', 0)} events via V1 events system",
                    "processed_events": result.get("processed", 0),
                    "failed_events": result.get("failed", 0),
                    "api_version": "v1",
                    "processing_system": "events_v1",
                    "processed_at": datetime.utcnow().isoformat() + "Z",
                }

            except Exception as exc:
                logger.error(f"❌ Event processing delegation failed: {exc}")
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                safe_set_span_attributes(
                    span,
                    {
                        "error": True,
                        "error.message": str(exc),
                        "delegation.failed": True,
                    },
                )

                return {
                    "status": "error",
                    "message": f"Event processing failed: {exc}",
                    "api_version": "v1",
                    "processing_system": "events_v1",
                    "processed_at": datetime.utcnow().isoformat() + "Z",
                }


# Utility functions for ACS operations
def get_participant_phone(event: CloudEvent, cm: MemoManager) -> Optional[str]:
    """
    Extract participant phone number from event.

    :param event: CloudEvent containing participant information
    :type event: CloudEvent
    :param cm: MemoManager for context access
    :type cm: MemoManager
    :return: Participant phone number or None if not found
    :rtype: Optional[str]
    """

    def digits_tail(s: Optional[str], n: int = 10) -> str:
        return "".join(ch for ch in (s or "") if ch.isdigit())[-n:]

    participants = _get_event_field(event, "participants", []) or []
    target_number = cm.get_context("target_number")
    target_tail = digits_tail(target_number) if target_number else ""

    pstn_candidates = []
    for p in participants:
        ident = p.get("identifier", {}) or {}
        # prefer explicit phone number
        phone = (ident.get("phoneNumber") or {}).get("value")
        # fallback: rawId like "4:+12246234441"
        if not phone:
            raw = ident.get("rawId")
            if isinstance(raw, str) and raw.startswith("4:"):
                phone = raw[2:]
        if phone:
            pstn_candidates.append(phone)

    if not pstn_candidates:
        return None

    if target_tail:
        for ph in pstn_candidates:
            if digits_tail(ph) == target_tail:
                return ph

    # fallback to first PSTN participant
    return pstn_candidates[0]


def create_enterprise_media_handler(
    websocket,
    orchestrator: callable,
    call_connection_id: str,
    recognizer,
    cm: MemoManager,
    session_id: str,
) -> ACSMediaHandler:
    """
    Factory function for creating media handlers.

    :param websocket: WebSocket connection
    :param orchestrator: Conversation orchestrator
    :type orchestrator: callable
    :param call_connection_id: ACS call connection ID
    :type call_connection_id: str
    :param recognizer: Speech recognition client
    :param cm: Conversation memory manager
    :type cm: MemoManager
    :param session_id: Session identifier
    :type session_id: str
    :return: Configured ACSMediaHandler instance
    :rtype: ACSMediaHandler
    """
    if orchestrator is None:
        orchestrator = get_orchestrator()
    return ACSMediaHandler(
        ws=websocket,
        orchestrator=orchestrator,
        call_connection_id=call_connection_id,
        recognizer=recognizer,
        cm=cm,
        session_id=session_id,
    )
