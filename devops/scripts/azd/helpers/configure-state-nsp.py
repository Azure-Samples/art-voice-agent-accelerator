#!/usr/bin/env python3
"""Bootstrap an enforced perimeter around an existing Terraform state account."""

from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
import sys
from pathlib import Path


def vpn_prefixes(values: list[str]) -> list[str]:
    """Require explicit, canonical public IPv4 ranges; never infer a VPN subnet."""
    prefixes = []
    for value in values:
        network = ipaddress.ip_network(value, strict=True)
        if (
            network.version != 4
            or network.prefixlen == 0
            or not network.is_global
            or network.is_multicast
        ):
            raise ValueError(f"An approved public IPv4 CIDR is required: {value}")
        prefixes.append(str(network))
    if not prefixes:
        raise ValueError("At least one approved VPN egress CIDR is required")
    return sorted(set(prefixes))


def azure(args: list[str]) -> dict:
    """Read metadata or apply the explicitly scoped bootstrap operation."""
    result = subprocess.run(
        ["az", *args, "--only-show-errors", "--output", "json"],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Azure {' '.join(args[:3])} failed (exit {result.returncode}); "
            "check subscription permissions and network connectivity."
        )
    return json.loads(result.stdout)


def configure(subscription: str, resource_group: str, account: str, prefixes: list[str]) -> dict:
    """Create only the state perimeter, then switch the existing account to it."""
    prefixes = vpn_prefixes(prefixes)
    scope = ["--subscription", subscription, "--resource-group", resource_group]
    storage = azure(["storage", "account", "show", *scope, "--name", account])
    expected = (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Storage/storageAccounts/{account}"
    )
    if storage["id"].casefold() != expected.casefold():
        raise ValueError("The returned storage account is outside the requested scope")
    if storage.get("networkRuleSet", {}).get("defaultAction") != "Deny":
        raise ValueError("Set the state account firewall default to Deny before bootstrap")

    template = (
        Path(__file__).resolve().parents[4]
        / "infra/bootstrap/state-network-security-perimeter.json"
    )
    deployment = azure(
        [
            "deployment",
            "group",
            "create",
            *scope,
            "--name",
            "terraform-state-perimeter",
            "--mode",
            "Incremental",
            "--template-file",
            str(template),
            "--parameters",
            f"storageAccountName={account}",
            f"location={storage['location']}",
            f"vpnAddressPrefixes={json.dumps(prefixes)}",
        ]
    )
    if deployment["properties"].get("provisioningState") != "Succeeded":
        raise RuntimeError("The state perimeter deployment did not succeed")
    outputs = deployment["properties"]["outputs"]
    profile_id = outputs["profileId"]["value"]
    perimeter_id = outputs["perimeterId"]["value"]
    association = azure(
        [
            "rest",
            "--method",
            "GET",
            "--subscription",
            subscription,
            "--url",
            f"{perimeter_id}/resourceAssociations/terraform-state?api-version=2025-07-01",
        ]
    )["properties"]
    if (
        association.get("accessMode") != "Enforced"
        or association.get("profile", {}).get("id", "").casefold() != profile_id.casefold()
        or association.get("privateLinkResource", {}).get("id", "").casefold()
        != storage["id"].casefold()
    ):
        raise RuntimeError("The expected enforced state association was not established")
    azure(
        [
            "rest",
            "--method",
            "PATCH",
            "--subscription",
            subscription,
            "--url",
            f"{storage['id']}?api-version=2025-01-01",
            "--body",
            json.dumps(
                {
                    "properties": {
                        "publicNetworkAccess": "SecuredByPerimeter",
                        "allowBlobPublicAccess": False,
                    }
                }
            ),
        ]
    )
    current = azure(["storage", "account", "show", *scope, "--name", account])
    if (
        current.get("publicNetworkAccess") != "SecuredByPerimeter"
        or current.get("allowBlobPublicAccess") is not False
    ):
        raise RuntimeError("The state account did not retain its perimeter-secured configuration")
    return {
        "profileId": profile_id,
        "perimeterId": perimeter_id,
        "storageAccountId": storage["id"],
        "vpnAddressPrefixes": prefixes,
        "publicNetworkAccess": "SecuredByPerimeter",
    }


def main() -> int:
    """Bootstrap explicitly approved networking; data-plane validation is separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--vpn-cidr", required=True, action="append")
    args = parser.parse_args()
    try:
        result = configure(args.subscription, args.resource_group, args.account, args.vpn_cidr)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"State perimeter bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
