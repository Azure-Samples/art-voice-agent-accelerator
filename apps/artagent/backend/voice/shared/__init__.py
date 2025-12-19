"""
Voice Shared Modules
=====================

Shared data classes and configuration utilities for voice channel orchestrators.

Contents:
    - OrchestratorContext: Context passed to orchestrator for each turn
    - OrchestratorResult: Result from an orchestrator turn
    - resolve_orchestrator_config: Scenario-aware configuration resolution
    - resolve_from_app_state: Configuration from FastAPI app.state
    - SessionStateKeys: Standard keys for MemoManager state
    - sync_state_from_memo: Load session state from MemoManager
    - sync_state_to_memo: Persist session state to MemoManager
    - OrchestratorMetrics: Token tracking and TTFT metrics
    - GreetingService: Centralized greeting resolution
    - resolve_start_agent: Unified start agent resolution

Usage:
    from apps.artagent.backend.voice.shared import (
        OrchestratorContext,
        OrchestratorResult,
        resolve_orchestrator_config,
        SessionStateKeys,
        sync_state_from_memo,
        sync_state_to_memo,
        OrchestratorMetrics,
        GreetingService,
        resolve_start_agent,
    )
"""

# Shared dataclasses
from .base import (
    OrchestratorContext,
    OrchestratorResult,
)

# Config resolution
from .config_resolver import (
    DEFAULT_START_AGENT,
    SCENARIO_ENV_VAR,
    OrchestratorConfigResult,
    get_scenario_greeting,
    resolve_from_app_state,
    resolve_orchestrator_config,
)

# Session state sync (shared between orchestrators)
from .session_state import (
    SessionState,
    SessionStateKeys,
    sync_state_from_memo,
    sync_state_to_memo,
)

# Handoff service (unified handoff resolution)
from .handoff_service import (
    HandoffResolution,
    HandoffService,
    create_handoff_service,
)

# Metrics (token tracking, TTFT)
from .metrics import (
    AgentSessionSummary,
    OrchestratorMetrics,
    TTFTMetrics,
)

# Greeting service (centralized greeting resolution)
from .greeting_service import (
    GreetingContext,
    GreetingService,
    build_greeting_context,
    resolve_greeting,
)

# Start agent resolution
from .start_agent_resolver import (
    StartAgentResult,
    StartAgentSource,
    resolve_start_agent,
)

__all__ = [
    # Context/Result (shared data classes)
    "OrchestratorContext",
    "OrchestratorResult",
    # Config Resolution
    "DEFAULT_START_AGENT",
    "SCENARIO_ENV_VAR",
    "OrchestratorConfigResult",
    "resolve_orchestrator_config",
    "resolve_from_app_state",
    "get_scenario_greeting",
    # Session State Sync
    "SessionStateKeys",
    "SessionState",
    "sync_state_from_memo",
    "sync_state_to_memo",
    # Handoff Service
    "HandoffService",
    "HandoffResolution",
    "create_handoff_service",
    # Metrics
    "OrchestratorMetrics",
    "AgentSessionSummary",
    "TTFTMetrics",
    # Greeting Service
    "GreetingService",
    "GreetingContext",
    "resolve_greeting",
    "build_greeting_context",
    # Start Agent Resolution
    "resolve_start_agent",
    "StartAgentResult",
    "StartAgentSource",
]
