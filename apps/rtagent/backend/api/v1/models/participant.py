"""
Participant-related database models.

Models for tracking call participants and their interactions.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from uuid import UUID

from pydantic import Field

from .base import TimestampedModel


class ParticipantRole(str, Enum):
    """Participant role enumeration."""

    CALLER = "caller"
    AGENT = "agent"
    MODERATOR = "moderator"
    OBSERVER = "observer"


class ParticipantStatus(str, Enum):
    """Participant status enumeration."""

    INVITED = "invited"
    JOINING = "joining"
    CONNECTED = "connected"
    MUTED = "muted"
    ON_HOLD = "on_hold"
    DISCONNECTED = "disconnected"


class Participant(TimestampedModel):
    """
    Database model for call participants.

    Extended participant information beyond the basic CallParticipant model,
    including role-based permissions and detailed interaction tracking.
    """

    # Core identification
    participant_id: str = Field(
        description="Azure Communication Services participant ID"
    )

    display_name: Optional[str] = Field(
        default=None, description="Display name of the participant"
    )

    # Contact information
    phone_number: Optional[str] = Field(
        default=None, description="Phone number of the participant"
    )

    email: Optional[str] = Field(
        default=None, description="Email address of the participant"
    )

    # Role and permissions
    role: ParticipantRole = Field(
        default=ParticipantRole.CALLER,
        description="Role of the participant in the call",
    )

    status: ParticipantStatus = Field(
        default=ParticipantStatus.INVITED,
        description="Current status of the participant",
    )

    # Capabilities and permissions
    can_speak: bool = Field(
        default=True, description="Whether participant can speak (unmuted)"
    )

    can_listen: bool = Field(
        default=True, description="Whether participant can hear audio"
    )

    # Session information
    session_id: Optional[str] = Field(
        default=None, description="Session identifier for this participant"
    )

    user_agent: Optional[str] = Field(
        default=None, description="User agent string if applicable"
    )

    ip_address: Optional[str] = Field(
        default=None, description="IP address of the participant"
    )

    # Quality metrics
    audio_quality_score: Optional[float] = Field(
        default=None, description="Audio quality score (0.0 to 1.0)"
    )

    network_quality_score: Optional[float] = Field(
        default=None, description="Network quality score (0.0 to 1.0)"
    )

    # Interaction tracking
    total_speak_time_seconds: int = Field(
        default=0, description="Total time participant spoke in seconds"
    )

    total_mute_time_seconds: int = Field(
        default=0, description="Total time participant was muted in seconds"
    )

    interaction_count: int = Field(
        default=0, description="Number of interactions (speak turns)"
    )

    # Timestamps
    invited_at: Optional[datetime] = Field(
        default=None, description="When the participant was invited"
    )

    joined_at: Optional[datetime] = Field(
        default=None, description="When the participant joined"
    )

    left_at: Optional[datetime] = Field(
        default=None, description="When the participant left"
    )

    last_activity_at: Optional[datetime] = Field(
        default=None, description="Last activity timestamp"
    )

    # Metadata and preferences
    preferences: Dict = Field(
        default_factory=dict, description="Participant preferences and settings"
    )

    metadata: Dict = Field(
        default_factory=dict, description="Additional participant metadata"
    )

    # Device information
    device_info: Optional[Dict] = Field(
        default=None, description="Information about participant's device"
    )

    browser_info: Optional[Dict] = Field(
        default=None, description="Browser information if web-based"
    )
