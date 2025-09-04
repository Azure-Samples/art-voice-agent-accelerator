"""
Call-related database models.

Models for tracking call sessions, participants, and call state.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import Field

from .base import TimestampedModel


class CallStatus(str, Enum):
    """Call status enumeration."""

    INITIATED = "initiated"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ESTABLISHED = "established"
    TRANSFERRING = "transferring"
    TRANSFERRED = "transferred"
    TERMINATED = "terminated"
    FAILED = "failed"


class CallType(str, Enum):
    """Call type enumeration."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    TRANSFER = "transfer"


class Call(TimestampedModel):
    """
    Database model for call records.

    Tracks the complete lifecycle of a call session including:
    - Call metadata and configuration
    - Participant information
    - Status transitions
    - Duration and timing
    """

    # Core identifiers
    call_connection_id: str = Field(
        description="Azure Communication Services call connection ID"
    )

    correlation_id: str = Field(
        description="Correlation ID for tracing across services"
    )

    # Call configuration
    call_type: CallType = Field(
        description="Type of call (inbound, outbound, transfer)"
    )

    status: CallStatus = Field(
        default=CallStatus.INITIATED, description="Current status of the call"
    )

    # Participant information
    caller_number: Optional[str] = Field(
        default=None, description="Phone number of the caller"
    )

    target_number: Optional[str] = Field(
        default=None, description="Phone number being called"
    )

    # Timing information
    initiated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the call was initiated"
    )

    connected_at: Optional[datetime] = Field(
        default=None, description="When the call was connected"
    )

    ended_at: Optional[datetime] = Field(
        default=None, description="When the call ended"
    )

    duration_seconds: Optional[int] = Field(
        default=None, description="Total call duration in seconds"
    )

    # Configuration and metadata
    agent_config: Dict = Field(
        default_factory=dict, description="Agent configuration used for this call"
    )

    metadata: Dict = Field(default_factory=dict, description="Additional call metadata")

    # Error tracking
    error_message: Optional[str] = Field(
        default=None, description="Error message if call failed"
    )

    error_code: Optional[str] = Field(
        default=None, description="Error code if call failed"
    )


class CallParticipant(TimestampedModel):
    """
    Database model for call participants.

    Tracks individual participants in a call including:
    - Participant identification
    - Join/leave timestamps
    - Media capabilities
    """

    # Relationships
    call_id: UUID = Field(description="ID of the associated call")

    # Participant identification
    participant_id: str = Field(
        description="Azure Communication Services participant ID"
    )

    display_name: Optional[str] = Field(
        default=None, description="Display name of the participant"
    )

    phone_number: Optional[str] = Field(
        default=None, description="Phone number of the participant"
    )

    # Timing
    joined_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the participant joined the call",
    )

    left_at: Optional[datetime] = Field(
        default=None, description="When the participant left the call"
    )

    # Media capabilities
    audio_enabled: bool = Field(
        default=True, description="Whether audio is enabled for this participant"
    )

    video_enabled: bool = Field(
        default=False, description="Whether video is enabled for this participant"
    )

    # Status
    is_active: bool = Field(
        default=True, description="Whether the participant is currently active"
    )

    # Metadata
    metadata: Dict = Field(
        default_factory=dict, description="Additional participant metadata"
    )
