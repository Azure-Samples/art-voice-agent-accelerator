"""
Session-Level Agent Configuration Manager
==========================================

Manages agent configurations at the session level, enabling dynamic runtime
modification of agent capabilities without service restarts.

This module provides:
- Per-session agent overrides (prompt, voice, model, tools)
- Runtime hot-swap of agent configurations
- Integration with MemoManager for persistence
- Experiment/sandbox tracking for A/B testing

Usage:
    from apps.artagent.backend.registries.agentstore.session_manager import SessionAgentManager

    # Create manager for session
    session_mgr = SessionAgentManager(
        session_id="session_123",
        base_agents=discover_agents(),
        memo_manager=memo,
    )

    # Get agent with overrides applied
    agent = session_mgr.get_agent("EricaConcierge")

    # Modify agent at runtime
    session_mgr.update_agent_prompt("EricaConcierge", "New prompt...")
    await session_mgr.persist()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from apps.artagent.backend.registries.agentstore.base import (
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
    build_handoff_map,
)
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from src.redis.manager import AzureRedisManager
    from src.stateful.state_managment import MemoManager

logger = get_logger("agents.session_manager")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SessionAgentConfig:
    """
    Per-session agent configuration with override tracking.

    Stores session-specific overrides for an agent. When resolving an agent,
    overrides are merged with the base agent configuration.

    Attributes:
        base_agent_name: Name of the base agent this config extends
        prompt_override: Session-specific prompt template (replaces base)
        voice_override: Session-specific voice configuration
        model_override: Session-specific model configuration
        tool_names_override: Session-specific tool list (replaces base)
        template_vars_override: Additional template variables (merged with base)
        greeting_override: Session-specific greeting message
        created_at: Timestamp when config was created
        modified_at: Timestamp of last modification
        modification_count: Number of times config has been modified
        source: Origin of the configuration (base, session, api, admin)
    """

    base_agent_name: str
    prompt_override: str | None = None
    voice_override: VoiceConfig | None = None
    model_override: ModelConfig | None = None
    tool_names_override: list[str] | None = None
    template_vars_override: dict[str, Any] | None = None
    greeting_override: str | None = None
    created_at: float = field(default_factory=time.time)
    modified_at: float | None = None
    modification_count: int = 0
    source: Literal["base", "session", "api", "admin", "websocket"] = "base"

    def has_overrides(self) -> bool:
        """Check if any overrides are set."""
        return any(
            [
                self.prompt_override is not None,
                self.voice_override is not None,
                self.model_override is not None,
                self.tool_names_override is not None,
                self.template_vars_override is not None,
                self.greeting_override is not None,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for Redis storage."""
        result = {
            "base_agent_name": self.base_agent_name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "modification_count": self.modification_count,
            "source": self.source,
        }

        if self.prompt_override is not None:
            result["prompt_override"] = self.prompt_override
        if self.voice_override is not None:
            result["voice_override"] = self.voice_override.to_dict()
        if self.model_override is not None:
            result["model_override"] = self.model_override.to_dict()
        if self.tool_names_override is not None:
            result["tool_names_override"] = self.tool_names_override
        if self.template_vars_override is not None:
            result["template_vars_override"] = self.template_vars_override
        if self.greeting_override is not None:
            result["greeting_override"] = self.greeting_override

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionAgentConfig:
        """Deserialize from dictionary."""
        voice = None
        if "voice_override" in data:
            voice = VoiceConfig.from_dict(data["voice_override"])

        model = None
        if "model_override" in data:
            model = ModelConfig.from_dict(data["model_override"])

        return cls(
            base_agent_name=data["base_agent_name"],
            prompt_override=data.get("prompt_override"),
            voice_override=voice,
            model_override=model,
            tool_names_override=data.get("tool_names_override"),
            template_vars_override=data.get("template_vars_override"),
            greeting_override=data.get("greeting_override"),
            created_at=data.get("created_at", time.time()),
            modified_at=data.get("modified_at"),
            modification_count=data.get("modification_count", 0),
            source=data.get("source", "base"),
        )


@dataclass
class SessionAgentRegistry:
    """
    Complete agent registry for a session.

    Contains all agent configurations and handoff mappings for a session,
    along with experiment tracking metadata.

    Attributes:
        session_id: Unique session identifier
        agents: Map of agent_name → SessionAgentConfig
        handoff_map: Map of tool_name → target_agent_name
        active_agent: Currently active agent name
        experiment_id: Optional experiment identifier for A/B testing
        variant: Optional variant name within experiment
        created_at: Timestamp when registry was created
    """

    session_id: str
    agents: dict[str, SessionAgentConfig] = field(default_factory=dict)
    handoff_map: dict[str, str] = field(default_factory=dict)
    active_agent: str | None = None
    experiment_id: str | None = None
    variant: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for Redis storage."""
        return {
            "session_id": self.session_id,
            "agents": {name: config.to_dict() for name, config in self.agents.items()},
            "handoff_map": self.handoff_map,
            "active_agent": self.active_agent,
            "experiment_id": self.experiment_id,
            "variant": self.variant,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionAgentRegistry:
        """Deserialize from dictionary."""
        agents = {}
        for name, config_data in data.get("agents", {}).items():
            agents[name] = SessionAgentConfig.from_dict(config_data)

        return cls(
            session_id=data["session_id"],
            agents=agents,
            handoff_map=data.get("handoff_map", {}),
            active_agent=data.get("active_agent"),
            experiment_id=data.get("experiment_id"),
            variant=data.get("variant"),
            created_at=data.get("created_at", time.time()),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PROTOCOLS
# ═══════════════════════════════════════════════════════════════════════════════


class AgentProvider(Protocol):
    """Protocol for session-aware agent resolution."""

    def get_agent(self, name: str) -> UnifiedAgent:
        """Get agent configuration with session overrides applied."""
        ...

    @property
    def active_agent(self) -> str | None:
        """Get currently active agent name."""
        ...

    def set_active_agent(self, name: str) -> None:
        """Set the currently active agent."""
        ...

    def list_agents(self) -> list[str]:
        """List all available agent names."""
        ...


class HandoffProvider(Protocol):
    """Protocol for session-aware handoff resolution."""

    def get_handoff_target(self, tool_name: str) -> str | None:
        """Get target agent for a handoff tool."""
        ...

    @property
    def handoff_map(self) -> dict[str, str]:
        """Get current handoff mappings."""
        ...

    def is_handoff_tool(self, tool_name: str) -> bool:
        """Check if a tool triggers a handoff."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION AGENT MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class SessionAgentManager:
    """
    Manages agent configurations at the session level.

    Provides session-scoped agent configuration storage with:
    - Override inheritance from base agents
    - Runtime modification capabilities
    - Redis persistence integration via MemoManager
    - Experiment tracking for A/B testing

    The manager implements both AgentProvider and HandoffProvider protocols,
    allowing it to be used as a drop-in replacement for static agent dicts
    in orchestrators.

    Example:
        # Create manager
        mgr = SessionAgentManager(
            session_id="session_123",
            base_agents=discover_agents(),
            memo_manager=memo,
        )

        # Get agent with overrides
        agent = mgr.get_agent("EricaConcierge")

        # Modify at runtime
        mgr.update_agent_prompt("EricaConcierge", "New prompt...")
        await mgr.persist()
    """

    _AGENT_REGISTRY_KEY = "agent_registry"

    def __init__(
        self,
        session_id: str,
        base_agents: dict[str, UnifiedAgent],
        memo_manager: MemoManager | None = None,
        *,
        redis_mgr: AzureRedisManager | None = None,
        auto_persist: bool = True,
    ) -> None:
        """
        Initialize SessionAgentManager.

        Args:
            session_id: Unique session identifier
            base_agents: Base agent configurations (immutable reference)
            memo_manager: MemoManager for session state storage
            redis_mgr: Optional Redis manager for persistence
            auto_persist: If True, automatically persist changes to MemoManager
        """
        self.session_id = session_id
        self._base_agents = base_agents
        self._memo = memo_manager
        self._redis = redis_mgr
        self._auto_persist = auto_persist
        self._custom_agents: dict[str, UnifiedAgent] = {}  # Custom agents created at runtime
        self._registry: SessionAgentRegistry = self._init_registry()

        logger.info(
            "SessionAgentManager initialized | session=%s agents=%d",
            session_id,
            len(base_agents),
        )

    def _init_registry(self) -> SessionAgentRegistry:
        """Initialize registry from base agents or load from session."""
        # Check if session already has registry in memo
        if self._memo:
            existing = self._memo.get_context(self._AGENT_REGISTRY_KEY)
            if existing and isinstance(existing, dict):
                try:
                    registry = SessionAgentRegistry.from_dict(existing)
                    logger.debug(
                        "Loaded existing registry | session=%s agents=%d",
                        self.session_id,
                        len(registry.agents),
                    )
                    return registry
                except Exception as e:
                    logger.warning(
                        "Failed to load existing registry, creating new | error=%s",
                        e,
                    )

        # Create fresh registry from base agents
        registry = SessionAgentRegistry(
            session_id=self.session_id,
            agents={name: SessionAgentConfig(base_agent_name=name) for name in self._base_agents},
            handoff_map=build_handoff_map(self._base_agents),
        )

        logger.debug(
            "Created new registry | session=%s agents=%d handoffs=%d",
            self.session_id,
            len(registry.agents),
            len(registry.handoff_map),
        )

        return registry

    # ─────────────────────────────────────────────────────────────────────────
    # Agent Resolution (AgentProvider Protocol)
    # ─────────────────────────────────────────────────────────────────────────

    def get_agent(self, name: str) -> UnifiedAgent:
        """
        Get agent with session overrides applied.

        Returns a new UnifiedAgent instance with:
        - Base agent properties (or custom agent if dynamically created)
        - Session-specific overrides merged in

        Args:
            name: Agent name to retrieve

        Returns:
            UnifiedAgent with overrides applied

        Raises:
            ValueError: If agent name is unknown
        """
        # Check custom agents first (dynamically created)
        if name in self._custom_agents:
            return self._custom_agents[name]
        
        # Then check base agents (from YAML)
        base = self._base_agents.get(name)
        if not base:
            raise ValueError(f"Unknown agent: {name}")

        config = self._registry.agents.get(name)
        if not config or not config.has_overrides():
            return base  # No overrides, return base agent

        return self._apply_overrides(base, config)

    def _apply_overrides(
        self,
        base: UnifiedAgent,
        config: SessionAgentConfig,
    ) -> UnifiedAgent:
        """Create new agent with session overrides applied."""
        return UnifiedAgent(
            name=base.name,
            description=base.description,
            greeting=config.greeting_override or base.greeting,
            return_greeting=base.return_greeting,
            handoff=base.handoff,
            model=config.model_override or base.model,
            voice=config.voice_override or base.voice,
            session=base.session,
            prompt_template=config.prompt_override or base.prompt_template,
            tool_names=(
                config.tool_names_override
                if config.tool_names_override is not None
                else base.tool_names
            ),
            template_vars={
                **base.template_vars,
                **(config.template_vars_override or {}),
            },
            metadata={
                **base.metadata,
                "_session_override": True,
                "_override_source": config.source,
                "_modification_count": config.modification_count,
            },
            source_dir=base.source_dir,
        )

    @property
    def active_agent(self) -> str | None:
        """Get currently active agent name."""
        return self._registry.active_agent

    def set_active_agent(self, name: str) -> None:
        """Set the currently active agent."""
        if name not in self._base_agents and name not in self._custom_agents:
            raise ValueError(f"Unknown agent: {name}")
        self._registry.active_agent = name
        self._mark_dirty()
        logger.debug("Active agent set | session=%s agent=%s", self.session_id, name)

    def list_agents(self) -> list[str]:
        """List all available agent names (base + custom)."""
        all_agents = set(self._base_agents.keys())
        all_agents.update(self._custom_agents.keys())
        return list(all_agents)

    def get_base_agent(self, name: str) -> UnifiedAgent | None:
        """Get base agent without overrides (for comparison)."""
        return self._base_agents.get(name)

    # ─────────────────────────────────────────────────────────────────────────
    # Handoff Resolution (HandoffProvider Protocol)
    # ─────────────────────────────────────────────────────────────────────────

    def get_handoff_target(self, tool_name: str) -> str | None:
        """Get the target agent for a handoff tool."""
        return self._registry.handoff_map.get(tool_name)

    @property
    def handoff_map(self) -> dict[str, str]:
        """Get the current handoff map (copy)."""
        return self._registry.handoff_map.copy()

    def is_handoff_tool(self, tool_name: str) -> bool:
        """Check if a tool name triggers a handoff."""
        return tool_name in self._registry.handoff_map

    def update_handoff_map(self, tool_name: str, target_agent: str) -> None:
        """
        Add or update a handoff mapping.

        Args:
            tool_name: Name of the handoff tool
            target_agent: Target agent name

        Raises:
            ValueError: If target agent is unknown
        """
        if target_agent not in self._base_agents:
            raise ValueError(f"Unknown target agent: {target_agent}")
        self._registry.handoff_map[tool_name] = target_agent
        self._mark_dirty()
        logger.debug(
            "Handoff map updated | session=%s tool=%s target=%s",
            self.session_id,
            tool_name,
            target_agent,
        )

    def remove_handoff(self, tool_name: str) -> bool:
        """
        Remove a handoff mapping.

        Args:
            tool_name: Name of the handoff tool to remove

        Returns:
            True if removed, False if not found
        """
        if tool_name in self._registry.handoff_map:
            del self._registry.handoff_map[tool_name]
            self._mark_dirty()
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Runtime Modification API
    # ─────────────────────────────────────────────────────────────────────────

    def update_agent_prompt(
        self,
        agent_name: str,
        prompt: str,
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's prompt for this session.

        Args:
            agent_name: Name of the agent to modify
            prompt: New prompt template
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        config.prompt_override = prompt
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.info(
            "Agent prompt updated | session=%s agent=%s source=%s len=%d",
            self.session_id,
            agent_name,
            source,
            len(prompt),
        )

    def update_agent_voice(
        self,
        agent_name: str,
        voice: VoiceConfig,
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's voice configuration.

        Args:
            agent_name: Name of the agent to modify
            voice: New voice configuration
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        config.voice_override = voice
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.info(
            "Agent voice updated | session=%s agent=%s voice=%s source=%s",
            self.session_id,
            agent_name,
            voice.name,
            source,
        )

    def update_agent_model(
        self,
        agent_name: str,
        model: ModelConfig,
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's model configuration.

        Args:
            agent_name: Name of the agent to modify
            model: New model configuration
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        config.model_override = model
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.info(
            "Agent model updated | session=%s agent=%s model=%s source=%s",
            self.session_id,
            agent_name,
            model.name,
            source,
        )

    def update_agent_tools(
        self,
        agent_name: str,
        tool_names: list[str],
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's available tools.

        Args:
            agent_name: Name of the agent to modify
            tool_names: New list of tool names
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        config.tool_names_override = tool_names
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.info(
            "Agent tools updated | session=%s agent=%s tools=%s source=%s",
            self.session_id,
            agent_name,
            tool_names,
            source,
        )

    def update_agent_greeting(
        self,
        agent_name: str,
        greeting: str,
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's greeting message.

        Args:
            agent_name: Name of the agent to modify
            greeting: New greeting message
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        config.greeting_override = greeting
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.info(
            "Agent greeting updated | session=%s agent=%s source=%s",
            self.session_id,
            agent_name,
            source,
        )

    def update_agent_template_vars(
        self,
        agent_name: str,
        template_vars: dict[str, Any],
        *,
        merge: bool = True,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Update an agent's template variables.

        Args:
            agent_name: Name of the agent to modify
            template_vars: Template variables to set
            merge: If True, merge with existing; if False, replace
            source: Origin of the modification
        """
        config = self._ensure_config(agent_name)
        if merge and config.template_vars_override:
            config.template_vars_override = {
                **config.template_vars_override,
                **template_vars,
            }
        else:
            config.template_vars_override = template_vars
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
        logger.debug(
            "Agent template vars updated | session=%s agent=%s vars=%s",
            self.session_id,
            agent_name,
            list(template_vars.keys()),
        )

    def reset_agent(self, agent_name: str) -> None:
        """
        Reset agent to base configuration (remove all overrides).

        Args:
            agent_name: Name of the agent to reset
        """
        if agent_name in self._registry.agents:
            self._registry.agents[agent_name] = SessionAgentConfig(base_agent_name=agent_name)
            self._mark_dirty()
            logger.info(
                "Agent reset to base | session=%s agent=%s",
                self.session_id,
                agent_name,
            )

    def reset_all_agents(self) -> None:
        """Reset all agents to base configuration."""
        old_active = self._registry.active_agent
        old_experiment = self._registry.experiment_id
        old_variant = self._registry.variant

        self._registry = SessionAgentRegistry(
            session_id=self.session_id,
            agents={name: SessionAgentConfig(base_agent_name=name) for name in self._base_agents},
            handoff_map=build_handoff_map(self._base_agents),
            active_agent=old_active,
            experiment_id=old_experiment,
            variant=old_variant,
        )
        # Keep custom agents
        for name, agent in self._custom_agents.items():
            self._registry.agents[name] = SessionAgentConfig(base_agent_name=name)
        self._mark_dirty()
        logger.info("All agents reset to base | session=%s", self.session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Custom Agent Registration
    # ─────────────────────────────────────────────────────────────────────────

    def register_custom_agent(
        self,
        agent: UnifiedAgent,
        *,
        source: Literal["session", "api", "admin", "websocket"] = "api",
    ) -> None:
        """
        Register a custom agent created at runtime (not from YAML).

        This adds an entirely new agent to the session, not an override
        of an existing base agent. The agent is stored separately from
        base agents and can be listed, retrieved, and modified.

        Args:
            agent: The UnifiedAgent to register
            source: Origin of the agent creation
        """
        name = agent.name
        
        # Store in custom agents dict
        self._custom_agents[name] = agent
        
        # Create a session config for tracking
        config = SessionAgentConfig(
            base_agent_name=name,
            created_at=time.time(),
            source=source,
        )
        self._registry.agents[name] = config
        
        # Register handoff if configured
        if agent.handoff and agent.handoff.trigger:
            self._registry.handoff_map[agent.handoff.trigger] = name
        
        self._mark_dirty()
        logger.info(
            "Custom agent registered | session=%s agent=%s tools=%d source=%s",
            self.session_id,
            name,
            len(agent.tool_names) if agent.tool_names else 0,
            source,
        )

    def unregister_custom_agent(self, agent_name: str) -> bool:
        """
        Remove a custom agent from the session.

        Args:
            agent_name: Name of the custom agent to remove

        Returns:
            True if removed, False if not found
        """
        if agent_name not in self._custom_agents:
            return False
        
        agent = self._custom_agents.pop(agent_name)
        
        # Remove from registry
        if agent_name in self._registry.agents:
            del self._registry.agents[agent_name]
        
        # Remove handoff mapping
        if agent.handoff and agent.handoff.trigger:
            self._registry.handoff_map.pop(agent.handoff.trigger, None)
        
        self._mark_dirty()
        logger.info(
            "Custom agent unregistered | session=%s agent=%s",
            self.session_id,
            agent_name,
        )
        return True

    def list_custom_agents(self) -> dict[str, UnifiedAgent]:
        """
        Get all custom agents registered in this session.

        Returns:
            Dict of agent_name → UnifiedAgent for custom agents only
        """
        return dict(self._custom_agents)

    def is_custom_agent(self, agent_name: str) -> bool:
        """Check if an agent is a custom (dynamically created) agent."""
        return agent_name in self._custom_agents

    # ─────────────────────────────────────────────────────────────────────────
    # Experiment Support
    # ─────────────────────────────────────────────────────────────────────────

    def set_experiment(self, experiment_id: str, variant: str) -> None:
        """
        Tag session with experiment metadata.

        Args:
            experiment_id: Unique experiment identifier
            variant: Variant name within the experiment
        """
        self._registry.experiment_id = experiment_id
        self._registry.variant = variant
        self._mark_dirty()
        logger.info(
            "Experiment set | session=%s experiment=%s variant=%s",
            self.session_id,
            experiment_id,
            variant,
        )

    def clear_experiment(self) -> None:
        """Clear experiment metadata from session."""
        self._registry.experiment_id = None
        self._registry.variant = None
        self._mark_dirty()

    @property
    def experiment_id(self) -> str | None:
        """Get current experiment ID."""
        return self._registry.experiment_id

    @property
    def variant(self) -> str | None:
        """Get current variant."""
        return self._registry.variant

    # ─────────────────────────────────────────────────────────────────────────
    # Audit & Introspection
    # ─────────────────────────────────────────────────────────────────────────

    def get_audit_log(self) -> dict[str, Any]:
        """
        Get modification history for audit purposes.

        Returns:
            Dict containing session metadata and per-agent modification info
        """
        return {
            "session_id": self.session_id,
            "experiment_id": self._registry.experiment_id,
            "variant": self._registry.variant,
            "active_agent": self._registry.active_agent,
            "created_at": self._registry.created_at,
            "agents": {
                name: {
                    "modification_count": config.modification_count,
                    "modified_at": config.modified_at,
                    "source": config.source,
                    "has_prompt_override": config.prompt_override is not None,
                    "has_voice_override": config.voice_override is not None,
                    "has_model_override": config.model_override is not None,
                    "has_tools_override": config.tool_names_override is not None,
                    "has_greeting_override": config.greeting_override is not None,
                }
                for name, config in self._registry.agents.items()
                if config.modification_count > 0
            },
            "handoff_map": self._registry.handoff_map,
        }

    def get_agent_overrides(self, agent_name: str) -> dict[str, Any]:
        """
        Get current overrides for a specific agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Dict of override field → value (only non-None overrides)
        """
        config = self._registry.agents.get(agent_name)
        if not config:
            return {}

        overrides = {}
        if config.prompt_override is not None:
            overrides["prompt"] = config.prompt_override
        if config.voice_override is not None:
            overrides["voice"] = config.voice_override.to_dict()
        if config.model_override is not None:
            overrides["model"] = config.model_override.to_dict()
        if config.tool_names_override is not None:
            overrides["tools"] = config.tool_names_override
        if config.template_vars_override is not None:
            overrides["template_vars"] = config.template_vars_override
        if config.greeting_override is not None:
            overrides["greeting"] = config.greeting_override

        return overrides

    def has_overrides(self, agent_name: str) -> bool:
        """Check if an agent has any session overrides."""
        config = self._registry.agents.get(agent_name)
        return config.has_overrides() if config else False

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_config(self, agent_name: str) -> SessionAgentConfig:
        """Ensure agent has a config entry, creating if needed."""
        if agent_name not in self._base_agents and agent_name not in self._custom_agents:
            raise ValueError(f"Unknown agent: {agent_name}")

        if agent_name not in self._registry.agents:
            self._registry.agents[agent_name] = SessionAgentConfig(base_agent_name=agent_name)
        return self._registry.agents[agent_name]

    def _mark_dirty(self) -> None:
        """Mark registry as needing persistence."""
        if self._memo and self._auto_persist:
            self._memo.set_context(
                self._AGENT_REGISTRY_KEY,
                self._registry.to_dict(),
            )

    async def persist(self) -> None:
        """Persist registry to Redis via MemoManager."""
        if self._memo:
            self._memo.set_context(
                self._AGENT_REGISTRY_KEY,
                self._registry.to_dict(),
            )
            if self._redis:
                await self._memo.persist_to_redis_async(self._redis)
                logger.debug("Registry persisted to Redis | session=%s", self.session_id)

    async def persist_background(self) -> None:
        """Non-blocking persist for hot path operations."""
        if self._memo and self._redis:
            import asyncio

            asyncio.create_task(
                self._memo.persist_background(self._redis),
                name=f"persist_agent_registry_{self.session_id}",
            )

    async def reload(self) -> None:
        """Reload registry from Redis via MemoManager."""
        if self._memo and self._redis:
            await self._memo.refresh_from_redis_async(self._redis)
            existing = self._memo.get_context(self._AGENT_REGISTRY_KEY)
            if existing and isinstance(existing, dict):
                try:
                    self._registry = SessionAgentRegistry.from_dict(existing)
                    logger.debug(
                        "Registry reloaded from Redis | session=%s",
                        self.session_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to reload registry from Redis | error=%s",
                        e,
                    )

    def to_dict(self) -> dict[str, Any]:
        """Export registry as dictionary."""
        return self._registry.to_dict()

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        base_agents: dict[str, UnifiedAgent],
        memo_manager: MemoManager | None = None,
        **kwargs,
    ) -> SessionAgentManager:
        """
        Create manager from serialized data.

        Args:
            data: Serialized registry data
            base_agents: Base agent configurations
            memo_manager: Optional MemoManager
            **kwargs: Additional arguments for constructor

        Returns:
            SessionAgentManager with restored state
        """
        registry = SessionAgentRegistry.from_dict(data)
        manager = cls(
            session_id=registry.session_id,
            base_agents=base_agents,
            memo_manager=memo_manager,
            **kwargs,
        )
        manager._registry = registry
        return manager


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_session_agent_manager(
    session_id: str,
    memo_manager: MemoManager,
    *,
    agents_dir: str | None = None,
    redis_mgr: AzureRedisManager | None = None,
) -> SessionAgentManager:
    """
    Factory function to create a SessionAgentManager with auto-discovery.

    Args:
        session_id: Unique session identifier
        memo_manager: MemoManager for session state
        agents_dir: Optional path to agents directory
        redis_mgr: Optional Redis manager

    Returns:
        Configured SessionAgentManager
    """
    from pathlib import Path

    from apps.artagent.backend.registries.agentstore.loader import AGENTS_DIR, discover_agents

    agents_path = Path(agents_dir) if agents_dir else AGENTS_DIR
    base_agents = discover_agents(agents_path)

    return SessionAgentManager(
        session_id=session_id,
        base_agents=base_agents,
        memo_manager=memo_manager,
        redis_mgr=redis_mgr,
    )


__all__ = [
    "SessionAgentConfig",
    "SessionAgentRegistry",
    "SessionAgentManager",
    "AgentProvider",
    "HandoffProvider",
    "create_session_agent_manager",
]
