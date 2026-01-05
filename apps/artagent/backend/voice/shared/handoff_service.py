"""
Handoff Service
===============

Unified handoff resolution for all orchestrators (Cascade and VoiceLive).

This service provides a single source of truth for:
- Detecting handoff tools
- Resolving handoff targets from scenario config or handoff maps
- Getting handoff behavior (discrete/announced, share_context)
- Building consistent system_vars for agent switches
- Selecting appropriate greetings based on handoff mode

Usage:
    from apps.artagent.backend.voice.shared.handoff_service import HandoffService

    # Create service (typically once per session)
    service = HandoffService(
        scenario_name="banking",
        handoff_map={"handoff_fraud": "FraudAgent"},
        agents=agent_registry,
    )

    # Check if tool triggers handoff
    if service.is_handoff("handoff_fraud"):
        # Resolve the handoff
        resolution = service.resolve_handoff(
            tool_name="handoff_fraud",
            tool_args={"reason": "fraud inquiry"},
            source_agent="Concierge",
            current_system_vars={"session_profile": {...}},
            user_last_utterance="I think my card was stolen",
        )

        # Use resolution to switch agents
        await orchestrator.switch_to(
            resolution.target_agent,
            resolution.system_vars,
        )

        # Get greeting if announced handoff
        greeting = service.select_greeting(
            agent=agents[resolution.target_agent],
            is_first_visit=True,
            greet_on_switch=resolution.greet_on_switch,
            system_vars=resolution.system_vars,
        )

See Also:
    - docs/proposals/handoff-consolidation-plan.md
    - apps/artagent/backend/registries/scenariostore/loader.py
    - apps/artagent/backend/voice/handoffs/context.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jinja2 import Template

from apps.artagent.backend.registries.scenariostore.loader import (
    HandoffConfig,
    ScenarioConfig,
    get_handoff_config,
    load_scenario,
)
from apps.artagent.backend.registries.toolstore.registry import (
    is_handoff_tool as registry_is_handoff_tool,
)
from apps.artagent.backend.voice.handoffs.context import build_handoff_system_vars

if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
    from src.stateful.state_managment import MemoManager

try:
    from utils.ml_logging import get_logger

    logger = get_logger("voice.shared.handoff_service")
except ImportError:
    import logging

    logger = logging.getLogger("voice.shared.handoff_service")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class HandoffResolution:
    """
    Result of resolving a handoff tool call.

    Contains all information needed by an orchestrator to execute the
    agent switch consistently, regardless of orchestration mode.

    Attributes:
        success: Whether handoff resolution succeeded
        target_agent: Name of the agent to switch to
        source_agent: Name of the agent initiating the handoff
        tool_name: The handoff tool that triggered this resolution
        system_vars: Pre-built system_vars for agent.apply_session()
        greet_on_switch: Whether target agent should announce the handoff
        share_context: Whether to pass conversation context to target
        handoff_type: "discrete" (silent) or "announced" (greeting)
        error: Error message if success=False

    Example:
        resolution = service.resolve_handoff(...)
        if resolution.success:
            await self._switch_to(resolution.target_agent, resolution.system_vars)
            if resolution.greet_on_switch:
                greeting = service.select_greeting(...)
    """

    success: bool
    target_agent: str = ""
    source_agent: str = ""
    tool_name: str = ""
    system_vars: dict[str, Any] = field(default_factory=dict)
    greet_on_switch: bool = True
    share_context: bool = True
    handoff_type: str = "announced"  # "discrete" or "announced"
    error: str | None = None

    @property
    def is_discrete(self) -> bool:
        """Check if this is a discrete (silent) handoff."""
        return self.handoff_type == "discrete"

    @property
    def is_announced(self) -> bool:
        """Check if this is an announced (greeting) handoff."""
        return self.handoff_type == "announced"


# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


class HandoffService:
    """
    Unified handoff resolution for Cascade and VoiceLive orchestrators.

    This service encapsulates all handoff logic to ensure consistent behavior:
    - Scenario store configs are always respected
    - Greeting selection follows the same rules
    - System vars are built the same way

    The service is stateless and can be shared across turns within a session.
    Session-specific state (like visited_agents) should be passed as arguments.

    Attributes:
        scenario_name: Active scenario (e.g., "banking", "insurance")
        handoff_map: Static tool→agent mapping (fallback if no scenario)
        agents: Registry of available agents

    Example:
        service = HandoffService(
            scenario_name="banking",
            handoff_map=build_handoff_map(agents),
            agents=discover_agents(),
        )
    """

    def __init__(
        self,
        scenario_name: str | None = None,
        handoff_map: dict[str, str] | None = None,
        agents: dict[str, UnifiedAgent] | None = None,
        memo_manager: MemoManager | None = None,
        scenario: ScenarioConfig | None = None,
    ) -> None:
        """
        Initialize HandoffService.

        Args:
            scenario_name: Active scenario name (for config lookup from YAML files)
            handoff_map: Static tool→agent mapping (fallback)
            agents: Registry of available agents
            memo_manager: Optional MemoManager for session state access
            scenario: Optional ScenarioConfig object (for session-scoped scenarios)
                      If provided, this takes precedence over scenario_name lookup.
        """
        self._scenario_name = scenario_name
        self._handoff_map = handoff_map or {}
        self._agents = agents or {}
        self._memo_manager = memo_manager
        self._scenario = scenario  # Direct scenario object for session-scoped scenarios

        logger.debug(
            "HandoffService initialized | scenario=%s agents=%d handoff_tools=%d session_scoped=%s",
            scenario_name or "(none)",
            len(self._agents),
            len(self._handoff_map),
            scenario is not None,
        )

    # ───────────────────────────────────────────────────────────────────────────
    # Properties
    # ───────────────────────────────────────────────────────────────────────────

    @property
    def scenario_name(self) -> str | None:
        """Get the active scenario name."""
        return self._scenario_name

    @property
    def handoff_map(self) -> dict[str, str]:
        """Get the current handoff map (tool→agent)."""
        return self._handoff_map

    def _get_scenario(self) -> ScenarioConfig | None:
        """
        Get the scenario configuration.

        Priority:
        1. Direct scenario object (session-scoped scenarios from Scenario Builder)
        2. Load from YAML file by scenario_name (file-based scenarios)

        Returns:
            ScenarioConfig or None if not found
        """
        # Priority 1: Use direct scenario object if provided
        if self._scenario is not None:
            return self._scenario

        # Priority 2: Load from YAML file
        if self._scenario_name:
            return load_scenario(self._scenario_name)

        return None

    # ───────────────────────────────────────────────────────────────────────────
    # Handoff Detection
    # ───────────────────────────────────────────────────────────────────────────

    def is_handoff(self, tool_name: str) -> bool:
        """
        Check if a tool triggers an agent handoff.

        Uses the centralized tool registry check, which looks at the
        is_handoff flag set during tool registration.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool triggers a handoff
        """
        return registry_is_handoff_tool(tool_name)

    # ───────────────────────────────────────────────────────────────────────────
    # Handoff Resolution
    # ───────────────────────────────────────────────────────────────────────────

    def get_handoff_target(self, tool_name: str) -> str | None:
        """
        Get the target agent for a handoff tool.

        Resolution order:
        1. Handoff map (static or from scenario)
        2. Infer from tool name pattern (e.g., handoff_concierge → Concierge)
        3. Match against scenario edge targets
        4. Returns None if not found

        Args:
            tool_name: The handoff tool name

        Returns:
            Target agent name, or None if not found
        """
        # 1. Check handoff_map first
        if tool_name in self._handoff_map:
            return self._handoff_map[tool_name]

        # 2. Try to infer target from tool name pattern
        target = self._infer_target_from_tool_name(tool_name)
        if target:
            return target

        return None

    def _infer_target_from_tool_name(self, tool_name: str) -> str | None:
        """
        Infer target agent from handoff tool naming convention.

        Handles patterns like:
        - handoff_concierge → Concierge or BankingConcierge
        - handoff_fraud_agent → FraudAgent
        - handoff_investment_advisor → InvestmentAdvisor

        Args:
            tool_name: The handoff tool name

        Returns:
            Inferred agent name if found, None otherwise
        """
        if not tool_name.startswith("handoff_"):
            return None

        # Extract suffix after "handoff_"
        suffix = tool_name[len("handoff_"):]
        if not suffix:
            return None

        # Build possible agent name variations
        # e.g., "concierge" → ["Concierge", "BankingConcierge", "concierge"]
        # e.g., "fraud_agent" → ["FraudAgent", "fraud_agent", "Fraud_Agent"]
        candidates = []

        # CamelCase: fraud_agent → FraudAgent
        camel = "".join(word.capitalize() for word in suffix.split("_"))
        candidates.append(camel)

        # With common prefixes: concierge → BankingConcierge
        candidates.append(f"Banking{camel}")
        candidates.append(f"Insurance{camel}")

        # As-is
        candidates.append(suffix)

        # Title case
        candidates.append(suffix.title().replace("_", ""))

        # Check against available agents
        for candidate in candidates:
            if candidate in self._agents:
                logger.debug(
                    "Inferred handoff target | tool=%s → agent=%s",
                    tool_name,
                    candidate,
                )
                return candidate

        # Check scenario edges if available (supports both file-based and session-scoped)
        scenario = self._get_scenario()
        if scenario:
            for h in scenario.handoffs:
                if h.tool == tool_name:
                    return h.to_agent

        return None

    def get_handoff_config(
        self,
        source_agent: str,
        tool_name: str,
    ) -> HandoffConfig:
        """
        Get handoff configuration for a specific route.

        Looks up the handoff config by (source_agent, tool_name) to find
        the exact route behavior (discrete/announced, share_context).

        Args:
            source_agent: The agent initiating the handoff
            tool_name: The handoff tool being called

        Returns:
            HandoffConfig with type, share_context, greet_on_switch
        """
        return get_handoff_config(
            scenario_name=self._scenario_name,
            from_agent=source_agent,
            tool_name=tool_name,
        )

    def resolve_handoff(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        source_agent: str,
        current_system_vars: dict[str, Any],
        user_last_utterance: str | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> HandoffResolution:
        """
        Resolve a handoff tool call into a complete HandoffResolution.

        This is the main method called by orchestrators when a handoff tool
        is detected. It:
        1. Looks up the target agent (from handoff_map or tool_args for generic)
        2. Gets handoff config from scenario (discrete/announced, share_context)
        3. Builds system_vars using the shared helper
        4. Returns a complete resolution for the orchestrator to execute

        Args:
            tool_name: The handoff tool that was called
            tool_args: Arguments passed to the handoff tool
            source_agent: Name of the agent initiating the handoff
            current_system_vars: Current session's system_vars
            user_last_utterance: User's most recent speech
            tool_result: Result from executing the handoff tool (if any)

        Returns:
            HandoffResolution with all info needed to execute the switch

        Example:
            resolution = service.resolve_handoff(
                tool_name="handoff_fraud",
                tool_args={"reason": "suspicious activity"},
                source_agent="Concierge",
                current_system_vars={"session_profile": {...}},
                user_last_utterance="I think someone stole my card",
            )

            if resolution.success:
                await self._switch_to(resolution.target_agent, resolution.system_vars)
        """
        # Step 1: Get target agent
        # For generic handoff_to_agent, extract target from tool_args/tool_result
        is_generic_handoff = tool_name == "handoff_to_agent"
        target_agent: str | None = None
        handoff_cfg: HandoffConfig | None = None

        if is_generic_handoff:
            # Generic handoff - extract target from args or result
            target_agent = self._resolve_generic_handoff_target(
                tool_args=tool_args,
                tool_result=tool_result,
                source_agent=source_agent,
            )
            if not target_agent:
                return HandoffResolution(
                    success=False,
                    source_agent=source_agent,
                    tool_name=tool_name,
                    error="Generic handoff requires 'target_agent' in tool arguments",
                )

            # Validate generic handoff is allowed for this target
            handoff_cfg = self._get_generic_handoff_config(source_agent, target_agent)
            if not handoff_cfg:
                return HandoffResolution(
                    success=False,
                    source_agent=source_agent,
                    tool_name=tool_name,
                    target_agent=target_agent,
                    error=f"Generic handoff to '{target_agent}' is not allowed in this scenario",
                )
        else:
            # Standard handoff - lookup from handoff_map
            target_agent = self.get_handoff_target(tool_name)
            if not target_agent:
                logger.warning(
                    "Handoff tool '%s' not found in handoff_map | scenario=%s",
                    tool_name,
                    self._scenario_name,
                )
                return HandoffResolution(
                    success=False,
                    source_agent=source_agent,
                    tool_name=tool_name,
                    error=f"No target agent configured for handoff tool: {tool_name}",
                )

        # Validate target agent exists
        if target_agent not in self._agents:
            logger.warning(
                "Handoff target '%s' not in agent registry | tool=%s",
                target_agent,
                tool_name,
            )
            return HandoffResolution(
                success=False,
                source_agent=source_agent,
                tool_name=tool_name,
                target_agent=target_agent,
                error=f"Target agent '{target_agent}' not found in registry",
            )

        # Step 2: Get handoff config from scenario (if not already set for generic)
        if handoff_cfg is None:
            handoff_cfg = self.get_handoff_config(source_agent, tool_name)

        # Step 3: Build system_vars using shared helper
        system_vars = build_handoff_system_vars(
            source_agent=source_agent,
            target_agent=target_agent,
            tool_result=tool_result or {},
            tool_args=tool_args,
            current_system_vars=current_system_vars,
            user_last_utterance=user_last_utterance,
            share_context=handoff_cfg.share_context,
            greet_on_switch=handoff_cfg.greet_on_switch,
        )
        system_vars = self._apply_context_vars(
            system_vars=system_vars,
            current_system_vars=current_system_vars,
            context_vars=handoff_cfg.context_vars,
        )

        logger.info(
            "Handoff resolved | %s → %s | tool=%s type=%s share_context=%s generic=%s",
            source_agent,
            target_agent,
            tool_name,
            handoff_cfg.type,
            handoff_cfg.share_context,
            is_generic_handoff,
        )

        return HandoffResolution(
            success=True,
            target_agent=target_agent,
            source_agent=source_agent,
            tool_name=tool_name,
            system_vars=system_vars,
            greet_on_switch=handoff_cfg.greet_on_switch,
            share_context=handoff_cfg.share_context,
            handoff_type=handoff_cfg.type,
        )

    def _apply_context_vars(
        self,
        *,
        system_vars: dict[str, Any],
        current_system_vars: dict[str, Any],
        context_vars: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge configured context vars into system_vars, rendering templates if needed."""
        if not context_vars or not isinstance(context_vars, dict):
            return system_vars

        render_context = {
            **self._filter_render_context(current_system_vars),
            **self._filter_render_context(system_vars),
        }

        for key, raw_value in context_vars.items():
            if not key:
                continue
            rendered_value = self._render_context_value(raw_value, render_context)
            if "." in key:
                self._set_nested_value(system_vars, key.split("."), rendered_value)
            else:
                system_vars[key] = rendered_value

        return system_vars

    @staticmethod
    def _filter_render_context(context: dict[str, Any]) -> dict[str, Any]:
        """Remove None values so Jinja default filters behave as expected."""
        if not context:
            return {}
        return {k: v for k, v in context.items() if v is not None and v != "None"}

    @staticmethod
    def _render_context_value(value: Any, render_context: dict[str, Any]) -> Any:
        """Render string values as Jinja templates, returning raw value on failure."""
        if not isinstance(value, str):
            return value
        if "{{" not in value:
            return value
        try:
            template = Template(value)
            return template.render(**render_context)
        except Exception:
            return value

    @staticmethod
    def _set_nested_value(target: dict[str, Any], path: list[str], value: Any) -> None:
        """Set a nested value on a dict using a dot-separated path."""
        if not path:
            return
        cursor = target
        for part in path[:-1]:
            if not isinstance(cursor.get(part), dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[path[-1]] = value

    # ───────────────────────────────────────────────────────────────────────────
    # Generic Handoff Helpers
    # ───────────────────────────────────────────────────────────────────────────

    def _resolve_generic_handoff_target(
        self,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any] | None,
        source_agent: str,
    ) -> str | None:
        """
        Extract target agent from generic handoff_to_agent tool call.

        Checks tool_args first, then tool_result for target_agent.

        Args:
            tool_args: Arguments passed to handoff_to_agent
            tool_result: Result from handoff_to_agent execution (if available)
            source_agent: For logging context

        Returns:
            Target agent name, or None if not found
        """
        # Check tool_args first (LLM's direct intent)
        target = tool_args.get("target_agent", "")
        if isinstance(target, str) and target.strip():
            return target.strip()

        # Check tool_result (executor may have resolved/normalized target)
        if tool_result and isinstance(tool_result, dict):
            target = tool_result.get("target_agent", "")
            if isinstance(target, str) and target.strip():
                return target.strip()

        logger.warning(
            "Generic handoff missing target_agent | source=%s args=%s",
            source_agent,
            tool_args,
        )
        return None

    def _get_generic_handoff_config(
        self,
        source_agent: str,
        target_agent: str,
    ) -> HandoffConfig | None:
        """
        Get handoff configuration for a generic handoff_to_agent call.

        Validates that the scenario allows generic handoffs and that
        the target agent is in the allowed list.

        Supports both:
        - Session-scoped scenarios (from Scenario Builder)
        - File-based YAML scenarios

        Args:
            source_agent: Agent initiating the handoff
            target_agent: Target agent from tool args

        Returns:
            HandoffConfig if allowed, None otherwise
        """
        # Get scenario (supports both session-scoped and file-based)
        scenario = self._get_scenario()
        if not scenario:
            logger.debug(
                "Generic handoff denied - no scenario available | target=%s scenario_name=%s session_scoped=%s",
                target_agent,
                self._scenario_name,
                self._scenario is not None,
            )
            return None

        # Get generic handoff config from scenario
        generic_cfg = scenario.get_generic_handoff_config(source_agent, target_agent)
        if not generic_cfg:
            logger.info(
                "Generic handoff denied | scenario=%s source=%s target=%s "
                "enabled=%s allowed_targets=%s edges=%s",
                scenario.name,
                source_agent,
                target_agent,
                scenario.generic_handoff.enabled,
                scenario.generic_handoff.allowed_targets or "(all scenario agents)",
                [f"{h.from_agent}→{h.to_agent}" for h in scenario.handoffs],
            )
            return None

        logger.debug(
            "Generic handoff allowed | %s → %s | type=%s share_context=%s",
            source_agent,
            target_agent,
            generic_cfg.type,
            generic_cfg.share_context,
        )
        return generic_cfg

    # ───────────────────────────────────────────────────────────────────────────
    # Greeting Selection (delegates to GreetingService)
    # ───────────────────────────────────────────────────────────────────────────

    def select_greeting(
        self,
        agent: UnifiedAgent,
        is_first_visit: bool,
        greet_on_switch: bool,
        system_vars: dict[str, Any],
    ) -> str | None:
        """
        Select appropriate greeting for agent activation.

        Delegates to the centralized GreetingService for consistent behavior:
        - Priority 1: Explicit greeting override in system_vars
        - Priority 2: Skip if discrete handoff (greet_on_switch=False)
        - Priority 3: Render agent's greeting/return_greeting template

        Args:
            agent: The agent being activated
            is_first_visit: Whether this is first visit to this agent
            greet_on_switch: Whether handoff mode allows greeting
            system_vars: Context for template rendering

        Returns:
            Rendered greeting string, or None if no greeting needed

        Example:
            greeting = service.select_greeting(
                agent=agents["FraudAgent"],
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            if greeting:
                await agent.trigger_response(conn, say=greeting)
        """
        from apps.artagent.backend.voice.shared.greeting_service import GreetingService

        greeting_service = GreetingService()
        return greeting_service.select_greeting(
            agent=agent,
            context=system_vars,
            is_first_visit=is_first_visit,
            greet_on_switch=greet_on_switch,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def create_handoff_service(
    scenario_name: str | None = None,
    agents: dict[str, UnifiedAgent] | None = None,
    handoff_map: dict[str, str] | None = None,
    memo_manager: MemoManager | None = None,
    scenario: ScenarioConfig | None = None,
) -> HandoffService:
    """
    Factory function to create a HandoffService with proper defaults.

    If no agents or handoff_map provided, attempts to load from the
    agent registry and scenario configuration.

    Args:
        scenario_name: Active scenario name (for YAML file-based lookup)
        agents: Agent registry (will load if not provided)
        handoff_map: Handoff mappings (will build from scenario if not provided)
        memo_manager: Optional MemoManager for session state
        scenario: Optional ScenarioConfig object (for session-scoped scenarios)

    Returns:
        Configured HandoffService instance

    Example:
        # Simple creation with scenario
        service = create_handoff_service(scenario_name="banking")

        # With session-scoped scenario
        service = create_handoff_service(scenario=my_scenario_config)

        # Full control
        service = create_handoff_service(
            scenario_name="banking",
            agents=my_agents,
            handoff_map=my_map,
        )
    """
    # Load agents if not provided
    if agents is None:
        try:
            from apps.artagent.backend.registries.agentstore.loader import discover_agents

            agents = discover_agents()
        except ImportError:
            logger.warning("Could not load agents from registry")
            agents = {}

    # Build handoff map from scenario or agents
    if handoff_map is None:
        if scenario_name:
            try:
                from apps.artagent.backend.registries.scenariostore.loader import (
                    build_handoff_map_from_scenario,
                )

                handoff_map = build_handoff_map_from_scenario(scenario_name)
            except ImportError:
                pass

        # Fallback to building from agents
        if not handoff_map and agents:
            try:
                from apps.artagent.backend.registries.agentstore.loader import build_handoff_map

                handoff_map = build_handoff_map(agents)
            except ImportError:
                pass

        handoff_map = handoff_map or {}

    return HandoffService(
        scenario_name=scenario_name,
        handoff_map=handoff_map,
        agents=agents,
        memo_manager=memo_manager,
        scenario=scenario,
    )


__all__ = [
    "HandoffService",
    "HandoffResolution",
    "create_handoff_service",
]
