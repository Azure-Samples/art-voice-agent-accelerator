"""
Tests for ACS managed identity authentication.

Validates that Call Automation, Email (ECS), and SMS clients correctly
prefer managed identity when an endpoint is configured and the env-var
override / auto-detect heuristic allows it, while still honoring connection
strings as a fallback for local development.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# utils.azure_auth.should_use_managed_identity_for_acs
# ---------------------------------------------------------------------------


def test_should_use_mi_explicit_true(monkeypatch):
    from utils.azure_auth import should_use_managed_identity_for_acs

    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "true")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("MSI_ENDPOINT", raising=False)
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)

    assert should_use_managed_identity_for_acs() is True


def test_should_use_mi_explicit_false(monkeypatch):
    from utils.azure_auth import should_use_managed_identity_for_acs

    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "false")
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000000")

    assert should_use_managed_identity_for_acs() is False


def test_should_use_mi_autodetect_in_azure(monkeypatch):
    from utils.azure_auth import should_use_managed_identity_for_acs

    monkeypatch.delenv("ACS_USE_MANAGED_IDENTITY", raising=False)
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000000")

    assert should_use_managed_identity_for_acs() is True


def test_should_use_mi_autodetect_local(monkeypatch):
    from utils.azure_auth import should_use_managed_identity_for_acs

    monkeypatch.delenv("ACS_USE_MANAGED_IDENTITY", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("MSI_ENDPOINT", raising=False)
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)

    assert should_use_managed_identity_for_acs() is False


# ---------------------------------------------------------------------------
# src.acs.acs_helper.AcsCaller — prefers MI when endpoint is provided.
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_credential(monkeypatch):
    cred = SimpleNamespace(name="stub-credential")
    monkeypatch.setattr("src.acs.acs_helper.get_credential", lambda: cred)
    return cred


def test_acs_caller_prefers_managed_identity_when_endpoint_set(
    monkeypatch, stub_credential
):
    """When endpoint + MI override are present, MI wins over connection string."""
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "true")

    captured = {}

    class StubCallAutomationClient:
        def __init__(self, endpoint=None, credential=None):
            captured["mode"] = "credential"
            captured["endpoint"] = endpoint
            captured["credential"] = credential

        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            captured["conn_str"] = conn_str
            return cls()

    monkeypatch.setattr("src.acs.acs_helper.CallAutomationClient", StubCallAutomationClient)

    from src.acs.acs_helper import AcsCaller

    AcsCaller(
        source_number="+15555550100",
        callback_url="https://example.test/api/cb",
        acs_connection_string="endpoint=https://x.communication.azure.com/;accesskey=key",
        acs_endpoint="https://x.communication.azure.com/",
    )

    assert captured["mode"] == "credential"
    assert captured["endpoint"] == "https://x.communication.azure.com/"
    assert captured["credential"] is stub_credential


def test_acs_caller_falls_back_to_connection_string_when_mi_disabled(
    monkeypatch, stub_credential
):
    """With MI explicitly disabled, connection string is used even if endpoint is set."""
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "false")

    captured = {}

    class StubCallAutomationClient:
        def __init__(self, endpoint=None, credential=None):
            captured["mode"] = "credential"

        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            captured["conn_str"] = conn_str
            return cls.__new__(cls)

    monkeypatch.setattr("src.acs.acs_helper.CallAutomationClient", StubCallAutomationClient)

    from src.acs.acs_helper import AcsCaller

    AcsCaller(
        source_number="+15555550100",
        callback_url="https://example.test/api/cb",
        acs_connection_string="endpoint=https://x.communication.azure.com/;accesskey=key",
        acs_endpoint="https://x.communication.azure.com/",
    )

    assert captured["mode"] == "conn_string"


def test_acs_caller_uses_mi_when_only_endpoint_provided(monkeypatch, stub_credential):
    """No connection string + endpoint => MI even with override absent."""
    monkeypatch.delenv("ACS_USE_MANAGED_IDENTITY", raising=False)

    captured = {}

    class StubCallAutomationClient:
        def __init__(self, endpoint=None, credential=None):
            captured["mode"] = "credential"
            captured["endpoint"] = endpoint

    monkeypatch.setattr("src.acs.acs_helper.CallAutomationClient", StubCallAutomationClient)

    from src.acs.acs_helper import AcsCaller

    AcsCaller(
        source_number="+15555550100",
        callback_url="https://example.test/api/cb",
        acs_endpoint="https://x.communication.azure.com/",
    )

    assert captured["mode"] == "credential"
    assert captured["endpoint"] == "https://x.communication.azure.com/"


# ---------------------------------------------------------------------------
# src.acs.email_service.EmailService — ECS data plane uses ACS endpoint + MI.
# ---------------------------------------------------------------------------


def _reload_email_module():
    """Reload email_service after env var changes so module-level globals refresh."""
    sys.modules.pop("src.acs.email_service", None)
    return importlib.import_module("src.acs.email_service")


def test_email_service_prefers_managed_identity(monkeypatch):
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "true")
    monkeypatch.setenv("ACS_ENDPOINT", "https://x.communication.azure.com/")
    monkeypatch.setenv("AZURE_EMAIL_SENDER_ADDRESS", "noreply@example.com")
    monkeypatch.setenv(
        "AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING",
        "endpoint=https://x.communication.azure.com/;accesskey=key",
    )

    email_mod = _reload_email_module()

    captured = {}

    class StubEmailClient:
        def __init__(self, endpoint, credential):
            captured["mode"] = "credential"
            captured["endpoint"] = endpoint
            captured["credential"] = credential

        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            return cls("x", "y")

    stub_cred = SimpleNamespace(name="stub-credential")
    monkeypatch.setattr(email_mod, "EmailClient", StubEmailClient)
    monkeypatch.setattr(email_mod, "get_credential", lambda: stub_cred)
    monkeypatch.setattr(email_mod, "AZURE_EMAIL_AVAILABLE", True)

    service = email_mod.EmailService()

    assert captured["mode"] == "credential"
    assert captured["endpoint"] == "https://x.communication.azure.com/"
    assert captured["credential"] is stub_cred
    assert service.is_configured() is True


def test_email_service_uses_connection_string_when_mi_disabled(monkeypatch):
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "false")
    monkeypatch.setenv("ACS_ENDPOINT", "https://x.communication.azure.com/")
    monkeypatch.setenv("AZURE_EMAIL_SENDER_ADDRESS", "noreply@example.com")
    monkeypatch.setenv(
        "AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING",
        "endpoint=https://x.communication.azure.com/;accesskey=key",
    )

    email_mod = _reload_email_module()

    captured = {}

    class StubEmailClient:
        def __init__(self, endpoint, credential):
            captured["mode"] = "credential"

        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            captured["conn_str"] = conn_str
            return cls.__new__(cls)

    monkeypatch.setattr(email_mod, "EmailClient", StubEmailClient)
    monkeypatch.setattr(email_mod, "AZURE_EMAIL_AVAILABLE", True)

    email_mod.EmailService()

    assert captured["mode"] == "conn_string"


# ---------------------------------------------------------------------------
# src.acs.sms_service.SmsService — MI support (new behavior).
# ---------------------------------------------------------------------------


def _reload_sms_module():
    sys.modules.pop("src.acs.sms_service", None)
    return importlib.import_module("src.acs.sms_service")


def test_sms_service_prefers_managed_identity(monkeypatch):
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "true")
    monkeypatch.setenv("ACS_ENDPOINT", "https://x.communication.azure.com/")
    monkeypatch.setenv("AZURE_SMS_FROM_PHONE_NUMBER", "+15555550100")
    monkeypatch.setenv(
        "AZURE_COMMUNICATION_SMS_CONNECTION_STRING",
        "endpoint=https://x.communication.azure.com/;accesskey=key",
    )

    sms_mod = _reload_sms_module()

    captured = {}

    class StubSmsClient:
        def __init__(self, endpoint, credential):
            captured["mode"] = "credential"
            captured["endpoint"] = endpoint
            captured["credential"] = credential

        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            return cls("x", "y")

    stub_cred = SimpleNamespace(name="stub-credential")
    monkeypatch.setattr(sms_mod, "SmsClient", StubSmsClient)
    monkeypatch.setattr(sms_mod, "get_credential", lambda: stub_cred)
    monkeypatch.setattr(sms_mod, "AZURE_SMS_AVAILABLE", True)

    service = sms_mod.SmsService()

    assert captured["mode"] == "credential"
    assert captured["endpoint"] == "https://x.communication.azure.com/"
    assert captured["credential"] is stub_cred
    assert service.is_configured() is True


def test_sms_service_uses_endpoint_mi_when_no_connection_string(monkeypatch):
    """The previous SMS implementation had NO MI path — verify the new fallback works."""
    monkeypatch.delenv("ACS_USE_MANAGED_IDENTITY", raising=False)
    monkeypatch.delenv("AZURE_COMMUNICATION_SMS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("ACS_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("ACS_ENDPOINT", "https://x.communication.azure.com/")
    monkeypatch.setenv("AZURE_SMS_FROM_PHONE_NUMBER", "+15555550100")
    # Simulate Azure-hosted environment so auto-detect picks MI.
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000000")

    sms_mod = _reload_sms_module()

    captured = {}

    class StubSmsClient:
        def __init__(self, endpoint, credential):
            captured["mode"] = "credential"
            captured["endpoint"] = endpoint

    stub_cred = SimpleNamespace(name="stub-credential")
    monkeypatch.setattr(sms_mod, "SmsClient", StubSmsClient)
    monkeypatch.setattr(sms_mod, "get_credential", lambda: stub_cred)
    monkeypatch.setattr(sms_mod, "AZURE_SMS_AVAILABLE", True)

    service = sms_mod.SmsService()

    assert captured["mode"] == "credential"
    assert service.is_configured() is True


def test_sms_service_falls_back_to_connection_string(monkeypatch):
    monkeypatch.setenv("ACS_USE_MANAGED_IDENTITY", "false")
    monkeypatch.setenv("AZURE_SMS_FROM_PHONE_NUMBER", "+15555550100")
    monkeypatch.setenv(
        "AZURE_COMMUNICATION_SMS_CONNECTION_STRING",
        "endpoint=https://x.communication.azure.com/;accesskey=key",
    )

    sms_mod = _reload_sms_module()

    captured = {}

    class StubSmsClient:
        @classmethod
        def from_connection_string(cls, conn_str):
            captured["mode"] = "conn_string"
            captured["conn_str"] = conn_str
            return cls.__new__(cls)

    monkeypatch.setattr(sms_mod, "SmsClient", StubSmsClient)
    monkeypatch.setattr(sms_mod, "AZURE_SMS_AVAILABLE", True)

    sms_mod.SmsService()

    assert captured["mode"] == "conn_string"
    assert "accesskey=key" in captured["conn_str"]
