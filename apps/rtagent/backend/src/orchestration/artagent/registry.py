from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Protocol

from utils.ml_logging import get_logger

logger = get_logger(__name__)


# ---- Agent handler protocol (async callable) ---------------------------------
class AgentHandler(Protocol):
    async def __call__(self, cm, utterance: str, ws, *, is_acs: bool) -> None: ...


# ---- Public registry API ------------------------------------------------------
_REGISTRY: Dict[str, AgentHandler] = {}


def register_specialist(name: str, handler: AgentHandler) -> None:
    """
    Register an agent handler under a name (e.g., 'Claims', 'General', 'AutoAuth').

    :param name: Registry key that matches `active_agent` values in CoreMemory.
    :param handler: Async callable with signature (cm, utterance, ws, *, is_acs)
    :return: None
    """
    _REGISTRY[name] = handler


def register_specialists(handlers: Dict[str, AgentHandler]) -> None:
    """
    Bulk-register handlers in one call.

    :param handlers: {name: handler, ...}
    :return: None
    """
    for k, v in (handlers or {}).items():
        register_specialist(k, v)


def get_specialist(name: str) -> Optional[AgentHandler]:
    """
    Lookup a registered agent handler.

    :param name: Agent name
    :return: Handler or None
    """
    return _REGISTRY.get(name)


def list_specialists() -> Iterable[str]:
    """
    List all registered specialists.

    :return: Iterable of agent names
    """
    return _REGISTRY.keys()


# Back-compat alias used by your original code
SPECIALIST_MAP: Dict[str, AgentHandler] = _REGISTRY
