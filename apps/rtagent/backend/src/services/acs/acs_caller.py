"""
services/acs_caller.py
----------------------
Thin wrapper that creates (or returns) the AcsCaller helper you already
have in `src.acs.acs_helper`.  Splitting it out lets `main.py`
initialise it once during startup and any router import it later.
"""

from __future__ import annotations

from typing import Optional

from config import (
    ACS_CALL_CALLBACK_PATH,
    ACS_CONNECTION_STRING,
    ACS_ENDPOINT,
    ACS_SOURCE_PHONE_NUMBER,
    ACS_WEBSOCKET_PATH,
    AZURE_SPEECH_ENDPOINT,
    AZURE_STORAGE_CONTAINER_URL,
    BASE_URL,
)
from apps.rtagent.backend.src.services.acs.acs_helpers import construct_websocket_url
from src.acs.acs_helper import AcsCaller
from utils.ml_logging import get_logger

logger = get_logger("services.acs_caller")

# Singleton instance (created on first call)
_instance: Optional[AcsCaller] = None


def initialize_acs_caller_instance() -> Optional[AcsCaller]:
    """
    Initialize and cache Azure Communication Services caller instance for telephony operations.

    This function creates a singleton AcsCaller instance configured with environment
    variables for outbound calling capabilities. It validates required configuration
    parameters and constructs appropriate callback and WebSocket URLs for ACS
    integration with the voice agent system.

    :return: Configured AcsCaller instance if environment variables are properly set, None otherwise.
    :raises ValueError: If required ACS configuration parameters are missing or invalid.
    """
    global _instance  # noqa: PLW0603
    if _instance:
        return _instance

    if not all([ACS_SOURCE_PHONE_NUMBER, BASE_URL]):
        logger.warning("ACS env vars not fully configured – outbound calling disabled")
        return None

    callback_url = f"{BASE_URL.rstrip('/')}{ACS_CALL_CALLBACK_PATH}"
    ws_url = construct_websocket_url(BASE_URL, ACS_WEBSOCKET_PATH)
    if not ws_url:
        logger.error(
            "Could not build ACS media WebSocket URL; disabling outbound calls"
        )
        return None

    try:
        _instance = AcsCaller(
            source_number=ACS_SOURCE_PHONE_NUMBER,
            acs_connection_string=ACS_CONNECTION_STRING,
            acs_endpoint=ACS_ENDPOINT,
            callback_url=callback_url,
            websocket_url=ws_url,
            cognitive_services_endpoint=AZURE_SPEECH_ENDPOINT,
            recording_storage_container_url=AZURE_STORAGE_CONTAINER_URL,
        )
        logger.info("AcsCaller initialised")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to initialise AcsCaller: %s", exc, exc_info=True)
        _instance = None
    return _instance
