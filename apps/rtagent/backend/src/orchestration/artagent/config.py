from __future__ import annotations

import os
from typing import Iterable, Optional

from utils.ml_logging import get_logger

logger = get_logger(__name__)

# Feature flags / constants
ORCHESTRATOR_TRACING: bool = os.getenv("ORCHESTRATOR_TRACING", "true").lower() == "true"
LAST_ANNOUNCED_KEY = "last_announced_agent"
APP_GREETS_ATTR = "greet_counts"

# Orchestration pattern (entry + specialists). Defaults preserve your flow.
ENTRY_AGENT: str = "AutoAuth"
SPECIALISTS: list[str] = ["General", "Claims"]


def configure_entry_and_specialists(
    *, entry_agent: str = "AutoAuth", specialists: Optional[Iterable[str]] = None
) -> None:
    """
    Configure the entry agent and ordered list of specialists.

    Entry agent is coerced to `AutoAuth` for behavior parity with the original orchestrator.

    :param entry_agent: Requested entry agent name (forced to 'AutoAuth')
    :param specialists: Ordered list of specialist agent names
    :return: None
    """
    global ENTRY_AGENT, SPECIALISTS  # noqa: PLW0603
    if entry_agent != "AutoAuth":
        logger.warning("Entry agent overridden to 'AutoAuth' (requested '%s')", entry_agent)
    ENTRY_AGENT = "AutoAuth"
    SPECIALISTS = list(specialists or ["General", "Claims"])
