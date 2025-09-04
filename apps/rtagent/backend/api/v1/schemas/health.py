"""
Health check API schemas.

Pydantic schemas for health and readiness API responses.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(
        ...,
        description="Overall health status",
        json_schema_extra={"example": "healthy"},
    )
    version: str = Field(default="1.0.0", description="API version", example="1.0.0")
    timestamp: float = Field(
        ..., description="Timestamp when check was performed", example=1691668800.0
    )
    message: str = Field(
        ...,
        description="Human-readable status message",
        json_schema_extra={"example": "Real-Time Audio Agent API v1 is running"},
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional health details",
        json_schema_extra={
            "example": {"api_version": "v1", "service": "rtagent-backend"}
        },
    )
    active_sessions: int | None = Field(
        default=None,
        description="Current number of active realtime conversation sessions (None if unavailable)",
        json_schema_extra={"example": 3},
    )
    session_metrics: Dict[str, Any] | None = Field(
        default=None,
        description="Optional granular session metrics (connected/disconnected, etc.)",
        json_schema_extra={"example": {"connected": 5, "disconnected": 2, "active": 3}},
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": 1691668800.0,
                "message": "Real-Time Audio Agent API v1 is running",
                "details": {"api_version": "v1", "service": "rtagent-backend"},
                "active_sessions": 3,
                "session_metrics": {"connected": 5, "disconnected": 2, "active": 3},
            }
        }
    )


class ServiceCheck(BaseModel):
    """Individual service check result."""

    component: str = Field(
        ...,
        description="Name of the component being checked",
        json_schema_extra={"example": "redis"},
    )
    status: str = Field(
        ...,
        description="Health status of the component",
        json_schema_extra={
            "example": "healthy",
            "enum": ["healthy", "unhealthy", "degraded"],
        },
    )
    check_time_ms: float = Field(
        ..., description="Time taken to perform the check in milliseconds", example=12.5
    )
    error: Optional[str] = Field(
        None, description="Error message if check failed", example="Connection timeout"
    )
    details: Optional[str] = Field(
        None,
        description="Additional details about the check",
        json_schema_extra={"example": "Connected to Redis successfully"},
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "component": "redis",
                "status": "healthy",
                "check_time_ms": 12.5,
                "details": "Connected to Redis successfully",
            }
        }
    )


class ReadinessResponse(BaseModel):
    """Comprehensive readiness check response model."""

    status: str = Field(
        ...,
        description="Overall readiness status",
        json_schema_extra={
            "example": "ready",
            "enum": ["ready", "not_ready", "degraded"],
        },
    )
    timestamp: float = Field(
        ..., description="Timestamp when check was performed", example=1691668800.0
    )
    response_time_ms: float = Field(
        ..., description="Total time taken for all checks in milliseconds", example=45.2
    )
    checks: List[ServiceCheck] = Field(
        ..., description="Individual component health checks"
    )
    event_system: Optional[Dict[str, Any]] = Field(
        None,
        description="Event system status information",
        json_schema_extra={
            "example": {"is_healthy": True, "handlers_count": 7, "domains_count": 2}
        },
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ready",
                "timestamp": 1691668800.0,
                "response_time_ms": 45.2,
                "checks": [
                    {
                        "component": "redis",
                        "status": "healthy",
                        "check_time_ms": 12.5,
                        "details": "Connected to Redis successfully",
                    },
                    {
                        "component": "azure_openai",
                        "status": "healthy",
                        "check_time_ms": 8.3,
                        "details": "Client initialized",
                    },
                ],
                "event_system": {
                    "is_healthy": True,
                    "handlers_count": 7,
                    "domains_count": 2,
                },
            }
        }
    )
