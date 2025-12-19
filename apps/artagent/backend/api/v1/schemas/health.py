"""
Health check API schemas.

Pydantic schemas for health and readiness API responses.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PoolMetrics(BaseModel):
    """Resource pool metrics for monitoring warm pool behavior."""

    name: str = Field(..., description="Pool name", example="speech-tts")
    ready: bool = Field(..., description="Whether pool is ready", example=True)
    warm_pool_size: int = Field(
        ..., description="Current number of pre-warmed resources", example=3
    )
    warm_pool_target: int = Field(..., description="Target warm pool size", example=3)
    active_sessions: int = Field(
        ..., description="Number of active session-bound resources", example=2
    )
    session_awareness: bool = Field(
        ..., description="Whether session caching is enabled", example=True
    )
    allocations_total: int = Field(..., description="Total allocations since startup", example=150)
    allocations_dedicated: int = Field(
        ..., description="Allocations from session cache (0ms)", example=95
    )
    allocations_warm: int = Field(..., description="Allocations from warm pool (<50ms)", example=40)
    allocations_cold: int = Field(..., description="On-demand allocations (~200ms)", example=15)
    warmup_cycles: int = Field(..., description="Background warmup cycles completed", example=42)
    warmup_failures: int = Field(..., description="Warmup failures count", example=0)
    background_warmup: bool = Field(
        ..., description="Whether background warmup is enabled", example=True
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "speech-tts",
                "ready": True,
                "warm_pool_size": 3,
                "warm_pool_target": 3,
                "active_sessions": 2,
                "session_awareness": True,
                "allocations_total": 150,
                "allocations_dedicated": 95,
                "allocations_warm": 40,
                "allocations_cold": 15,
                "warmup_cycles": 42,
                "warmup_failures": 0,
                "background_warmup": True,
            }
        }
    )


class PoolsHealthResponse(BaseModel):
    """Response for pool health endpoint."""

    status: str = Field(..., description="Overall pools status", example="healthy")
    timestamp: float = Field(..., description="Timestamp", example=1691668800.0)
    pools: dict[str, PoolMetrics] = Field(..., description="Pool metrics by name")
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregate metrics across all pools",
        json_schema_extra={
            "example": {
                "total_warm": 5,
                "total_active_sessions": 4,
                "hit_rate_percent": 90.0,
            }
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": 1691668800.0,
                "pools": {
                    "speech-tts": {
                        "name": "speech-tts",
                        "ready": True,
                        "warm_pool_size": 3,
                        "warm_pool_target": 3,
                    }
                },
                "summary": {
                    "total_warm": 5,
                    "total_active_sessions": 4,
                    "hit_rate_percent": 90.0,
                },
            }
        }
    )


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
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional health details",
        json_schema_extra={"example": {"api_version": "v1", "service": "artagent-backend"}},
    )
    active_sessions: int | None = Field(
        default=None,
        description="Current number of active realtime conversation sessions (None if unavailable)",
        json_schema_extra={"example": 3},
    )
    session_metrics: dict[str, Any] | None = Field(
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
                "details": {"api_version": "v1", "service": "artagent-backend"},
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
    error: str | None = Field(
        None, description="Error message if check failed", example="Connection timeout"
    )
    details: str | None = Field(
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
    checks: list[ServiceCheck] = Field(..., description="Individual component health checks")
    event_system: dict[str, Any] | None = Field(
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
