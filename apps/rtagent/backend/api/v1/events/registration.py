"""
V1 Event Registration
====================

Simple registration module that sets up event handlers inspired by Azure's Event Processor pattern.
Registers legacy handlers with the V1 CallEventProcessor for clean event processing.
"""

from .processor import get_call_event_processor
from .handlers import CallEventHandlers
from .types import ACSEventTypes, V1EventTypes
from ..handlers.dtmf_validation_lifecycle import DTMFValidationLifecycle
from utils.ml_logging import get_logger

logger = get_logger("v1.events.registration")

# Track whether handlers have been registered
_handlers_registered = False


def register_default_handlers() -> None:
    """
    Register default call event handlers with the V1 Event Processor.

    This function sets up the standard ACS event handlers adapted from
    the legacy implementation, following Azure's Event Processor pattern.

    Uses singleton pattern to avoid re-registering handlers on every request.
    """
    global _handlers_registered

    if _handlers_registered:
        logger.debug("🔄 Handlers already registered, skipping...")
        return  # Already registered, skip

    logger.info("🆕 First time registration, setting up handlers...")
    processor = get_call_event_processor()

    # Register V1 API-initiated events
    processor.register_handler(
        V1EventTypes.CALL_INITIATED, CallEventHandlers.handle_call_initiated
    )

    processor.register_handler(
        V1EventTypes.WEBHOOK_EVENTS, CallEventHandlers.handle_webhook_events
    )

    # Register standard ACS webhook events
    processor.register_handler(
        ACSEventTypes.CALL_CONNECTED, CallEventHandlers.handle_call_connected
    )

    processor.register_handler(
        ACSEventTypes.CALL_DISCONNECTED, CallEventHandlers.handle_call_disconnected
    )

    processor.register_handler(
        ACSEventTypes.CREATE_CALL_FAILED, CallEventHandlers.handle_create_call_failed
    )

    processor.register_handler(
        ACSEventTypes.ANSWER_CALL_FAILED, CallEventHandlers.handle_answer_call_failed
    )

    # Register participant handlers
    processor.register_handler(
        ACSEventTypes.PARTICIPANTS_UPDATED,
        CallEventHandlers.handle_participants_updated,
    )

    # Register DTMF handlers (delegated to DTMFValidationLifecycle)
    processor.register_handler(
        ACSEventTypes.DTMF_TONE_RECEIVED,
        DTMFValidationLifecycle.handle_dtmf_tone_received,
    )

    processor.register_handler(
        V1EventTypes.DTMF_RECOGNITION_START_REQUESTED,
        DTMFValidationLifecycle.handle_dtmf_recognition_start_requested,
    )

    # Register media handlers
    processor.register_handler(
        ACSEventTypes.PLAY_COMPLETED, CallEventHandlers.handle_play_completed
    )

    processor.register_handler(
        ACSEventTypes.PLAY_FAILED, CallEventHandlers.handle_play_failed
    )

    # Register recognition handlers
    processor.register_handler(
        ACSEventTypes.RECOGNIZE_COMPLETED, CallEventHandlers.handle_recognize_completed
    )

    processor.register_handler(
        ACSEventTypes.RECOGNIZE_FAILED, CallEventHandlers.handle_recognize_failed
    )

    _handlers_registered = True  # Mark as registered
    logger.info("✅ V1 call event handlers registered successfully")


def register_all_handlers() -> None:
    """
    Register all event handlers (Call and Live Voice) with the V1 Event Processor.

    This is the main registration function that should be called to set up
    the complete event processing system.
    """
    register_default_handlers()


def get_processor_stats() -> dict:
    """
    Get current processor statistics.

    :return: Dictionary containing processor metrics and statistics
    :rtype: dict
    """
    processor = get_call_event_processor()
    return processor.get_stats()


def get_active_calls() -> set:
    """
    Get currently active call connection IDs.

    :return: Set of active call connection IDs
    :rtype: set
    """
    processor = get_call_event_processor()
    return processor.get_active_calls()
