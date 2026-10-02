#!/usr/bin/env python3
"""Fail-closed, opt-in AZD lifecycle operations for Front Door Private Link.

Uses the published Microsoft.App 2025-07-01 privateEndpointConnections,
Microsoft.Cdn 2024-02-01 origins, and Event Grid 2022-06-15 subscription APIs.
No SDK dependency and no secret values in subprocess arguments or hook output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

APP_API = "2025-07-01"
AFD_API = "2024-02-01"
EVENT_API = "2022-06-15"
ARM_HOST = "management.azure.com"
INCOMING_CALL = "Microsoft.Communication.IncomingCall"


class HookError(Exception):
    """A deployment prerequisite failed; no public-origin fallback is permitted."""


def command(args: list[str], *, timeout: int = 90) -> str:
    """Capture output without exposing CLI diagnostics that may contain secrets."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HookError(
            f"{args[0]} could not complete; check installation, access and connectivity."
        ) from exc
    if result.returncode:
        raise HookError(
            f"{args[0]} operation failed (exit {result.returncode}); "
            f"operation: {' '.join(args[1:4])}. "
            "Check Azure login, resource permissions and connectivity. CLI output suppressed."
        )
    return result.stdout.strip()


def setting(name: str, *, required: bool = True) -> str:
    """Resolve explicit process configuration before the local azd environment."""
    value = os.environ.get(name)
    if value is None:
        try:
            value = command(["azd", "env", "get-value", name])
        except HookError:
            value = ""
    if value in ("null", "None") or value.startswith("ERROR"):
        value = ""
    if required and not value:
        raise HookError(f"{name} is missing. Refresh azd outputs from the provisioned deployment.")
    return value


def enabled() -> bool:
    """Read resolved output only; the desired input may differ from deployed state."""
    value = os.environ.get("FRONT_DOOR_ENABLED")
    if value is None:
        try:
            values = json.loads(command(["azd", "env", "get-values", "--output", "json"]))
        except ValueError as exc:
            raise HookError("azd returned invalid environment JSON.") from exc
        if not isinstance(values, dict):
            raise HookError("azd returned an invalid environment object.")
        value = str(values.get("FRONT_DOOR_ENABLED", "false"))
    if value.lower() not in ("true", "false"):
        raise HookError("FRONT_DOOR_ENABLED must be true or false.")
    return value.lower() == "true"


@contextmanager
def private_file(content: str) -> Iterator[Path]:
    """Create an exclusive 0600 scratch file in the project; remove on every exit."""
    path = Path.cwd() / f".frontdoor-hook-{secrets.token_hex(16)}"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        yield path
    finally:
        path.unlink(missing_ok=True)


def rest(url: str, *, body: dict | None = None) -> dict:
    """Call ARM through the signed-in CLI, passing request bodies by private file."""
    args = ["az", "rest", "--method", "GET" if body is None else "PUT", "--url", url]
    args += ["--only-show-errors", "--output", "json"]
    if body is None:
        output = command(args)
    else:
        with private_file(json.dumps(body)) as path:
            output = command([*args, "--body", f"@{path}"])
    try:
        return json.loads(output) if output else {}
    except ValueError as exc:
        raise HookError("ARM returned an invalid JSON response.") from exc


def resource_id(name: str, resource_type: str) -> str:
    """Require a full, explicitly supplied resource ID rather than global discovery."""
    value = setting(name).rstrip("/")
    pattern = (
        rf"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/{re.escape(resource_type)}/[^/]+"
    )
    if not re.fullmatch(pattern, value, flags=re.IGNORECASE):
        raise HookError(f"{name} must be the ARM ID of {resource_type}.")
    return value


def scoped_items(scope: str, api: str) -> list[dict]:
    """Read all pages while keeping continuation requests within the supplied scope."""
    url = f"{scope}?api-version={api}"
    result = []
    seen = set()
    while url:
        parsed = urlsplit(url)
        if parsed.netloc and (parsed.scheme != "https" or parsed.netloc != ARM_HOST):
            raise HookError("ARM returned an unexpected continuation host.")
        if parsed.path.lower() != scope.lower() or url in seen:
            raise HookError("ARM returned an unexpected or repeated continuation scope.")
        seen.add(url)
        page = rest(url)
        if not isinstance(page.get("value"), list):
            raise HookError("ARM list response did not contain a resource collection.")
        result.extend(page["value"])
        url = page.get("nextLink") or ""
    return result


def poll_settings() -> tuple[int, float]:
    """Bound propagation polling; overrides allow faster hermetic validation."""
    try:
        attempts = int(os.environ.get("FRONT_DOOR_MAX_ATTEMPTS", "60"))
        delay = float(os.environ.get("FRONT_DOOR_POLL_SECONDS", "10"))
        if not 1 <= attempts <= 120 or not 0 <= delay <= 60:
            raise ValueError
    except ValueError as exc:
        raise HookError(
            "Polling requires 1..120 attempts and 0..60 seconds between attempts."
        ) from exc
    return attempts, delay


def origins_approved(profile: str, environment: str, message: str) -> bool:
    """Check every deployment origin so late or shared private links cannot be missed."""
    origins = []
    for group in scoped_items(f"{profile}/originGroups", AFD_API):
        group_id = group["id"]
        if not group_id.lower().startswith(f"{profile}/originGroups/".lower()):
            raise HookError("An origin group was outside FRONT_DOOR_PROFILE_ID.")
        origins.extend(scoped_items(f"{group_id}/origins", AFD_API))
    if not origins:
        return False
    ready = True
    for origin in origins:
        link = origin.get("properties", {}).get("sharedPrivateLinkResource") or {}
        if (
            link.get("privateLink", {}).get("id", "").lower() != environment.lower()
            or link.get("requestMessage") != message
        ):
            raise HookError(
                "Front Door origin private-link target/message differs from this deployment."
            )
        status = link.get("status")
        if status in ("Rejected", "Disconnected", "Timeout"):
            raise HookError(
                f"Front Door origin private link is {status}; repair it and rerun provision."
            )
        if status is None:
            # Managed-environment origins can omit link status even after their
            # environment connection is Approved. Require completed provisioning.
            ready = ready and origin.get("properties", {}).get("provisioningState") == "Succeeded"
        else:
            ready = ready and status == "Approved"
    return ready


def approve_private_links() -> None:
    """Approve only exact-message connections on this environment and await all origins."""
    environment = resource_id("CONTAINER_APPS_ENVIRONMENT_ID", "Microsoft.App/managedEnvironments")
    profile = resource_id("FRONT_DOOR_PROFILE_ID", "Microsoft.Cdn/profiles")
    message = setting("FRONT_DOOR_PRIVATE_LINK_REQUEST_MESSAGE")
    scope = f"{environment}/privateEndpointConnections"
    attempts, delay = poll_settings()
    submitted = set()
    last_status = "no matching requests"
    for attempt in range(attempts):
        matches = []
        for connection in scoped_items(scope, APP_API):
            state = connection.get("properties", {}).get("privateLinkServiceConnectionState", {})
            if state.get("description") == message:
                matches.append(connection)
        ready = bool(matches)
        statuses = []
        for connection in matches:
            connection_id = connection["id"]
            if not connection_id.lower().startswith(f"{scope}/".lower()):
                raise HookError("A private endpoint request was outside the expected environment.")
            state = connection["properties"]["privateLinkServiceConnectionState"]
            status = state.get("status", "Unknown")
            statuses.append(status)
            if status not in ("Approved", "Pending"):
                raise HookError(
                    f"Matching private endpoint is {status}: {connection_id}. "
                    "Resolve the connection in Azure and rerun azd provision; unrelated requests were not changed."
                )
            if status == "Pending":
                ready = False
                if connection_id not in submitted:
                    # Preserve the exact request message for future idempotent scope checks.
                    rest(
                        f"{connection_id}?api-version={APP_API}",
                        body={
                            "properties": {
                                "privateLinkServiceConnectionState": {
                                    "status": "Approved",
                                    "description": message,
                                }
                            }
                        },
                    )
                    submitted.add(connection_id)
        last_status = ", ".join(statuses) or "no matching requests"
        if ready and origins_approved(profile, environment, message):
            print(f"Front Door private links approved ({len(matches)} scoped connections).")
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise HookError(
        f"Timed out waiting for Front Door private links ({last_status}). "
        f"Inspect {scope} and the profile's origin private-link status/message; rerun azd provision. "
        "Origin public access was not opened."
    )


def public_backend_url() -> str:
    """Require a public HTTPS base URL, never silently fall back to the private origin."""
    value = setting("BACKEND_API_URL").rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.hostname.endswith(".azurecontainerapps.io")
    ):
        raise HookError(
            "BACKEND_API_URL must be the public Front Door HTTPS base URL, not an origin URL."
        )
    return value


def wait_for_backend(url: str, acs: str, secret: str) -> None:
    """Validate authenticated Event Grid handshake through WAF, not a placeholder GET."""
    code = secrets.token_hex(24)
    payload = [
        {
            "id": secrets.token_hex(16),
            "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
            "subject": "",
            "eventTime": datetime.now(UTC).isoformat(),
            "topic": acs,
            "data": {"validationCode": code},
            "dataVersion": "1.0",
            "metadataVersion": "1",
        }
    ]
    # curl config quoting prevents quotes/backslashes in a secret changing its syntax.
    header = json.dumps(f"X-EventGrid-Webhook-Secret: {secret}")
    attempts, delay = poll_settings()
    status = "connection error"
    with private_file(f"header = {header}\n") as config, private_file(json.dumps(payload)) as data:
        for attempt in range(attempts):
            args = [
                "curl",
                "--disable",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--connect-timeout",
                "10",
                "--max-time",
                "30",
                "--config",
                str(config),
                "--request",
                "POST",
                "--header",
                "Content-Type: application/json",
                "--header",
                "aeg-event-type: SubscriptionValidation",
                "--data-binary",
                f"@{data}",
                "--write-out",
                "\n%{http_code}",
                url,
            ]
            try:
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=35, check=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HookError("curl readiness probe could not complete.") from exc
            if result.returncode:
                # DNS/connect/timeout/empty reply/receive failures can be propagation.
                if result.returncode not in (5, 6, 7, 28, 52, 55, 56):
                    raise HookError(
                        f"Readiness transport failed (curl {result.returncode}); check TLS and curl."
                    )
                status = "connection error"
            else:
                body, _, status = result.stdout.rstrip("\n").rpartition("\n")
                if status == "200":
                    try:
                        if json.loads(body).get("validationResponse") == code:
                            return
                    except (ValueError, AttributeError):
                        pass
                    raise HookError(
                        "Backend returned 200 without the expected validationResponse; deploy the app."
                    )
                if status not in ("404", "502", "503"):
                    raise HookError(
                        f"Authenticated Event Grid readiness failed (HTTP {status}). "
                        "Check webhook secret, ACS topic, exact-path WAF exception and deployed backend."
                    )
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise HookError(
        f"Backend readiness timed out ({status}); inspect deployment and Front Door origin health. "
        "No Event Grid subscription was created."
    )


def configure_subscription() -> None:
    """Create/update the marked, owned IncomingCall subscription only after readiness."""
    acs = resource_id("ACS_RESOURCE_ID", "Microsoft.Communication/communicationServices")
    profile = resource_id("FRONT_DOOR_PROFILE_ID", "Microsoft.Cdn/profiles")
    callback = f"{public_backend_url()}/api/v1/calls/answer"
    owner = hashlib.sha256(profile.lower().encode()).hexdigest()[:20]
    name = f"art-incoming-call-{owner}"
    marker = f"art-frontdoor-{owner}"
    scope = f"{acs}/providers/Microsoft.EventGrid/eventSubscriptions"
    for subscription in scoped_items(scope, EVENT_API):
        properties = subscription.get("properties", {})
        if subscription.get("name") == name:
            if marker not in (properties.get("labels") or []):
                raise HookError(
                    f"Subscription {name} exists without the ownership label; refusing to replace it."
                )
            continue
        types = (properties.get("filter") or {}).get("includedEventTypes")
        destination = properties.get("destination") or (
            properties.get("deliveryWithResourceIdentity") or {}
        ).get("destination", {})
        incoming = not types or any(kind in types for kind in (INCOMING_CALL, "All", "*"))
        if incoming and destination.get("endpointType") == "WebHook":
            raise HookError(
                f"Competing IncomingCall webhook subscription: {subscription.get('name')}. "
                "Migrate or remove it explicitly before rerunning azd deploy to avoid duplicate calls. "
                "The hook does not delete user subscriptions."
            )

    vault = setting("AZURE_KEY_VAULT_NAME")
    secret_name = setting("EVENT_GRID_WEBHOOK_SECRET_NAME")
    secret = command(
        [
            "az",
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            vault,
            "--name",
            secret_name,
            "--query",
            "value",
            "--output",
            "tsv",
            "--only-show-errors",
        ]
    )
    if (
        not 32 <= len(secret) <= 4096
        or not secret.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in secret)
    ):
        raise HookError(
            "Key Vault webhook secret must contain 32..4096 printable ASCII characters."
        )
    wait_for_backend(callback, acs, secret)
    body = {
        "properties": {
            "labels": [marker],
            "eventDeliverySchema": "EventGridSchema",
            "filter": {"includedEventTypes": [INCOMING_CALL]},
            "destination": {
                "endpointType": "WebHook",
                "properties": {
                    "endpointUrl": callback,
                    "deliveryAttributeMappings": [
                        {
                            "name": "X-EventGrid-Webhook-Secret",
                            "type": "Static",
                            "properties": {"value": secret, "isSecret": True},
                        }
                    ],
                },
            },
        }
    }
    url = f"{scope}/{name}?api-version={EVENT_API}"
    rest(url, body=body)
    attempts, delay = poll_settings()
    for attempt in range(attempts):
        state = rest(url).get("properties", {}).get("provisioningState", "Unknown")
        if state == "Succeeded":
            print(f"Owned ACS IncomingCall subscription ready: {name}")
            return
        if state not in ("Creating", "Updating", "AwaitingManualAction"):
            raise HookError(
                f"Event Grid subscription state is {state}; inspect {name} and backend validation."
            )
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise HookError(
        f"Event Grid subscription {name} validation is still pending; inspect it before retrying."
    )


def main() -> int:
    """Run only the requested lifecycle stage; opt-out performs no Azure operations."""

    def interrupt(signum, frame):
        raise HookError("Hook interrupted; project-local secret files were removed.")

    signal.signal(signal.SIGTERM, interrupt)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("provision", "deploy", "enabled"))
    args = parser.parse_args()
    try:
        opted_in = enabled()
        if args.stage == "enabled":
            print(str(opted_in).lower())
        elif not opted_in:
            print("Front Door disabled; no Front Door lifecycle operations.")
        elif args.stage == "provision":
            approve_private_links()
        else:
            configure_subscription()
    except HookError as exc:
        print(f"Front Door hook failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
