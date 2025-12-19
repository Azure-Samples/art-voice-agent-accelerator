"""
Call-related API schemas.

Pydantic schemas for call management API requests and responses.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from src.enums.stream_modes import StreamMode


class CallInitiateRequest(BaseModel):
    """Request model for initiating a call."""

    target_number: str = Field(
        ...,
        description="Phone number to call in E.164 format (e.g., +1234567890)",
        json_schema_extra={"example": "+1234567890"},
        pattern=r"^\+[1-9]\d{1,14}$",
    )
    caller_id: str | None = Field(
        None,
        description="Caller ID to display (optional, uses system default if not provided)",
        json_schema_extra={"example": "+1987654321"},
    )
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional call context metadata",
        json_schema_extra={
            "example": {
                "customer_id": "cust_12345",
                "department": "support",
                "priority": "high",
                "source": "web_portal",
            }
        },
    )
    streaming_mode: StreamMode | None = Field(
        default=None,
        description=(
            "Optional streaming mode override for Azure Communication Services media "
            "handling. When provided, this value supersedes the default ACS_STREAMING_MODE "
            "environment setting for the duration of the call."
        ),
        json_schema_extra={"example": "voice_live"},
    )
    record_call: bool | None = Field(
        default=None,
        description=(
            "Optional flag indicating whether this call should be recorded."
            " When omitted, recording falls back to the default environment toggle."
        ),
        json_schema_extra={"example": True},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_number": "+1234567890",
                "caller_id": "+1987654321",
                "context": {"customer_id": "cust_12345", "department": "support"},
                "record_call": True,
            }
        }
    )


class CallInitiateResponse(BaseModel):
    """Response model for call initiation."""

    call_id: str = Field(
        ...,
        description="Unique call identifier",
        json_schema_extra={"example": "call_abc12345"},
    )
    status: str = Field(
        ...,
        description="Current call status",
        json_schema_extra={"example": "initiating"},
    )
    target_number: str = Field(
        ...,
        description="Target phone number",
        json_schema_extra={"example": "+1234567890"},
    )
    message: str = Field(
        ...,
        description="Human-readable status message",
        json_schema_extra={"example": "Call initiation requested"},
    )
    streaming_mode: StreamMode | None = Field(
        default=None,
        description="Effective streaming mode used for media handling.",
        json_schema_extra={"example": "voice_live"},
    )
    initiated_at: str | None = Field(
        default=None,
        description="Timestamp indicating when call initiation completed.",
        json_schema_extra={"example": "2025-07-18T22:45:30Z"},
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Backend metadata useful for debugging call initiation.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "call_id": "call_abc12345",
                "status": "initiating",
                "target_number": "+1234567890",
                "message": "Call initiation requested for +1234567890",
                "streaming_mode": "voice_live",
                "initiated_at": "2025-07-18T22:45:30Z",
                "details": {"api_version": "v1"},
            }
        }
    )


class CallStatusResponse(BaseModel):
    """Response model for call status."""

    call_id: str = Field(
        ...,
        description="Unique call identifier",
        json_schema_extra={"example": "call_abc12345"},
    )
    status: Literal[
        "initiating",
        "ringing",
        "connected",
        "on_hold",
        "disconnected",
        "failed",
    ] = Field(
        ...,
        description="Current call status",
        json_schema_extra={"example": "connected"},
    )
    duration: int | None = Field(
        None,
        description="Call duration in seconds (null if not connected)",
        json_schema_extra={"example": 120},
    )
    participants: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of call participants",
        json_schema_extra={
            "example": [
                {
                    "id": "participant_1",
                    "phone_number": "+1234567890",
                    "role": "caller",
                    "status": "connected",
                }
            ]
        },
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent call events",
        json_schema_extra={
            "example": [
                {
                    "type": "call_connected",
                    "timestamp": "2025-08-10T13:45:30Z",
                    "details": {"connection_established": True},
                }
            ]
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "call_id": "call_abc12345",
                "status": "connected",
                "duration": 120,
                "participants": [
                    {
                        "id": "participant_1",
                        "phone_number": "+1234567890",
                        "role": "caller",
                        "status": "connected",
                    }
                ],
                "events": [
                    {
                        "type": "call_connected",
                        "timestamp": "2025-08-10T13:45:30Z",
                        "details": {"connection_established": True},
                    }
                ],
            }
        }
    )


class CallUpdateRequest(BaseModel):
    """Request model for updating call properties."""

    status: Literal["on_hold", "connected", "muted", "unmuted"] | None = Field(
        None, description="New call status"
    )
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata for the call")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "on_hold",
                "metadata": {
                    "hold_reason": "customer_request",
                    "hold_duration_estimate": 120,
                },
            }
        }
    )


class CallHangupResponse(BaseModel):
    """Response model for call hangup."""

    call_id: str = Field(
        ...,
        description="Unique call identifier",
        json_schema_extra={"example": "call_abc12345"},
    )
    status: str = Field(..., description="Updated call status", example="hanging_up")
    message: str = Field(
        ...,
        description="Human-readable status message",
        json_schema_extra={"example": "Call hangup requested"},
    )

    status: str = Field(
        ...,
        description="Updated call status",
        json_schema_extra={"example": "hanging_up"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "call_id": "call_abc12345",
                "status": "hanging_up",
                "message": "Call hangup requested",
            }
        }
    )


class CallTerminateRequest(BaseModel):
    """Request model for terminating an ACS call."""

    call_id: str = Field(..., description="Call connection ID to terminate")
    session_id: str | None = Field(
        None,
        description="Browser session ID associated with the ACS call (optional)",
    )
    reason: str | None = Field(
        "normal",
        description="Termination reason label (defaults to 'normal')",
    )


class CallListResponse(BaseModel):
    """Response model for listing calls."""

    calls: list[CallStatusResponse] = Field(..., description="List of calls")
    total: int = Field(
        ...,
        description="Total number of calls matching criteria",
        json_schema_extra={"example": 25},
    )
    page: int = Field(1, description="Current page number (1-based)", example=1)
    limit: int = Field(10, description="Number of items per page", example=10)

    page: int = Field(
        1, description="Current page number (1-based)", json_schema_extra={"example": 1}
    )
    limit: int = Field(
        10, description="Number of items per page", json_schema_extra={"example": 10}
    )

    model_config = ConfigDict(
        json_schema_extra={
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
    )
