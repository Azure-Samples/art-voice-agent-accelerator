"""Read-only discovery of the configured communication services."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from apps.artagent.backend.config.settings import get_communication_provider_settings
from src.acs.acs_helper import AcsCaller, teams_phone_supported

if TYPE_CHECKING:
    from apps.artagent.backend.api.v1.schemas.call import (
        CommunicationProvidersResponse,
        CommunicationServiceOptions,
    )


def communication_providers(acs_caller: AcsCaller | None) -> CommunicationProvidersResponse:
    """Expose configuration only. Never provision resources, probe calls or return secrets."""
    from apps.artagent.backend.api.v1.schemas.call import (
        CommunicationProviderOption,
        CommunicationProvidersResponse,
        CommunicationServiceOptions,
    )

    settings = get_communication_provider_settings()
    client_configured = acs_caller is not None and acs_caller.client is not None
    acs_missing = []
    if not client_configured:
        acs_missing.append("Initialized ACS Call Automation client")
    source_number = getattr(acs_caller, "source_number", "") or ""
    if not re.fullmatch(r"\+[1-9]\d{1,14}", source_number):
        acs_missing.append("ACS_SOURCE_PHONE_NUMBER (E.164)")

    teams_missing = settings.teams_missing_settings
    sdk_supported = teams_phone_supported()
    if not sdk_supported:
        teams_missing.append("Call Automation SDK with teams_app_source support")
    if not client_configured:
        teams_missing.append("Initialized ACS Call Automation client")
    if not settings.teams_missing_settings:
        expected_id = str(UUID(settings.teams_resource_account_id))
        if getattr(acs_caller, "teams_resource_account_id", None) != expected_id:
            teams_missing.append("Backend restart after Teams Phone configuration")

    return CommunicationProvidersResponse(
        telephony=CommunicationServiceOptions(
            options=[
                CommunicationProviderOption(
                    id="acs",
                    label="ACS (standalone)",
                    available=not acs_missing,
                    status="not_configured" if acs_missing else "configured",
                    detail="Existing ACS calling. Configuration only; connectivity is not verified.",
                    missing_settings=acs_missing,
                ),
                CommunicationProviderOption(
                    id="teams",
                    label="Teams Phone (via ACS/TPE)",
                    available=not teams_missing,
                    status=(
                        "unavailable"
                        if not sdk_supported
                        else "not_configured" if teams_missing else "configured"
                    ),
                    detail=(
                        "Uses the server-configured Teams resource account through ACS. "
                        "Teams admin provisioning, licensing, routing and connectivity are not "
                        "verified here. Selection applies only to the next outbound call."
                    ),
                    missing_settings=teams_missing,
                ),
            ],
        ),
        email=_messaging_options("email", settings.email_missing_settings),
        sms=_messaging_options("sms", settings.sms_missing_settings),
    )


def _messaging_options(
    service: str, missing_settings: tuple[str, ...]
) -> CommunicationServiceOptions:
    from apps.artagent.backend.api.v1.schemas.call import (
        CommunicationProviderOption,
        CommunicationServiceOptions,
    )

    label = "Email" if service == "email" else "SMS"
    return CommunicationServiceOptions(
        options=[
            CommunicationProviderOption(
                id="acs",
                label=f"ACS {label}",
                available=not missing_settings,
                status="not_configured" if missing_settings else "configured",
                detail=(
                    "Server-configured ACS service; delivery is not verified. "
                    "This selection does not enable delivery for demo-only tools."
                ),
                missing_settings=list(missing_settings),
            ),
            CommunicationProviderOption(
                id="external",
                label=f"External {service if service == 'email' else 'SMS'} provider",
                available=False,
                status="unavailable",
                detail="Not implemented. Teams Phone is not an email or programmable SMS provider.",
            ),
        ]
    )
