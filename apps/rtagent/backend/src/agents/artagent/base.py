from __future__ import annotations

"""
rt_agent.py – YAML-driven agents with per-agent memory, model params, tools, and
a configurable *prompt template path*, with context-aware slot + tool output sharing.
"""

from pathlib import Path
from textwrap import shorten
from typing import Any, Dict, Optional

import yaml
from fastapi import WebSocket

from apps.rtagent.backend.src.agents.artagent.prompt_store.prompt_manager import PromptManager
from apps.rtagent.backend.src.agents.artagent.tool_store import tool_registry as tool_store
from apps.rtagent.backend.src.orchestration.artagent.gpt_flow import process_gpt_response
from utils.ml_logging import get_logger

logger = get_logger("rt_agent")


class ARTAgent:
    CONFIG_PATH: str | Path = "agent.yaml"

    def __init__(
        self,
        *,
        config_path: Optional[str | Path] = None,
        template_dir: str = "templates",
    ) -> None:
        """
        Initialize YAML-driven agent with configuration and prompt templates.

        :param config_path: Path to agent configuration YAML file
        :type config_path: Optional[str | Path]
        :param template_dir: Directory containing prompt templates
        :type template_dir: str
        :raises Exception: When YAML config loading fails
        :raises ValueError: When required configuration is missing
        :raises TypeError: When tool configuration is invalid
        """
        cfg_path = Path(config_path or self.CONFIG_PATH).expanduser().resolve()
        try:
            self._cfg = self._load_yaml(cfg_path)
        except Exception:
            logger.exception("Error loading YAML config: %s", cfg_path)
            raise
        self._validate_cfg()

        self.name: str = self._cfg["agent"]["name"]
        self.creator: str = self._cfg["agent"].get("creator", "Unknown")
        self.organization: str = self._cfg["agent"].get("organization", "")
        self.description: str = self._cfg["agent"].get("description", "")

        m = self._cfg["model"]
        self.model_id: str = m["deployment_id"]
        self.temperature: float = float(m.get("temperature", 0.7))
        self.top_p: float = float(m.get("top_p", 1.0))
        self.max_tokens: int = int(m.get("max_tokens", 4096))

        # Voice configuration (optional)
        voice_cfg = self._cfg.get("voice", {})
        self.voice_name: Optional[str] = voice_cfg.get("name")
        self.voice_style: str = voice_cfg.get("style", "chat")
        self.voice_rate: str = voice_cfg.get("rate", "+3%")

        self.prompt_path: str = self._cfg.get("prompts", {}).get(
            "path", "voice_agent_authentication.jinja"
        )
        logger.debug("Agent '%s' prompt template: %s", self.name, self.prompt_path)

        self.tools: list[dict[str, Any]] = []
        for entry in self._cfg.get("tools", []):
            if isinstance(entry, str):
                if entry not in tool_store.TOOL_REGISTRY:
                    raise ValueError(
                        f"Unknown tool name '{entry}' in YAML for {self.name}"
                    )
                self.tools.append(tool_store.TOOL_REGISTRY[entry])
            elif isinstance(entry, dict):
                self.tools.append(entry)
            else:
                raise TypeError("Each tools entry must be a str or dict")

        self.pm: PromptManager = PromptManager(template_dir=template_dir)
        self._log_loaded_summary()

    async def respond(
        self,
        cm,
        user_prompt: str,
        ws: WebSocket,
        *,
        is_acs: bool = False,
        **prompt_kwargs,
    ) -> Any:
        """
        Generate agent response using GPT with context-aware prompting.

        :param cm: Conversation memory manager
        :param user_prompt: User input text
        :type user_prompt: str
        :param ws: WebSocket connection for communication
        :type ws: WebSocket
        :param is_acs: Whether this is an ACS call context
        :type is_acs: bool
        :param prompt_kwargs: Additional template variables for prompt rendering
        :return: GPT response processing result
        :rtype: Any
        """
        # For context-rich prompting
        system_prompt = self.pm.get_prompt(self.prompt_path, **prompt_kwargs)
        cm.ensure_system_prompt(
            self.name,
            system_prompt=system_prompt,
        )

        result = await process_gpt_response(
            cm,
            user_prompt,
            ws,
            agent_name=self.name,
            is_acs=is_acs,
            model_id=self.model_id,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            available_tools=self.tools,
            session_id=cm.session_id,  # Pass session_id for AOAI client pooling
        )

        return result

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        """
        Load YAML configuration from file path.

        :param path: Path to YAML configuration file
        :type path: Path
        :return: Parsed YAML configuration dictionary
        :rtype: Dict[str, Any]
        """
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _validate_cfg(self) -> None:
        """
        Validate required configuration sections and keys.

        :raises ValueError: When required configuration is missing
        """
        required = [("agent", ["name"]), ("model", ["deployment_id"])]
        for section, keys in required:
            if section not in self._cfg:
                raise ValueError(f"Missing '{section}' section in YAML config.")
            for key in keys:
                if key not in self._cfg[section]:
                    raise ValueError(f"Missing '{section}.{key}' in YAML config.")
        if "prompts" in self._cfg and "path" not in self._cfg["prompts"]:
            raise ValueError("If 'prompts' is declared, it must include 'path'")

    def _log_loaded_summary(self) -> None:
        """
        Log summary of loaded agent configuration for debugging.
        """
        desc_preview = shorten(self.description, width=60, placeholder="…")
        tool_names = [t["function"]["name"] for t in self.tools]
        voice_info = (
            f"voice={self.voice_name or 'default'}"
            + (f"/{self.voice_style}" if self.voice_name else "")
            + (f"@{self.voice_rate}" if hasattr(self, "voice_rate") else "")
        )
        logger.info(
            "Loaded agent '%s' | org='%s' | desc='%s' | model=%s | %s | prompt=%s | "
            "tools=%s",
            self.name,
            self.organization or "-",
            desc_preview,
            self.model_id,
            voice_info,
            self.prompt_path,
            tool_names or "∅",
        )
