"""ACS call transfer helpers centralised for VoiceLive and ACS handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.src.services.acs.acs_caller import initialize_acs_caller_instance
from azure.communication.callautomation import (
    CallAutomationClient,
    CallConnectionClient,
    CommunicationIdentifier,
    PhoneNumberIdentifier,
)
from azure.core.exceptions import HttpResponseError
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.acs.acs_helper import AcsCaller
from utils.ml_logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing assistance only
    from azure.communication.callautomation import CallParticipant
else:  # noqa: D401 - runtime alias for older SDKs lacking CallParticipant export
    CallParticipant = Any  # type: ignore[assignment]

logger = get_logger("services.acs.call_transfer")
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True)
class TransferRequest:
    """Normalized payload for initiating an ACS call transfer."""

    call_connection_id: str
    target_address: str
    operation_context: str | None = None
    operation_callback_url: str | None = None
    transferee: str | None = None
    transferee_identifier: CommunicationIdentifier | None = None
    sip_headers: Mapping[str, str] | None = None
    voip_headers: Mapping[str, str] | None = None
    source_caller_id: str | None = None


def _build_target_identifier(target: str) -> CommunicationIdentifier:
    """Convert a transfer target string into the appropriate ACS identifier."""

    normalized = (target or "").strip()
    if not normalized:
        raise ValueError("Transfer target must be a non-empty string.")
    if normalized.lower().startswith("sip:"):
        return PhoneNumberIdentifier(normalized)
    return PhoneNumberIdentifier(normalized)


def _build_optional_phone(number: str | None) -> PhoneNumberIdentifier | None:
    if not number:
        return None
    return PhoneNumberIdentifier(number)


def _build_optional_target(target: str | None) -> CommunicationIdentifier | None:
    if not target:
        return None
    return _build_target_identifier(target)


def _prepare_transfer_args(request: TransferRequest) -> tuple[str, dict[str, Any]]:
    identifier = _build_target_identifier(request.target_address)
    kwargs: dict[str, Any] = {}
    if request.operation_context:
        kwargs["operation_context"] = request.operation_context
    if request.operation_callback_url:
        kwargs["operation_callback_url"] = request.operation_callback_url
    transferee_identifier = request.transferee_identifier or _build_optional_target(
        request.transferee
    )
    if transferee_identifier:
        kwargs["transferee"] = transferee_identifier
    if request.sip_headers:
        kwargs["sip_headers"] = dict(request.sip_headers)
    if request.voip_headers:
        kwargs["voip_headers"] = dict(request.voip_headers)
    source_identifier = _build_optional_phone(request.source_caller_id)
    if source_identifier:
        kwargs["source_caller_id_number"] = source_identifier
    return request.call_connection_id, {"target": identifier, "kwargs": kwargs}


async def _invoke_transfer(
    *,
    call_conn: CallConnectionClient,
    identifier: CommunicationIdentifier,
    kwargs: dict[str, Any],
) -> Any:
    return await asyncio.to_thread(call_conn.transfer_call_to_participant, identifier, **kwargs)


async def transfer_call(
    *,
    call_connection_id: str,
    target_address: str,
    operation_context: str | None = None,
    operation_callback_url: str | None = None,
    transferee: str | None = None,
    sip_headers: Mapping[str, str] | None = None,
    voip_headers: Mapping[str, str] | None = None,
    source_caller_id: str | None = None,
    acs_caller: AcsCaller | None = None,
    acs_client: CallAutomationClient | None = None,
    call_connection: CallConnectionClient | None = None,
    transferee_identifier: CommunicationIdentifier | None = None,
    auto_detect_transferee: bool = False,
) -> dict[str, Any]:
    """Transfer the active ACS call to the specified target participant."""

    if not call_connection_id:
        return {"success": False, "message": "call_connection_id is required for call transfer."}
    if not target_address:
        return {"success": False, "message": "target address is required for call transfer."}

    caller = acs_caller or initialize_acs_caller_instance()
    client = acs_client or (caller.client if caller else None)
    if not client and not call_connection:
        return {"success": False, "message": "ACS CallAutomationClient is not configured."}

    conn = call_connection or client.get_call_connection(call_connection_id)
    if conn is None:
        return {
            "success": False,
            "message": f"Call connection '{call_connection_id}' is not available.",
        }

    if auto_detect_transferee and not transferee_identifier and not transferee:
        transferee_identifier = await _discover_transferee(conn)

    request = TransferRequest(
        call_connection_id=call_connection_id,
        target_address=target_address,
        operation_context=operation_context,
        operation_callback_url=operation_callback_url,
        transferee=transferee,
        transferee_identifier=transferee_identifier,
        sip_headers=sip_headers,
        voip_headers=voip_headers,
        source_caller_id=source_caller_id,
    )

    try:
        connection_id, prepared = _prepare_transfer_args(request)
    except ValueError as exc:
        logger.warning("Invalid call transfer parameters: %s", exc)
        return {"success": False, "message": str(exc)}

    attributes = {
        "call.connection.id": connection_id,
        "transfer.target": target_address,
    }
    if request.transferee:
        attributes["transfer.transferee"] = request.transferee
    if request.transferee_identifier:
        attributes["transfer.transferee_raw_id"] = getattr(
            request.transferee_identifier, "raw_id", str(request.transferee_identifier)
        )

    with tracer.start_as_current_span(
        "acs.transfer_call",
        kind=SpanKind.CLIENT,
        attributes=attributes,
    ) as span:
        try:
            result = await _invoke_transfer(
                call_conn=conn,
                identifier=prepared["target"],
                kwargs=prepared["kwargs"],
            )
        except HttpResponseError as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.error(
                "ACS transfer failed | call=%s target=%s error=%s",
                connection_id,
                target_address,
                exc,
            )
            return {
                "success": False,
                "message": "Call transfer failed due to an ACS error.",
                "error": str(exc),
            }
        except Exception as exc:  # pragma: no cover - defensive
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.exception(
                "Unexpected error during ACS transfer | call=%s target=%s",
                connection_id,
                target_address,
            )
            return {
                "success": False,
                "message": "Call transfer encountered an unexpected error.",
                "error": str(exc),
            }

        status_value = getattr(result, "status", "unknown")
        operation_context_value = getattr(result, "operation_context", operation_context)
        span.set_status(Status(StatusCode.OK))

        logger.info(
            "ACS transfer initiated | call=%s target=%s status=%s",
            connection_id,
            target_address,
            status_value,
        )

        return {
            "success": True,
            "message": f"Transferring the caller to {target_address}.",
            "call_transfer": {
                "status": str(status_value),
                "operation_context": operation_context_value,
                "target": target_address,
                "transferee": transferee
                or getattr(transferee_identifier, "raw_id", transferee_identifier),
            },
            "should_interrupt_playback": True,
            "terminate_session": True,
        }


async def _discover_transferee(
    call_conn: CallConnectionClient,
) -> CommunicationIdentifier | None:
    """Best-effort discovery of the active caller participant for transfer operations."""

    participants = await _list_participants(call_conn)
    if not participants:
        logger.warning("No participants returned when attempting to detect transferee.")
        return None

    identifier = _select_transferee_identifier(participants)
    if identifier:
        logger.debug(
            "Auto-detected transferee identifier: %s", getattr(identifier, "raw_id", identifier)
        )
    else:
        logger.warning("Unable to auto-detect transferee identifier from participants list.")
    return identifier


async def _list_participants(call_conn: CallConnectionClient) -> Iterable[CallParticipant]:
    """Fetch participants using whichever API the installed SDK exposes."""

    def _sync_list() -> Iterable[CallParticipant]:
        if hasattr(call_conn, "get_participants"):
            return call_conn.get_participants()  # type: ignore[attr-defined]
        if hasattr(call_conn, "list_participants"):
            return call_conn.list_participants()  # type: ignore[attr-defined]
        return []

    try:
        participants = await asyncio.to_thread(_sync_list)
        return (
            getattr(participants, "value", getattr(participants, "participants", participants))
            or []
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to list participants for transfer auto-detect: %s", exc)
        return []


def _select_transferee_identifier(
    participants: Iterable[CallParticipant],
) -> CommunicationIdentifier | None:
    """Pick the most appropriate candidate to transfer away (the active caller)."""

    phone_candidates: list[CommunicationIdentifier] = []
    other_candidates: list[CommunicationIdentifier] = []

    for participant in participants:
        identifier = getattr(participant, "identifier", None)
        if not isinstance(identifier, CommunicationIdentifier):
            continue

        if isinstance(identifier, PhoneNumberIdentifier):
            phone_candidates.append(identifier)
            continue

        raw_id = getattr(identifier, "raw_id", "")
        if isinstance(raw_id, str) and raw_id.startswith("4:"):
            phone_candidates.append(identifier)
            continue

        other_candidates.append(identifier)

    if phone_candidates:
        return phone_candidates[0]
    if other_candidates:
        return other_candidates[0]
    return None


__all__ = ["transfer_call"]
