"""
Handoff Context for Multi-Agent Voice Applications
===================================================

Provides shared dataclasses and helper functions for agent-to-agent transitions:

- **HandoffContext**: Information passed when switching agents
- **HandoffResult**: Outcome of a handoff operation
- **sanitize_handoff_context**: Removes control flags from handoff context
- **build_handoff_system_vars**: Builds system_vars dict for agent switches

For unified handoff resolution, use HandoffService from voice/shared:

    from apps.artagent.backend.voice.shared import (
        HandoffService,
        HandoffResolution,
        create_handoff_service,
    )

The handoff_map (tool_name → agent_name) is built dynamically from agent
YAML declarations via `build_handoff_map()` in agents/loader.py.

Usage:
    from apps.artagent.backend.voice.handoffs import (
        HandoffContext,
        HandoffResult,
        build_handoff_system_vars,
    )
    from apps.artagent.backend.registries.agentstore.loader import build_handoff_map, discover_agents

    # Build handoff_map from agent declarations
    agents = discover_agents()
    handoff_map = build_handoff_map(agents)

    # Build system_vars for handoff
    ctx = build_handoff_system_vars(
        source_agent="Concierge",
        target_agent="FraudAgent",
        tool_result={"handoff_summary": "fraud inquiry"},
        tool_args={"reason": "user reported fraud"},
        current_system_vars={"session_profile": {...}},
        user_last_utterance="I think my card was stolen",
    )

See Also:
    - docs/proposals/handoff-consolidation-plan.md for consolidation plan
    - docs/architecture/handoff-inventory.md for handoff architecture
    - apps/artagent/backend/registries/agentstore/loader.py for build_handoff_map()
"""

from __future__ import annotations

# Context, result dataclasses, and helper functions
from .context import (
    HandoffContext,
    HandoffResult,
    build_handoff_system_vars,
    sanitize_handoff_context,
)

# Note: HandoffResolution is available from voice.shared.handoff_service
# We don't re-export it here to avoid circular imports

__all__ = [
    # Dataclasses
    "HandoffContext",
    "HandoffResult",
    # Helper functions
    "build_handoff_system_vars",
    "sanitize_handoff_context",
]
