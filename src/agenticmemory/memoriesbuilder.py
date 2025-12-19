"""
EphemeralSummaryAgent - Stateless summarization agent.

NOTE: This module is currently a placeholder/template and is not integrated
with the main application. The imports below are stubs to satisfy linting.
This code requires the letta SDK to function properly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# Type stubs - this module requires letta SDK which is not installed
if TYPE_CHECKING:
    from typing import List

    # These would come from letta SDK
    class BaseAgent:
        pass

    class MessageManager:
        pass

    class AgentManager:
        pass

    class BlockManager:
        pass

    class User:
        pass

    class MessageCreate:
        pass

    class Message:
        pass

    class MessageRole:
        system = "system"
        assistant = "assistant"

    class TextContent:
        pass

    class Block:
        pass

    class BlockUpdate:
        pass

    class NoResultFound(Exception):
        pass

    class LLMClient:
        pass

    DEFAULT_MAX_STEPS = 10

    def get_system_text(x):
        return ""

    def convert_message_creates_to_messages(*args, **kwargs):
        return []

else:
    # Runtime stubs - module is not functional without letta SDK
    List = list
    DEFAULT_MAX_STEPS = 10


class EphemeralSummaryAgent:
    """
    A stateless summarization agent that utilizes the caller's LLM client to summarize the conversation.

    NOTE: This class requires the letta SDK to function. It is currently a placeholder.
    TODO (cliandy): allow the summarizer to use another llm_config from the main agent maybe?
    """

    def __init__(
        self,
        target_block_label: str,
        agent_id: str,
        message_manager: Any,
        agent_manager: Any,
        block_manager: Any,
        actor: Any,
    ):
        raise NotImplementedError("EphemeralSummaryAgent requires letta SDK which is not installed")
