"""
Participant-related API schemas.

Pydantic schemas for participant management API requests and responses.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParticipantResponse(BaseModel):
    """Response model for participant information."""

    participant_id: str = Field(
        ...,
        description="Unique participant identifier",
        json_schema_extra={"example": "participant_abc123"},
    )
    display_name: str | None = Field(
        None,
        description="Display name of the participant",
        json_schema_extra={"example": "John Doe"},
    )
    phone_number: str | None = Field(
        None,
        description="Phone number of the participant",
        json_schema_extra={"example": "+1234567890"},
    )
    email: str | None = Field(
        None,
        description="Email address of the participant",
        json_schema_extra={"example": "john.doe@example.com"},
    )
    role: Literal["caller", "agent", "moderator", "observer"] = Field(
        ...,
        description="Role of the participant in the call",
        json_schema_extra={"example": "caller"},
    )
    status: Literal["invited", "joining", "connected", "muted", "on_hold", "disconnected"] = Field(
        ...,
        description="Current status of the participant",
        json_schema_extra={"example": "connected"},
    )
    capabilities: dict[str, bool] = Field(
        default_factory=dict,
        description="Participant capabilities and permissions",
        json_schema_extra={"example": {"can_speak": True, "can_listen": True}},
    )
    quality_metrics: dict[str, float] | None = Field(
        None,
        description="Audio and network quality metrics",
        json_schema_extra={"example": {"audio_quality_score": 0.85, "network_quality_score": 0.92}},
    )
    interaction_stats: dict[str, int] | None = Field(
        None,
        description="Interaction statistics",
        json_schema_extra={
            "example": {
                "total_speak_time_seconds": 120,
                "total_mute_time_seconds": 30,
                "interaction_count": 5,
            }
        },
    )
    timestamps: dict[str, str | None] = Field(
        default_factory=dict,
        description="Relevant timestamps for the participant",
        json_schema_extra={
            "example": {
                "invited_at": "2025-08-10T13:45:00Z",
                "joined_at": "2025-08-10T13:45:15Z",
                "last_activity_at": "2025-08-10T13:50:30Z",
            }
        },
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional participant metadata",
        json_schema_extra={
            "example": {
                "user_agent": "Mozilla/5.0...",
                "ip_address": "192.168.1.100",
                "device_type": "desktop",
            }
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "participant_id": "participant_abc123",
                "display_name": "John Doe",
                "phone_number": "+1234567890",
                "email": "john.doe@example.com",
                "role": "caller",
                "status": "connected",
                "capabilities": {"can_speak": True, "can_listen": True},
                "quality_metrics": {
                    "audio_quality_score": 0.85,
                    "network_quality_score": 0.92,
                },
                "interaction_stats": {
                    "total_speak_time_seconds": 120,
                    "total_mute_time_seconds": 30,
                    "interaction_count": 5,
                },
                "timestamps": {
                    "invited_at": "2025-08-10T13:45:00Z",
                    "joined_at": "2025-08-10T13:45:15Z",
                    "last_activity_at": "2025-08-10T13:50:30Z",
                },
                "metadata": {
                    "user_agent": "Mozilla/5.0...",
                    "ip_address": "192.168.1.100",
                    "device_type": "desktop",
                },
            }
        }
    )


class ParticipantUpdateRequest(BaseModel):
    """Request model for updating participant properties."""

    display_name: str | None = Field(
        None,
        description="Updated display name",
        json_schema_extra={"example": "John Smith"},
    )
    role: Literal["caller", "agent", "moderator", "observer"] | None = Field(
        None,
        description="Updated participant role",
        json_schema_extra={"example": "moderator"},
    )
    status: Literal["connected", "muted", "on_hold", "disconnected"] | None = Field(
        None,
        description="Updated participant status",
        json_schema_extra={"example": "muted"},
    )
    capabilities: dict[str, bool] | None = Field(
        None,
        description="Updated capabilities",
        json_schema_extra={"example": {"can_speak": False, "can_listen": True}},
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Updated metadata",
        json_schema_extra={
            "example": {
                "notes": "Participant requested to be muted",
                "updated_by": "agent_123",
            }
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "muted",
                "capabilities": {"can_speak": False, "can_listen": True},
                "metadata": {
                    "mute_reason": "background_noise",
                    "updated_by": "agent_123",
                },
            }
        }
    )


class ParticipantInviteRequest(BaseModel):
    """Request model for inviting participants to a call."""

    phone_number: str | None = Field(
        None,
        description="Phone number to invite (E.164 format)",
        pattern=r"^\+[1-9]\d{1,14}$",
        json_schema_extra={"example": "+1234567890"},
    )
    email: str | None = Field(
        None,
        description="Email address to invite",
        json_schema_extra={"example": "participant@example.com"},
    )
    display_name: str | None = Field(
        None,
        description="Display name for the participant",
        json_schema_extra={"example": "Jane Doe"},
    )
    role: Literal["caller", "agent", "moderator", "observer"] = Field(
        default="caller",
        description="Role to assign to the participant",
        json_schema_extra={"example": "caller"},
    )
    capabilities: dict[str, bool] | None = Field(
        default_factory=lambda: {
            "can_speak": True,
            "can_listen": True,
        },
        description="Initial capabilities for the participant",
    )
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional context for the invitation",
        json_schema_extra={
            "example": {"invitation_reason": "customer_support", "priority": "high"}
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "phone_number": "+1234567890",
                "display_name": "Jane Doe",
                "role": "caller",
                "capabilities": {"can_speak": True, "can_listen": True},
                "context": {
                    "invitation_reason": "customer_support",
                    "priority": "high",
                },
            }
        }
    )


class ParticipantInviteResponse(BaseModel):
    """Response model for participant invitation."""

    participant_id: str = Field(
        ...,
        description="Generated participant ID",
        json_schema_extra={"example": "participant_xyz789"},
    )
    invitation_status: Literal["sent", "failed", "pending"] = Field(
        ...,
        description="Status of the invitation",
        json_schema_extra={"example": "sent"},
    )
    message: str = Field(
        ...,
        description="Human-readable status message",
        json_schema_extra={"example": "Invitation sent successfully"},
    )
    invitation_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Details about the invitation",
        json_schema_extra={
            "example": {
                "invited_at": "2025-08-10T13:45:00Z",
                "invitation_method": "phone",
                "expected_join_time": "2025-08-10T13:46:00Z",
            }
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "participant_id": "participant_xyz789",
                "invitation_status": "sent",
                "message": "Invitation sent successfully to +1234567890",
                "invitation_details": {
                    "invited_at": "2025-08-10T13:45:00Z",
                    "invitation_method": "phone",
                    "expected_join_time": "2025-08-10T13:46:00Z",
                },
            }
        }
    )


class ParticipantListResponse(BaseModel):
    """Response model for listing participants."""

    participants: list[ParticipantResponse] = Field(..., description="List of participants")
    total: int = Field(
        ...,
        description="Total number of participants",
        json_schema_extra={"example": 3},
    )
    active: int = Field(
        ...,
        description="Number of active participants",
        json_schema_extra={"example": 2},
    )
    call_id: str | None = Field(
        None,
        description="Associated call ID if filtered by call",
        json_schema_extra={"example": "call_abc123"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "participants": [
                    {
                        "participant_id": "participant_abc123",
                        "display_name": "John Doe",
                        "phone_number": "+1234567890",
                        "role": "caller",
                        "status": "connected",
                        "capabilities": {"can_speak": True, "can_listen": True},
                        "timestamps": {"joined_at": "2025-08-10T13:45:15Z"},
                        "metadata": {},
                    }
                ],
                "total": 3,
                "active": 2,
                "call_id": "call_abc123",
            }
        }
    )
