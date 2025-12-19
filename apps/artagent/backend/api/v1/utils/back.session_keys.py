"""Session identifier helpers for mapping ACS calls to persistent memo sessions."""

from __future__ import annotations

import re

from utils.ml_logging import get_logger

logger = get_logger("v1.utils.session_keys")

_CALL_PHONE_IDENTIFIER_PREFIX = "call_phone_identifier"
_CALL_MEMO_SESSION_PREFIX = "call_memo_session_map"
_PHONE_SESSION_PREFIX = "phone"
_SESSION_KEY_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _call_phone_key(call_connection_id: str) -> str:
    return f"{_CALL_PHONE_IDENTIFIER_PREFIX}:{call_connection_id}"


def normalize_phone_identifier(raw_identifier: str | None) -> str | None:
    """Return a sanitized, E.164-like phone identifier for Redis keys."""
    if not raw_identifier:
        return None

    candidate = str(raw_identifier).strip()
    if not candidate:
        return None

    digits = re.sub(r"[^0-9]", "", candidate)
    if not digits:
        return None

    if candidate.startswith("+"):
        return f"+{digits}"

    return f"+{digits}"


def build_phone_session_id(normalized_phone: str) -> str:
    return f"{_PHONE_SESSION_PREFIX}:{normalized_phone}"


async def persist_call_phone_identifier(
    redis_mgr,
    call_connection_id: str | None,
    raw_phone: str | None,
    *,
    ttl_seconds: int = _SESSION_KEY_TTL_SECONDS,
) -> str | None:
    """Persist the normalized phone identifier for a call connection."""
    normalized = normalize_phone_identifier(raw_phone)
    if not normalized or not call_connection_id or redis_mgr is None:
        return normalized

    try:
        await redis_mgr.set_value_async(
            _call_phone_key(call_connection_id),
            normalized,
            ttl_seconds=ttl_seconds,
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to persist phone identifier for %s", call_connection_id, exc_info=True)
    return normalized


async def fetch_call_phone_identifier(redis_mgr, call_connection_id: str | None) -> str | None:
    if redis_mgr is None or not call_connection_id:
        return None
    try:
        value = await redis_mgr.get_value_async(_call_phone_key(call_connection_id))
    except Exception:  # noqa: BLE001
        logger.debug("Failed to fetch phone identifier for %s", call_connection_id, exc_info=True)
        return None

    if not value:
        return None

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    return str(value)


async def resolve_memo_session_id(
    redis_mgr,
    call_connection_id: str | None,
    fallback_session_id: str | None = None,
) -> str | None:
    """Resolve the memo session identifier using stored phone mappings when available."""
    if redis_mgr and call_connection_id:
        try:
            cached_override = await redis_mgr.get_value_async(
                f"{_CALL_MEMO_SESSION_PREFIX}:{call_connection_id}"
            )
        except Exception:  # noqa: BLE001
            cached_override = None

        if cached_override:
            if isinstance(cached_override, (bytes, bytearray)):
                try:
                    cached_override = cached_override.decode("utf-8")
                except Exception:  # noqa: BLE001
                    cached_override = cached_override.decode("utf-8", errors="ignore")
            return str(cached_override)

    normalized = await fetch_call_phone_identifier(redis_mgr, call_connection_id)
    if normalized:
        return build_phone_session_id(normalized)
    return fallback_session_id or call_connection_id


__all__ = [
    "normalize_phone_identifier",
    "build_phone_session_id",
    "persist_call_phone_identifier",
    "fetch_call_phone_identifier",
    "resolve_memo_session_id",
]
