from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import WebSocket

from utils.ml_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AgentBinding:
    """
    Binding information for known agents to resolve their instance from app.state.

    :param name: Agent name
    :param ws_attr: Attribute name on ws.app.state where the instance lives
    """
    name: str
    ws_attr: Optional[str]


# Static binding map (parity with original)
AGENT_BINDINGS: Dict[str, AgentBinding] = {
    "AutoAuth": AgentBinding(name="AutoAuth", ws_attr="auth_agent"),
    "Claims": AgentBinding(name="Claims", ws_attr="claim_intake_agent"),
    "General": AgentBinding(name="General", ws_attr="general_info_agent"),
}


def get_agent_instance(ws: WebSocket, agent_name: str) -> Any:
    """
    Resolve an agent instance from the WebSocket's app.state.

    :param ws: FastAPI WebSocket
    :param agent_name: Agent name key
    :return: Concrete agent instance or None
    """
    binding = AGENT_BINDINGS.get(agent_name)
    if binding and binding.ws_attr:
        return getattr(ws.app.state, binding.ws_attr, None)

    # Fallback dictionary for custom agents
    instances = getattr(ws.app.state, "agent_instances", None)
    if isinstance(instances, dict):
        return instances.get(agent_name)
    return None
