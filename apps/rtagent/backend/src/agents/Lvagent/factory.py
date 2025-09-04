from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # PyYAML
from utils.ml_logging import get_logger

from .base import (
    AzureLiveVoiceAgent,
    LvaAgentBinding,
    LvaModel,
    LvaSessionCfg,
)

logger = get_logger(__name__)

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _resolve_env(value: Any) -> Any:
    """
    Resolve ${ENV_VAR} placeholders recursively in scalar/list/dict values.

    :param value: Arbitrary nested structure with optional ${VAR} strings.
    :return: Value with environment expansions applied.
    """
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            var = match.group(1)
            return os.getenv(var, "")
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


def _load_yaml(path: str | Path) -> Dict[str, Any]:
    """
    Load YAML from a path and resolve ${ENV_VAR} placeholders.

    :param path: File path to YAML.
    :return: Dict representing the YAML contents.
    :raises FileNotFoundError: If file does not exist.
    :raises ValueError: If YAML is empty or invalid.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"YAML not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML at {p} (expected mapping).")
    return _resolve_env(data)  # type: ignore[return-value]


def build_lva_from_yaml(path: str | Path) -> AzureLiveVoiceAgent:
    """
    Build AzureLiveVoiceAgent from YAML configuration file.
    
    This follows the simplified configuration pattern that matches the working
    notebook implementation and your environment file structure.

    :param path: Path to YAML file.
    :return: Initialized AzureLiveVoiceAgent instance.
    :raises ValueError: If required fields are missing.
    """
    cfg = _load_yaml(path)

    # --- model ---
    model_cfg = cfg.get("model") or {}
    deployment_id = model_cfg.get("deployment_id")
    if not deployment_id:
        raise ValueError("model.deployment_id is required.")
    model = LvaModel(deployment_id=str(deployment_id))

    # --- azure_ai_foundry_agent_connected ---
    binding_cfg = cfg.get("azure_ai_foundry_agent_connected") or {}
    agent_id = binding_cfg.get("agent_id")
    if not agent_id:
        raise ValueError("azure_ai_foundry_agent_connected.agent_id is required.")

    project_name = binding_cfg.get("project_name")
    if not project_name:
        raise ValueError("azure_ai_foundry_agent_connected.project_name is required.")
    
    binding = LvaAgentBinding(
        agent_id=str(agent_id),
        project_name=str(project_name),
    )

    # --- session (optional with defaults) ---
    session_cfg = cfg.get("session") or {}
    voice_cfg = session_cfg.get("voice") or {}
    
    # Use simplified session configuration with sensible defaults
    session = LvaSessionCfg(
        voice_name=str(voice_cfg.get("name", "en-US-Ava:DragonHDLatestNeural")),
        voice_temperature=float(voice_cfg.get("temperature", 0.8)),
        vad_threshold=float(session_cfg.get("vad_threshold", 0.5)),
        vad_prefix_ms=int(session_cfg.get("vad_prefix_ms", 300)),
        vad_silence_ms=int(session_cfg.get("vad_silence_ms", 1000)),
    )

    agent = AzureLiveVoiceAgent(
        model=model, 
        binding=binding, 
        session=session
    )
    
    logger.info(
        "Built AzureLiveVoiceAgent | deployment=%s | agent_id=%s | project=%s | voice=%s",
        model.deployment_id,
        binding.agent_id,
        binding.project_name,
        session.voice_name,
    )
    return agent
