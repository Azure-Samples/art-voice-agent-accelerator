"""
V1 Call Event Processor
======================

Simplified event processor inspired by Azure's CallAutomationEventProcessor.
Focuses on call correlation and handler registration without complex middleware.
"""

import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
from azure.core.messaging import CloudEvent

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from utils.ml_logging import get_logger
from .types import CallEventContext, CallEventHandler, ACSEventTypes

logger = get_logger("v1.events.processor")
tracer = trace.get_tracer(__name__)


class CallEventProcessor:
    """
    Simplified call event processor inspired by Azure's Event Processor pattern.

    Key features:
    - Call correlation by callConnectionId
    - Simple handler registration per event type
    - No complex middleware or retry logic
    - Direct integration with legacy handlers
    """

    def __init__(self):
        # Event handlers by event type
        self._handlers: Dict[str, List[CallEventHandler]] = defaultdict(list)

        # Active calls being tracked
        self._active_calls: Set[str] = set()

        # Simple metrics
        self._stats = {
            "events_processed": 0,
            "events_failed": 0,
            "handlers_registered": 0,
        }

    def register_handler(self, event_type: str, handler: CallEventHandler) -> None:
        """
        Register a handler for a specific event type.

        :param event_type: ACS event type (e.g., "Microsoft.Communication.CallConnected")
        :type event_type: str
        :param handler: Async function to handle the event
        :type handler: CallEventHandler
        """
        self._handlers[event_type].append(handler)
        self._stats["handlers_registered"] += 1

        handler_name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.info(f"📋 Registered handler {handler_name} for {event_type}")

    def unregister_handler(self, event_type: str, handler: CallEventHandler) -> bool:
        """
        Unregister a specific handler.

        :param event_type: ACS event type
        :type event_type: str
        :param handler: Handler function to remove
        :type handler: CallEventHandler
        :return: True if handler was found and removed
        :rtype: bool
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                self._stats["handlers_registered"] -= 1
                return True
            except ValueError:
                pass
        return False

    async def process_events(
        self, events: List[CloudEvent], request_state: Any
    ) -> Dict[str, Any]:
        """
        Process a list of CloudEvents from ACS webhook.

        :param events: List of CloudEvent objects from webhook
        :type events: List[CloudEvent]
        :param request_state: FastAPI request app state for dependencies
        :type request_state: Any
        :return: Processing result summary
        :rtype: Dict[str, Any]
        """
        with tracer.start_as_current_span(
            "call_event_processor.process_events",
            kind=SpanKind.INTERNAL,
            attributes={"events.count": len(events)},
        ):
            processed_count = 0
            failed_count = 0

            for event in events:
                try:
                    await self._process_single_event(event, request_state)
                    processed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Failed to process event {event.type}: {e}")

            self._stats["events_processed"] += processed_count
            self._stats["events_failed"] += failed_count

            logger.debug(
                f"✅ Processed {processed_count}/{len(events)} events successfully"
            )

            return {
                "status": "success" if failed_count == 0 else "partial_failure",
                "processed": processed_count,
                "failed": failed_count,
                "timestamp": time.time(),
            }

    async def _process_single_event(
        self, event: CloudEvent, request_state: Any
    ) -> None:
        """
        Process a single CloudEvent.

        :param event: CloudEvent to process
        :type event: CloudEvent
        :param request_state: FastAPI request app state for dependencies
        :type request_state: Any
        """
        # Extract call connection ID
        call_connection_id = self._extract_call_connection_id(event)
        if not call_connection_id:
            logger.warning(f"⚠️ No call connection ID found in event {event.type}")
            return

        # Track active calls
        if event.type == ACSEventTypes.CALL_CONNECTED:
            self._active_calls.add(call_connection_id)
        elif event.type == ACSEventTypes.CALL_DISCONNECTED:
            self._active_calls.discard(call_connection_id)

        # Create event context
        context = self._create_event_context(event, call_connection_id, request_state)

        # Get handlers for this event type
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug(f"🔍 No handlers registered for {event.type}")
            return

        # Execute all handlers for this event type
        await self._execute_handlers(handlers, context)

    def _extract_call_connection_id(self, event: CloudEvent) -> Optional[str]:
        """
        Extract call connection ID from CloudEvent.

        :param event: CloudEvent to extract connection ID from
        :type event: CloudEvent
        :return: Call connection ID or None if not found
        :rtype: Optional[str]
        """
        try:
            data = event.data
            if isinstance(data, dict):
                return data.get("callConnectionId")
            elif hasattr(data, "callConnectionId"):
                return data.callConnectionId
            elif hasattr(data, "call_connection_id"):
                return data.call_connection_id
        except Exception as e:
            logger.error(f"Error extracting call connection ID: {e}")
        return None

    def _create_event_context(
        self, event: CloudEvent, call_connection_id: str, request_state: Any
    ) -> CallEventContext:
        """
        Create event context from CloudEvent and request state.

        :param event: CloudEvent to create context from
        :type event: CloudEvent
        :param call_connection_id: Call connection identifier
        :type call_connection_id: str
        :param request_state: FastAPI request app state for dependencies
        :type request_state: Any
        :return: Event context for handlers
        :rtype: CallEventContext
        """
        # Extract dependencies from request state
        memo_manager = None
        if hasattr(request_state, "redis") and request_state.redis:
            try:
                from src.stateful.state_managment import MemoManager

                memo_manager = MemoManager.from_redis(
                    session_id=call_connection_id, redis_mgr=request_state.redis
                )
            except Exception:
                # Skip memo manager if Redis not available (e.g., in demo)
                pass

        return CallEventContext(
            event=event,
            call_connection_id=call_connection_id,
            event_type=event.type,
            memo_manager=memo_manager,
            redis_mgr=getattr(request_state, "redis", None),
            acs_caller=getattr(request_state, "acs_caller", None),
            clients=getattr(request_state, "clients", []),
            app_state=request_state,  # Pass full app state for ConnectionManager access
        )

    async def _execute_handlers(
        self, handlers: List[CallEventHandler], context: CallEventContext
    ) -> None:
        """
        Execute all handlers for an event with error isolation.

        :param handlers: List of event handlers to execute
        :type handlers: List[CallEventHandler]
        :param context: Event context containing call details
        :type context: CallEventContext
        """
        successful = 0
        failed = 0

        for handler in handlers:
            try:
                with tracer.start_as_current_span(
                    f"call_event_handler.{getattr(handler, '__name__', 'unknown')}",
                    kind=SpanKind.INTERNAL,
                    attributes={
                        "event.type": context.event_type,
                        "call.connection.id": context.call_connection_id,
                    },
                ):
                    await handler(context)
                    successful += 1
            except Exception as e:
                failed += 1
                handler_name = getattr(handler, "__name__", handler.__class__.__name__)
                logger.error(
                    f"❌ Handler {handler_name} failed for {context.event_type}: {e}"
                )

        logger.debug(f"Handler execution: {successful} successful, {failed} failed")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processor statistics.

        :return: Dictionary containing processor metrics and statistics
        :rtype: Dict[str, Any]
        """
        return {
            **self._stats,
            "active_calls": len(self._active_calls),
            "registered_handlers": sum(
                len(handlers) for handlers in self._handlers.values()
            ),
            "event_types": list(self._handlers.keys()),
        }

    def get_active_calls(self) -> Set[str]:
        """
        Get set of currently active call connection IDs.

        :return: Set of active call connection IDs
        :rtype: Set[str]
        """
        return self._active_calls.copy()


# Global processor instance
_global_processor: Optional[CallEventProcessor] = None


def get_call_event_processor() -> CallEventProcessor:
    """
    Get the global call event processor instance.

    :return: Global call event processor instance
    :rtype: CallEventProcessor
    """
    global _global_processor
    if _global_processor is None:
        _global_processor = CallEventProcessor()
    return _global_processor


def reset_call_event_processor() -> None:
    """
    Reset the global processor (primarily for testing).
    """
    global _global_processor
    _global_processor = None
