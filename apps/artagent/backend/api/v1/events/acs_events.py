"""
V1 Call Event Handlers
===================================

Event handlers with DTMF logic moved to DTMFValidationLifecycle.
Focuses on core call lifecycle events only.

Key Features:
- Basic call lifecycle handling (connected, disconnected, etc.)
- Delegates DTMF processing to DTMFValidationLifecycle
- Comprehensive event routing for all ACS webhook events
- Proper OpenTelemetry tracing and error handling
"""

import json
from datetime import datetime
from typing import Any

from apps.artagent.backend.api.v1.handlers.dtmf_validation_lifecycle import (
    DTMFValidationLifecycle,
)
from apps.artagent.backend.src.ws_helpers.envelopes import (
    make_event_envelope,
    make_status_envelope,
)
from apps.artagent.backend.src.ws_helpers.shared_ws import broadcast_session_envelope
from azure.core.messaging import CloudEvent
from config import DTMF_VALIDATION_ENABLED
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from utils.ml_logging import get_logger

from .types import ACSEventTypes, CallEventContext

logger = get_logger("v1.events.handlers")
tracer = trace.get_tracer(__name__)


class CallEventHandlers:
    """
    Event handlers for Azure Communication Services call events.

    Centralized handlers for core call lifecycle events:
    - API-initiated operations (call initiation, answering)
    - ACS webhook events (connected, disconnected, etc.)
    - Media and recognition events (delegates DTMF to DTMFValidationLifecycle)
    """

    @staticmethod
    async def handle_call_initiated(context: CallEventContext) -> None:
        """
        Handle call initiation events from API operations.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_call_initiated",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            logger.info(f"🚀 Call initiated: {context.call_connection_id}")

            # Log call initiation details
            event_data = context.get_event_data()
            target_number = event_data.get("target_number")
            api_version = event_data.get("api_version", "unknown")

            logger.info(f"   Target: {target_number}, API: {api_version}")

            # Initialize call tracking and state
            if context.memo_manager:
                try:
                    context.memo_manager.update_context("call_initiated_via", "api")
                    context.memo_manager.update_context("api_version", api_version)
                    context.memo_manager.update_context("call_direction", "outbound")
                    if target_number:
                        context.memo_manager.update_context("target_number", target_number)
                    if context.redis_mgr:
                        await context.memo_manager.persist_to_redis_async(context.redis_mgr)
                except Exception as e:
                    logger.error(f"Failed to update call state: {e}")

    @staticmethod
    async def handle_inbound_call_received(context: CallEventContext) -> None:
        """
        Handle inbound call events from Event Grid webhooks.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_inbound_call_received",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            event_data = context.get_event_data()
            caller_info = event_data.get("from", {})
            caller_id = CallEventHandlers._extract_caller_id(caller_info)

            logger.info(f"📞 Inbound call received from {caller_id}")

            # Initialize inbound call state
            if context.memo_manager:
                try:
                    context.memo_manager.update_context("call_direction", "inbound")
                    context.memo_manager.update_context("caller_id", caller_id)
                    context.memo_manager.update_context("caller_info", caller_info)
                    context.memo_manager.update_context("api_version", "v1")
                    if context.redis_mgr:
                        await context.memo_manager.persist_to_redis_async(context.redis_mgr)
                except Exception as e:
                    logger.error(f"Failed to initialize inbound call state: {e}")

    @staticmethod
    async def handle_call_answered(context: CallEventContext) -> None:
        """
        Handle call answered events (both inbound and outbound).

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_call_answered",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            logger.info(f"📞 Call answered: {context.call_connection_id}")

            # Update call state with answer information
            if context.memo_manager:
                try:
                    context.memo_manager.update_context("call_answered", True)
                    context.memo_manager.update_context(
                        "answered_at", datetime.utcnow().isoformat() + "Z"
                    )
                    if context.redis_mgr:
                        await context.memo_manager.persist_to_redis_async(context.redis_mgr)
                except Exception as e:
                    logger.error(f"Failed to update call answer state: {e}")

    @staticmethod
    async def handle_webhook_events(context: CallEventContext) -> None:
        """
        Handle all ACS webhook events that come through callbacks endpoint.

        This is the central handler for events from /callbacks endpoint,
        routing them to specific handlers based on event type.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_webhook_events",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
                "event.source": "acs_webhook",
            },
        ):
            logger.info(f"🌐 Webhook event: {context.event_type} for {context.call_connection_id}")

            # Route to specific handlers
            if context.event_type == ACSEventTypes.CALL_CONNECTED:
                await CallEventHandlers.handle_call_connected(context)
            elif context.event_type == ACSEventTypes.CALL_DISCONNECTED:
                await CallEventHandlers.handle_call_disconnected(context)
            elif context.event_type == ACSEventTypes.CREATE_CALL_FAILED:
                await CallEventHandlers.handle_create_call_failed(context)
            elif context.event_type == ACSEventTypes.ANSWER_CALL_FAILED:
                await CallEventHandlers.handle_answer_call_failed(context)
            elif context.event_type == ACSEventTypes.PARTICIPANTS_UPDATED:
                await CallEventHandlers.handle_participants_updated(context)
            elif context.event_type == ACSEventTypes.CALL_TRANSFER_ACCEPTED:
                await CallEventHandlers.handle_call_transfer_accepted(context)
            elif context.event_type == ACSEventTypes.CALL_TRANSFER_FAILED:
                await CallEventHandlers.handle_call_transfer_failed(context)
            elif context.event_type == ACSEventTypes.DTMF_TONE_RECEIVED:
                await DTMFValidationLifecycle.handle_dtmf_tone_received(context)
            elif context.event_type == ACSEventTypes.PLAY_COMPLETED:
                await CallEventHandlers.handle_play_completed(context)
            elif context.event_type == ACSEventTypes.PLAY_FAILED:
                await CallEventHandlers.handle_play_failed(context)
            elif context.event_type == ACSEventTypes.RECOGNIZE_COMPLETED:
                await CallEventHandlers.handle_recognize_completed(context)
            elif context.event_type == ACSEventTypes.RECOGNIZE_FAILED:
                await CallEventHandlers.handle_recognize_failed(context)
            else:
                logger.warning(f"⚠️  Unhandled webhook event type: {context.event_type}")

            # Update webhook statistics
            try:
                if context.memo_manager:
                    context.memo_manager.update_context("last_webhook_event", context.event_type)
                    if context.redis_mgr:
                        await context.memo_manager.persist_to_redis_async(context.redis_mgr)
            except Exception as e:
                logger.error(f"Failed to update webhook stats: {e}")

    @staticmethod
    async def handle_call_connected(context: CallEventContext) -> None:
        """
        Handle call connected event - broadcast status and play greeting.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_call_connected",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            logger.info(f"📞 Call connected: {context.call_connection_id}")

            # Extract target phone from call connected event
            call_conn = context.acs_caller.get_call_connection(context.call_connection_id)
            participants = call_conn.list_participants()

            caller_participant = None
            acs_participant = None
            caller_id = None

            for participant in participants:
                identifier = participant.identifier
                if getattr(identifier, "kind", None) == "phone_number":
                    caller_participant = participant
                    caller_id = identifier.properties.get("value")
                elif getattr(identifier, "kind", None) == "communicationUser":
                    acs_participant = participant

            if not caller_participant:
                logger.warning("Caller participant not found in participants list.")
            if not acs_participant:
                logger.warning("ACS participant not found in participants list.")

            logger.info(f"   Caller phone number: {caller_id if caller_id else 'unknown'}")

            if DTMF_VALIDATION_ENABLED:
                try:
                    await DTMFValidationLifecycle.setup_aws_connect_validation_flow(
                        context,
                        call_conn,
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Failed to start continuous DTMF recognition for {context.call_connection_id}: {e}"
                    )
            # Broadcast connection status to WebSocket clients
            try:
                if context.app_state:
                    browser_session_id = await CallEventHandlers._lookup_browser_session_id(context)

                    # Use browser session_id if available, fallback to call_connection_id
                    session_id = browser_session_id or context.call_connection_id

                    logger.info(
                        f"🎯 Broadcasting call_connected to session: {session_id} (browser_session_id={browser_session_id}, call_connection_id={context.call_connection_id})"
                    )

                    status_envelope = make_status_envelope(
                        message="📞 Call connected",
                        sender="System",
                        topic="session",
                        session_id=session_id,
                        label="Call Connected",
                    )

                    await broadcast_session_envelope(
                        app_state=context.app_state,
                        envelope=status_envelope,
                        session_id=session_id,
                        event_label="call_connected_broadcast",
                    )
                    await CallEventHandlers._broadcast_session_event_envelope(
                        context=context,
                        session_id=session_id,
                        event_type="call_connected",
                        event_data={
                            "call_connection_id": context.call_connection_id,
                            "browser_session_id": browser_session_id,
                            "caller_id": caller_id,
                            "connected_at": datetime.utcnow().isoformat() + "Z",
                        },
                        event_label="call_connected_event",
                    )
            except Exception as e:
                logger.error(f"Failed to broadcast call connected: {e}")

            # Note: Greeting and conversation flow will be triggered AFTER validation succeeds

    @staticmethod
    async def handle_call_disconnected(context: CallEventContext) -> None:
        """
        Handle call disconnected event - log reason and cleanup.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_call_disconnected",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            # Extract disconnect reason
            event_data = context.get_event_data()
            disconnect_reason = event_data.get("callConnectionState")
            call_props = event_data.get("callConnectionProperties", {})
            end_time_iso = call_props.get("endTime")

            logger.info(
                f"📞 Call disconnected: {context.call_connection_id}, reason: {disconnect_reason}"
            )

            # Notify session listeners about the disconnect event
            session_id = await CallEventHandlers._resolve_session_id(context)
            if session_id and context.app_state:
                try:
                    reason_label: str | None = None
                    if isinstance(disconnect_reason, str) and disconnect_reason:
                        reason_label = disconnect_reason.replace("_", " ").strip().title()
                    message_lines = ["📞 Call disconnected"]
                    if reason_label:
                        message_lines.append(f"Reason: {reason_label}")
                    if end_time_iso:
                        message_lines.append(f"Ended: {end_time_iso}")
                    status_envelope = make_status_envelope(
                        message="\n".join(message_lines),
                        sender="System",
                        topic="session",
                        session_id=session_id,
                        label="Call Disconnected",
                    )

                    await broadcast_session_envelope(
                        app_state=context.app_state,
                        envelope=status_envelope,
                        session_id=session_id,
                        event_label="call_disconnected_broadcast",
                    )
                    await CallEventHandlers._broadcast_session_event_envelope(
                        context=context,
                        session_id=session_id,
                        event_type="call_disconnected",
                        event_data={
                            "call_connection_id": context.call_connection_id,
                            "disconnect_reason": disconnect_reason,
                            "reason_label": reason_label,
                            "ended_at": end_time_iso,
                        },
                        event_label="call_disconnected_event",
                    )
                    logger.info(
                        "📨 Broadcast call_disconnected to session %s (call=%s)",
                        session_id,
                        context.call_connection_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to broadcast call disconnected status for %s: %s",
                        context.call_connection_id,
                        exc,
                    )

            # Clean up call state
            await CallEventHandlers._cleanup_call_state(context)

    @staticmethod
    async def handle_call_transfer_accepted(context: CallEventContext) -> None:
        """
        Handle call transfer accepted events by notifying the UI session.
        """
        event_data = context.get_event_data()
        session_id = await CallEventHandlers._resolve_session_id(context)
        if not session_id or not context.app_state:
            logger.warning(
                "Call transfer accepted but session context missing for call %s",
                context.call_connection_id,
            )
            return

        operation_context = event_data.get("operationContext") or event_data.get(
            "operation_context"
        )
        target_label = CallEventHandlers._describe_transfer_target(event_data)

        message_lines = ["🔄 Call transfer accepted"]
        if target_label:
            message_lines.append(f"Target: {target_label}")
        if operation_context:
            message_lines.append(f"Context: {operation_context}")

        try:
            status_envelope = make_status_envelope(
                message="\n".join(message_lines),
                sender="ACS",
                topic="session",
                session_id=session_id,
                label="Transfer Accepted",
            )

            await broadcast_session_envelope(
                app_state=context.app_state,
                envelope=status_envelope,
                session_id=session_id,
                event_label="call_transfer_accepted_status",
            )

            await CallEventHandlers._broadcast_session_event_envelope(
                context=context,
                session_id=session_id,
                event_type="call_transfer_accepted",
                event_data={
                    "call_connection_id": context.call_connection_id,
                    "operation_context": operation_context,
                    "target": target_label,
                    "raw_event": event_data,
                },
                event_label="call_transfer_accepted_event",
            )
        except Exception as exc:
            logger.error("Failed to broadcast call transfer accepted: %s", exc)

    @staticmethod
    async def handle_call_transfer_failed(context: CallEventContext) -> None:
        """
        Handle call transfer failure events by notifying the UI session.
        """
        event_data = context.get_event_data()
        session_id = await CallEventHandlers._resolve_session_id(context)
        if not session_id or not context.app_state:
            logger.warning(
                "Call transfer failed but session context missing for call %s",
                context.call_connection_id,
            )
            return

        operation_context = event_data.get("operationContext") or event_data.get(
            "operation_context"
        )
        target_label = CallEventHandlers._describe_transfer_target(event_data)
        result_info = event_data.get("resultInformation") or {}
        failure_reason = (
            result_info.get("message")
            or result_info.get("subCode")
            or event_data.get("errorMessage")
            or "Unknown reason"
        )

        message_lines = ["⚠️ Call transfer failed"]
        if target_label:
            message_lines.append(f"Target: {target_label}")
        if failure_reason:
            message_lines.append(f"Reason: {failure_reason}")
        if operation_context:
            message_lines.append(f"Context: {operation_context}")

        try:
            status_envelope = make_status_envelope(
                message="\n".join(message_lines),
                sender="ACS",
                topic="session",
                session_id=session_id,
                label="Transfer Failed",
            )

            await broadcast_session_envelope(
                app_state=context.app_state,
                envelope=status_envelope,
                session_id=session_id,
                event_label="call_transfer_failed_status",
            )

            await CallEventHandlers._broadcast_session_event_envelope(
                context=context,
                session_id=session_id,
                event_type="call_transfer_failed",
                event_data={
                    "call_connection_id": context.call_connection_id,
                    "operation_context": operation_context,
                    "target": target_label,
                    "reason": failure_reason,
                    "raw_event": event_data,
                },
                event_label="call_transfer_failed_event",
            )
        except Exception as exc:
            logger.error("Failed to broadcast call transfer failure: %s", exc)

    @staticmethod
    async def _resolve_session_id(context: CallEventContext) -> str | None:
        """Resolve the session identifier tied to a call connection."""
        if not context.app_state:
            return None

        browser_session_id: str | None = await CallEventHandlers._lookup_browser_session_id(context)

        return browser_session_id or context.call_connection_id

    @staticmethod
    async def _broadcast_session_event_envelope(
        *,
        context: CallEventContext,
        session_id: str | None,
        event_type: str,
        event_data: dict[str, Any],
        event_label: str,
    ) -> None:
        """Broadcast a structured event envelope to the UI session if available."""
        if not session_id or not context.app_state:
            return

        clean_payload = {
            key: value for key, value in (event_data or {}).items() if value is not None
        }
        if "call_connection_id" not in clean_payload and context.call_connection_id:
            clean_payload["call_connection_id"] = context.call_connection_id

        try:
            event_envelope = make_event_envelope(
                event_type=event_type,
                event_data=clean_payload,
                sender="ACS",
                topic="session",
                session_id=session_id,
            )
            await broadcast_session_envelope(
                app_state=context.app_state,
                envelope=event_envelope,
                session_id=session_id,
                event_label=event_label,
            )
        except Exception as exc:
            logger.error(
                "Failed to broadcast %s event for session %s (call=%s): %s",
                event_type,
                session_id,
                context.call_connection_id,
                exc,
            )

    @staticmethod
    async def _lookup_browser_session_id(
        context: CallEventContext,
    ) -> str | None:
        """Retrieve the browser session ID mapped to a call connection."""
        key_suffix = context.call_connection_id
        if not key_suffix:
            return None

        keys_to_try = [
            f"call_session_map:{key_suffix}",
            f"call_session_mapping:{key_suffix}",
        ]

        # Fallback to redis manager helper if available
        redis_mgr = getattr(context, "redis_mgr", None)
        if redis_mgr and hasattr(redis_mgr, "get_value_async"):
            for redis_key in keys_to_try:
                try:
                    redis_value = await redis_mgr.get_value_async(redis_key)
                    if redis_value:
                        return (
                            redis_value.decode("utf-8")
                            if isinstance(redis_value, (bytes, bytearray))
                            else str(redis_value)
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch session mapping %s via redis_mgr: %s",
                        redis_key,
                        exc,
                    )

        # Final fallback: use connection manager call context (if available)
        conn_manager = getattr(context.app_state, "conn_manager", None)
        if conn_manager and hasattr(conn_manager, "get_call_context"):
            try:
                ctx = await conn_manager.get_call_context(key_suffix)
                if ctx:
                    return ctx.get("browser_session_id") or ctx.get("session_id")
            except Exception as exc:
                logger.warning(
                    "Failed to fetch session mapping %s via conn_manager: %s",
                    key_suffix,
                    exc,
                )

        return None

    @staticmethod
    def _describe_transfer_target(event_data: dict[str, Any]) -> str | None:
        """Best-effort extraction of the transfer destination label."""
        candidate = (
            event_data.get("targetParticipant")
            or event_data.get("target")
            or event_data.get("destination")
        )
        if not candidate:
            targets = event_data.get("targets")
            if isinstance(targets, list) and targets:
                candidate = targets[0]

        if isinstance(candidate, str):
            return candidate

        if isinstance(candidate, dict):
            phone = (
                candidate.get("phoneNumber", {}).get("value")
                if isinstance(candidate.get("phoneNumber"), dict)
                else candidate.get("phoneNumber")
            )
            raw_id = candidate.get("rawId") or candidate.get("raw_id")
            user = candidate.get("user", {}).get("communicationUserId")
            return phone or raw_id or user

        return None

    @staticmethod
    async def handle_create_call_failed(context: CallEventContext) -> None:
        """
        Handle create call failed event - log error details.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_create_call_failed",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            result_info = context.get_event_field("resultInformation", {})
            logger.error(
                f"❌ Create call failed: {context.call_connection_id}, reason: {result_info}"
            )

    @staticmethod
    async def handle_answer_call_failed(context: CallEventContext) -> None:
        """
        Handle answer call failed event - log error details.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_answer_call_failed",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            result_info = context.get_event_field("resultInformation", {})
            logger.error(
                f"❌ Answer call failed: {context.call_connection_id}, reason: {result_info}"
            )

    @staticmethod
    async def handle_participants_updated(context: CallEventContext) -> None:
        """
        Handle participant updates and start DTMF recognition.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        with tracer.start_as_current_span(
            "v1.handle_participants_updated",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            try:
                participants = context.get_event_field("participants", [])
                logger.info(f"👥 Participants updated: {len(participants)} participants")

                # Log participant details
                for i, participant in enumerate(participants):
                    identifier = participant.get("identifier", {})
                    is_muted = participant.get("isMuted", False)
                    logger.info(
                        f"   Participant {i+1}: {identifier.get('kind', 'unknown')}, muted: {is_muted}"
                    )

            except Exception as e:
                logger.error(f"Error in participants updated handler: {e}")

    @staticmethod
    async def handle_dtmf_tone_received(context: CallEventContext) -> None:
        """Handle DTMF tone with sequence validation."""
        with tracer.start_as_current_span(
            "v1.handle_dtmf_tone_received",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
            },
        ):
            tone = context.get_event_field("tone")
            sequence_id = context.get_event_field("sequenceId")

            logger.info(f"🔢 DTMF tone received: {tone}, sequence_id: {sequence_id}")

            # Normalize and process tone
            normalized_tone = CallEventHandlers._normalize_tone(tone)
            if normalized_tone and context.memo_manager:
                CallEventHandlers._update_dtmf_sequence(context, normalized_tone, sequence_id)

    @staticmethod
    async def handle_play_completed(context: CallEventContext) -> None:
        """
        Handle play completed event.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        logger.info(f"🎵 Play completed: {context.call_connection_id}")

    @staticmethod
    async def handle_play_failed(context: CallEventContext) -> None:
        """
        Handle play failed event.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        result_info = context.get_event_field("resultInformation", {})
        logger.error(f"🎵 Play failed: {context.call_connection_id}, reason: {result_info}")

    @staticmethod
    async def handle_recognize_completed(context: CallEventContext) -> None:
        """
        Handle recognize completed event.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        logger.info(f"🎤 Recognize completed: {context.call_connection_id}")

    @staticmethod
    async def handle_recognize_failed(context: CallEventContext) -> None:
        """
        Handle recognize failed event.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        result_info = context.get_event_field("resultInformation", {})
        logger.error(f"🎤 Recognize failed: {context.call_connection_id}, reason: {result_info}")

    # ============================================================================
    # Helper Methods
    # ============================================================================

    @staticmethod
    def _extract_caller_id(caller_info: dict[str, Any]) -> str:
        """
        Extract caller ID from caller information.

        :param caller_info: Caller information dictionary from ACS event
        :type caller_info: Dict[str, Any]
        :return: Extracted caller ID or 'unknown' if not found
        :rtype: str
        """
        if caller_info.get("kind") == "phoneNumber":
            return caller_info.get("phoneNumber", {}).get("value", "unknown")
        return caller_info.get("rawId", "unknown")

    @staticmethod
    async def _play_greeting(context: CallEventContext) -> None:
        """
        Play greeting to connected call.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        try:
            if not context.acs_caller or not context.memo_manager:
                return

            from azure.communication.callautomation import TextSource
            from config import GREETING, GREETING_VOICE_TTS

            # Create greeting source
            text_source = TextSource(
                text=GREETING,
                voice_name=GREETING_VOICE_TTS,
                custom_voice_endpoint_id=None,
            )

            # Play greeting
            await context.acs_caller.play_to_all(context.call_connection_id, text_source)

            logger.info(f"🎵 Greeting played to call {context.call_connection_id}")

        except Exception as e:
            logger.error(f"Failed to play greeting: {e}")

    @staticmethod
    async def _cleanup_call_state(context: CallEventContext) -> None:
        """
        Clean up call state when call disconnects.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        """
        try:
            # Basic cleanup - delegate DTMF cleanup to lifecycle handler
            logger.info(f"🧹 Cleaning up call state: {context.call_connection_id}")

            # Clear memo context if available
            if context.memo_manager:
                context.memo_manager.update_context("call_active", False)
                context.memo_manager.update_context("call_disconnected", True)

            if context.memo_manager and context.redis_mgr:
                # Persist final state before cleanup
                await context.memo_manager.persist_to_redis_async(context.redis_mgr)
            logger.info(f"🧹 Call state cleaned up for {context.call_connection_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup call state: {e}")

    @staticmethod
    def _get_participant_phone(event: CloudEvent, memo_manager: Any | None) -> str | None:
        """
        Extract participant phone number from event.

        :param event: CloudEvent containing participant information
        :type event: CloudEvent
        :param memo_manager: Memory manager for accessing context
        :type memo_manager: Optional[Any]
        :return: Extracted phone number or None if not found
        :rtype: Optional[str]
        """
        try:
            event_data = CallEventHandlers._safe_get_event_data(event)
            participants = event_data.get("participants", [])

            def digits_tail(s: str | None, n: int = 10) -> str:
                return "".join(ch for ch in (s or "") if ch.isdigit())[-n:]

            # Get target number from context
            target_number = None
            if memo_manager:
                target_number = memo_manager.get_context("target_number")
            target_tail = digits_tail(target_number) if target_number else ""

            # Find PSTN participants
            pstn_candidates = []
            for participant in participants:
                identifier = participant.get("identifier", {})

                # Try phoneNumber field first
                phone = identifier.get("phoneNumber", {}).get("value")

                # Fallback to rawId parsing (format: "4:+12345678901")
                if not phone:
                    raw_id = identifier.get("rawId", "")
                    if isinstance(raw_id, str) and raw_id.startswith("4:"):
                        phone = raw_id[2:]  # Remove "4:" prefix

                if phone:
                    pstn_candidates.append(phone)

            if not pstn_candidates:
                return None

            # Match with target number if available
            if target_tail:
                for phone in pstn_candidates:
                    if digits_tail(phone) == target_tail:
                        return phone

            # Return first PSTN participant
            return pstn_candidates[0]

        except Exception as e:
            logger.error(f"Error extracting participant phone: {e}")
            return None

    @staticmethod
    async def _start_dtmf_recognition(context: CallEventContext, target_phone: str) -> None:
        """
        Start DTMF recognition for participant.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        :param target_phone: Phone number to start DTMF recognition for
        :type target_phone: str
        """
        try:
            if context.acs_caller:
                call_conn = context.acs_caller.get_call_connection(context.call_connection_id)
                if not call_conn:
                    logger.error("Call connection not found for %s", context.call_connection_id)
                    return

                await call_conn.start_continuous_dtmf_recognition(
                    context.call_connection_id, target_phone
                )
                logger.info(f"🔢 DTMF recognition started for {target_phone}")
        except Exception as e:
            logger.error(f"Failed to start DTMF recognition: {e}")

    @staticmethod
    def _normalize_tone(tone: str) -> str | None:
        """
        Normalize DTMF tone to standard format.

        :param tone: Raw DTMF tone from ACS event
        :type tone: str
        :return: Normalized tone or None if invalid
        :rtype: Optional[str]
        """
        if not tone:
            return None

        tone_str = str(tone).strip().lower()

        tone_map = {
            "0": "0",
            "zero": "0",
            "1": "1",
            "one": "1",
            "2": "2",
            "two": "2",
            "3": "3",
            "three": "3",
            "4": "4",
            "four": "4",
            "5": "5",
            "five": "5",
            "6": "6",
            "six": "6",
            "7": "7",
            "seven": "7",
            "8": "8",
            "eight": "8",
            "9": "9",
            "nine": "9",
            "*": "*",
            "star": "*",
            "asterisk": "*",
            "#": "#",
            "pound": "#",
            "hash": "#",
        }

        normalized = tone_map.get(tone_str)
        return (
            normalized
            if normalized in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"}
            else None
        )

    @staticmethod
    def _update_dtmf_sequence(
        context: CallEventContext, tone: str, sequence_id: int | None
    ) -> None:
        """
        Update DTMF sequence in memory.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        :param tone: Normalized DTMF tone to add to sequence
        :type tone: str
        :param sequence_id: Optional sequence ID for ordering
        :type sequence_id: Optional[int]
        """
        if not context.memo_manager:
            return

        current_sequence = context.memo_manager.get_context("dtmf_sequence", "")

        # Handle special tones
        if tone == "#":
            # End sequence - validate
            if current_sequence:
                CallEventHandlers._validate_sequence(context, current_sequence)
            return
        elif tone == "*":
            # Clear sequence
            context.memo_manager.update_context("dtmf_sequence", "")
            if context.redis_mgr:
                context.memo_manager.persist_to_redis(context.redis_mgr)
            logger.info(f"🔢 DTMF sequence cleared for {context.call_connection_id}")
            return

        # Handle sequence ordering
        if sequence_id is not None:
            seq_index = sequence_id - 1  # 1-based to 0-based
            dtmf_list = list(current_sequence)

            # Expand list if needed
            while len(dtmf_list) <= seq_index:
                dtmf_list.append("")

            dtmf_list[seq_index] = tone
            new_sequence = "".join(dtmf_list)
        else:
            # Append to end
            new_sequence = current_sequence + tone

        # Update context
        context.memo_manager.update_context("dtmf_sequence", new_sequence)
        if context.redis_mgr:
            context.memo_manager.persist_to_redis(context.redis_mgr)

        logger.info(f"🔢 DTMF sequence updated: {new_sequence}")

    @staticmethod
    def _validate_sequence(context: CallEventContext, sequence: str) -> None:
        """
        Validate DTMF sequence.

        :param context: Call event context containing connection details and managers
        :type context: CallEventContext
        :param sequence: DTMF sequence to validate
        :type sequence: str
        """
        if not context.memo_manager:
            return

        # Simple validation - 4-digit PIN
        is_valid = len(sequence) == 4 and sequence.isdigit()

        # Update context
        context.memo_manager.update_context("dtmf_sequence", "")
        context.memo_manager.update_context("dtmf_validated", is_valid)
        context.memo_manager.update_context("entered_pin", sequence if is_valid else None)

        if context.redis_mgr:
            context.memo_manager.persist_to_redis(context.redis_mgr)

        logger.info(f"🔢 DTMF sequence {'validated' if is_valid else 'rejected'}: {sequence}")

    @staticmethod
    def _safe_get_event_data(event: CloudEvent) -> dict[str, Any]:
        """
        Safely extract event data as dictionary.

        :param event: CloudEvent to extract data from
        :type event: CloudEvent
        :return: Event data as dictionary
        :rtype: Dict[str, Any]
        """
        try:
            data = event.data
            if isinstance(data, dict):
                return data
            elif isinstance(data, str):
                return json.loads(data)
            elif isinstance(data, bytes):
                return json.loads(data.decode("utf-8"))
            elif hasattr(data, "__dict__"):
                return data.__dict__
            else:
                return {}
        except Exception:
            return {}
