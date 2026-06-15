from unittest.mock import MagicMock, patch

import pytest
from src.acs.acs_helper import AcsCaller, _normalize_acs_auth_mode

BASE_KWARGS = {
    "source_number": "+15551234567",
    "callback_url": "https://example.com/api/v1/calls/callbacks",
    "websocket_url": "wss://example.com/api/v1/media/stream",
    "acs_endpoint": "https://test.communication.azure.com",
}


def test_normalize_acs_auth_mode_aliases():
    assert _normalize_acs_auth_mode(None) == "auto"
    assert _normalize_acs_auth_mode("connection-string") == "connection_string"
    assert _normalize_acs_auth_mode("managed_identity") == "entra"


@patch("src.acs.acs_helper.get_credential")
@patch("src.acs.acs_helper.CallAutomationClient")
def test_auto_auth_uses_connection_string_when_present(mock_client, mock_get_credential):
    mock_client.from_connection_string.return_value = object()

    caller = AcsCaller(
        **BASE_KWARGS,
        acs_connection_string="endpoint=https://test.communication.azure.com/;accesskey=key",
        acs_auth_mode="auto",
    )

    assert caller.effective_auth_mode == "connection_string"
    mock_client.from_connection_string.assert_called_once_with(
        "endpoint=https://test.communication.azure.com/;accesskey=key"
    )
    mock_client.assert_not_called()
    mock_get_credential.assert_not_called()


@patch("src.acs.acs_helper.get_credential")
@patch("src.acs.acs_helper.CallAutomationClient")
def test_entra_auth_uses_endpoint_credential_even_when_connection_string_present(
    mock_client,
    mock_get_credential,
):
    credential = MagicMock(name="credential")
    mock_get_credential.return_value = credential

    caller = AcsCaller(
        **BASE_KWARGS,
        acs_connection_string="endpoint=https://test.communication.azure.com/;accesskey=stale",
        acs_auth_mode="entra",
    )

    assert caller.effective_auth_mode == "entra"
    mock_client.from_connection_string.assert_not_called()
    mock_get_credential.assert_called_once_with()
    mock_client.assert_called_once_with(
        endpoint="https://test.communication.azure.com",
        credential=credential,
    )


@patch("src.acs.acs_helper.CallAutomationClient")
def test_connection_string_auth_requires_connection_string(mock_client):
    with pytest.raises(ValueError, match="ACS_CONNECTION_STRING is required"):
        AcsCaller(
            **BASE_KWARGS,
            acs_connection_string="",
            acs_auth_mode="connection_string",
        )

    mock_client.from_connection_string.assert_not_called()
    mock_client.assert_not_called()
