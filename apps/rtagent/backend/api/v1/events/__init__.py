"""
V1 Event System
===============

Simplified event processing system inspired by Azure's Event Processor pattern.
Provides clean call event handling without complex middleware.
"""

from .processor import (
    CallEventProcessor,
    get_call_event_processor,
    reset_call_event_processor,
)
from .handlers import CallEventHandlers
from .types import CallEventContext, ACSEventTypes
from .registration import (
    register_default_handlers,
    get_processor_stats,
    get_active_calls,
)

# Note: Handlers are registered on first use of the processor
# Call register_default_handlers() explicitly if needed at startup

__all__ = [
    # Core processor
    "CallEventProcessor",
    "get_call_event_processor",
    "reset_call_event_processor",
    # Handlers and types
    "CallEventHandlers",
    "CallEventContext",
    "ACSEventTypes",
    # Registration utilities
    "register_default_handlers",
    "get_processor_stats",
    "get_active_calls",
]
