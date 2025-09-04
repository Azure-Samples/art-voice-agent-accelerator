from __future__ import annotations

"""
Modular orchestration package.

Exports:
- route_turn: main per-turn entry point
- registration helpers: register_specialist, register_specialists, get_specialist, list_specialists
- configure_entry_and_specialists: tweak entry/specialist list (entry is coerced to AutoAuth)
- SPECIALIST_MAP: backward-compatible alias of the internal registry
"""

from .orchestrator import route_turn, bind_default_handlers  # noqa: F401
from .config import configure_entry_and_specialists  # noqa: F401
from .registry import (  # noqa: F401
    register_specialist,
    register_specialists,
    get_specialist,
    list_specialists,
    SPECIALIST_MAP,
)

# Bind defaults immediately (AutoAuth, General, Claims) to preserve behavior.
bind_default_handlers()
