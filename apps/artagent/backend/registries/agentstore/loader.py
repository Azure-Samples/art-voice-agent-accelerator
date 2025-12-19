"""
Agent Configuration Loader
==========================

Auto-discovers and loads agents from the modular folder structure.
Integrates with the shared tool registry for tool schemas and executors.

Usage:
    from apps.artagent.backend.registries.agentstore.loader import discover_agents, build_handoff_map

    agents = discover_agents()
    handoffs = build_handoff_map(agents)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
)
from utils.ml_logging import get_logger

logger = get_logger("agents.loader")

# Default path to agents directory
AGENTS_DIR = Path(__file__).parent

# Legacy alias for backward compatibility
AgentConfig = UnifiedAgent


# Legacy alias for backward compatibility
AgentConfig = UnifiedAgent


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_defaults(agents_dir: Path = AGENTS_DIR) -> dict[str, Any]:
    """Load default configuration from _defaults.yaml."""
    defaults_file = agents_dir / "_defaults.yaml"
    if defaults_file.exists():
        with open(defaults_file) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_prompt(agent_dir: Path, prompt_value: str) -> str:
    """
    Load prompt content.

    If prompt_value ends with .jinja, .md, or .txt, load from file.
    Otherwise, treat as inline prompt.
    """
    if not prompt_value:
        return ""

    if prompt_value.endswith((".jinja", ".md", ".txt")):
        prompt_file = agent_dir / prompt_value
        if prompt_file.exists():
            return prompt_file.read_text()
        logger.warning("Prompt file not found: %s", prompt_file)
        return ""
    return prompt_value


def _extract_agent_identity(raw: dict[str, Any], agent_dir: Path) -> dict[str, Any]:
    """Extract agent identity fields from raw YAML, handling nested 'agent:' key."""
    # Support both flat and nested 'agent:' key
    agent_block = raw.get("agent", {})

    return {
        "name": agent_block.get("name") or raw.get("name") or agent_dir.name,
        "description": agent_block.get("description") or raw.get("description", ""),
        "greeting": agent_block.get("greeting") or raw.get("greeting", ""),
        "return_greeting": agent_block.get("return_greeting") or raw.get("return_greeting", ""),
    }


def _extract_prompt(raw: dict[str, Any], agent_dir: Path) -> str:
    """Extract prompt from raw YAML, handling multiple formats."""
    # Check 'prompts:' block first
    prompts_block = raw.get("prompts", {})
    if prompts_block:
        # Check for 'content' (inline prompt)
        if prompts_block.get("content"):
            return prompts_block["content"]
        # Check for 'path' (file reference)
        if prompts_block.get("path"):
            return load_prompt(agent_dir, prompts_block["path"])

    # Check top-level 'prompt:' key
    if raw.get("prompt"):
        return load_prompt(agent_dir, raw["prompt"])

    return ""


def _extract_handoff_config(raw: dict[str, Any]) -> HandoffConfig:
    """Extract handoff configuration from raw YAML."""
    # New-style: handoff: block
    if "handoff" in raw:
        return HandoffConfig.from_dict(raw["handoff"])

    # Legacy: handoff_trigger at top level
    if "handoff_trigger" in raw:
        return HandoffConfig(trigger=raw["handoff_trigger"])

    return HandoffConfig()


def load_agent(
    agent_file: Path,
    defaults: dict[str, Any],
) -> UnifiedAgent:
    """Load a single agent from its agent.yaml file."""
    with open(agent_file) as f:
        raw = yaml.safe_load(f) or {}

    agent_dir = agent_file.parent

    # Extract identity (handles nested 'agent:' block)
    identity = _extract_agent_identity(raw, agent_dir)

    # =========================================================================
    # MODEL CONFIGURATION - Store BOTH mode-specific models
    # =========================================================================
    # Load all model configs:
    #   - model: fallback/default config
    #   - voicelive_model: for VoiceLive/realtime mode
    #   - cascade_model: for Cascade/media mode
    # =========================================================================

    # Load default/fallback model config
    model_raw = _deep_merge(defaults.get("model", {}), raw.get("model", {}))

    # Load mode-specific model configs (if present in YAML)
    voicelive_model_raw = None
    cascade_model_raw = None

    if "voicelive_model" in raw:
        voicelive_model_raw = _deep_merge(defaults.get("model", {}), raw["voicelive_model"])
        logger.debug(
            f"Loaded voicelive_model for agent {identity['name']}: "
            f"deployment_id={raw['voicelive_model'].get('deployment_id')}"
        )

    if "cascade_model" in raw:
        cascade_model_raw = _deep_merge(defaults.get("model", {}), raw["cascade_model"])
        logger.debug(
            f"Loaded cascade_model for agent {identity['name']}: "
            f"deployment_id={raw['cascade_model'].get('deployment_id')}"
        )

    # Merge with defaults for voice, speech, session
    voice_raw = _deep_merge(defaults.get("voice", {}), raw.get("voice", {}))
    speech_raw = _deep_merge(defaults.get("speech", {}), raw.get("speech", {}))
    session_raw = _deep_merge(defaults.get("session", {}), raw.get("session", {}))
    template_vars = _deep_merge(defaults.get("template_vars", {}), raw.get("template_vars", {}))

    # Handle voice inside session block (VoiceLive style)
    if "voice" in session_raw:
        voice_raw = _deep_merge(voice_raw, session_raw.pop("voice"))

    # Load prompt (handles multiple formats)
    prompt_template = _extract_prompt(raw, agent_dir)

    # Extract handoff config
    handoff = _extract_handoff_config(raw)

    return UnifiedAgent(
        name=identity["name"],
        description=identity["description"],
        greeting=identity["greeting"],
        return_greeting=identity["return_greeting"],
        handoff=handoff,
        model=ModelConfig.from_dict(model_raw),
        voicelive_model=ModelConfig.from_dict(voicelive_model_raw) if voicelive_model_raw else None,
        cascade_model=ModelConfig.from_dict(cascade_model_raw) if cascade_model_raw else None,
        voice=VoiceConfig.from_dict(voice_raw),
        speech=SpeechConfig.from_dict(speech_raw),
        session=session_raw,
        prompt_template=prompt_template,
        tool_names=raw.get("tools", []),
        template_vars=template_vars,
        metadata=raw.get("metadata", {}),
        source_dir=agent_dir,
    )


def discover_agents(agents_dir: Path = AGENTS_DIR) -> dict[str, UnifiedAgent]:
    """
    Auto-discover agents by scanning for agent.yaml files.

    Structure:
        agents/
          fraud_agent/agent.yaml  → FraudAgent
          auth_agent/agent.yaml   → AuthAgent
          ...

    Returns:
        Dict of agent_name → UnifiedAgent
    """
    agents: dict[str, UnifiedAgent] = {}

    # Load shared config
    defaults = load_defaults(agents_dir)

    # Scan for agent folders
    for item in agents_dir.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("."):
            continue
        if item.name in ("tools", "store", "__pycache__"):
            continue

        agent_file = item / "agent.yaml"
        if agent_file.exists():
            try:
                config = load_agent(agent_file, defaults)
                agents[config.name] = config
                logger.debug("Loaded agent: %s from %s", config.name, item.name)
            except Exception as e:
                logger.error("Failed to load agent from %s: %s", item, e)

    logger.debug("Discovered %d agents: %s", len(agents), list(agents.keys()))
    return agents


def build_handoff_map(agents: dict[str, UnifiedAgent]) -> dict[str, str]:
    """
    Build handoff map from agent declarations.

    Each agent can declare a `handoff.trigger` which is the tool name
    that other agents use to transfer to this agent.

    Returns:
        Dict of tool_name → agent_name
    """
    handoff_map: dict[str, str] = {}

    for agent in agents.values():
        if agent.handoff.trigger:
            handoff_map[agent.handoff.trigger] = agent.name

    logger.debug("Built handoff map: %s", handoff_map)
    return handoff_map


def build_agent_summaries(agents: dict[str, UnifiedAgent]) -> list[dict[str, Any]]:
    """
    Build lightweight summaries for telemetry/UI without dumping full configs.

    Fields are intentionally small to avoid token bloat when shipped to clients.
    """
    summaries: list[dict[str, Any]] = []
    for name, agent in agents.items():
        tools = list(agent.tool_names or [])
        summaries.append(
            {
                "name": name,
                "description": (agent.description or "")[:160],
                "greeting": bool(agent.greeting),
                "return_greeting": bool(agent.return_greeting),
                "tool_count": len(tools),
                "tools_preview": tools[:5],
                "handoff_trigger": agent.handoff.trigger if agent.handoff else None,
                "model": getattr(agent.model, "deployment_id", None),
                "voice": getattr(agent.voice, "name", None),
            }
        )
    return summaries


def get_agent(name: str, agents_dir: Path = AGENTS_DIR) -> UnifiedAgent | None:
    """Load a single agent by name."""
    agents = discover_agents(agents_dir)
    return agents.get(name)


def list_agent_names(agents_dir: Path = AGENTS_DIR) -> list[str]:
    """List all discovered agent names."""
    agents = discover_agents(agents_dir)
    return list(agents.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def render_prompt(config: UnifiedAgent, context: dict[str, Any]) -> str:
    """
    Render an agent's prompt template with context.

    Args:
        config: Agent configuration
        context: Runtime context (caller_name, customer_intelligence, etc.)

    Returns:
        Rendered prompt string
    """
    return config.render_prompt(context)


__all__ = [
    "UnifiedAgent",
    "AgentConfig",  # Legacy alias
    "HandoffConfig",
    "discover_agents",
    "build_handoff_map",
    "get_agent",
    "list_agent_names",
    "load_defaults",
    "render_prompt",
]
