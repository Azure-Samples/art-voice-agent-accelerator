from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import WebSocket
from opentelemetry import trace

from .auth import run_auth_agent
from .cm_utils import cm_get, cm_set, get_correlation_context
from .config import ENTRY_AGENT
from .registry import (
    get_specialist,
    register_specialist,
)
from .specialists import run_claims_agent, run_general_agent
from .termination import maybe_terminate_if_escalated
from apps.rtagent.backend.src.utils.tracing import (
    create_service_dependency_attrs,
    create_service_handler_attrs,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


async def route_turn(
    cm: "MemoManager",
    transcript: str,
    ws: WebSocket,
    *,
    is_acs: bool,
) -> None:
    """
    Handle one user turn plus immediate follow-ups (behavior-preserving).

    :param cm: MemoManager
    :param transcript: User transcript text
    :param ws: WebSocket
    :param is_acs: Whether this turn is part of an ACS phone call
    :return: None
    """
    if cm is None:
        logger.error("MemoManager (cm) is None - cannot process orchestration")
        raise ValueError("MemoManager (cm) parameter cannot be None")

    call_connection_id, session_id = get_correlation_context(ws, cm)

    # Start a per-turn latency run id
    try:
        run_id = ws.state.lt.begin_run(label="turn")
        if hasattr(ws.state.lt, "set_current_run"):
            ws.state.lt.set_current_run(run_id)
    except Exception:
        run_id = uuid.uuid4().hex[:12]
    cm_set(cm, current_run_id=run_id)

    # Initialize with entry agent if not authenticated yet
    if (not cm_get(cm, "authenticated", False)) and cm_get(cm, "active_agent") != ENTRY_AGENT:
        cm_set(cm, active_agent=ENTRY_AGENT)

    span_attrs = create_service_handler_attrs(
        service_name="orchestrator",
        call_connection_id=call_connection_id,
        session_id=session_id,
        operation="route_turn",
        transcript_length=len(transcript),
        is_acs=is_acs,
        authenticated=cm_get(cm, "authenticated", False),
        active_agent=cm_get(cm, "active_agent", "none"),
    )
    span_attrs["run.id"] = run_id

    with tracer.start_as_current_span("orchestrator.route_turn", attributes=span_attrs) as span:
        redis_mgr = ws.app.state.redis

        try:
            # 1) Check escalation (any agent)
            if await maybe_terminate_if_escalated(cm, ws, is_acs=is_acs):
                return

            # 2) Dispatch to active agent
            active: str = cm_get(cm, "active_agent") or ENTRY_AGENT
            span.set_attribute("orchestrator.stage", "specialist_dispatch")
            span.set_attribute("orchestrator.target_agent", active)
            span.set_attribute("run.id", run_id)

            handler = get_specialist(active)
            if handler is None:
                logger.warning("Unknown active_agent=%s session=%s", active, cm.session_id)
                span.set_attribute("orchestrator.error", "unknown_agent")
                return

            agent_attrs = create_service_dependency_attrs(
                source_service="orchestrator",
                target_service=active.lower() + "_agent",
                call_connection_id=call_connection_id,
                session_id=session_id,
                operation="process_turn",
                transcript_length=len(transcript),
            )
            agent_attrs["run.id"] = run_id

            with tracer.start_as_current_span(f"orchestrator.call_{active.lower()}_agent", attributes=agent_attrs):
                await handler(cm, transcript, ws, is_acs=is_acs)

                # 3) Terminate if escalated by the handler
                if await maybe_terminate_if_escalated(cm, ws, is_acs=is_acs):
                    return

        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("route_turn crash – session=%s", cm.session_id)
            span.set_attribute("orchestrator.error", "exception")
            raise
        finally:
            # Non-blocking persistence (same as original)
            await cm.persist_background(redis_mgr)


def bind_default_handlers() -> None:
    """
    Register default agent handlers to preserve current behavior.
    """
    register_specialist("AutoAuth", run_auth_agent)
    register_specialist("General", run_general_agent)
    register_specialist("Claims", run_claims_agent)
