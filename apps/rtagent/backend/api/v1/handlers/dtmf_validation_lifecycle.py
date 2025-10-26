"""
DTMF Validation Lifecycle
======================================

DTMF handling for call transfer flows

Core Features:
- DTMF tone processing for AWS Connect-style validation
- Basic tone sequence management
- Validation state management via memory context
- OpenTelemetry tracing for core operations

Essential Flow:
1. setup_aws_connect_validation_flow - Initialize validation
2. handle_dtmf_tone_received - Process DTMF tones
"""

import asyncio
import json
import random
import string
import time
from typing import Any, Dict, Optional
from azure.communication.callautomation import CallConnectionClient

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from utils.ml_logging import get_logger
from ..events.types import CallEventContext

logger = get_logger("v1.handlers.dtmf_validation_lifecycle")
tracer = trace.get_tracer(__name__)

try:
    from apps.rtagent.backend.src.services.acs.session_terminator import SessionTerminator
except ImportError:  # pragma: no cover
    SessionTerminator = None


class DTMFValidationLifecycle:
    """
    Simplified DTMF validation lifecycle handler.

    Handles core DTMF processing including:
    - AWS Connect-style validation flow
    - Basic tone sequence management
    - Validation state tracking
    - DTMF validation blocking logic for media streams
    """

    # Standard stream key format for DTMF validation events
    DTMF_VALIDATION_STREAM_KEY_FORMAT = "dtmf_validation:{call_connection_id}"

    # ============================================================================
    # Core Event Handlers
    # ============================================================================

    @staticmethod
    async def handle_dtmf_recognition_start_requested(
        context: CallEventContext,
    ) -> None:
        """
        Handle request to start DTMF recognition.

        This is a custom V1 event that can be triggered anywhere in the call lifecycle
        to start DTMF recognition. It provides a clean, reusable way to initiate DTMF
        processing regardless of when it's needed.
        """
        with tracer.start_as_current_span(
            "v1.handle_dtmf_recognition_start_requested",
            kind=SpanKind.INTERNAL,
            attributes={
                "call.connection.id": context.call_connection_id,
                "event.type": context.event_type,
                "dtmf.operation": "start_recognition",
            },
        ) as span:
            logger.info(
                f"DTMF recognition start requested: {context.call_connection_id}"
            )

            if not context.acs_caller:
                logger.error("❌ ACS caller not available for DTMF recognition")
                span.set_status(trace.Status(trace.StatusCode.ERROR, "No ACS caller"))
                return

            # Get target phone from call (async call)
            call_conn = context.acs_caller.get_call_connection(
                context.call_connection_id
            )

            # Start DTMF recognition in a non-blocking way using an executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: call_conn.start_continuous_dtmf_recognition(
                    target_participant=DTMFValidationLifecycle._get_target_participant(
                        call_conn
                    ),
                    operation_context=f"dtmf_recognition_{context.call_connection_id}",
                ),
            )

    @staticmethod
    def is_dtmf_validation_gate_open(memory_manager, call_connection_id: str) -> bool:
        """
        Check if DTMF validation gate is open (validation completed).

        Args:
            memory_manager: Memory manager instance
            call_connection_id: Call connection ID for logging

        Returns:
            bool: True if validation gate is open, False if blocked
        """
        if not memory_manager:
            # No memory manager - fail open for safety
            return True

        try:
            # Check the validation gate status
            gate_open = memory_manager.get_context("dtmf_validation_gate_open", False)

            if not gate_open:
                logger.debug(
                    f"🔒 DTMF validation gate CLOSED for call {call_connection_id}"
                )

            return gate_open

        except Exception as e:
            logger.warning(
                f"⚠️ Error checking DTMF validation gate for call {call_connection_id}: {e}. Failing open."
            )
            # Fail open to avoid blocking system on errors
            return True

    # ============================================================================
    # AWS Connect Validation Flow
    # ============================================================================

    @staticmethod
    async def setup_aws_connect_validation_flow(
        context: CallEventContext, call_conn: CallConnectionClient
    ) -> None:
        """Set up AWS Connect-style validation flow."""
        try:
            # Generate 3 random validation digits
            validation_digits = "".join(random.choices(string.digits, k=3))
            logger.info(f"🔐 AWS Connect validation setup: digits={validation_digits}")

            # Update context to track validation state
            if context.memo_manager:
                context.memo_manager.set_context("aws_connect_validation_pending", True)
                context.memo_manager.set_context(
                    "aws_connect_validation_digits", validation_digits
                )
                context.memo_manager.set_context("aws_connect_input_sequence", "")

                if context.redis_mgr:
                    await context.memo_manager.persist_to_redis_async(context.redis_mgr)

            # Start DTMF recognition
            await DTMFValidationLifecycle._start_dtmf_recognition(context, call_conn)

        except Exception as e:
            logger.error(f"❌ Error setting up AWS Connect validation flow: {e}")

    async def handle_dtmf_tone_received(context: CallEventContext) -> None:
        """Handle incoming DTMF tones."""
        try:
            if not context.memo_manager:
                return

            # Get the latest DTMF tone
            tone = context.get_event_data().get("tone")
            logger.info(f"🔢 Received DTMF tone: {tone}")
            sequence_id = context.get_event_data().get("sequenceId")

            logger.info(f"🔢 DTMF tone received: {tone}, sequence_id: {sequence_id}")

            if tone:
                tone = DTMFValidationLifecycle._normalize_tone(tone)

            # Handle the tone based on the current validation state
            if context.memo_manager.get_context(
                "aws_connect_validation_pending", False
            ):
                await DTMFValidationLifecycle._handle_aws_connect_validation_tone(
                    context, tone
                )
            else:
                # Append the received tone to the current dtmf_tone context
                current_tones = context.memo_manager.get_context("dtmf_tone", "")
                updated_tones = current_tones + tone
                context.memo_manager.set_context("dtmf_tone", updated_tones)
                logger.info(f"🔢 DTMF tone sequence updated: {updated_tones}")

                await context.memo_manager.persist_to_redis_async(context.redis_mgr)

        except Exception as e:
            logger.error(f"❌ Error handling DTMF tone: {e}")

    @staticmethod
    def get_fresh_dtmf_validation_status(
        memory_manager, call_connection_id: str
    ) -> bool:
        """
        Get the most current DTMF validation status.

        This method uses the locally cached context which gets refreshed periodically
        from parallel streams via the adaptive refresh mechanism.

        Args:
            memory_manager: Memory manager instance
            call_connection_id: Call connection ID for logging

        Returns:
            bool: True if DTMF validation is complete, False otherwise
        """
        if not memory_manager:
            # No memory manager - fail open for performance
            return True

        try:
            # Use local context which gets refreshed from Redis periodically
            dtmf_validated = memory_manager.get_context("dtmf_validated", False)
            return dtmf_validated
        except Exception as e:
            logger.warning(
                f"Error getting DTMF validation status for call {call_connection_id}: {e}, assuming validated"
            )
            # Fail open - assume validated to avoid blocking audio processing
            return True

    # ============================================================================
    # Helper Methods (Simplified)
    # ============================================================================

    @staticmethod
    def _normalize_tone(tone: str) -> Optional[str]:
        """Normalize DTMF tone to standard format."""
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
            "#": "#",
            "pound": "#",
        }

        return tone_map.get(tone_str)

    @staticmethod
    def _update_dtmf_sequence(
        context: CallEventContext, tone: str, sequence_id: Optional[int]
    ) -> None:
        """Update DTMF sequence in memory (simplified)."""
        if not context.memo_manager:
            return

        current_sequence = context.memo_manager.get_context("dtmf_sequence", "")

        # Handle special tones
        if tone == "#":
            # End sequence marker
            new_sequence = current_sequence + tone
            logger.info(f"🔢 DTMF sequence completed with #: {new_sequence}")
        elif tone == "*":
            # Clear sequence
            new_sequence = ""
            logger.info("🔄 DTMF sequence cleared with *")
        else:
            # Handle sequence ordering (sequence_id helps put tones in place)
            if sequence_id is not None:
                # TODO: Implement sequence ordering if needed
                # For now, just append in order received
                new_sequence = current_sequence + tone
            else:
                # Simple append
                new_sequence = current_sequence + tone

        # Update context
        context.memo_manager.update_context("dtmf_sequence", new_sequence)
        if context.redis_mgr:
            asyncio.create_task(
                context.redis_mgr.set_value_async(
                    f"dtmf_sequence:{context.call_connection_id}",
                    new_sequence,
                    ttl_seconds=300,
                )
            )

        logger.info(f"🔢 DTMF sequence updated: {new_sequence}")

    @staticmethod
    async def _start_dtmf_recognition(
        context: CallEventContext, call_conn: CallConnectionClient
    ) -> None:
        """Start DTMF recognition (simplified)."""
        try:
            # Get target participant (caller)
            participants = call_conn.list_participants()
            caller_participant = None

            for participant in participants:
                if (
                    hasattr(participant.identifier, "kind")
                    and participant.identifier.kind == "phone_number"
                ):
                    caller_participant = participant
                    break

            if caller_participant:
                call_conn.start_continuous_dtmf_recognition(
                    target_participant=caller_participant.identifier,
                    operation_context=f"dtmf_recognition_{context.call_connection_id}",
                )
                logger.info(
                    f"Started DTMF recognition for {context.call_connection_id}"
                )
            else:
                logger.warning("⚠️ No caller participant found for DTMF recognition")

        except Exception as e:
            logger.error(f"❌ Error starting DTMF recognition: {e}")

    @classmethod
    async def cancel_call_for_dtmf_failure(
        cls,
        call_connection_id: str,
        acs_caller: Optional[Any],
        reason: str,
    ) -> bool:
        """Public entry point for tests and handlers to cancel the call on DTMF failure."""
        return await cls._cancel_call_for_validation_failure(
            call_connection_id, acs_caller, reason
        )

    @classmethod
    async def _cancel_call_for_validation_failure(
        cls,
        call_connection_id: str,
        acs_caller: Optional[Any],
        reason: str,
    ) -> bool:
        """Hang up the active call when validation fails or times out."""
        if not acs_caller:
            logger.warning(
                "⚠️ Cannot cancel call %s: ACS caller unavailable (%s)",
                call_connection_id,
                reason,
            )
            return False

        terminator = getattr(acs_caller, "session_terminator", None)
        if terminator is None and SessionTerminator:
            try:
                terminator = SessionTerminator(acs_caller)
            except Exception as exc:  # pragma: no cover
                logger.debug(
                    "SessionTerminator initialization failed for %s: %s",
                    call_connection_id,
                    exc,
                )
                terminator = None

        if terminator and await cls._try_session_termination(
            terminator, call_connection_id, reason
        ):
            return True

        try:
            call_conn = acs_caller.get_call_connection(call_connection_id)
        except Exception as exc:
            logger.error(
                "❌ Failed to resolve call connection %s for cancellation: %s",
                call_connection_id,
                exc,
            )
            return False

        if not call_conn:
            logger.warning(
                "⚠️ No active call connection for %s – nothing to cancel", call_connection_id
            )
            return False

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, lambda: call_conn.hang_up(is_for_everyone=True)
            )
            logger.info(
                "☎️ Call %s cancelled via direct hang-up: %s",
                call_connection_id,
                reason,
            )
            return True
        except Exception as exc:
            logger.error(
                "❌ Failed to cancel call %s after validation failure: %s",
                call_connection_id,
                exc,
            )
            return False

    @staticmethod
    async def _try_session_termination(terminator: Any, call_connection_id: str, reason: str) -> bool:
        """Attempt session termination using the provided terminator."""
        try:
            cancel = getattr(terminator, "cancel_call_with_reason", None)
            if callable(cancel):
                maybe = cancel(call_connection_id, reason)
                if asyncio.iscoroutine(maybe):
                    await maybe
                logger.info(
                    "☎️ Call %s cancelled via SessionTerminator.cancel_call_with_reason",
                    call_connection_id,
                )
                return True

            end_async = getattr(terminator, "end_call_async", None)
            if callable(end_async):
                maybe = end_async(call_connection_id, reason=reason)
                if asyncio.iscoroutine(maybe):
                    await maybe
                logger.info(
                    "☎️ Call %s cancelled via SessionTerminator.end_call_async",
                    call_connection_id,
                )
                return True
        except Exception as exc:
            logger.debug(
                "Session terminator cancellation failed for %s: %s",
                call_connection_id,
                exc,
            )
        return False

    @classmethod
    def _validate_sequence(cls, sequence: Optional[str]) -> bool:
        """Return True when the DTMF sequence is non-empty and contains only digits."""
        return bool(sequence) and sequence.isdigit()
