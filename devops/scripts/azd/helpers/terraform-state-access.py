#!/usr/bin/env python3
"""Temporarily allow one CI runner IPv4 address to access Terraform state."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_LEASE_FILE = ".terraform-state-access-lease.json"
IP_DISCOVERY_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com")
NSP_API_VERSION = "2024-07-01"


class StateAccessError(RuntimeError):
    """Raised when safe Terraform state access cannot be established."""


def _required(value: str | None, name: str) -> str:
    if not value:
        raise StateAccessError(f"{name} is required")
    return value


def _enabled(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise StateAccessError("TF_STATE_MANAGE_RUNNER_IP must be true or false")
    return normalized == "true"


def _single_ipv4(value: str, source: str) -> str:
    candidate = value.strip()
    if "/" in candidate:
        raise StateAccessError(f"{source} must contain one IPv4 address, not a CIDR")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise StateAccessError(f"{source} must contain one IPv4 address") from exc
    if address.version != 4 or address.is_unspecified:
        raise StateAccessError(f"{source} must contain one IPv4 address")
    return str(address)


def discover_runner_ip(override: str | None) -> str:
    """Return one explicit or HTTPS-discovered public IPv4 address."""
    if override:
        return _single_ipv4(override, "TF_STATE_RUNNER_IP")

    for url in IP_DISCOVERY_URLS:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status != 200:
                    continue
                return _single_ipv4(response.read(64).decode("ascii"), url)
        except (OSError, UnicodeError, StateAccessError):
            continue
    raise StateAccessError("Could not discover the runner public IPv4 over bounded HTTPS")


def run_az(arguments: list[str], *, expect_json: bool = False) -> Any:
    """Run Azure CLI without exposing response bodies on failure."""
    command = ["az", *arguments, "--only-show-errors"]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=45)
    if result.returncode != 0:
        operation = " ".join(arguments[:3])
        raise StateAccessError(
            f"Azure CLI operation failed: {operation} (exit {result.returncode})"
        )
    if not expect_json:
        return result.stdout.strip()
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StateAccessError("Azure CLI returned invalid JSON") from exc


def _account(
    subscription: str,
    resource_group: str,
    account: str,
) -> dict[str, Any]:
    data = run_az(
        [
            "storage",
            "account",
            "show",
            "--subscription",
            subscription,
            "--resource-group",
            resource_group,
            "--name",
            account,
            "--output",
            "json",
        ],
        expect_json=True,
    )
    if not isinstance(data, dict):
        raise StateAccessError("Azure CLI returned an invalid storage account response")
    return data


def _validate_classic_account(account_data: dict[str, Any]) -> None:
    if account_data.get("publicNetworkAccess") == "SecuredByPerimeter":
        raise StateAccessError("SecuredByPerimeter requires an explicit TF_STATE_NSP_PROFILE_ID")
    if account_data.get("publicNetworkAccess") != "Enabled":
        raise StateAccessError(
            "Classic Terraform state access requires publicNetworkAccess=Enabled"
        )
    network = account_data.get("networkRuleSet") or {}
    if network.get("defaultAction") != "Deny":
        raise StateAccessError(
            "Classic Terraform state access requires firewall defaultAction=Deny"
        )


def _ip_rules(account_data: dict[str, Any]) -> list[str]:
    rules = (account_data.get("networkRuleSet") or {}).get("ipRules") or []
    values: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        value = rule.get("ipAddressOrRange") or rule.get("value")
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _covered(address: str, rules: list[str]) -> bool:
    runner = ipaddress.ip_address(address)
    networks = []
    for rule in rules:
        try:
            network = ipaddress.ip_network(rule, strict=False)
        except (TypeError, ValueError) as exc:
            raise StateAccessError("Azure returned an invalid network prefix") from exc
        if network.prefixlen == 0:
            raise StateAccessError("An all-network access rule is not accepted")
        networks.append(network)
    return any(runner in network for network in networks)


def _normalized_resource_id(value: str) -> str:
    return value.rstrip("/").lower()


def _validated_profile_id(profile_id: str, subscription: str) -> str:
    normalized = profile_id.rstrip("/")
    if "?" in normalized or "#" in normalized:
        raise StateAccessError("NSP profile IDs cannot contain query strings or fragments")
    parts = normalized.split("/")
    if (
        len(parts) != 11
        or parts[1].lower() != "subscriptions"
        or parts[3].lower() != "resourcegroups"
        or parts[5].lower() != "providers"
        or parts[6].lower() != "microsoft.network"
        or parts[7].lower() != "networksecurityperimeters"
        or parts[9].lower() != "profiles"
        or not all(parts[index] for index in (2, 4, 8, 10))
    ):
        raise StateAccessError(
            "TF_STATE_NSP_PROFILE_ID must be a full network security perimeter profile ID"
        )
    if parts[2].lower() != subscription.lower():
        raise StateAccessError(
            "TF_STATE_NSP_PROFILE_ID subscription does not match AZURE_SUBSCRIPTION_ID"
        )
    return normalized


def _rest_get(resource_id: str, subscription: str) -> dict[str, Any]:
    result = run_az(
        [
            "rest",
            "--method",
            "get",
            "--url",
            f"{resource_id}?api-version={NSP_API_VERSION}",
            "--subscription",
            subscription,
            "--output",
            "json",
        ],
        expect_json=True,
    )
    if not isinstance(result, dict):
        raise StateAccessError("Azure REST API returned an invalid response")
    return result


def _validate_nsp(
    *,
    profile_id: str,
    subscription: str,
    account_data: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    if account_data.get("publicNetworkAccess") != "SecuredByPerimeter":
        raise StateAccessError(
            "NSP Terraform state access requires publicNetworkAccess=SecuredByPerimeter"
        )
    profile = _rest_get(profile_id, subscription)
    if _normalized_resource_id(str(profile.get("id", ""))) != _normalized_resource_id(profile_id):
        raise StateAccessError("Azure returned a different NSP profile than requested")

    perimeter_id = "/".join(profile_id.split("/")[:9])
    associations = _rest_get(f"{perimeter_id}/resourceAssociations", subscription).get("value", [])
    account_id = _normalized_resource_id(str(account_data.get("id", "")))
    matching = [
        item
        for item in associations
        if isinstance(item, dict)
        if _normalized_resource_id(
            str((item.get("properties") or {}).get("privateLinkResource", {}).get("id", ""))
        )
        == account_id
        and _normalized_resource_id(
            str((item.get("properties") or {}).get("profile", {}).get("id", ""))
        )
        == _normalized_resource_id(profile_id)
    ]
    if len(matching) != 1:
        raise StateAccessError(
            "State account must have exactly one matching NSP profile association"
        )
    if (matching[0].get("properties") or {}).get("accessMode") != "Enforced":
        raise StateAccessError("State account NSP association must be Enforced")

    rules = _rest_get(f"{profile_id}/accessRules", subscription).get("value", [])
    if not isinstance(rules, list):
        raise StateAccessError("Azure returned invalid NSP access rules")
    return perimeter_id, rules


def _nsp_rule_prefixes(rules: list[dict[str, Any]]) -> list[str]:
    prefixes: list[str] = []
    for rule in rules:
        properties = rule.get("properties") or {}
        if properties.get("direction") != "Inbound":
            continue
        values = properties.get("addressPrefixes") or []
        if isinstance(values, list):
            prefixes.extend(value for value in values if isinstance(value, str))
    return prefixes


def _nsp_rule_name(run_id: str, *, job: str | None = None, attempt: str | None = None) -> str:
    job = job or os.environ.get("GITHUB_JOB") or "job"
    attempt = attempt or os.environ.get("GITHUB_RUN_ATTEMPT") or "1"
    if not attempt.isascii() or not attempt.isdecimal() or int(attempt) < 1:
        raise StateAccessError("The workflow attempt must be a positive integer")
    identity = f"{run_id}:{attempt}:{job}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    safe_job = "".join(character if character.isalnum() else "-" for character in job)
    safe_job = safe_job.strip("-")[:32] or "job"
    safe_run = "".join(character for character in run_id if character.isalnum())[:20] or "run"
    return f"gha-{safe_job}-{safe_run}-{attempt}-{digest}"[:80].rstrip("-")


def _put_nsp_rule(rule_id: str, subscription: str, runner_ip: str) -> None:
    body = json.dumps(
        {
            "properties": {
                "direction": "Inbound",
                "addressPrefixes": [f"{runner_ip}/32"],
            }
        }
    )
    run_az(
        [
            "rest",
            "--method",
            "put",
            "--url",
            f"{rule_id}?api-version={NSP_API_VERSION}",
            "--subscription",
            subscription,
            "--body",
            body,
            "--output",
            "none",
        ]
    )


def _delete_nsp_rule(rule_id: str, subscription: str) -> None:
    run_az(
        [
            "rest",
            "--method",
            "delete",
            "--url",
            f"{rule_id}?api-version={NSP_API_VERSION}",
            "--subscription",
            subscription,
            "--output",
            "none",
        ]
    )


def _write_lease(path: Path, lease: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise StateAccessError("A lease already exists; close it before opening another") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(lease, stream, sort_keys=True)
        stream.write("\n")
    path.chmod(0o600)


def _validate_blob(
    *,
    subscription: str,
    account: str,
    container: str,
    blob: str,
    attempts: int,
    delay: float,
) -> None:
    last_error: StateAccessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            exists = run_az(
                [
                    "storage",
                    "blob",
                    "exists",
                    "--subscription",
                    subscription,
                    "--account-name",
                    account,
                    "--container-name",
                    container,
                    "--name",
                    blob,
                    "--auth-mode",
                    "login",
                    "--query",
                    "exists",
                    "--output",
                    "tsv",
                ]
            ).lower()
            if exists == "true":
                print("Terraform state blob is reachable with Microsoft Entra authentication.")
                return
            if exists == "false":
                raise StateAccessError(
                    "Terraform state blob does not exist; refusing to create or select alternate state"
                )
            raise StateAccessError("Azure CLI returned an invalid blob existence result")
        except StateAccessError as exc:
            if "does not exist" in str(exc) or "invalid blob" in str(exc):
                raise
            last_error = exc
            if attempt < attempts:
                time.sleep(delay)
    raise StateAccessError(
        f"Terraform state data-plane access did not propagate after {attempts} attempts"
    ) from last_error


def open_access(args: argparse.Namespace) -> None:
    """Validate account posture, optionally add this runner IP, and validate state."""
    if not _enabled(args.manage):
        print("Terraform state runner-IP management is disabled; no network changes made.")
        return
    lease_path = Path(args.lease_file)
    if lease_path.exists() or lease_path.is_symlink():
        raise StateAccessError("A lease already exists; close it before opening another")

    subscription = _required(args.subscription, "AZURE_SUBSCRIPTION_ID")
    resource_group = _required(args.resource_group, "RS_RESOURCE_GROUP")
    account = _required(args.account, "RS_STORAGE_ACCOUNT")
    container = _required(args.container, "RS_CONTAINER_NAME")
    blob = _required(args.blob, "RS_STATE_KEY")
    _required(args.run_id, "GITHUB_RUN_ID or --run-id")
    runner_ip = discover_runner_ip(args.runner_ip)
    account_data = _account(subscription, resource_group, account)
    profile_id = (
        _validated_profile_id(args.nsp_profile_id, subscription) if args.nsp_profile_id else None
    )
    if profile_id:
        _, nsp_rules = _validate_nsp(
            profile_id=profile_id,
            subscription=subscription,
            account_data=account_data,
        )
        covered = _covered(runner_ip, _nsp_rule_prefixes(nsp_rules))
        mode = "nsp"
        rule_id = None if covered else f"{profile_id}/accessRules/{_nsp_rule_name(args.run_id)}"
        if rule_id and any(
            _normalized_resource_id(str(rule.get("id", ""))) == _normalized_resource_id(rule_id)
            for rule in nsp_rules
        ):
            raise StateAccessError("The proposed CI rule already exists; refusing to overwrite it")
    else:
        _validate_classic_account(account_data)
        covered = _covered(runner_ip, _ip_rules(account_data))
        mode = "classic"
        rule_id = None

    lease = {
        "version": 2,
        "mode": mode,
        "subscription_id": subscription,
        "resource_group": resource_group,
        "storage_account": account,
        "container": container,
        "blob": blob,
        "runner_ip": runner_ip,
        "run_id": args.run_id,
        "owns_rule": not covered,
        # Record cleanup intent before the mutation, including lost API responses.
        "rule_added": not covered,
        "nsp_profile_id": profile_id,
        "rule_id": rule_id,
    }
    if mode == "nsp":
        lease["job"] = os.environ.get("GITHUB_JOB") or "job"
        lease["attempt"] = os.environ.get("GITHUB_RUN_ATTEMPT") or "1"
    _write_lease(lease_path, lease)

    if covered:
        print(f"Runner IPv4 is already covered by an existing {mode} rule; preserving it.")
    elif mode == "nsp":
        _put_nsp_rule(_required(rule_id, "NSP access rule ID"), subscription, runner_ip)
        print("Added a temporary per-job NSP inbound /32 access rule.")
    else:
        run_az(
            [
                "storage",
                "account",
                "network-rule",
                "add",
                "--subscription",
                subscription,
                "--resource-group",
                resource_group,
                "--account-name",
                account,
                "--ip-address",
                runner_ip,
                "--output",
                "none",
            ]
        )
        print("Added a temporary exact runner IPv4 firewall rule.")

    _validate_blob(
        subscription=subscription,
        account=account,
        container=container,
        blob=blob,
        attempts=args.attempts,
        delay=args.delay,
    )


def validate_access(args: argparse.Namespace) -> None:
    """Validate the existing perimeter and Entra state access without changing rules."""
    subscription = _required(args.subscription, "AZURE_SUBSCRIPTION_ID")
    account = _required(args.account, "RS_STORAGE_ACCOUNT")
    data = _account(subscription, _required(args.resource_group, "RS_RESOURCE_GROUP"), account)
    if args.nsp_profile_id:
        profile = _validated_profile_id(args.nsp_profile_id, subscription)
        _, rules = _validate_nsp(profile_id=profile, subscription=subscription, account_data=data)
        _covered("0.0.0.0", _nsp_rule_prefixes(rules))
    else:
        _validate_classic_account(data)
        _covered("0.0.0.0", _ip_rules(data))
    _validate_blob(
        subscription=subscription,
        account=account,
        container=_required(args.container, "RS_CONTAINER_NAME"),
        blob=_required(args.blob, "RS_STATE_KEY"),
        attempts=args.attempts,
        delay=args.delay,
    )


def close_access(args: argparse.Namespace) -> None:
    """Remove only the exact firewall rule recorded as owned by this run."""
    lease_path = Path(args.lease_file)
    if not lease_path.exists():
        print("No Terraform state access lease exists; cleanup skipped.")
        return
    try:
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateAccessError("Terraform state access lease is unreadable") from exc

    if lease.get("version") != 2:
        raise StateAccessError("Terraform state access lease version is invalid")
    subscription = _required(args.subscription, "AZURE_SUBSCRIPTION_ID")
    if lease.get("subscription_id") != subscription:
        raise StateAccessError("Lease subscription does not match AZURE_SUBSCRIPTION_ID")
    if args.run_id and lease.get("run_id") != args.run_id:
        raise StateAccessError("Lease run does not match the current workflow run")
    if args.resource_group and lease.get("resource_group") != args.resource_group:
        raise StateAccessError("Lease resource group does not match RS_RESOURCE_GROUP")
    if args.account and lease.get("storage_account") != args.account:
        raise StateAccessError("Lease storage account does not match RS_STORAGE_ACCOUNT")

    if not lease.get("rule_added"):
        print("Lease owns no firewall rule; preserving existing rules.")
        lease_path.unlink()
        return
    if not lease.get("owns_rule"):
        raise StateAccessError("Lease does not own the rule marked for cleanup")

    if lease.get("mode") == "nsp":
        profile_id = _validated_profile_id(
            _required(lease.get("nsp_profile_id"), "lease NSP profile ID"),
            subscription,
        )
        if args.nsp_profile_id and _normalized_resource_id(
            args.nsp_profile_id
        ) != _normalized_resource_id(profile_id):
            raise StateAccessError("Lease NSP profile does not match TF_STATE_NSP_PROFILE_ID")
        rule_id = _required(lease.get("rule_id"), "lease NSP access rule ID")
        expected_name = _nsp_rule_name(
            _required(lease.get("run_id"), "lease run ID"),
            job=_required(lease.get("job"), "lease job"),
            attempt=_required(lease.get("attempt"), "lease attempt"),
        )
        expected_id = f"{profile_id}/accessRules/{expected_name}"
        if _normalized_resource_id(rule_id) != _normalized_resource_id(expected_id):
            raise StateAccessError("Lease NSP access rule ID does not match its run ownership")
        current_rules = _rest_get(f"{profile_id}/accessRules", subscription).get("value", [])
        matching = [
            rule
            for rule in current_rules
            if _normalized_resource_id(str(rule.get("id", ""))) == _normalized_resource_id(rule_id)
        ]
        if not matching:
            lease_path.unlink()
            print("Owned NSP rule is already absent; cleanup complete.")
            return
        properties = matching[0].get("properties", {})
        runner_ip = _single_ipv4(
            _required(lease.get("runner_ip"), "lease runner IP"), "lease runner IP"
        )
        if properties.get("direction") != "Inbound" or properties.get("addressPrefixes") != [
            f"{runner_ip}/32"
        ]:
            raise StateAccessError("The leased NSP rule changed; refusing to delete it")
        _delete_nsp_rule(rule_id, subscription)
        lease_path.unlink()
        print("Removed the temporary per-job NSP access rule.")
        return

    if lease.get("mode") != "classic":
        raise StateAccessError("Lease access mode is invalid")
    run_az(
        [
            "storage",
            "account",
            "network-rule",
            "remove",
            "--subscription",
            subscription,
            "--resource-group",
            _required(lease.get("resource_group"), "lease resource group"),
            "--account-name",
            _required(lease.get("storage_account"), "lease storage account"),
            "--ip-address",
            _single_ipv4(_required(lease.get("runner_ip"), "lease runner IP"), "lease runner IP"),
            "--output",
            "none",
        ]
    )
    lease_path.unlink()
    print("Removed the temporary runner IPv4 firewall rule.")


def parse_args() -> argparse.Namespace:
    """Parse helper command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("open", "close", "validate"))
    parser.add_argument("--subscription", default=os.environ.get("AZURE_SUBSCRIPTION_ID"))
    parser.add_argument("--resource-group", default=os.environ.get("RS_RESOURCE_GROUP"))
    parser.add_argument("--account", default=os.environ.get("RS_STORAGE_ACCOUNT"))
    parser.add_argument("--container", default=os.environ.get("RS_CONTAINER_NAME"))
    parser.add_argument("--blob", default=os.environ.get("RS_STATE_KEY"))
    parser.add_argument("--runner-ip", default=os.environ.get("TF_STATE_RUNNER_IP"))
    parser.add_argument("--nsp-profile-id", default=os.environ.get("TF_STATE_NSP_PROFILE_ID"))
    parser.add_argument("--manage", default=os.environ.get("TF_STATE_MANAGE_RUNNER_IP", "false"))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--lease-file", default=DEFAULT_LEASE_FILE)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    """Run the requested access lifecycle operation."""
    try:
        args = parse_args()
        if args.attempts < 1 or args.delay < 0:
            raise StateAccessError("--attempts must be positive and --delay cannot be negative")
        if args.command == "open":
            open_access(args)
        elif args.command == "validate":
            validate_access(args)
        else:
            close_access(args)
    except (StateAccessError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
