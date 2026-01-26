"""
Session Management Endpoints
============================

REST API endpoints for managing and retrieving session information from Redis cache.
Provides comprehensive session history and metadata management.

Endpoints:
- GET /api/v1/sessions - List all sessions with metadata
- GET /api/v1/sessions/{session_id} - Get detailed session information
- DELETE /api/v1/sessions/{session_id} - Delete a specific session
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from utils.ml_logging import get_logger

from apps.artagent.backend.src.orchestration.naming import (
    SCENARIO_KEY_ACTIVE,
    SCENARIO_KEY_ALL,
    SCENARIO_KEY_CONFIG,
)

logger = get_logger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class SessionAgent(BaseModel):
    """Agent information within a session."""
    name: str
    is_active: bool = False
    is_custom: bool = False
    tools: List[str] = []
    voice: Dict[str, Any] = {}
    model: Dict[str, Any] = {}


class SessionScenario(BaseModel):
    """Scenario information within a session."""
    name: str
    is_active: bool = False
    agents: List[str] = []
    handoffs: List[Dict[str, Any]] = []


class SessionMetadata(BaseModel):
    """Session metadata and information."""
    session_id: str
    created_at: float
    last_activity: float
    last_activity_readable: str | None = None  # Human-readable last activity
    turn_count: int = 0
    connection_status: str = "inactive"
    streaming_mode: str | None = None
    user_email: str | None = None

    # Profile information
    profile_name: str | None = None
    profile_type: str | None = None  # e.g., "banking", "insurance", "custom"

    # Agent/Scenario counts and details
    agents_count: int = 0
    scenarios_count: int = 0
    active_agents_count: int = 0
    scenario_agents_count: int = 0
    custom_scenarios_count: int = 0

    agents: List[SessionAgent] = []
    scenarios: List[SessionScenario] = []
    has_scenario_agents: bool = False
    has_custom_scenarios: bool = False


class SessionListResponse(BaseModel):
    """Response for listing sessions."""
    sessions: List[SessionMetadata]
    total_count: int
    active_count: int


class SessionDetailResponse(BaseModel):
    """Response for detailed session information."""
    session: SessionMetadata
    chat_history: List[Dict[str, Any]] = []
    memory: Dict[str, Any] = {}
    agent_configs: Dict[str, Any] = {}
    scenario_configs: Dict[str, Any] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _format_timestamp(timestamp: float) -> str:
    """Format timestamp into human-readable string."""
    try:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt

        total_seconds = diff.total_seconds()

        if total_seconds < 60:  # Less than 1 minute
            return "Just now"
        elif total_seconds < 3600:  # Less than 1 hour
            minutes = int(total_seconds / 60)
            return f"{minutes}m ago"
        elif total_seconds < 86400:  # Less than 1 day
            hours = int(total_seconds / 3600)
            return f"{hours}h ago"
        elif total_seconds < 604800:  # Less than 1 week
            days = int(total_seconds / 86400)
            return f"{days}d ago"
        else:
            return dt.strftime("%b %d, %Y")
    except Exception as e:
        logger.warning(f"Failed to format timestamp {timestamp}: {e}")
        return "Unknown"


async def _get_redis_manager(request: Request):
    """Get Redis manager from app state."""
    redis_manager = getattr(request.app.state, "redis", None)
    if not redis_manager:
        raise HTTPException(
            status_code=503,
            detail="Redis cache service unavailable"
        )
    return redis_manager


async def _scan_session_keys(redis_manager) -> List[str]:
    """Scan for all session keys in Redis using pattern matching."""
    try:
        session_keys = []

        # First try the most reliable method: scan_iter
        try:
            if hasattr(redis_manager.redis_client, 'scan_iter'):
                logger.debug("Using scan_iter method for key scanning")
                for key in redis_manager.redis_client.scan_iter(match="session:session_*", count=100):
                    if isinstance(key, bytes):
                        session_keys.append(key.decode('utf-8'))
                    elif isinstance(key, str):
                        session_keys.append(key)
                    else:
                        # Handle any other format by converting to string
                        session_keys.append(str(key))

                if session_keys:
                    logger.debug(f"scan_iter found {len(session_keys)} session keys")
                    return session_keys
        except Exception as scan_iter_error:
            logger.warning(f"scan_iter failed: {scan_iter_error}")

        # Fallback to manual SCAN with improved cluster handling
        logger.debug("Falling back to manual SCAN operation")
        cursor = 0
        scan_attempts = 0
        max_scan_attempts = 1000  # Prevent infinite loops

        while scan_attempts < max_scan_attempts:
            try:
                scan_attempts += 1
                result = redis_manager.redis_client.scan(
                    cursor=cursor,
                    match="session:session_*",
                    count=100
                )

                # Handle different response formats
                if isinstance(result, tuple) and len(result) == 2:
                    next_cursor, keys = result
                    # Convert cursor to int if needed
                    try:
                        cursor = int(next_cursor) if next_cursor is not None else 0
                    except (ValueError, TypeError):
                        logger.warning(f"Failed to convert cursor to int: {next_cursor}, type: {type(next_cursor)}")
                        cursor = 0

                elif isinstance(result, dict):
                    # Handle cluster mode response
                    next_cursor = result.get('cursor', 0)
                    keys = result.get('keys', [])

                    # Ensure cursor is an integer for Redis cluster
                    try:
                        cursor = int(next_cursor) if next_cursor is not None else 0
                    except (ValueError, TypeError):
                        logger.warning(f"Failed to convert dict cursor to int: {next_cursor}, type: {type(next_cursor)}")
                        cursor = 0

                else:
                    logger.warning(f"Unexpected SCAN result format: {type(result)}, value: {result}")
                    break

                # Process keys with robust type handling
                if keys:
                    for key in keys:
                        try:
                            if isinstance(key, bytes):
                                session_keys.append(key.decode('utf-8'))
                            elif isinstance(key, str):
                                session_keys.append(key)
                            else:
                                # Handle any other format by converting to string
                                key_str = str(key)
                                if key_str and key_str != 'None':
                                    session_keys.append(key_str)
                        except Exception as key_error:
                            logger.warning(f"Failed to process key {key}: {key_error}")
                            continue

                # Check if we're done scanning
                if cursor == 0:
                    break

            except Exception as scan_error:
                logger.warning(f"SCAN operation attempt {scan_attempts} failed: {scan_error}")
                # Try to continue with next cursor or break if too many failures
                if scan_attempts > 10:
                    break
                cursor = cursor + 1 if cursor < 100 else 0

        if session_keys:
            logger.debug(f"Manual SCAN found {len(session_keys)} session keys")
            return session_keys

        # Last resort: KEYS command fallback (less efficient but reliable)
        try:
            logger.info("No keys found with SCAN, trying KEYS fallback")
            keys_result = redis_manager.redis_client.keys("session:session_*")

            if keys_result:
                for key in keys_result:
                    try:
                        if isinstance(key, bytes):
                            session_keys.append(key.decode('utf-8'))
                        elif isinstance(key, str):
                            session_keys.append(key)
                        else:
                            key_str = str(key)
                            if key_str and key_str != 'None':
                                session_keys.append(key_str)
                    except Exception as key_error:
                        logger.warning(f"Failed to process KEYS result {key}: {key_error}")
                        continue

                logger.info(f"Found {len(session_keys)} session keys using KEYS fallback")
            else:
                logger.info("No session keys found in Redis")

        except Exception as keys_error:
            logger.warning(f"KEYS fallback also failed: {keys_error}")

        logger.debug(f"Final result: Found {len(session_keys)} session keys in Redis")
        return session_keys

    except Exception as e:
        logger.error(f"Failed to scan session keys: {e}")
        return []


async def _parse_session_data(session_key: str, redis_data: Dict[str, Any]) -> SessionMetadata | None:
    """Parse Redis session data into SessionMetadata."""
    try:
        # Extract session ID from key (session:session_12345 -> session_12345)
        session_id = session_key.replace("session:", "")

        # Debug: Log the structure we're working with
        logger.debug(f"Parsing session {session_id} with keys: {list(redis_data.keys()) if isinstance(redis_data, dict) else 'Not a dict'}")

        # Initialize with defaults
        current_time = time.time()
        metadata = {
            "session_id": session_id,
            "created_at": current_time,
            "last_activity": current_time,
            "last_activity_readable": None,
            "turn_count": 0,
            "connection_status": "inactive",
            "streaming_mode": None,
            "user_email": None,
            "profile_name": None,
            "profile_type": None,
            "agents_count": 0,
            "scenarios_count": 0,
            "active_agents_count": 0,
            "scenario_agents_count": 0,
            "custom_scenarios_count": 0,
            "agents": [],
            "scenarios": [],
            "has_scenario_agents": False,
            "has_custom_scenarios": False
        }

        # Parse core memory for session metadata
        if "corememory" in redis_data:
            try:
                core_memory = redis_data["corememory"]
                if isinstance(core_memory, str):
                    core_memory = json.loads(core_memory)

                # Extract session metadata from core memory
                if isinstance(core_memory, dict):
                    # Session info (may be in various locations)
                    session_info = core_memory.get("session_info", {})
                    metadata.update({
                        "created_at": session_info.get("created_at", metadata["created_at"]),
                        "last_activity": session_info.get("last_activity", metadata["last_activity"]),
                        "streaming_mode": session_info.get("streaming_mode"),
                        "user_email": session_info.get("user_email"),
                    })

                    # Extract profile information from various possible locations
                    profile_data = (
                        core_memory.get("session_profile", {}) or
                        core_memory.get("profile", {}) or
                        core_memory.get("user_profile", {})
                    )
                    if profile_data:
                        metadata.update({
                            "profile_name": (
                                profile_data.get("display_name") or
                                profile_data.get("name") or
                                profile_data.get("profile_name") or
                                profile_data.get("caller_name")
                            ),
                            "profile_type": (
                                profile_data.get("profile_type") or
                                profile_data.get("industry") or
                                profile_data.get("scenario_type")
                            ),
                        })

                    # Extract user email from various locations
                    if not metadata["user_email"]:
                        metadata["user_email"] = (
                            core_memory.get("user_email") or
                            core_memory.get("caller_email") or
                            profile_data.get("email")
                        )

                    # Extract agent information from various possible locations
                    agents_list = []
                    agents_count = 0
                    scenario_agents_count = 0
                    active_count = 0
                    active_agent_name = None

                    # Method 1: Check session_scenario_config for agents list
                    session_scenario_config = core_memory.get(SCENARIO_KEY_CONFIG, {})
                    if session_scenario_config and isinstance(session_scenario_config, dict):
                        agents_in_scenario = session_scenario_config.get("agents", [])
                        if agents_in_scenario:
                            agents_count = len(agents_in_scenario)
                            # These are scenario-specific agents
                            scenario_agents_count = agents_count

                            # Try to identify the active agent from various sources
                            active_agent_name = (
                                core_memory.get("active_agent") or
                                core_memory.get("current_agent") or
                                session_scenario_config.get("start_agent")
                            )

                            for agent_name in agents_in_scenario:
                                is_active = (agent_name == active_agent_name)
                                if is_active:
                                    active_count = 1

                                agents_list.append(SessionAgent(
                                    name=agent_name,
                                    is_active=is_active,
                                    is_custom=True,  # Assume custom if in session scenario
                                    tools=[],  # Tool details not readily available here
                                ).model_dump())

                    # Method 2: Check session_scenarios_all for agent information
                    if not agents_count:
                        session_scenarios = core_memory.get(SCENARIO_KEY_ALL, {})
                        active_scenario_name = core_memory.get(SCENARIO_KEY_ACTIVE)

                        if session_scenarios and active_scenario_name:
                            active_scenario = session_scenarios.get(active_scenario_name, {})
                            if active_scenario:
                                agents_in_scenario = active_scenario.get("agents", [])
                                if agents_in_scenario:
                                    agents_count = len(agents_in_scenario)
                                    scenario_agents_count = agents_count

                                    active_agent_name = (
                                        core_memory.get("active_agent") or
                                        active_scenario.get("start_agent")
                                    )

                                    for agent_name in agents_in_scenario:
                                        is_active = (agent_name == active_agent_name)
                                        if is_active:
                                            active_count = 1

                                        agents_list.append(SessionAgent(
                                            name=agent_name,
                                            is_active=is_active,
                                            is_custom=True,
                                            tools=[],
                                        ).model_dump())

                    # Method 3: Fallback to agent_registry structure
                    if not agents_count:
                        agent_registry = core_memory.get("agent_registry", {})
                        if agent_registry and isinstance(agent_registry, dict):
                            agents_data = agent_registry.get("agents", {})
                            active_agent = agent_registry.get("active_agent")

                            for name, agent_config in agents_data.items():
                                is_active = (name == active_agent)
                                is_scenario_agent = (
                                    agent_config.get("has_overrides", False) or
                                    agent_config.get("source", "") != "base"
                                )

                                if is_active:
                                    active_count += 1
                                if is_scenario_agent:
                                    scenario_agents_count += 1

                                agents_list.append(SessionAgent(
                                    name=name,
                                    is_active=is_active,
                                    is_custom=is_scenario_agent,
                                    tools=agent_config.get("tool_names_override", []) or [],
                                ).model_dump())

                            agents_count = len(agents_data)

                    metadata.update({
                        "agents": agents_list,
                        "agents_count": agents_count,
                        "active_agents_count": active_count,
                        "scenario_agents_count": scenario_agents_count,
                        "has_scenario_agents": scenario_agents_count > 0,
                    })

                    logger.debug(f"Session {session_id} agents: count={agents_count}, scenario={scenario_agents_count}, active={active_count}")

                    # Extract scenario information from various possible locations
                    scenarios_list = []
                    scenarios_count = 0
                    custom_scenarios_count = 0
                    active_scenario_name = core_memory.get(SCENARIO_KEY_ACTIVE)

                    # Method 1: Try the new structure: session_scenarios_all + active_scenario_name
                    session_scenarios = core_memory.get(SCENARIO_KEY_ALL, {})

                    if session_scenarios and isinstance(session_scenarios, dict):
                        scenarios_count = len(session_scenarios)
                        custom_scenarios_count = scenarios_count  # Assume all are custom

                        for name, scenario_config in session_scenarios.items():
                            if isinstance(scenario_config, dict):
                                is_active = (name == active_scenario_name)

                                scenarios_list.append(SessionScenario(
                                    name=name,
                                    is_active=is_active,
                                    agents=scenario_config.get("agents", []),
                                    handoffs=scenario_config.get("handoffs", []),
                                ).model_dump())

                    # Fallback to scenario_registry structure
                    else:
                        scenario_registry = core_memory.get("scenario_registry", {})
                        if scenario_registry and isinstance(scenario_registry, dict):
                            scenarios_data = scenario_registry.get("scenarios", {})
                            active_scenario = scenario_registry.get("active_scenario")

                            scenarios_count = len(scenarios_data)

                            for name, scenario_config in scenarios_data.items():
                                is_active = (name == active_scenario)
                                is_custom = scenario_config.get("is_custom", True)

                                if is_custom:
                                    custom_scenarios_count += 1

                                scenarios_list.append(SessionScenario(
                                    name=name,
                                    is_active=is_active,
                                    agents=scenario_config.get("agents", []),
                                    handoffs=scenario_config.get("handoffs", []),
                                ).model_dump())

                    # Check for session_scenario_config as well (active scenario details)
                    # Only add if we didn't find scenarios in the methods above
                    if not scenarios_count:
                        session_scenario_config = core_memory.get(SCENARIO_KEY_CONFIG, {})
                        if session_scenario_config and isinstance(session_scenario_config, dict):
                            scenario_name = session_scenario_config.get("name")
                            if scenario_name:
                                scenarios_count = 1
                                custom_scenarios_count = 1

                                scenarios_list.append(SessionScenario(
                                    name=scenario_name,
                                    is_active=True,  # This is the active session scenario
                                    agents=session_scenario_config.get("agents", []),
                                    handoffs=session_scenario_config.get("handoffs", []),
                                ).model_dump())

                    metadata.update({
                        "scenarios": scenarios_list,
                        "scenarios_count": scenarios_count,
                        "custom_scenarios_count": custom_scenarios_count,
                        "has_custom_scenarios": custom_scenarios_count > 0,
                    })

                    logger.debug(f"Session {session_id} scenarios: count={scenarios_count}, custom={custom_scenarios_count}, active={active_scenario_name}")

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse corememory for {session_id}: {e}")

        # Parse chat history for turn count and activity
        if "chat_history" in redis_data:
            try:
                chat_history = redis_data["chat_history"]
                if isinstance(chat_history, str):
                    chat_history = json.loads(chat_history)

                total_messages = 0
                latest_timestamp = None

                # Handle agent-specific chat history structure
                if isinstance(chat_history, dict):
                    for agent_name, agent_messages in chat_history.items():
                        if isinstance(agent_messages, list):
                            total_messages += len(agent_messages)

                            # Look for timestamps in messages to find latest activity
                            for msg in agent_messages:
                                if isinstance(msg, dict):
                                    # Check for timestamp in various formats
                                    msg_timestamp = msg.get("timestamp")
                                    if msg_timestamp:
                                        if latest_timestamp is None or msg_timestamp > latest_timestamp:
                                            latest_timestamp = msg_timestamp

                # Handle simple list format (fallback)
                elif isinstance(chat_history, list):
                    total_messages = len(chat_history)

                    # Get last activity from most recent message
                    if chat_history:
                        last_msg = chat_history[-1]
                        if isinstance(last_msg, dict) and "timestamp" in last_msg:
                            latest_timestamp = last_msg["timestamp"]

                metadata["turn_count"] = total_messages
                if latest_timestamp:
                    metadata["last_activity"] = latest_timestamp

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse chat_history for {session_id}: {e}")

        # Format last activity timestamp
        metadata["last_activity_readable"] = _format_timestamp(metadata["last_activity"])

        # Check if session appears to be active (recent activity within last hour)
        current_time = time.time()
        if current_time - metadata["last_activity"] < 3600:  # 1 hour
            metadata["connection_status"] = "active"

        return SessionMetadata(**metadata)

    except Exception as e:
        logger.error(f"Failed to parse session data for {session_key}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List all sessions",
    description="Get a list of all sessions stored in Redis with metadata.",
    tags=["Session Management"],
)
async def list_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of sessions to return"),
    active_only: bool = Query(False, description="Return only active sessions"),
) -> SessionListResponse:
    """
    List all sessions with their metadata.

    Returns session information including:
    - Session ID and activity timestamps
    - Custom agents and scenarios
    - Connection status and turn counts
    - User email and streaming mode if available
    """
    redis_manager = await _get_redis_manager(request)

    try:
        # Scan for session keys
        session_keys = await _scan_session_keys(redis_manager)

        sessions = []
        active_count = 0

        for session_key in session_keys[:limit]:  # Apply limit during processing
            try:
                # Get session data from Redis
                session_data = redis_manager.get_session_data(session_key)

                if not session_data:
                    logger.debug(f"No data found for session key: {session_key}")
                    continue

                # Ensure session_data is a dictionary
                if not isinstance(session_data, dict):
                    logger.warning(f"Unexpected session data format for {session_key}: {type(session_data)}")
                    continue

                # Parse into metadata
                session_metadata = await _parse_session_data(session_key, session_data)

                if session_metadata:
                    # Count active sessions
                    if session_metadata.connection_status == "active":
                        active_count += 1

                    # Apply active filter
                    if active_only and session_metadata.connection_status != "active":
                        continue

                    sessions.append(session_metadata)

            except Exception as e:
                logger.warning(f"Failed to process session {session_key}: {e}")
                continue

        # Sort by last activity (most recent first)
        sessions.sort(key=lambda s: s.last_activity, reverse=True)

        logger.info(f"Retrieved {len(sessions)} sessions (active: {active_count})")

        return SessionListResponse(
            sessions=sessions,
            total_count=len(sessions),
            active_count=active_count,
        )

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sessions: {str(e)}"
        )


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details",
    description="Get detailed information about a specific session.",
    tags=["Session Management"],
)
async def get_session_details(
    request: Request,
    session_id: str,
    include_history: bool = Query(True, description="Include chat history in response"),
    include_memory: bool = Query(True, description="Include memory data in response"),
) -> SessionDetailResponse:
    """
    Get detailed information about a specific session.

    Returns comprehensive session data including:
    - Session metadata and configuration
    - Chat history (if requested)
    - Memory and context data (if requested)
    - Agent and scenario configurations
    """
    redis_manager = await _get_redis_manager(request)

    try:
        # Construct session key
        session_key = f"session:{session_id}"

        # Get session data from Redis
        session_data = redis_manager.get_session_data(session_key)

        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Parse session metadata
        session_metadata = await _parse_session_data(session_key, session_data)

        if not session_metadata:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse session data for {session_id}"
            )

        # Prepare response
        response_data = {
            "session": session_metadata,
            "chat_history": [],
            "memory": {},
            "agent_configs": {},
            "scenario_configs": {},
        }

        # Add chat history if requested
        if include_history and "chat_history" in session_data:
            try:
                chat_history = session_data["chat_history"]
                if isinstance(chat_history, str):
                    chat_history = json.loads(chat_history)

                # Handle agent-specific chat history structure
                if isinstance(chat_history, dict):
                    # Flatten agent-specific history into a single list for the frontend
                    # while preserving agent context in each message
                    flattened_history = []
                    for agent_name, agent_messages in chat_history.items():
                        if isinstance(agent_messages, list):
                            for msg in agent_messages:
                                if isinstance(msg, dict):
                                    # Add agent context to each message
                                    enriched_msg = dict(msg)
                                    enriched_msg["agent"] = agent_name
                                    flattened_history.append(enriched_msg)

                    # Sort by timestamp if available
                    def get_timestamp(msg):
                        return msg.get("timestamp", 0)

                    flattened_history.sort(key=get_timestamp)
                    response_data["chat_history"] = flattened_history

                # Handle simple list format (fallback)
                elif isinstance(chat_history, list):
                    response_data["chat_history"] = chat_history
                else:
                    response_data["chat_history"] = []

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse chat history for {session_id}: {e}")

        # Add memory data if requested
        if include_memory and "corememory" in session_data:
            try:
                memory = session_data["corememory"]
                if isinstance(memory, str):
                    memory = json.loads(memory)
                response_data["memory"] = memory if isinstance(memory, dict) else {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse memory for {session_id}: {e}")

        # Try to fetch agent and scenario configs from their respective endpoints
        try:
            # This would normally call the agent_builder and scenario_builder APIs
            # For now, we'll extract what we can from the core memory
            core_memory = response_data.get("memory", {})

            if "agent_registry" in core_memory:
                response_data["agent_configs"] = core_memory["agent_registry"]

            # Scenario configs would be in a similar structure
            if "scenario_registry" in core_memory:
                response_data["scenario_configs"] = core_memory["scenario_registry"]

        except Exception as e:
            logger.warning(f"Failed to fetch additional configs for {session_id}: {e}")

        logger.info(f"Retrieved detailed session data for {session_id}")

        return SessionDetailResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session details for {session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session details: {str(e)}"
        )


@router.delete(
    "/{session_id}",
    summary="Delete session",
    description="Delete a specific session from Redis cache.",
    tags=["Session Management"],
)
async def delete_session(
    request: Request,
    session_id: str,
) -> Dict[str, Any]:
    """
    Delete a session and all its associated data from Redis.

    This removes:
    - Session data (corememory, chat_history, etc.)
    - Any cached agent configurations
    - Any cached scenario configurations
    """
    redis_manager = await _get_redis_manager(request)

    try:
        # Construct session key
        session_key = f"session:{session_id}"

        # Check if session exists
        exists = redis_manager.redis_client.exists(session_key)

        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Delete the session
        deleted_count = redis_manager.delete_session(session_key)

        logger.info(f"Deleted session {session_id} (deleted {deleted_count} keys)")

        return {
            "status": "success",
            "message": f"Session {session_id} deleted successfully",
            "deleted_keys": deleted_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete session: {str(e)}"
        )