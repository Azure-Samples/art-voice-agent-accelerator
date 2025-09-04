"""
Event-related database models.

Models for tracking system events, event processing, and event history.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import Field

from .base import TimestampedModel


class EventStatus(str, Enum):
    """Event processing status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class EventSeverity(str, Enum):
    """Event severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Event(TimestampedModel):
    """
    Database model for system events.

    Tracks events throughout the system including:
    - Event metadata and classification
    - Processing status and results
    - Relationships to calls and other entities
    """

    # Event identification
    event_type: str = Field(
        description="Type of event (e.g., CallConnected, MediaReceived)"
    )

    event_source: str = Field(description="Source system that generated the event")

    correlation_id: str = Field(
        description="Correlation ID for tracing across services"
    )

    # Relationships
    call_id: Optional[UUID] = Field(
        default=None, description="Associated call ID if applicable"
    )

    participant_id: Optional[str] = Field(
        default=None, description="Associated participant ID if applicable"
    )

    # Event data
    event_data: Dict[str, Any] = Field(
        default_factory=dict, description="Event payload data"
    )

    # Processing information
    status: EventStatus = Field(
        default=EventStatus.PENDING, description="Current processing status"
    )

    severity: EventSeverity = Field(
        default=EventSeverity.INFO, description="Event severity level"
    )

    # Timing
    occurred_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the event occurred"
    )

    processed_at: Optional[datetime] = Field(
        default=None, description="When the event was processed"
    )

    # Processing results
    processing_duration_ms: Optional[int] = Field(
        default=None, description="Time taken to process the event in milliseconds"
    )

    retry_count: int = Field(
        default=0, description="Number of processing retry attempts"
    )

    # Error tracking
    error_message: Optional[str] = Field(
        default=None, description="Error message if processing failed"
    )

    error_code: Optional[str] = Field(
        default=None, description="Error code if processing failed"
    )

    # Metadata
    metadata: Dict = Field(
        default_factory=dict, description="Additional event metadata"
    )


class EventHistory(TimestampedModel):
    """
    Database model for event processing history.

    Maintains an audit trail of event processing attempts including:
    - Processing attempts and outcomes
    - Performance metrics
    - Error details and debugging information
    """

    # Relationships
    event_id: UUID = Field(description="ID of the associated event")

    # Processing attempt information
    attempt_number: int = Field(description="Processing attempt number (1-based)")

    status: EventStatus = Field(description="Status of this processing attempt")

    # Timing
    started_at: datetime = Field(
        default_factory=datetime.utcnow, description="When processing started"
    )

    completed_at: Optional[datetime] = Field(
        default=None, description="When processing completed"
    )

    duration_ms: Optional[int] = Field(
        default=None, description="Processing duration in milliseconds"
    )

    # Results
    result_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Processing result data"
    )

    # Error tracking
    error_message: Optional[str] = Field(
        default=None, description="Error message if processing failed"
    )

    error_code: Optional[str] = Field(
        default=None, description="Error code if processing failed"
    )

    error_details: Optional[Dict] = Field(
        default=None, description="Detailed error information for debugging"
    )

    # Context
    handler_name: Optional[str] = Field(
        default=None,
        description="Name of the event handler that processed this attempt",
    )

    handler_version: Optional[str] = Field(
        default=None, description="Version of the event handler"
    )

    # Metadata
    metadata: Dict = Field(
        default_factory=dict, description="Additional processing metadata"
    )
