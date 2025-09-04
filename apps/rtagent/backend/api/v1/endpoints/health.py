"""
Health Endpoints
===============

Comprehensive health check and readiness endpoints for monitoring.
Includes all critical dependency checks with proper timeouts and error handling.
"""

import asyncio
import re
import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse

from config import (
    ACS_CONNECTION_STRING,
    ACS_ENDPOINT,
    ACS_SOURCE_PHONE_NUMBER,
    BACKEND_AUTH_CLIENT_ID,
    AZURE_TENANT_ID,
    ALLOWED_CLIENT_IDS,
    ENABLE_AUTH_VALIDATION,
)
from apps.rtagent.backend.api.v1.schemas.health import (
    HealthResponse,
    ServiceCheck,
    ReadinessResponse,
)
from utils.ml_logging import get_logger

logger = get_logger("v1.health")

router = APIRouter()


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
        if not ENABLE_AUTH_VALIDATION:
            logger.debug("Authentication validation is disabled")
            return True, "Auth validation disabled"

        validation_errors = []

        # Check BACKEND_AUTH_CLIENT_ID is a valid GUID
        if not BACKEND_AUTH_CLIENT_ID:
            validation_errors.append("BACKEND_AUTH_CLIENT_ID is not set")
        elif not _validate_guid(BACKEND_AUTH_CLIENT_ID):
            validation_errors.append("BACKEND_AUTH_CLIENT_ID is not a valid GUID")

        # Check AZURE_TENANT_ID is a valid GUID
        if not AZURE_TENANT_ID:
            validation_errors.append("AZURE_TENANT_ID is not set")
        elif not _validate_guid(AZURE_TENANT_ID):
            validation_errors.append("AZURE_TENANT_ID is not a valid GUID")

        # Check ALLOWED_CLIENT_IDS has at least one valid client ID
        if not ALLOWED_CLIENT_IDS:
            validation_errors.append(
                "ALLOWED_CLIENT_IDS is empty - at least one client ID required"
            )
        else:
            invalid_client_ids = [
                cid for cid in ALLOWED_CLIENT_IDS if not _validate_guid(cid)
            ]
            if invalid_client_ids:
                validation_errors.append(
                    f"Invalid GUID format in ALLOWED_CLIENT_IDS: {invalid_client_ids}"
                )

        if validation_errors:
            error_message = "; ".join(validation_errors)
            logger.error(
                f"Authentication configuration validation failed: {error_message}"
            )
            return False, error_message

        success_message = (
            f"Auth validation enabled with {len(ALLOWED_CLIENT_IDS)} allowed client(s)"
        )
        logger.info(
            f"Authentication configuration validation successful: {success_message}"
        )
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
                        "details": {"api_version": "v1", "service": "rtagent-backend"},
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
        details={"api_version": "v1", "service": "rtagent-backend"},
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
    health_checks: List[ServiceCheck] = []
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
    redis_status = await fast_ping(
        _check_redis_fast, request.app.state.redis, component="redis"
    )
    health_checks.append(redis_status)

    # Check Azure OpenAI
    openai_status = await fast_ping(
        _check_azure_openai_fast,
        request.app.state.azureopenai_client,
        component="azure_openai",
    )
    health_checks.append(openai_status)

    # Check Speech Services (pools)
    speech_status = await fast_ping(
        _check_speech_services_fast,
        request.app.state.tts_pool,
        request.app.state.stt_pool,
        component="speech_services",
    )
    health_checks.append(speech_status)

    # Check ACS Caller
    acs_status = await fast_ping(
        _check_acs_caller_fast, request.app.state.acs_caller, component="acs_caller"
    )
    health_checks.append(acs_status)

    # Check RT Agents
    agent_status = await fast_ping(
        _check_rt_agents_fast,
        request.app.state.auth_agent,
        request.app.state.claim_intake_agent,
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
        overall_status = (
            "degraded" if len(failed_checks) < len(health_checks) else "unhealthy"
        )

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
    return ServiceCheck(
        component="azure_openai",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details="client initialized",
    )


async def _check_speech_services_fast(tts_pool, stt_pool) -> ServiceCheck:
    """Fast Speech Services check using pools.

    Checks that both TTS and STT pools are initialized and ready.
    """
    start = time.time()
    if not tts_pool or not stt_pool:
        return ServiceCheck(
            component="speech_services",
            status="unhealthy",
            error="pools not initialized",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Check if pools are properly configured
    try:
        pool_info = {
            "tts_pool_size": tts_pool._size,
            "tts_pool_queue_size": tts_pool._q.qsize(),
            "tts_pool_ready": tts_pool._ready.is_set(),
            "stt_pool_size": stt_pool._size,
            "stt_pool_queue_size": stt_pool._q.qsize(),
            "stt_pool_ready": stt_pool._ready.is_set(),
        }
    except Exception as e:
        return ServiceCheck(
            component="speech_services",
            status="unhealthy",
            error=f"pool introspection failed: {e}",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    return ServiceCheck(
        component="speech_services",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details=f"pools ready: TTS={pool_info['tts_pool_ready']}, STT={pool_info['stt_pool_ready']}",
    )


async def _check_acs_caller_fast(acs_caller) -> ServiceCheck:
    """Fast ACS caller check with comprehensive phone number and config validation."""
    start = time.time()

    # Check if ACS phone number is provided
    if not ACS_SOURCE_PHONE_NUMBER or ACS_SOURCE_PHONE_NUMBER == "null":
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error="ACS_SOURCE_PHONE_NUMBER not provided",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Validate phone number format
    is_valid, error_msg = _validate_phone_number(ACS_SOURCE_PHONE_NUMBER)
    if not is_valid:
        return ServiceCheck(
            component="acs_caller",
            status="unhealthy",
            error=f"ACS phone number validation failed: {error_msg}",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Check ACS connection string or endpoint
    acs_conn_missing = not ACS_CONNECTION_STRING
    acs_endpoint_missing = not ACS_ENDPOINT
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
        if not ACS_CONNECTION_STRING:
            missing.append("ACS_CONNECTION_STRING")
        if not ACS_ENDPOINT:
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
        "*" * (len(ACS_SOURCE_PHONE_NUMBER) - 4) + ACS_SOURCE_PHONE_NUMBER[-4:]
        if len(ACS_SOURCE_PHONE_NUMBER) > 4
        else ACS_SOURCE_PHONE_NUMBER
    )
    return ServiceCheck(
        component="acs_caller",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details=f"ACS caller configured with phone: {obfuscated_phone}",
    )


async def _check_rt_agents_fast(auth_agent, claim_intake_agent) -> ServiceCheck:
    """Fast RT Agents check."""
    start = time.time()
    if not auth_agent or not claim_intake_agent:
        return ServiceCheck(
            component="rt_agents",
            status="unhealthy",
            error="not initialized",
            check_time_ms=round((time.time() - start) * 1000, 2),
        )
    return ServiceCheck(
        component="rt_agents",
        status="healthy",
        check_time_ms=round((time.time() - start) * 1000, 2),
        details="auth and claim intake agents initialized",
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


@router.get("/agents")
async def get_agents_info(request: Request):
    """
    Get information about loaded RT agents including their configuration,
    model settings, and voice settings that can be modified.
    """
    start_time = time.time()
    agents_info = []

    try:
        # Get agents from app state
        auth_agent = getattr(request.app.state, "auth_agent", None)
        claim_intake_agent = getattr(request.app.state, "claim_intake_agent", None)
        general_info_agent = getattr(request.app.state, "general_info_agent", None)

        # Helper function to extract agent info
        def extract_agent_info(agent, config_path: str = None):
            if not agent:
                return None

            try:
                # Get voice setting from agent configuration
                agent_voice = getattr(agent, "voice_name", None)
                agent_voice_style = getattr(agent, "voice_style", "chat")

                # Fallback to global GREETING_VOICE_TTS if agent doesn't have voice configured
                from config import GREETING_VOICE_TTS

                current_voice = agent_voice or GREETING_VOICE_TTS

                agent_info = {
                    "name": getattr(agent, "name", "Unknown"),
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
                        "is_per_agent_voice": bool(
                            agent_voice
                        ),  # True if agent has its own voice
                    },
                    "config_path": config_path,
                    "prompt_path": getattr(agent, "prompt_path", "Unknown"),
                    "tools": [
                        tool.get("function", {}).get("name", "Unknown")
                        for tool in getattr(agent, "tools", [])
                    ],
                    "modifiable_settings": {
                        "model_deployment": True,
                        "temperature": True,
                        "voice_name": True,
                        "voice_style": True,
                        "max_tokens": True,
                    },
                }
                return agent_info
            except Exception as e:
                logger.warning(f"Error extracting agent info: {e}")
                return {
                    "name": getattr(agent, "name", "Unknown"),
                    "status": "error",
                    "error": str(e),
                }

        # Extract info for each agent
        if auth_agent:
            from config import AGENT_AUTH_CONFIG

            agent_info = extract_agent_info(auth_agent, AGENT_AUTH_CONFIG)
            if agent_info:
                agents_info.append(agent_info)

        if claim_intake_agent:
            from config import AGENT_CLAIM_INTAKE_CONFIG

            agent_info = extract_agent_info(
                claim_intake_agent, AGENT_CLAIM_INTAKE_CONFIG
            )
            if agent_info:
                agents_info.append(agent_info)

        if general_info_agent:
            from config import AGENT_GENERAL_INFO_CONFIG

            agent_info = extract_agent_info(
                general_info_agent, AGENT_GENERAL_INFO_CONFIG
            )
            if agent_info:
                agents_info.append(agent_info)

        response_time = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "success",
            "agents_count": len(agents_info),
            "agents": agents_info,
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


class AgentModelUpdate(BaseModel):
    deployment_id: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


class AgentVoiceUpdate(BaseModel):
    voice_name: Optional[str] = None
    voice_style: Optional[str] = None


class AgentConfigUpdate(BaseModel):
    model: Optional[AgentModelUpdate] = None
    voice: Optional[AgentVoiceUpdate] = None


@router.put("/agents/{agent_name}")
async def update_agent_config(
    agent_name: str, config: AgentConfigUpdate, request: Request
):
    """
    Update configuration for a specific agent (model settings, voice, etc.).
    Changes are applied to the runtime instance but not persisted to YAML files.
    """
    start_time = time.time()

    try:
        # Get the agent instance from app state
        agent = None
        if agent_name.lower() in ["authagent", "auth_agent", "auth"]:
            agent = getattr(request.app.state, "auth_agent", None)
        elif agent_name.lower() in [
            "fnolintakeagent",
            "claim_intake_agent",
            "claim",
            "fnol",
        ]:
            agent = getattr(request.app.state, "claim_intake_agent", None)
        elif agent_name.lower() in [
            "generalinfoagent",
            "general_info_agent",
            "general",
        ]:
            agent = getattr(request.app.state, "general_info_agent", None)

        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_name}' not found. Available agents: auth, claim, general",
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
                    raise HTTPException(
                        status_code=400, detail="top_p must be between 0.0 and 1.0"
                    )

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
                logger.info(f"Updated {agent.name} voice to: {config.voice.voice_name}")

            if config.voice.voice_style is not None:
                agent.voice_style = config.voice.voice_style
                updated_fields.append(f"voice_style -> {config.voice.voice_style}")
                logger.info(
                    f"Updated {agent.name} voice style to: {config.voice.voice_style}"
                )

        response_time = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "success",
            "agent_name": agent.name,
            "updated_fields": updated_fields,
            "message": f"Successfully updated {len(updated_fields)} settings for {agent.name}",
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
