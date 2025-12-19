"""
Health Endpoints
===============

Comprehensive health check and readiness endpoints for monitoring.
Includes all critical dependency checks with proper timeouts and error handling.

Note: Health checks are secondary priority to the core voice-to-voice orchestration
pipeline. All checks use short timeouts and non-blocking patterns to avoid
impacting real-time audio processing.
"""

import asyncio
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from config import (
    get_provider_status,
    refresh_appconfig_cache,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _get_config_dynamic():
    """
    Read configuration values dynamically at runtime.

    This is needed because App Configuration bootstrap sets environment variables
    AFTER the module is imported. Reading from os.getenv() ensures we get the
    latest values that were set by the bootstrap process.
    """
    return {
        "ACS_CONNECTION_STRING": os.getenv("ACS_CONNECTION_STRING", ""),
        "ACS_ENDPOINT": os.getenv("ACS_ENDPOINT", ""),
        "ACS_SOURCE_PHONE_NUMBER": os.getenv("ACS_SOURCE_PHONE_NUMBER", ""),
        "AZURE_SPEECH_ENDPOINT": os.getenv("AZURE_SPEECH_ENDPOINT", ""),
        "AZURE_SPEECH_KEY": os.getenv("AZURE_SPEECH_KEY", ""),
        "AZURE_SPEECH_REGION": os.getenv("AZURE_SPEECH_REGION", ""),
        "AZURE_SPEECH_RESOURCE_ID": os.getenv("AZURE_SPEECH_RESOURCE_ID", ""),
        "BACKEND_AUTH_CLIENT_ID": os.getenv("BACKEND_AUTH_CLIENT_ID", ""),
        "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID", ""),
        "ALLOWED_CLIENT_IDS": [
            x.strip() for x in os.getenv("ALLOWED_CLIENT_IDS", "").split(",") if x.strip()
        ],
        "ENABLE_AUTH_VALIDATION": os.getenv("ENABLE_AUTH_VALIDATION", "false").lower()
        in ("true", "1", "yes"),
        "DEFAULT_TTS_VOICE": os.getenv("DEFAULT_TTS_VOICE", ""),
    }


from apps.artagent.backend.registries.agentstore.loader import build_agent_summaries
from apps.artagent.backend.api.v1.schemas.health import (
    HealthResponse,
    PoolMetrics,
    PoolsHealthResponse,
    ReadinessResponse,
    ServiceCheck,
)
from utils.ml_logging import get_logger

logger = get_logger("v1.health")

router = APIRouter()


# ==============================================================================
# AGENT REGISTRY - Dynamic Agent Discovery
# ==============================================================================


@dataclass
class AgentDefinition:
    """Definition of an agent for discovery and health checks."""

    name: str  # Human-readable name (e.g., "auth", "fraud")
    state_attr: str  # Attribute name on app.state (e.g., "auth_agent")
    config_path: str = ""  # Legacy - agents now in backend/registries/agentstore/<name>/agent.yaml
    aliases: list[str] = field(default_factory=list)  # Alternative names for API lookup


class AgentRegistry:
    """
    Dynamic agent registry for health checks and API operations.

    Provides a single source of truth for agent discovery, avoiding
    hardcoded agent names scattered throughout the codebase.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        self._alias_map: dict[str, str] = {}  # alias -> canonical name

    def register(self, definition: AgentDefinition) -> None:
        """Register an agent definition."""
        self._definitions[definition.name] = definition
        # Build alias map for fast lookup
        for alias in definition.aliases:
            self._alias_map[alias.lower()] = definition.name
        self._alias_map[definition.name.lower()] = definition.name
        self._alias_map[definition.state_attr.lower()] = definition.name

    def get_definition(self, name_or_alias: str) -> AgentDefinition | None:
        """Get agent definition by name or alias."""
        canonical = self._alias_map.get(name_or_alias.lower())
        return self._definitions.get(canonical) if canonical else None

    def list_definitions(self) -> Iterable[AgentDefinition]:
        """List all registered agent definitions."""
        return self._definitions.values()

    def discover_agents(self, app_state: Any) -> dict[str, Any]:
        """
        Discover all agents from app.state based on registered definitions.

        Returns dict of {name: agent_instance} for found agents.
        """
        discovered = {}
        for defn in self._definitions.values():
            agent = getattr(app_state, defn.state_attr, None)
            if agent is not None:
                discovered[defn.name] = agent
        return discovered

    def get_missing_agents(self, app_state: Any) -> list[str]:
        """Get list of expected but uninitialized agents."""
        missing = []
        for defn in self._definitions.values():
            if getattr(app_state, defn.state_attr, None) is None:
                missing.append(defn.name)
        return missing


# Global registry instance - populated at module load
# NOTE: Agents are now auto-discovered from apps/artagent/backend/registries/agentstore/
# This registry provides backward compatibility for health checks.
_agent_registry = AgentRegistry()

# Register known agent patterns for health check discovery
_agent_registry.register(
    AgentDefinition(
        name="auth",
        state_attr="auth_agent",
        aliases=["authagent", "auth_agent", "authentication"],
    )
)
_agent_registry.register(
    AgentDefinition(
        name="fraud",
        state_attr="fraud_agent",
        aliases=["fraudagent", "fraud_agent", "fraud_detection"],
    )
)
_agent_registry.register(
    AgentDefinition(
        name="agency",
        state_attr="agency_agent",
        aliases=["agencyagent", "agency_agent", "transfer_agency"],
    )
)
_agent_registry.register(
    AgentDefinition(
        name="compliance",
        state_attr="compliance_agent",
        aliases=["complianceagent", "compliance_agent"],
    )
)
_agent_registry.register(
    AgentDefinition(
        name="trading",
        state_attr="trading_agent",
        aliases=["tradingagent", "trading_agent"],
    )
)


def _validate_phone_number(phone_number: str) -> tuple[bool, str]:
    """
    Validate Azure Communication Services phone number format compliance.

    Performs comprehensive validation of phone number formatting according to
    ACS requirements including country code prefix validation, digit verification,
    and length constraints for international telephony standards (E.164 format).

    Args:
        phone_number: The phone number string to validate for ACS compatibility.

    Returns:
        tuple[bool, str]: Validation result (True/False) and error message
        if validation fails, empty string if successful.

    Raises:
        TypeError: If phone_number is not a string type.

    Example:
        >>> is_valid, error = _validate_phone_number("+1234567890")
        >>> if is_valid:
        ...     print("Valid phone number")
    """
    if not isinstance(phone_number, str):
        logger.error(f"Phone number must be string, got {type(phone_number)}")
        raise TypeError("Phone number must be a string")

    try:
        if not phone_number or phone_number == "null":
            return False, "Phone number not provided"

        if not phone_number.startswith("+"):
            return False, f"Phone number must start with '+': {phone_number}"

        if not phone_number[1:].isdigit():
            return (
                False,
                f"Phone number must contain only digits after '+': {phone_number}",
            )

        if len(phone_number) < 8 or len(phone_number) > 16:  # Basic length validation
            return (
                False,
                f"Phone number length invalid (8-15 digits expected): {phone_number}",
            )

        logger.debug(f"Phone number validation successful: {phone_number}")
        return True, ""
    except Exception as e:
        logger.error(f"Error validating phone number: {e}")
        raise


def _validate_guid(guid_str: str) -> bool:
    """
    Validate string format compliance with GUID (Globally Unique Identifier) standards.

    Performs strict validation of GUID format according to RFC 4122 standards,
    ensuring proper hexadecimal digit patterns and hyphen placement for Azure
    resource identification and tracking systems.

    Args:
        guid_str: The string to validate against GUID format requirements.

    Returns:
        bool: True if string matches valid GUID format, False otherwise.

    Raises:
        TypeError: If guid_str is not a string type.

    Example:
        >>> is_valid = _validate_guid("550e8400-e29b-41d4-a716-446655440000")
        >>> print(is_valid)  # True
    """
    if not isinstance(guid_str, str):
        logger.error(f"GUID must be string, got {type(guid_str)}")
        raise TypeError("GUID must be a string")

    try:
        if not guid_str:
            logger.debug("Empty GUID string provided")
            return False

        # GUID pattern: 8-4-4-4-12 hexadecimal digits
        guid_pattern = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        result = bool(guid_pattern.match(guid_str))

        if result:
            logger.debug(f"GUID validation successful: {guid_str}")
        else:
            logger.debug(f"GUID validation failed: {guid_str}")

        return result
    except Exception as e:
        logger.error(f"Error validating GUID: {e}")
        raise


def _validate_auth_configuration() -> tuple[bool, str]:
    """
    Validate authentication configuration for Azure AD integration compliance.

    This function performs comprehensive validation of authentication settings
    when ENABLE_AUTH_VALIDATION is enabled, ensuring proper GUID formatting
    for client IDs, tenant IDs, and allowed client configurations for secure operation.

    :param: None (reads from environment configuration variables).
    :return: Tuple containing validation status and descriptive message about configuration state.
    :raises ValueError: If critical authentication configuration is malformed.
    """
    try:
        # Read config dynamically to get values set by App Configuration bootstrap
        cfg = _get_config_dynamic()
        enable_auth = cfg["ENABLE_AUTH_VALIDATION"]
        backend_client_id = cfg["BACKEND_AUTH_CLIENT_ID"]
        tenant_id = cfg["AZURE_TENANT_ID"]
        allowed_clients = cfg["ALLOWED_CLIENT_IDS"]

        if not enable_auth:
            logger.debug("Authentication validation is disabled")
            return True, "Auth validation disabled"

        validation_errors = []

        # Check BACKEND_AUTH_CLIENT_ID is a valid GUID
        if not backend_client_id:
            validation_errors.append("BACKEND_AUTH_CLIENT_ID is not set")
        elif not _validate_guid(backend_client_id):
            validation_errors.append("BACKEND_AUTH_CLIENT_ID is not a valid GUID")

        # Check AZURE_TENANT_ID is a valid GUID
        if not tenant_id:
            validation_errors.append("AZURE_TENANT_ID is not set")
        elif not _validate_guid(tenant_id):
            validation_errors.append("AZURE_TENANT_ID is not a valid GUID")

        # Check ALLOWED_CLIENT_IDS has at least one valid client ID
        if not allowed_clients:
            validation_errors.append(
                "ALLOWED_CLIENT_IDS is empty - at least one client ID required"
            )
        else:
            invalid_client_ids = [cid for cid in allowed_clients if not _validate_guid(cid)]
            if invalid_client_ids:
                validation_errors.append(
                    f"Invalid GUID format in ALLOWED_CLIENT_IDS: {invalid_client_ids}"
                )

        if validation_errors:
            error_message = "; ".join(validation_errors)
            logger.error(f"Authentication configuration validation failed: {error_message}")
            return False, error_message

        success_message = f"Auth validation enabled with {len(allowed_clients)} allowed client(s)"
        logger.info(f"Authentication configuration validation successful: {success_message}")
        return True, success_message

    except Exception as e:
        logger.error(f"Error validating authentication configuration: {e}")
        raise


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Basic Health Check",
    description="Basic health check endpoint that returns 200 if the server is running. Used by load balancers for liveness checks.",
    tags=["Health"],
    responses={
        200: {
            "description": "Service is healthy and running",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "1.0.0",
                        "timestamp": 1691668800.0,
                        "message": "Real-Time Audio Agent API v1 is running",
                        "details": {"api_version": "v1", "service": "artagent-backend"},
                    }
                }
            },
        }
    },
)
async def health_check(request: Request) -> HealthResponse:
    """Basic liveness endpoint.

    Additionally (best-effort) augments response with:
    - active_sessions: current active realtime conversation sessions
    - session_metrics: websocket connection metrics snapshot
    (Failure to gather these must NOT cause liveness failure.)
    """
    active_sessions: int | None = None
    session_metrics: dict[str, Any] | None = None

    try:
        # Active sessions
        session_manager = getattr(request.app.state, "session_manager", None)
        if session_manager and hasattr(session_manager, "get_session_count"):
            active_sessions = await session_manager.get_session_count()  # type: ignore[func-returns-value]
    except Exception:
        active_sessions = None

    try:
        # Session metrics snapshot (WebSocket connection metrics)
        sm = getattr(request.app.state, "session_metrics", None)
        conn_manager = getattr(request.app.state, "conn_manager", None)

        if sm is not None:
            if hasattr(sm, "get_snapshot"):
                snap = await sm.get_snapshot()  # type: ignore[func-returns-value]
            elif isinstance(sm, dict):  # fallback if already a dict
                snap = sm
            else:
                snap = None
            if isinstance(snap, dict):
                # Use new metric names for clarity
                active_connections = snap.get("active_connections", 0)
                total_connected = snap.get("total_connected", 0)
                total_disconnected = snap.get("total_disconnected", 0)

                # Cross-check with actual ConnectionManager count for accuracy
                actual_ws_count = 0
                if conn_manager and hasattr(conn_manager, "stats"):
                    conn_stats = await conn_manager.stats()
                    actual_ws_count = conn_stats.get("total_connections", 0)

                session_metrics = {
                    "connected": active_connections,  # Currently active WebSocket connections (from metrics)
                    "disconnected": total_disconnected,  # Historical total disconnections
                    "active": active_connections,  # Same as connected (real-time active)
                    "total_connected": total_connected,  # Historical total connections made
                    "actual_ws_count": actual_ws_count,  # Real-time count from ConnectionManager (cross-check)
                }
    except Exception:
        session_metrics = None

    return HealthResponse(
        status="healthy",
        timestamp=time.time(),
        message="Real-Time Audio Agent API v1 is running",
        details={"api_version": "v1", "service": "artagent-backend"},
        active_sessions=active_sessions,
        session_metrics=session_metrics,
    )


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    summary="Comprehensive Readiness Check",
    description="""
    Comprehensive readiness probe that checks all critical dependencies with timeouts.
    
    This endpoint verifies:
    - Redis connectivity and performance
    - Azure OpenAI client health
    - Speech services (TTS/STT) availability
    - ACS caller configuration and connectivity
    - RT Agents initialization
    - Authentication configuration (when ENABLE_AUTH_VALIDATION=True)
    - Event system health
    
    When authentication validation is enabled, checks:
    - BACKEND_AUTH_CLIENT_ID is set and is a valid GUID
    - AZURE_TENANT_ID is set and is a valid GUID  
    - ALLOWED_CLIENT_IDS contains at least one valid GUID
    
    Returns 503 if any critical services are unhealthy, 200 if all systems are ready.
    """,
    tags=["Health"],
    responses={
        200: {
            "description": "All services are ready",
            "content": {
                "application/json": {
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
                                "component": "auth_configuration",
                                "status": "healthy",
                                "check_time_ms": 1.2,
                                "details": "Auth validation enabled with 2 allowed client(s)",
                            },
                        ],
                        "event_system": {
                            "is_healthy": True,
                            "handlers_count": 7,
                            "domains_count": 2,
                        },
                    }
                }
            },
        },
        503: {
            "description": "One or more services are not ready",
            "content": {
                "application/json": {
                    "example": {
                        "status": "not_ready",
                        "timestamp": 1691668800.0,
                        "response_time_ms": 1250.0,
                        "checks": [
                            {
                                "component": "redis",
                                "status": "unhealthy",
                                "check_time_ms": 1000.0,
                                "error": "Connection timeout",
                            },
                            {
                                "component": "auth_configuration",
                                "status": "unhealthy",
                                "check_time_ms": 2.1,
                                "error": "BACKEND_AUTH_CLIENT_ID is not a valid GUID",
                            },
                        ],
                    }
                }
            },
        },
    },
)
async def readiness_check(
    request: Request,
) -> ReadinessResponse:
    """
    Comprehensive readiness probe: checks all critical dependencies with timeouts.
    Returns 503 if any critical services are unhealthy.
    """
    start_time = time.time()
    health_checks: list[ServiceCheck] = []
    overall_status = "ready"
    timeout = 1.0  # seconds per check

    async def fast_ping(check_fn, *args, component=None):
        try:
            result = await asyncio.wait_for(check_fn(*args), timeout=timeout)
            return result
        except Exception as e:
            return ServiceCheck(
                component=component or check_fn.__name__,
                status="unhealthy",
                error=str(e),
                check_time_ms=round((time.time() - start_time) * 1000, 2),
            )

    # Pre-compute active session count (thread-safe)
    active_sessions = 0
    try:
        if hasattr(request.app.state, "session_manager"):
            active_sessions = await request.app.state.session_manager.get_session_count()  # type: ignore[attr-defined]
    except Exception:
        active_sessions = -1  # signal error fetching sessions

    # Check Redis connectivity (minimal – no verbose details)
    redis_status = await fast_ping(_check_redis_fast, request.app.state.redis, component="redis")
    health_checks.append(redis_status)

    # Check Azure OpenAI client
    aoai_status = await fast_ping(
        _check_azure_openai_fast,
        request.app.state.aoai_client,
        component="azure_openai",
    )
    health_checks.append(aoai_status)

    # Check Speech Services (configuration & pool readiness)
    speech_status = await fast_ping(
        _check_speech_configuration_fast,
        getattr(request.app.state, "stt_pool", None),
        getattr(request.app.state, "tts_pool", None),
        component="speech_services",
    )
    health_checks.append(speech_status)

    # Check ACS Caller
    acs_status = await fast_ping(
        _check_acs_caller_fast, request.app.state.acs_caller, component="acs_caller"
    )
    health_checks.append(acs_status)

    # Check RT Agents (dynamic discovery via registry)
    agent_status = await fast_ping(
        _check_rt_agents_fast,
        request.app.state,
        component="rt_agents",
    )
    health_checks.append(agent_status)

    # Check Authentication Configuration
    auth_config_status = await fast_ping(
        _check_auth_configuration_fast,
        component="auth_configuration",
    )
    health_checks.append(auth_config_status)

    # Determine overall status
    failed_checks = [check for check in health_checks if check.status != "healthy"]
    if failed_checks:
        overall_status = "degraded" if len(failed_checks) < len(health_checks) else "unhealthy"

    response_time = round((time.time() - start_time) * 1000, 2)

    response_data = ReadinessResponse(
        status=overall_status,
        timestamp=time.time(),
        response_time_ms=response_time,
        checks=health_checks,
    )

    # Return appropriate status code
    status_code = 200 if overall_status != "unhealthy" else 503
    return JSONResponse(content=response_data.dict(), status_code=status_code)


@router.get(
    "/pools",
    response_model=PoolsHealthResponse,
    summary="Resource Pool Health",
    description="""
    Get detailed health and metrics for resource pools (TTS/STT).
    
    Returns allocation statistics, warm pool levels, and session cache status.
    Useful for monitoring warm pool effectiveness and tuning pool sizes.
    """,
    tags=["Health"],
)
async def pools_health(request: Request) -> PoolsHealthResponse:
    """
    Get resource pool health and metrics.

    Returns detailed metrics for each pool including:
    - Warm pool levels vs targets
    - Allocation tier breakdown (DEDICATED/WARM/COLD)
    - Session cache statistics
    - Background warmup status
    """
    pools_data: dict[str, PoolMetrics] = {}
    totals = {
        "warm": 0,
        "active_sessions": 0,
        "allocations_total": 0,
        "allocations_dedicated": 0,
        "allocations_warm": 0,
        "allocations_cold": 0,
    }

    for pool_attr in ("tts_pool", "stt_pool"):
        pool = getattr(request.app.state, pool_attr, None)
        if pool is None:
            continue

        snapshot = pool.snapshot() if hasattr(pool, "snapshot") else {}
        metrics_raw = snapshot.get("metrics", {})

        pool_metrics = PoolMetrics(
            name=snapshot.get("name", pool_attr),
            ready=snapshot.get("ready", False),
            warm_pool_size=snapshot.get("warm_pool_size", 0),
            warm_pool_target=snapshot.get("warm_pool_target", 0),
            active_sessions=snapshot.get("active_sessions", 0),
            session_awareness=snapshot.get("session_awareness", False),
            allocations_total=metrics_raw.get("allocations_total", 0),
            allocations_dedicated=metrics_raw.get("allocations_dedicated", 0),
            allocations_warm=metrics_raw.get("allocations_warm", 0),
            allocations_cold=metrics_raw.get("allocations_cold", 0),
            warmup_cycles=metrics_raw.get("warmup_cycles", 0),
            warmup_failures=metrics_raw.get("warmup_failures", 0),
            background_warmup=snapshot.get("background_warmup", False),
        )
        pools_data[pool_metrics.name] = pool_metrics

        # Accumulate totals
        totals["warm"] += pool_metrics.warm_pool_size
        totals["active_sessions"] += pool_metrics.active_sessions
        totals["allocations_total"] += pool_metrics.allocations_total
        totals["allocations_dedicated"] += pool_metrics.allocations_dedicated
        totals["allocations_warm"] += pool_metrics.allocations_warm
        totals["allocations_cold"] += pool_metrics.allocations_cold

    # Calculate hit rate (DEDICATED + WARM vs COLD)
    total_allocs = totals["allocations_total"]
    fast_allocs = totals["allocations_dedicated"] + totals["allocations_warm"]
    hit_rate = round((fast_allocs / total_allocs * 100), 1) if total_allocs > 0 else 0.0

    # Determine overall status
    all_ready = all(p.ready for p in pools_data.values()) if pools_data else False
    status = "healthy" if all_ready else "degraded" if pools_data else "unhealthy"

    return PoolsHealthResponse(
        status=status,
        timestamp=time.time(),
        pools=pools_data,
        summary={
            "total_warm": totals["warm"],
            "total_active_sessions": totals["active_sessions"],
            "allocations_total": totals["allocations_total"],
            "hit_rate_percent": hit_rate,
            "tier_breakdown": {
                "dedicated": totals["allocations_dedicated"],
                "warm": totals["allocations_warm"],
                "cold": totals["allocations_cold"],
            },
        },
    )


@router.get(
    "/appconfig",
    summary="App Configuration Status",
    description="""
    Get Azure App Configuration provider status and cache metrics.
    
    This endpoint provides visibility into:
    - Whether App Configuration is enabled and connected
    - Cache hit/miss statistics
    - Configuration source breakdown (appconfig vs env vars)
    - Feature flag status
    
    Useful for verifying the migration from environment variables to App Configuration.
    """,
    tags=["Health"],
)
async def appconfig_status(request: Request, refresh: bool = False):
    """
    Get Azure App Configuration provider status.

    Args:
        request: FastAPI request object.
        refresh: If True, force refresh the cache before returning status.

    Returns:
        JSON object with provider status, cache metrics, and configuration source info.
    """
    start_time = time.time()

    try:
        # Optionally refresh cache
        if refresh:
            await asyncio.to_thread(refresh_appconfig_cache)

        # Get provider status (thread-safe)
        status = await asyncio.to_thread(get_provider_status)

        response_time = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "healthy" if status.get("enabled") else "disabled",
            "timestamp": time.time(),
            "response_time_ms": response_time,
            "provider": status,
            "message": (
                "App Configuration provider is active"
                if status.get("enabled")
                else "App Configuration not configured - using environment variables only"
            ),
        }
    except Exception as e:
        logger.error(f"Error getting App Configuration status: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "timestamp": time.time(),
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
                "error": str(e),
                "message": "Failed to get App Configuration status",
            },
            status_code=500,
        )


@router.post(
    "/appconfig/refresh",
    summary="Refresh App Configuration Cache",
    description="""
    Force refresh the App Configuration cache.
    
    This endpoint triggers a cache refresh to pull the latest configuration
    values from Azure App Configuration. Use this after updating configuration
    values in App Configuration to apply changes without restarting the application.
    """,
    tags=["Health"],
)
async def appconfig_refresh(request: Request):
    """
    Force refresh the App Configuration cache.

    Returns:
        JSON object confirming the refresh operation.
    """
    start_time = time.time()

    try:
        # Refresh cache
        await asyncio.to_thread(refresh_appconfig_cache)

        # Get updated status
        status = await asyncio.to_thread(get_provider_status)

        response_time = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "success",
            "timestamp": time.time(),
            "response_time_ms": response_time,
            "message": "App Configuration cache refreshed",
            "provider": status,
        }
    except Exception as e:
        logger.error(f"Error refreshing App Configuration cache: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "timestamp": time.time(),
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
                "error": str(e),
                "message": "Failed to refresh App Configuration cache",
            },
            status_code=500,
        )


async def _check_redis_fast(redis_manager) -> ServiceCheck:
    """Fast Redis connectivity check."""
    start = time.time()
    if not redis_manager:
        return ServiceCheck(
            component="redis",
            status="unhealthy",
            error="not initialized",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )
    try:
        pong = await asyncio.wait_for(redis_manager.ping(), timeout=0.5)
        if pong:
            return ServiceCheck(
                component="redis",
                status="healthy",
                check_time_ms=round((time.time() - start) * 1000, 2),
            )
        else:
            return ServiceCheck(
                component="redis",
                status="unhealthy",
                error="no pong response",
                check_time_ms=round((time.time() - start) * 1000, 2),
            )
    except Exception as e:
        return ServiceCheck(
            component="redis",
            status="unhealthy",
            error=str(e),
            check_time_ms=round((time.time() - start) * 1000, 2),
        )


async def _check_azure_openai_fast(openai_client) -> ServiceCheck:
    """Fast Azure OpenAI client check."""
    start = time.time()
    if not openai_client:
        return ServiceCheck(
            component="azure_openai",
            status="unhealthy",
            error="not initialized",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    ready_attributes = []
    if hasattr(openai_client, "api_version"):
        ready_attributes.append(f"api_version={openai_client.api_version}")
    if hasattr(openai_client, "deployment"):
        ready_attributes.append(f"deployment={getattr(openai_client, 'deployment', 'n/a')}")

    return ServiceCheck(
        component="azure_openai",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details=", ".join(ready_attributes) if ready_attributes else "client initialized",
    )


async def _check_speech_configuration_fast(stt_pool, tts_pool) -> ServiceCheck:
    """Validate speech configuration values and pool readiness without external calls."""
    start = time.time()

    # Read config dynamically to get values set by App Configuration bootstrap
    cfg = _get_config_dynamic()

    missing: list[str] = []
    config_summary = {
        "region": bool(cfg["AZURE_SPEECH_REGION"]),
        "endpoint": bool(cfg["AZURE_SPEECH_ENDPOINT"]),
        "key_present": bool(cfg["AZURE_SPEECH_KEY"]),
        "resource_id_present": bool(cfg["AZURE_SPEECH_RESOURCE_ID"]),
    }

    if not config_summary["region"]:
        missing.append("AZURE_SPEECH_REGION")

    if not (config_summary["key_present"] or config_summary["resource_id_present"]):
        missing.append("AZURE_SPEECH_KEY or AZURE_SPEECH_RESOURCE_ID")

    pool_snapshots: dict[str, dict[str, Any]] = {}
    for label, pool in (("stt_pool", stt_pool), ("tts_pool", tts_pool)):
        if pool is None:
            missing.append(f"{label} not initialized")
            continue

        snapshot_fn = getattr(pool, "snapshot", None)
        if not callable(snapshot_fn):
            missing.append(f"{label} missing snapshot")
            continue

        snapshot = snapshot_fn()
        pool_snapshots[label] = {
            "name": snapshot.get("name", label),
            "ready": bool(snapshot.get("ready")),
            "session_awareness": snapshot.get("session_awareness", False),
        }

        if not pool_snapshots[label]["ready"]:
            missing.append(f"{label} not ready")

    detail_parts = [
        f"region={'set' if config_summary['region'] else 'missing'}",
        f"endpoint={'set' if config_summary['endpoint'] else 'missing'}",
        f"key={'present' if config_summary['key_present'] else 'absent'}",
        f"managed_identity={'present' if config_summary['resource_id_present'] else 'absent'}",
    ]

    for label, snapshot in pool_snapshots.items():
        detail_parts.append(
            f"{label}_ready={snapshot['ready']}|session_awareness={snapshot['session_awareness']}"
        )

    elapsed_ms = round((time.time() - start) * 1000, 2)

    if missing:
        return ServiceCheck(
            component="speech_services",
            status="unhealthy",
            error="; ".join(missing),
            check_time_ms=elapsed_ms,
            details="; ".join(detail_parts),
        )

    return ServiceCheck(
        component="speech_services",
        status="healthy",
        check_time_ms=elapsed_ms,
        details="; ".join(detail_parts),
    )


async def _check_acs_caller_fast(acs_caller) -> ServiceCheck:
    """Fast ACS caller check with comprehensive phone number and config validation."""
    start = time.time()

    # Read config dynamically to get values set by App Configuration bootstrap
    cfg = _get_config_dynamic()
    acs_phone = cfg["ACS_SOURCE_PHONE_NUMBER"]
    acs_conn_string = cfg["ACS_CONNECTION_STRING"]
    acs_endpoint = cfg["ACS_ENDPOINT"]

    # Check if ACS phone number is provided
    if not acs_phone or acs_phone == "null":
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error="ACS_SOURCE_PHONE_NUMBER not provided",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Validate phone number format
    is_valid, error_msg = _validate_phone_number(acs_phone)
    if not is_valid:
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error=f"ACS phone number validation failed: {error_msg}",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Check ACS connection string or endpoint
    acs_conn_missing = not acs_conn_string
    acs_endpoint_missing = not acs_endpoint
    if acs_conn_missing and acs_endpoint_missing:
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error="Neither ACS_CONNECTION_STRING nor ACS_ENDPOINT is configured",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    if not acs_caller:
        # Try to diagnose why ACS caller is not configured
        missing = []
        if not is_valid:
            missing.append(f"ACS_SOURCE_PHONE_NUMBER ({error_msg})")
        if not acs_conn_string:
            missing.append("ACS_CONNECTION_STRING")
        if not acs_endpoint:
            missing.append("ACS_ENDPOINT")
        details = (
            f"ACS caller not configured. Missing: {', '.join(missing)}"
            if missing
            else "ACS caller not initialized for unknown reason"
        )
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error="ACS caller not initialized",
            check_time_ms=round((time.time() - start) * 1000, 2),
            details=details,
        )

    # Obfuscate phone number, show only last 4 digits
    obfuscated_phone = (
        "*" * (len(acs_phone) - 4) + acs_phone[-4:] if len(acs_phone) > 4 else acs_phone
    )
    return ServiceCheck(
        component="acs_caller",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details=f"ACS caller configured with phone: {obfuscated_phone}",
    )


async def _check_rt_agents_fast(app_state: Any) -> ServiceCheck:
    """
    Fast RT Agents check using dynamic agent discovery.

    Uses the AgentRegistry to discover agents from app.state rather than
    hardcoded parameter lists. This ensures health checks stay in sync
    with actual agent configuration.
    """
    start = time.time()

    try:
        unified_agents = getattr(app_state, "unified_agents", {}) or {}
        start_agent = getattr(app_state, "start_agent", None)
        handoff_map = getattr(app_state, "handoff_map", {}) or {}
        summaries = getattr(app_state, "agent_summaries", None)

        if summaries is None and unified_agents:
            summaries = build_agent_summaries(unified_agents)

        if not summaries:
            # Fallback to legacy registry discovery
            discovered = _agent_registry.discover_agents(app_state)
            summaries = [
                {
                    "name": name,
                    "description": getattr(agent, "description", ""),
                    "model": getattr(getattr(agent, "model", None), "deployment_id", None)
                    or getattr(agent, "model_id", None),
                    "voice": getattr(getattr(agent, "voice", None), "name", None),
                }
                for name, agent in discovered.items()
            ]

        agent_count = len(summaries or [])
        if agent_count == 0:
            missing = _agent_registry.get_missing_agents(app_state)
            detail = (
                f"agents not initialized: {', '.join(missing)}" if missing else "no agents loaded"
            )
            return ServiceCheck(
                component="rt_agents",
                status="unhealthy",
                error=detail,
                check_time_ms=round((time.time() - start) * 1000, 2),
            )

        agent_names = [s.get("name") for s in summaries if isinstance(s, dict) and s.get("name")]
        detail_parts = [f"{agent_count} agents loaded"]
        if agent_names:
            preview = ", ".join(agent_names[:5])
            if len(agent_names) > 5:
                preview += ", …"
            detail_parts.append(f"names: {preview}")
        if start_agent:
            detail_parts.append(f"start_agent={start_agent}")
        if handoff_map:
            detail_parts.append(f"handoffs={len(handoff_map)}")

        return ServiceCheck(
            component="rt_agents",
            status="healthy",
            check_time_ms=round((time.time() - start) * 1000, 2),
            details=" | ".join(detail_parts),
        )
    except Exception as exc:
        return ServiceCheck(
            component="rt_agents",
            status="unhealthy",
            error=str(exc),
            check_time_ms=round((time.time() - start) * 1000, 2),
        )


async def _check_auth_configuration_fast() -> ServiceCheck:
    """Fast authentication configuration validation check."""
    start = time.time()

    try:
        is_valid, message = _validate_auth_configuration()

        if is_valid:
            return ServiceCheck(
                component="auth_configuration",
                status="healthy",
                check_time_ms=round((time.time() - start) * 1000, 2),
                details=message,
            )
        else:
            return ServiceCheck(
                component="auth_configuration",
                status="unhealthy",
                error=message,
                check_time_ms=round((time.time() - start) * 1000, 2),
            )
    except Exception as e:
        return ServiceCheck(
            component="auth_configuration",
            status="unhealthy",
            error=f"Auth configuration check failed: {str(e)}",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )


async def _check_appconfig_fast() -> ServiceCheck:
    """Fast App Configuration provider check."""
    start = time.time()

    try:
        status = get_provider_status()

        if not status.get("enabled"):
            # App Config not configured - this is OK, not unhealthy
            return ServiceCheck(
                component="app_configuration",
                status="healthy",
                check_time_ms=round((time.time() - start) * 1000, 2),
                details="Not configured (using env vars)",
            )

        # Check if config was loaded successfully (key is "loaded", not "available")
        if status.get("loaded"):
            key_count = status.get("key_count", 0)
            details_parts = [
                f"endpoint={status.get('endpoint', 'unknown')}",
                f"keys={key_count}",
                f"label={status.get('label', 'none')}",
            ]
            return ServiceCheck(
                component="app_configuration",
                status="healthy",
                check_time_ms=round((time.time() - start) * 1000, 2),
                details=", ".join(details_parts),
            )
        else:
            return ServiceCheck(
                component="app_configuration",
                status="degraded",
                error=status.get("error", "Config not loaded"),
                check_time_ms=round((time.time() - start) * 1000, 2),
                details="Falling back to env vars",
            )
    except Exception as e:
        return ServiceCheck(
            component="app_configuration",
            status="unhealthy",
            error=f"App Configuration check failed: {str(e)}",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )


def _normalize_tools(agent_obj: Any) -> dict[str, list[str]]:
    """Normalize tools and handoff tools for consistent payloads."""

    def _to_name(item: Any) -> str | None:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return item.get("name") or item.get("tool") or item.get("id")
        return (
            getattr(item, "name", None) or getattr(item, "tool", None) or getattr(item, "id", None)
        )

    tools = (
        getattr(agent_obj, "tool_names", None)
        or getattr(agent_obj, "tools", None)
        or getattr(agent_obj, "tools_preview", None)
        or []
    )
    if isinstance(tools, dict):
        tools = tools.values()
    tools_list_raw = tools if isinstance(tools, (list, tuple, set)) else []
    tools_list: list[str] = []
    for t in tools_list_raw:
        name = _to_name(t)
        if name and name not in tools_list:
            tools_list.append(name)

    handoff_tools = getattr(agent_obj, "handoff_tools", None) or []
    if isinstance(handoff_tools, dict):
        handoff_tools = handoff_tools.values()
    handoff_list_raw = handoff_tools if isinstance(handoff_tools, (list, tuple, set)) else []
    handoff_list: list[str] = []
    for h in handoff_list_raw:
        name = _to_name(h)
        if name and name not in handoff_list:
            handoff_list.append(name)

    # If no explicit handoff_tools, infer from tool names that start with handoff_
    if not handoff_list:
        handoff_list = [t for t in tools_list if t.lower().startswith("handoff_")]

    return {"tools": tools_list, "handoff_tools": handoff_list}


def _extract_agent_info(agent: Any, defn: AgentDefinition) -> dict[str, Any] | None:
    """Extract agent info using registry definition."""
    if not agent:
        return None

    try:
        # Get voice setting from agent configuration
        agent_voice = getattr(agent, "voice_name", None)
        agent_voice_style = getattr(agent, "voice_style", "chat")

        # Fallback to DEFAULT_TTS_VOICE if agent doesn't have voice configured
        # Read dynamically as config may have been set by App Configuration bootstrap
        cfg = _get_config_dynamic()
        current_voice = agent_voice or cfg["DEFAULT_TTS_VOICE"]

        tools_normalized = _normalize_tools(agent)

        return {
            "name": getattr(agent, "name", defn.name),
            "status": "loaded",
            "creator": getattr(agent, "creator", "Unknown"),
            "organization": getattr(agent, "organization", "Unknown"),
            "description": getattr(agent, "description", ""),
            "model": {
                "deployment_id": getattr(agent, "model_id", "Unknown"),
                "temperature": getattr(agent, "temperature", 0.7),
                "top_p": getattr(agent, "top_p", 1.0),
                "max_tokens": getattr(agent, "max_tokens", 4096),
            },
            "voice": {
                "current_voice": current_voice,
                "voice_style": agent_voice_style,
                "voice_configurable": True,
                "is_per_agent_voice": bool(agent_voice),
            },
            "config_path": defn.config_path,
            "prompt_path": getattr(agent, "prompt_path", "Unknown"),
            "tools": tools_normalized["tools"],
            "handoff_tools": tools_normalized["handoff_tools"],
            "modifiable_settings": {
                "model_deployment": True,
                "temperature": True,
                "voice_name": True,
                "voice_style": True,
                "max_tokens": True,
            },
        }
    except Exception as e:
        logger.warning(f"Error extracting agent info for {defn.name}: {e}")
        return {
            "name": defn.name,
            "status": "error",
            "error": str(e),
        }


@router.get("/agents", tags=["Health"])
async def get_agents_info(request: Request, include_state: bool = False):
    """
    Get information about loaded RT agents including their configuration,
    model settings, and voice settings that can be modified.

    Uses dynamic agent discovery via AgentRegistry for maintainability.
    """
    start_time = time.time()
    agents_info = []
    app_state = request.app.state
    start_agent = getattr(app_state, "start_agent", None)
    handoff_map = getattr(app_state, "handoff_map", {}) or {}
    scenario = getattr(app_state, "scenario", None)
    scenario_name = getattr(scenario, "name", None) if scenario else None

    try:
        unified_agents = getattr(app_state, "unified_agents", {}) or {}
        summaries = getattr(app_state, "agent_summaries", None)

        if summaries is None and unified_agents:
            summaries = build_agent_summaries(unified_agents)

        if unified_agents:
            for name, agent in unified_agents.items():
                voice_obj = getattr(agent, "voice", None)
                model_obj = getattr(agent, "model", None)
                tools_normalized = _normalize_tools(agent)
                agents_info.append(
                    {
                        "name": name,
                        "status": "loaded",
                        "description": getattr(agent, "description", ""),
                        "prompt_path": getattr(agent, "prompt_path", None),
                        "config_path": getattr(agent, "config_path", None),
                        "model": {
                            "deployment_id": getattr(model_obj, "deployment_id", None)
                            or getattr(agent, "model_id", None)
                        },
                        "voice": {
                            "current_voice": getattr(voice_obj, "name", None)
                            or getattr(agent, "voice_name", None),
                            "voice_style": getattr(voice_obj, "style", None)
                            or getattr(agent, "voice_style", "chat"),
                            "voice_configurable": True,
                            "is_per_agent_voice": bool(
                                getattr(voice_obj, "name", None)
                                or getattr(agent, "voice_name", None)
                            ),
                        },
                        "tool_count": len(tools_normalized["tools"]),
                        "tools": tools_normalized["tools"],
                        "handoff_tools": tools_normalized["handoff_tools"],
                        "handoff_trigger": getattr(
                            getattr(agent, "handoff", None), "trigger", None
                        ),
                        "prompt_preview": (
                            getattr(agent, "prompt_template", None)[:320]
                            if getattr(agent, "prompt_template", None)
                            else None
                        ),
                        "source": "unified",
                    }
                )
        else:
            # Fallback to legacy registry if unified agents not available
            for defn in _agent_registry.list_definitions():
                agent = getattr(app_state, defn.state_attr, None)
                agent_info = _extract_agent_info(agent, defn)
                if agent_info:
                    agent_info["source"] = "legacy"
                    agents_info.append(agent_info)

        response_time = round((time.time() - start_time) * 1000, 2)
        connections = [
            {"tool": tool, "target": target} for tool, target in (handoff_map or {}).items()
        ]

        payload = {
            "status": "success",
            "agents_count": len(agents_info),
            "agents": agents_info,
            "summaries": summaries or agents_info,
            "handoff_map": handoff_map,
            "start_agent": start_agent,
            "scenario": scenario_name,
            "connections": connections,
            "response_time_ms": response_time,
            "available_voices": {
                "turbo_voices": [
                    "en-US-AlloyTurboMultilingualNeural",
                    "en-US-EchoTurboMultilingualNeural",
                    "en-US-FableTurboMultilingualNeural",
                    "en-US-OnyxTurboMultilingualNeural",
                    "en-US-NovaTurboMultilingualNeural",
                    "en-US-ShimmerTurboMultilingualNeural",
                ],
                "standard_voices": [
                    "en-US-AvaMultilingualNeural",
                    "en-US-AndrewMultilingualNeural",
                    "en-US-EmmaMultilingualNeural",
                    "en-US-BrianMultilingualNeural",
                ],
                "hd_voices": [
                    "en-US-Ava:DragonHDLatestNeural",
                    "en-US-Andrew:DragonHDLatestNeural",
                    "en-US-Brian:DragonHDLatestNeural",
                    "en-US-Emma:DragonHDLatestNeural",
                ],
            },
        }
        if include_state:
            payload["current_agent"] = getattr(app_state, "active_agent", None)

        return payload

    except Exception as e:
        logger.error(f"Error getting agents info: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
            },
            status_code=500,
        )


@router.get("/agents/{agent_name}", tags=["Health"])
async def get_agent_detail(agent_name: str, request: Request, session_id: str | None = None):
    """
    Get detailed info for a specific agent, including normalized tools/handoff tools.
    Optional session_id for future session-scoped context (non-blocking for hotpath).
    """
    app_state = request.app.state
    agent_name_lower = agent_name.lower()
    unified_agents = getattr(app_state, "unified_agents", {}) or {}

    target_agent = None
    for name, agent in unified_agents.items():
        if name.lower() == agent_name_lower:
            target_agent = agent
            break

    source = "unified"
    if not target_agent:
        # Fallback to legacy registry lookup
        defn = _agent_registry.get_definition(agent_name)
        if defn:
            target_agent = getattr(app_state, defn.state_attr, None)
            source = "legacy"

    if not target_agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found",
        )

    tools_normalized = _normalize_tools(target_agent)
    voice_obj = getattr(target_agent, "voice", None)
    model_obj = getattr(target_agent, "model", None)

    detail = {
        "name": getattr(target_agent, "name", agent_name),
        "description": getattr(target_agent, "description", ""),
        "prompt_path": getattr(target_agent, "prompt_path", None),
        "config_path": getattr(target_agent, "config_path", None),
        "model": {
            "deployment_id": getattr(model_obj, "deployment_id", None)
            or getattr(target_agent, "model_id", None)
        },
        "voice": {
            "current_voice": getattr(voice_obj, "name", None)
            or getattr(target_agent, "voice_name", None),
            "voice_style": getattr(voice_obj, "style", None)
            or getattr(target_agent, "voice_style", "chat"),
        },
        "tools": tools_normalized["tools"],
        "handoff_tools": tools_normalized["handoff_tools"],
        "handoff_trigger": getattr(getattr(target_agent, "handoff", None), "trigger", None),
        "prompt_preview": (
            getattr(target_agent, "prompt_template", None)[:320]
            if getattr(target_agent, "prompt_template", None)
            else None
        ),
        "source": source,
    }

    if session_id:
        detail["session_id"] = session_id
        detail["current_agent"] = getattr(app_state, "active_agent", None)

    return detail


class AgentModelUpdate(BaseModel):
    deployment_id: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


class AgentVoiceUpdate(BaseModel):
    voice_name: str | None = None
    voice_style: str | None = None


class AgentConfigUpdate(BaseModel):
    model: AgentModelUpdate | None = None
    voice: AgentVoiceUpdate | None = None


@router.put("/agents/{agent_name}", tags=["Health"])
async def update_agent_config(agent_name: str, config: AgentConfigUpdate, request: Request):
    """
    Update configuration for a specific agent (model settings, voice, etc.).
    Changes are applied to the runtime instance but not persisted to YAML files.

    Uses AgentRegistry for dynamic agent lookup via name or alias.
    """
    start_time = time.time()

    try:
        # Use registry to find agent by name or alias
        defn = _agent_registry.get_definition(agent_name)
        if not defn:
            available = [d.name for d in _agent_registry.list_definitions()]
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_name}' not found. Available agents: {', '.join(available)}",
            )

        agent = getattr(request.app.state, defn.state_attr, None)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{defn.name}' is registered but not initialized",
            )

        updated_fields = []

        # Update model settings
        if config.model:
            if config.model.deployment_id is not None:
                agent.model_id = config.model.deployment_id
                updated_fields.append(f"deployment_id -> {config.model.deployment_id}")

            if config.model.temperature is not None:
                if 0.0 <= config.model.temperature <= 2.0:
                    agent.temperature = config.model.temperature
                    updated_fields.append(f"temperature -> {config.model.temperature}")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Temperature must be between 0.0 and 2.0",
                    )

            if config.model.top_p is not None:
                if 0.0 <= config.model.top_p <= 1.0:
                    agent.top_p = config.model.top_p
                    updated_fields.append(f"top_p -> {config.model.top_p}")
                else:
                    raise HTTPException(status_code=400, detail="top_p must be between 0.0 and 1.0")

            if config.model.max_tokens is not None:
                if 1 <= config.model.max_tokens <= 16384:
                    agent.max_tokens = config.model.max_tokens
                    updated_fields.append(f"max_tokens -> {config.model.max_tokens}")
                else:
                    raise HTTPException(
                        status_code=400, detail="max_tokens must be between 1 and 16384"
                    )

        # Update voice settings per agent
        if config.voice:
            if config.voice.voice_name is not None:
                agent.voice_name = config.voice.voice_name
                updated_fields.append(f"voice_name -> {config.voice.voice_name}")
                logger.info(f"Updated {defn.name} voice to: {config.voice.voice_name}")

            if config.voice.voice_style is not None:
                agent.voice_style = config.voice.voice_style
                updated_fields.append(f"voice_style -> {config.voice.voice_style}")
                logger.info(f"Updated {defn.name} voice style to: {config.voice.voice_style}")

        response_time = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "success",
            "agent_name": getattr(agent, "name", defn.name),
            "updated_fields": updated_fields,
            "message": f"Successfully updated {len(updated_fields)} settings for {defn.name}",
            "response_time_ms": response_time,
            "note": "Changes applied to runtime instance. Restart required for persistence.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent config: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
            },
            status_code=500,
        )
