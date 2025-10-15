"""Azure Speech authentication helpers.

Provides a shared token manager that wraps the repo's credential helper and
applies Azure AD tokens to Speech SDK configurations with proper refresh and
thread-safety. This centralises AAD token handling for both TTS and STT flows.
"""
from __future__ import annotations

import os
import threading
import time
from functools import lru_cache
from typing import Optional

import azure.cognitiveservices.speech as speechsdk
from azure.core.credentials import AccessToken, TokenCredential

from utils.azure_auth import get_credential
from utils.ml_logging import get_logger

logger = get_logger(__name__)

# Speech service scope for Azure AD tokens
_SPEECH_SCOPE = "https://cognitiveservices.azure.com/.default"
# Refresh the cached token a little before it actually expires
_REFRESH_SKEW_SECONDS = 120


class SpeechTokenManager:
    """Caches Azure AD tokens and applies them to Speech SDK configs."""

    def __init__(self, credential: TokenCredential, resource_id: str) -> None:
        if not resource_id:
            raise ValueError(
                "AZURE_SPEECH_RESOURCE_ID is required for Azure AD authentication"
            )
        self._credential = credential
        self._resource_id = resource_id
        self._token_lock = threading.Lock()
        self._cached_token: Optional[AccessToken] = None

    @property
    def resource_id(self) -> str:
        return self._resource_id

    def _needs_refresh(self) -> bool:
        if not self._cached_token:
            return True
        expiry_buffer = self._cached_token.expires_on - _REFRESH_SKEW_SECONDS
        return time.time() >= expiry_buffer

    def get_token(self, force_refresh: bool = False) -> AccessToken:
        """Return a valid Azure AD token, refreshing if required."""
        with self._token_lock:
            if force_refresh or self._needs_refresh():
                logger.debug("Fetching new Azure Speech AAD token")
                token = self._credential.get_token(_SPEECH_SCOPE)
                self._cached_token = token
            token = self._cached_token
            if token is None:
                raise RuntimeError("Failed to obtain Azure Speech token")
            return token

    def apply_to_config(
        self, speech_config: speechsdk.SpeechConfig, *, force_refresh: bool = False
    ) -> None:
        """Attach the latest AAD token to the provided speech configuration."""
        token = self.get_token(force_refresh=force_refresh)
        speech_config.authorization_token = token.token
        try:
            speech_config.set_property_by_name(
                "SpeechServiceConnection_AuthorizationType", "aad"
            )
        except Exception as exc:
            logger.debug(
                "AuthorizationType property not supported by SDK: %s", exc
            )

        try:
            speech_config.set_property_by_name(
                "SpeechServiceConnection_AzureResourceId", self._resource_id
            )
        except Exception as exc:
            logger.warning(
                "Failed to set SpeechServiceConnection_AzureResourceId: %s", exc
            )


@lru_cache(maxsize=1)
def get_speech_token_manager() -> SpeechTokenManager:
    """Return the shared speech token manager for Azure AD auth."""
    credential = get_credential()
    resource_id = os.getenv("AZURE_SPEECH_RESOURCE_ID")
    if not resource_id:
        raise ValueError(
            "AZURE_SPEECH_RESOURCE_ID must be set when using Azure AD authentication"
        )
    return SpeechTokenManager(credential=credential, resource_id=resource_id)
