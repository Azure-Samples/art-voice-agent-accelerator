"""
Event-related API schemas.

Pydantic schemas for event management API requests and responses.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class EventMetricsResponse(BaseModel):
    """Response model for event metrics."""

    total_events_processed: int = Field(
        ...,
        description="Total number of events processed",
        json_schema_extra={"example": 1500},
    )
    events_by_type: Dict[str, int] = Field(
        ...,
        description="Event count by type",
        json_schema_extra={
            "example": {
                "Microsoft.Communication.CallConnected": 450,
                "Microsoft.Communication.CallDisconnected": 430,
                "Microsoft.Communication.DtmfToneReceived": 120,
            }
        },
    )
    average_processing_time_ms: float = Field(
        ...,
        description="Average processing time in milliseconds",
        json_schema_extra={"example": 12.5},
    )
    error_rate_percent: float = Field(
        ..., description="Error rate as percentage", json_schema_extra={"example": 0.2}
    )
    active_handlers: int = Field(
        ...,
        description="Number of active event handlers",
        json_schema_extra={"example": 7},
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_events_processed": 1500,
                "events_by_type": {
                    "Microsoft.Communication.CallConnected": 450,
                    "Microsoft.Communication.CallDisconnected": 430,
                },
                "average_processing_time_ms": 12.5,
                "error_rate_percent": 0.2,
                "active_handlers": 7,
            }
        }


class EventHandlerInfo(BaseModel):
    """Information about an event handler."""

    name: str = Field(
        ...,
        description="Handler function/class name",
        json_schema_extra={"example": "handle_call_connected"},
    )
    event_types: List[str] = Field(
        ...,
        description="Event types handled",
        json_schema_extra={"example": ["Microsoft.Communication.CallConnected"]},
    )
    handler_type: Literal["function", "class"] = Field(
        ...,
        description="Handler implementation type",
        json_schema_extra={"example": "function"},
    )
    domain: str = Field(
        ..., description="Event domain", json_schema_extra={"example": "call_events"}
    )
    is_active: bool = Field(
        ...,
        description="Whether handler is active",
        json_schema_extra={"example": True},
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "handle_call_connected",
                "event_types": ["Microsoft.Communication.CallConnected"],
                "handler_type": "function",
                "domain": "call_events",
                "is_active": True,
            }
        }


class EventSystemStatus(BaseModel):
    """Event system status response."""

    is_healthy: bool = Field(
        ..., description="Overall system health", json_schema_extra={"example": True}
    )
    registered_handlers: List[EventHandlerInfo] = Field(
        ..., description="List of registered handlers"
    )
    metrics: EventMetricsResponse = Field(..., description="Event processing metrics")
    domains: List[str] = Field(
        ...,
        description="Active event domains",
        json_schema_extra={"example": ["call_events", "media_events"]},
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_healthy": True,
                "registered_handlers": [
                    {
                        "name": "handle_call_connected",
                        "event_types": ["Microsoft.Communication.CallConnected"],
                        "handler_type": "function",
                        "domain": "call_events",
                        "is_active": True,
                    }
                ],
                "metrics": {
                    "total_events_processed": 1500,
                    "events_by_type": {},
                    "average_processing_time_ms": 12.5,
                    "error_rate_percent": 0.2,
                    "active_handlers": 7,
                },
                "domains": ["call_events", "media_events"],
            }
        }


class ProcessEventRequest(BaseModel):
    """Request model for processing events."""

    events: List[Dict[str, Any]] = Field(
        ...,
        description="CloudEvent data as dictionaries following CloudEvents spec",
        json_schema_extra={
            "example": [
                {
                    "specversion": "1.0",
                    "type": "Microsoft.Communication.CallConnected",
                    "source": "/acs/calls/test123",
                    "id": "test-event-001",
                    "time": "2025-08-10T13:45:00Z",
                    "datacontenttype": "application/json",
                    "data": {
                        "callConnectionId": "test123",
                        "serverCallId": "server-test-123",
                    },
                }
            ]
        },
    )

    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
                        "specversion": "1.0",
                        "type": "Microsoft.Communication.CallConnected",
                        "source": "/acs/calls/test123",
                        "id": "test-event-001",
                        "time": "2025-08-10T13:45:00Z",
                        "datacontenttype": "application/json",
                        "data": {
                            "callConnectionId": "test123",
                            "serverCallId": "server-test-123",
                        },
                    }
                ]
            }
        }


class ProcessEventResponse(BaseModel):
    """Response model for event processing."""

    processed_count: int = Field(
        ...,
        description="Number of successfully processed events",
        json_schema_extra={"example": 2},
    )
    failed_count: int = Field(
        ..., description="Number of failed events", json_schema_extra={"example": 0}
    )
    results: List[Dict[str, Any]] = Field(
        ...,
        description="Detailed results for each event",
        json_schema_extra={
            "example": [
                {
                    "event_id": "test-event-001",
                    "status": "success",
                    "message": "Event processed successfully",
                }
            ]
        },
    )

    class Config:
        json_schema_extra = {
            "example": {
                "processed_count": 2,
                "failed_count": 0,
                "results": [
                    {
                        "event_id": "test-event-001",
                        "status": "success",
                        "message": "Event processed successfully",
                    }
                ],
            }
        }


class EventListRequest(BaseModel):
    """Request model for listing events with filters."""

    event_type: Optional[str] = Field(
        None,
        description="Filter by event type",
        json_schema_extra={"example": "Microsoft.Communication.CallConnected"},
    )
    start_time: Optional[str] = Field(
        None,
        description="Filter events after this timestamp (ISO 8601)",
        json_schema_extra={"example": "2025-08-10T00:00:00Z"},
    )
    end_time: Optional[str] = Field(
        None,
        description="Filter events before this timestamp (ISO 8601)",
        json_schema_extra={"example": "2025-08-10T23:59:59Z"},
    )
    status: Optional[Literal["pending", "processing", "completed", "failed"]] = Field(
        None, description="Filter by processing status"
    )
    limit: int = Field(
        100, ge=1, le=1000, description="Maximum number of events to return"
    )


class EventDetail(BaseModel):
    """Detailed event information."""

    id: str = Field(..., description="Event ID")
    event_type: str = Field(..., description="Event type")
    source: str = Field(..., description="Event source")
    timestamp: str = Field(..., description="Event timestamp")
    status: str = Field(..., description="Processing status")
    data: Dict[str, Any] = Field(..., description="Event data")
    processing_duration_ms: Optional[int] = Field(
        None, description="Processing time in milliseconds"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")


class EventListResponse(BaseModel):
    """Response model for listing events."""

    events: List[EventDetail] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of events matching criteria")
    has_more: bool = Field(..., description="Whether there are more events available")

    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
                        "id": "event-123",
                        "event_type": "Microsoft.Communication.CallConnected",
                        "source": "/acs/calls/test123",
                        "timestamp": "2025-08-10T13:45:00Z",
                        "status": "completed",
                        "data": {"callConnectionId": "test123"},
                        "processing_duration_ms": 15,
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        }
