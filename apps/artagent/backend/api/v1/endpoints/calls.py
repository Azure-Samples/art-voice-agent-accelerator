"""
Call Management Endpoints
========================

REST API endpoints for managing phone calls through Azure Communication Services.
"""

import asyncio
from typing import Any

from apps.artagent.backend.api.v1.schemas.call import (
    CallHangupResponse,
    CallInitiateRequest,
    CallInitiateResponse,
    CallListResponse,
    CallStatusResponse,
    CallTerminateRequest,
)
from apps.artagent.backend.src.utils.tracing import (
    trace_acs_dependency,
    trace_acs_operation,
)
from azure.core.messaging import CloudEvent
from config import ACS_STREAMING_MODE
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from src.enums.stream_modes import StreamMode
from utils.ml_logging import get_logger

from ..events import CallEventProcessor

# V1 imports
from ..handlers.acs_call_lifecycle import ACSLifecycleHandler

logger = get_logger("api.v1.calls")
tracer = trace.get_tracer(__name__)
router = APIRouter()

_BOOL_TRUE = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}


def _coerce_optional_bool(value: Any) -> bool | None:
    """Normalize loosely-typed boolean inputs to strict Optional[bool]."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
        return None
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def create_call_event(event_type: str, call_id: str, data: dict) -> CloudEvent:
    """
    Create a CloudEvent for call-related operations using the V1 event system.

    Factory function that generates properly formatted CloudEvent instances for
    call lifecycle management. Events are processed by CallEventProcessor for
    asynchronous call handling and state management within the ACS integration.

    Args:
        event_type: Type of call event (e.g., 'call.initiated', 'call.ended').
        call_id: Unique call connection identifier for event correlation.
        data: Event data payload containing call-specific information.

    Returns:
        CloudEvent: Properly formatted event ready for V1 event processor
        consumption with standardized source and data structure.

    Note:
        When using with CallEventProcessor.process_events(), pass
        request.app.state as the second argument for dependency injection.
    """
    return CloudEvent(
        source="api/v1/calls",
        type=event_type,
        data={"callConnectionId": call_id, **data},
    )


@router.post(
    "/initiate",
    response_model=CallInitiateResponse,
    summary="Initiate Outbound Call",
    description="""
    Initiate a new outbound call to the specified phone number.
    
    This endpoint:
    - Validates the phone number format
    - Generates a unique call ID
    - Emits a call initiation event through the V1 event system
    - Returns immediately with call status
    
    The actual call establishment is handled asynchronously through Azure Communication Services.
    """,
    tags=["Call Management"],
    responses={
        200: {
            "description": "Call initiation successful",
            "content": {
                "application/json": {
                    "example": {
                        "call_id": "call_abc12345",
                        "status": "initiating",
                        "target_number": "+1234567890",
                        "message": "Call initiation requested for +1234567890",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request (e.g., malformed phone number)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid phone number format. Must be in E.164 format (e.g., +1234567890)"
                    }
                }
            },
        },
        500: {
            "description": "Internal server error during call initiation",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to initiate call: Azure Communication Service unavailable"
                    }
                }
            },
        },
    },
)
async def initiate_call(
    request: CallInitiateRequest,
    http_request: Request,
) -> CallInitiateResponse:
    """
    Initiate an outbound call through Azure Communication Services.

    Creates a new outbound call to the specified phone number using ACS call
    automation. Validates phone number format, generates unique call tracking
    ID, and processes the request asynchronously through the V1 event system
    for reliable call establishment and monitoring.

    Args:
        request: Call initiation request containing target phone number and
                optional context information for session coordination.
        http_request: FastAPI request object providing access to application
                     state and dependency injection services.

    Returns:
        CallInitiateResponse: Call status information including unique call ID,
        current status, target number, and confirmation message.

    Raises:
        HTTPException: When call initiation fails due to invalid phone number
                      format, ACS service unavailability, or system errors.

    Example:
        >>> request = CallInitiateRequest(target_number="+1234567890")
        >>> response = await initiate_call(request, http_request)
        >>> print(response.call_id)
    """
    with trace_acs_operation(
        tracer, logger, "initiate_call", session_id=None, call_connection_id=None
    ) as op:
        op.log_info(f"Initiating call to {request.target_number}")

        try:
            # Create ACS lifecycle handler
            acs_handler = ACSLifecycleHandler()

            with trace_acs_dependency(
                tracer, logger, "acs_lifecycle", "start_outbound_call"
            ) as dep_op:
                # Extract browser session ID from request context for UI coordination
                browser_session_id = (
                    request.context.get("browser_session_id") if request.context else None
                )

                # Log session correlation for debugging
                logger.info(
                    f"📞 [BACKEND] Phone call initiation received with browser_session_id: {browser_session_id}"
                )
                logger.info(
                    f"📞 [BACKEND] Target number: {request.target_number} | Session ID: {browser_session_id}"
                )

                # Determine effective streaming mode (request override > context > env default)
                effective_stream_mode = ACS_STREAMING_MODE
                override_candidates = []
                if request.streaming_mode is not None:
                    override_candidates.append(request.streaming_mode)
                if request.context and request.context.get("streaming_mode") is not None:
                    override_candidates.append(request.context.get("streaming_mode"))

                for candidate in override_candidates:
                    if candidate is None:
                        continue
                    if isinstance(candidate, StreamMode):
                        effective_stream_mode = candidate
                        break
                    if isinstance(candidate, str):
                        try:
                            effective_stream_mode = StreamMode.from_string(candidate)
                            break
                        except ValueError as exc:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=str(exc),
                            ) from exc

                if dep_op.span and hasattr(dep_op.span, "set_attribute"):
                    try:
                        dep_op.span.set_attribute(
                            "stream.mode.requested", str(effective_stream_mode)
                        )
                    except Exception:  # noqa: BLE001
                        dep_op.log_debug(
                            "Unable to record requested stream mode on dependency span",
                            stream_mode=str(effective_stream_mode),
                        )

                record_call_override: bool | None = _coerce_optional_bool(request.record_call)
                if record_call_override is None and request.context:
                    record_call_override = _coerce_optional_bool(request.context.get("record_call"))

                result = await acs_handler.start_outbound_call(
                    acs_caller=http_request.app.state.acs_caller,
                    target_number=request.target_number,
                    redis_mgr=http_request.app.state.redis,
                    browser_session_id=browser_session_id,  # 🎯 Pass browser session for coordination
                    stream_mode=effective_stream_mode,
                    record_call=record_call_override,
                )
                if result.get("status") == "success":
                    call_id = result.get("callId")
                    recording_enabled = result.get("recording_enabled")

                    # Pre-initialize a Voice Live session bound to this call (no audio yet, no pool)
                    try:
                        # Store browser-session mapping and optionally the Voice Live agent
                        if hasattr(http_request.app.state, "conn_manager"):
                            base_context = {
                                "target_number": request.target_number,
                                "browser_session_id": browser_session_id,
                                "streaming_mode": str(effective_stream_mode),
                            }
                            await http_request.app.state.conn_manager.set_call_context(
                                call_id, base_context
                            )

                    except Exception as e:
                        logger.warning(f"Failed to persist call context for {call_id}: {e}")

                    # Create V1 event processor instance and emit call initiation event
                    from ..events import get_call_event_processor

                    event_processor = (
                        get_call_event_processor()
                    )  # Use singleton with registered handlers

                    # Create CloudEvent for call initiation using helper function
                    call_initiated_event = create_call_event(
                        event_type="CallInitiated",  # Custom event type for API calls
                        call_id=call_id,
                        data={
                            "target_number": request.target_number,
                            "initiated_at": result.get("initiated_at"),
                            "api_version": "v1",
                            "status": "initiating",
                            "streaming_mode": str(effective_stream_mode),
                            "recording_enabled": recording_enabled,
                        },
                    )

                    # Process through V1 event system with request state
                    await event_processor.process_events(
                        [call_initiated_event], http_request.app.state
                    )

                    op.log_info(f"Call initiated successfully: {call_id}")

                    return CallInitiateResponse(
                        call_id=call_id,
                        status="initiating",
                        target_number=request.target_number,
                        message=result.get("message", "call initiated successfully"),
                        streaming_mode=effective_stream_mode,
                        initiated_at=result.get("initiated_at"),
                        recording_enabled=recording_enabled,
                        details={
                            "api_version": "v1",
                            "acs_result": result,
                            "streaming_mode": str(effective_stream_mode),
                            "recording_enabled": recording_enabled,
                        },
                    )

            # Handle failure case
            op.set_error(result.get("message", "Unknown error"))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Call initiation failed: {result.get('message', 'Unknown error')}",
            )

        except HTTPException:
            raise
        except Exception as e:
            op.set_error(str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}",
            )


@router.get(
    "/",
    response_model=CallListResponse,
    summary="List Calls",
    description="""
    Retrieve a paginated list of calls with optional filtering.
    
    Supports:
    - Pagination with page and limit parameters
    - Filtering by call status
    - Sorting by creation time (newest first)
    """,
    tags=["Call Management"],
    responses={
        200: {
            "description": "Calls retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "calls": [
                            {
                                "call_id": "call_abc12345",
                                "status": "connected",
                                "duration": 120,
                                "participants": [],
                                "events": [],
                            }
                        ],
                        "total": 25,
                        "page": 1,
                        "limit": 10,
                    }
                }
            },
        },
        400: {
            "description": "Invalid pagination parameters",
            "content": {
                "application/json": {"example": {"detail": "Page number must be positive"}}
            },
        },
    },
)
async def list_calls(
    request: Request,
    page: int = Query(
        1,
        ge=1,
        description="Page number (1-based)",
        examples={"default": {"summary": "page number", "value": 1}},
    ),
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of items per page (1-100)",
        examples={"default": {"summary": "items per page", "value": 10}},
    ),
    status_filter: str | None = Query(
        None,
        description="Filter calls by status",
        enum=[
            "initiating",
            "ringing",
            "connected",
            "on_hold",
            "disconnected",
            "failed",
        ],
        examples={"default": {"summary": "status filter", "value": "connected"}},
    ),
) -> CallListResponse:
    """
    List calls with pagination and filtering.

    :param request: FastAPI request object for accessing app state
    :type request: Request
    :param page: Page number (1-based)
    :type page: int
    :param limit: Number of items per page (1-100)
    :type limit: int
    :param status_filter: Filter calls by status
    :type status_filter: Optional[str]
    :return: Paginated list of calls with filtering results
    :rtype: CallListResponse
    :raises HTTPException: When database query fails or invalid parameters provided
    """
    with trace_acs_operation(tracer, logger, "list_calls") as op:
        try:
            op.log_info(f"Listing calls: page {page}, limit {limit}, filter: {status_filter}")

            # Get cosmos DB manager from app state
            cosmos_manager = request.app.state.cosmos

            # Build query filter
            query_filter = {}
            if status_filter:
                query_filter["status"] = status_filter

            # Query calls from database
            all_calls = cosmos_manager.query_documents(query_filter)

            # Filter to only call documents (those with call_id field)
            call_docs = [doc for doc in all_calls if "call_id" in doc]

            # Apply pagination
            start = (page - 1) * limit
            end = start + limit
            paginated_calls = call_docs[start:end]

            # Convert database documents to response models
            calls = []
            for doc in paginated_calls:
                call_response = CallStatusResponse(
                    call_id=doc.get("call_id", doc.get("_id", "unknown")),
                    status=doc.get("status", "unknown"),
                    duration=doc.get("duration", 0),
                    participants=doc.get("participants", []),
                    events=doc.get("events", []),
                )
                calls.append(call_response)

            op.log_info(f"Found {len(call_docs)} total calls, returning {len(calls)}")

            # Optional: Emit event for call list operations (for monitoring/analytics)
            if call_docs:  # Only emit if we actually found calls
                try:
                    event_processor = CallEventProcessor()
                    list_event = create_call_event(
                        event_type="CallListRequested",
                        call_id="api-operation",  # Use generic ID for API operations
                        data={
                            "total_calls": len(call_docs),
                            "returned_calls": len(calls),
                            "page": page,
                            "limit": limit,
                            "status_filter": status_filter,
                            "api_version": "v1",
                        },
                    )
                    # Fire and forget - don't await to avoid adding latency
                    import asyncio

                    asyncio.create_task(
                        event_processor.process_events([list_event], request.app.state)
                    )
                except Exception as e:
                    # Log but don't fail the main operation
                    op.log_info(f"Failed to emit list event: {e}")

            return CallListResponse(calls=calls, total=len(call_docs), page=page, limit=limit)

        except Exception as e:
            op.set_error(str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list calls: {str(e)}",
            )


@router.post(
    "/terminate",
    response_model=CallHangupResponse,
    summary="Terminate Active Call",
    description="Request hangup for an active ACS call by call_id (call_connection_id).",
    tags=["Call Management"],
)
async def terminate_call(request: Request, payload: CallTerminateRequest) -> CallHangupResponse:
    """Terminate an active ACS call and clean up associated browser session."""
    conn_manager = getattr(request.app.state, "conn_manager", None)
    acs_caller = getattr(request.app.state, "acs_caller", None)
    if conn_manager is None or acs_caller is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ACS infrastructure not initialized",
        )

    acs_client = getattr(acs_caller, "client", None)
    if not acs_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ACS client unavailable",
        )

    try:
        call_conn = acs_client.get_call_connection(payload.call_id)
        await asyncio.wait_for(
            call_conn.hang_up(is_for_everyone=True),
            timeout=5.0,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timed out waiting for ACS hangup",
        )
    except Exception as exc:
        logger.error("ACS hangup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to terminate ACS call",
        ) from exc

    try:
        await conn_manager.pop_call_context(payload.call_id)
    except Exception:
        logger.debug("Failed to remove call context for %s", payload.call_id)

    return CallHangupResponse(
        call_id=payload.call_id,
        status="terminated",
        message="Call hangup requested",
    )


@router.post(
    "/answer",
    summary="Answer Inbound Call",
    description="""
    Handle inbound call events and Event Grid subscription validation.
    
    This endpoint:
    - Validates Event Grid subscription requests
    - Answers incoming calls automatically with orchestrator selection
    - Initializes conversation state with features
    - Supports pluggable conversation orchestrators
    - Provides advanced tracing and monitoring
    
    Enhanced V1 features:
    - Pluggable orchestrator injection for conversation handling
    - Enhanced state management with orchestrator metadata
    - Advanced observability and correlation
    - Production-ready error handling
    """,
    tags=["Call Management"],
    responses={
        200: {
            "description": "Inbound call processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "call answered",
                        "orchestrator": "gpt_flow",
                        "acs_features": {
                            "orchestrator_support": True,
                            "advanced_tracing": True,
                            "api_version": "v1",
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid request body",
            "content": {
                "application/json": {"example": {"detail": "Invalid Event Grid request format"}}
            },
        },
        503: {
            "description": "Service dependencies not available",
            "content": {"application/json": {"example": {"detail": "ACS not initialised"}}},
        },
    },
)
async def answer_inbound_call(
    http_request: Request,
) -> JSONResponse:
    """
    Answer inbound calls with orchestrator support.

    This endpoint handles Event Grid subscription validation and
    automatic call answering with conversation routing.

    :param http_request: FastAPI request object containing Event Grid webhook payload
    :type http_request: Request
    :return: Processing result
    :rtype: JSONResponse
    :raises HTTPException: When dependencies are unavailable or processing fails
    """
    # Validate dependencies
    if not http_request.app.state.acs_caller:
        return JSONResponse({"error": "ACS not initialised"}, status_code=503)

    with trace_acs_operation(tracer, logger, "answer_inbound_call") as op:
        op.log_info("Processing inbound call")

        try:
            request_body = await http_request.json()

            def _extract_recording_override(payload: Any) -> bool | None:
                if isinstance(payload, dict):
                    candidates = [
                        payload.get("recordCall"),
                        payload.get("record_call"),
                        payload.get("recordingEnabled"),
                    ]
                    for candidate in candidates:
                        coerced = _coerce_optional_bool(candidate)
                        if coerced is not None:
                            return coerced

                    data_section = payload.get("data")
                    if data_section is not None:
                        return _extract_recording_override(data_section)

                    return None

                if isinstance(payload, list):
                    for item in payload:
                        coerced = _extract_recording_override(item)
                        if coerced is not None:
                            return coerced
                return None

            record_call_override = None
            query_value = http_request.query_params.get(
                "recordCall"
            ) or http_request.query_params.get("record_call")
            record_call_override = _coerce_optional_bool(query_value)
            if record_call_override is None:
                record_call_override = _extract_recording_override(request_body)

            # Create handler with orchestrator injection
            acs_handler = ACSLifecycleHandler()

            with trace_acs_dependency(
                tracer, logger, "acs_lifecycle", "accept_inbound_call"
            ) as dep_op:

                # Sample Payload for D365 Transfer
                # 'id' = '14bd8e31-bd47-4ae3-bbf6-21b103c21ba3_1fb971cadf0143cda27019ac20805d7c.8759326'
                # 'topic' = '/subscriptions/46c8d580-4e4e-43b3-b3db-4a2daea037b1/resourcegroups/devops-shared/providers/microsoft.communication/communicationservices/acs-local-test'
                # 'subject' = '/phoneCall/caller/+18557047380/recipient/+18666881708'
                # 'data' = {'to': {'kind': 'phoneNumber', 'rawId': '4:+18666881708', 'phoneNumber': {...}}, 'from': {'kind': 'phoneNumber', 'rawId': '4:+18557047380', 'phoneNumber': {...}}, 'serverCallId': 'aHR0cHM6Ly9hcGkuZmxpZ2h0cHJveHkuc2t5cGUuY29tL2FwaS92Mi9jcC9jb252LXVzZWEyLTA1LXByb2QtY...EyOC0yNy0xMjMmZT02Mzg5ODE1MjIwNzIwOTgwNDM=', 'callerDisplayName': '', 'incomingCallContext': 'eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJjYyI6Ikg0c0lBQUFBQUFBQUE4MVliWS9idUJIK0s0SUwzS...FNzUjBDUGk0a3NOYmI2WkRzUEl4R0VhSEZwS0EifQ.', 'correlationId': '14bd8e31-bd47-4ae3-bbf6-21b103c21ba3'}
                # 'eventType' = 'Microsoft.Communication.IncomingCall'
                # 'dataVersion' = '1.0'
                # 'metadataVersion' = '1'
                # 'eventTime' = '2025-11-12T22:39:21.3416931Z'
                result = await acs_handler.accept_inbound_call(
                    request_body=request_body,
                    acs_caller=http_request.app.state.acs_caller,
                    redis_mgr=getattr(http_request.app.state, "redis", None),
                    record_call=record_call_override,
                )

            return result

        except Exception as exc:
            op.set_error(str(exc))
            return JSONResponse({"error": str(exc)}, status_code=500)


@router.post(
    "/callbacks",
    summary="Handle ACS Callback Events",
    description="""
    Handle Azure Communication Services callback events.
    
    This endpoint receives webhooks from ACS when call events occur:
    - Call connected/disconnected
    - Participant joined/left
    - Media events (DTMF tones, play completed, etc.)
    - Transfer events
    
    The endpoint validates authentication, processes events through the 
    V1 CallEventProcessor system, and returns processing results.
    """,
    tags=["Call Events"],
    responses={
        200: {
            "description": "Events processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "processed_events": 1,
                        "call_connection_id": "abc123",
                    }
                }
            },
        },
        500: {
            "description": "Event processing failed",
            "content": {
                "application/json": {"example": {"error": "Failed to process callback events"}}
            },
        },
        503: {
            "description": "Service dependencies not available",
            "content": {"application/json": {"example": {"error": "ACS not initialised"}}},
        },
    },
)
async def handle_acs_callbacks(
    http_request: Request,
):
    """
    Handle ACS callback events from Azure Communication Services.

    This endpoint processes webhook events sent by ACS when call state changes
    occur. All processing is delegated to the V1 event system for consistency.

    :param http_request: FastAPI request object containing the ACS webhook payload
    :type http_request: Request
    :return: Processing result
    :rtype: JSONResponse
    :raises Exception: When event processing fails or dependencies are unavailable
    """
    # Validate dependencies
    if not http_request.app.state.acs_caller:
        return JSONResponse({"error": "ACS not initialised"}, status_code=503)

    try:
        events_data = await http_request.json()

        # Extract call connection ID for tracing
        call_connection_id = None
        if isinstance(events_data, dict):
            event_data = events_data.get("data", {})
            if isinstance(event_data, dict):
                call_connection_id = event_data.get("callConnectionId")
        elif isinstance(events_data, list) and events_data:
            first_event = events_data[0] if events_data else {}
            if isinstance(first_event, dict):
                event_data = first_event.get("data", {})
                if isinstance(event_data, dict):
                    call_connection_id = event_data.get("callConnectionId")

        # Fallback to header
        if not call_connection_id:
            call_connection_id = http_request.headers.get("x-ms-call-connection-id")

        with trace_acs_operation(
            tracer, logger, "process_callbacks", call_connection_id=call_connection_id
        ) as op:
            op.log_info(
                f"Processing ACS callbacks: {len(events_data) if isinstance(events_data, list) else 1} events"
            )

            # Import here to avoid circular imports
            from azure.core.messaging import CloudEvent

            from ..events import get_call_event_processor, register_default_handlers

            # Ensure handlers are registered
            register_default_handlers()

            # Convert to CloudEvent objects
            cloud_events = []
            if isinstance(events_data, list):
                for event_item in events_data:
                    if isinstance(event_item, dict):
                        event_type = event_item.get("eventType") or event_item.get(
                            "type", "Unknown"
                        )
                        cloud_event = CloudEvent(
                            source="azure.communication.callautomation",
                            type=event_type,
                            data=event_item.get("data", event_item),
                        )
                        cloud_events.append(cloud_event)
            elif isinstance(events_data, dict):
                event_type = events_data.get("eventType") or events_data.get("type", "Unknown")
                cloud_event = CloudEvent(
                    source="azure.communication.callautomation",
                    type=event_type,
                    data=events_data.get("data", events_data),
                )
                cloud_events.append(cloud_event)

            # Process through V1 event system
            processor = get_call_event_processor()
            result = await processor.process_events(cloud_events, http_request.app.state)

            op.log_info(f"Processed {result.get('processed', 0)} events successfully")

            return JSONResponse(
                {
                    "status": "success",
                    "processed_events": result.get("processed", 0),
                    "failed_events": result.get("failed", 0),
                    "call_connection_id": call_connection_id,
                    "processing_system": "events_v1",
                },
                status_code=200,
            )

    except Exception as exc:
        logger.error(f"Unexpected error processing ACS callbacks: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)
