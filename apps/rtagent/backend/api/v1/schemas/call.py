"""
Call-related API schemas.

Pydantic schemas for call management API requests and responses.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class CallInitiateRequest(BaseModel):
    """Request model for initiating a call."""

    target_number: str = Field(
        ...,
        description="Phone number to call in E.164 format (e.g., +1234567890)",
        json_schema_extra={"example": "+1234567890"},
        pattern=r"^\+[1-9]\d{1,14}$",
    )
    caller_id: Optional[str] = Field(
        None,
        description="Caller ID to display (optional, uses system default if not provided)",
        json_schema_extra={"example": "+1987654321"},
    )
    context: Optional[Dict[str, Any]] = Field(
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_number": "+1234567890",
                "caller_id": "+1987654321",
                "context": {"customer_id": "cust_12345", "department": "support"},
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "call_id": "call_abc12345",
                "status": "initiating",
                "target_number": "+1234567890",
                "message": "Call initiation requested for +1234567890",
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
    duration: Optional[int] = Field(
        None,
        description="Call duration in seconds (null if not connected)",
        json_schema_extra={"example": 120},
    )
    participants: List[Dict[str, Any]] = Field(
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
    events: List[Dict[str, Any]] = Field(
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

    status: Optional[Literal["on_hold", "connected", "muted", "unmuted"]] = Field(
        None, description="New call status"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Updated metadata for the call"
    )

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


class CallListResponse(BaseModel):
    """Response model for listing calls."""

    calls: List[CallStatusResponse] = Field(..., description="List of calls")
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
