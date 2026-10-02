"""Exercise state-network repair without contacting Azure."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "devops/scripts/azd/helpers/initialize-terraform.sh"

STUBS = r"""
get_azd_env() {
    case "$1" in
        LOCAL_STATE) echo false ;;
        AZURE_ENV_NAME) echo test ;;
        AZURE_LOCATION) echo westus2 ;;
        RS_STORAGE_ACCOUNT) echo stateaccount ;;
        RS_CONTAINER_NAME) echo tfstate ;;
        RS_RESOURCE_GROUP) echo rg-state ;;
        RS_STATE_KEY) echo test.tfstate ;;
        *) echo "" ;;
    esac
}
az() {
    printf '%s\n' "$*" >> "$CALL_LOG"
    if [[ "$1 $2" == "tag update" && "${FAIL_TAG:-false}" == true ]]; then
        return 1
    fi
    if [[ "${1:-} ${2:-} ${3:-}" == "storage account show" ]]; then
        if [[ "$*" == *"--query id"* ]]; then
            echo /subscriptions/sub/resourceGroups/rg-state/providers/Microsoft.Storage/storageAccounts/stateaccount
        elif [[ "$*" == *"--query publicNetworkAccess"* ]]; then
            echo "${MOCK_PNA:-Enabled}"
        else
            printf '{"publicNetworkAccess":"%s","defaultAction":"Deny"}\n' "${MOCK_PNA:-Enabled}"
        fi
    elif [[ "$1 $2" == "account show" ]]; then
        echo sub
    fi
}
azd() { return 0; }
"""


def run_repair(
    tmp_path: Path,
    *,
    command: str = "ensure_state_network_access stateaccount rg-state",
    **overrides: str,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the actual helper with narrowly scoped in-process CLI stubs."""
    calls = tmp_path / "calls.log"
    env = {
        **os.environ,
        "CALL_LOG": str(calls),
        "AZURE_SUBSCRIPTION_ID": "sub",
        "TF_STATE_ALLOW_PUBLIC_ACCESS": "true",
        "TF_STATE_ALLOWED_IP": "203.0.113.10",
        "TF_STATE_EXCLUSION_TAG_NAME": "",
        "TF_STATE_EXCLUSION_TAG_VALUE": "",
        **overrides,
    }
    result = subprocess.run(
        ["bash", "-c", f'source "$1"\n{STUBS}\n{command}', "test", str(HELPER)],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_disabled_repair_does_not_touch_azure(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, TF_STATE_ALLOW_PUBLIC_ACCESS="false")
    assert result.returncode == 0
    assert calls == []


def test_repair_merges_supported_tag_then_enables_only_ip_allowlist(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path)
    assert result.returncode == 0, result.stderr
    tag = next(i for i, call in enumerate(calls) if call.startswith("tag update"))
    deny = next(i for i, call in enumerate(calls) if "--default-action Deny" in call)
    rule = next(i for i, call in enumerate(calls) if "--ip-address 203.0.113.10" in call)
    enable = next(i for i, call in enumerate(calls) if "--public-network-access Enabled" in call)
    assert tag < deny < rule < enable
    assert "--operation Merge" in calls[tag]
    assert "--tags SecurityControl=Ignore" in calls[tag]
    assert "--allow-blob-public-access false" in calls[enable]
    assert all("--default-action Allow" not in call for call in calls)


@pytest.mark.parametrize("ip", ["0.0.0.0/0", "*", "999.1.1.1", "1.2.3", "not-an-ip"])
def test_invalid_or_broad_ip_is_rejected_before_mutation(tmp_path: Path, ip: str) -> None:
    result, calls = run_repair(tmp_path, TF_STATE_ALLOWED_IP=ip)
    assert result.returncode != 0
    assert "one IPv4 address" in result.stderr
    assert calls == []


def test_invalid_opt_in_is_not_silently_accepted(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, TF_STATE_ALLOW_PUBLIC_ACCESS="treu")
    assert result.returncode != 0
    assert "must be true or false" in result.stderr
    assert calls == []


def test_policy_override_is_reported_without_weakening_firewall(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, MOCK_PNA="Disabled")
    assert result.returncode != 0
    assert "restricted by policy" in result.stderr
    assert all("--default-action Allow" not in call for call in calls)


def test_failed_tag_merge_stops_before_network_changes(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, FAIL_TAG="true")
    assert result.returncode != 0
    assert not any(call.startswith("storage account update") for call in calls)


def test_fully_configured_state_account_is_repaired_before_return(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, command="main")
    assert result.returncode == 0, result.stderr
    assert any(call.startswith("tag update") for call in calls)
    assert any("--public-network-access Enabled" in call for call in calls)
    assert not any(call.startswith("storage account create") for call in calls)


def test_repair_does_not_touch_another_subscription(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, command="main", AZURE_SUBSCRIPTION_ID="another-sub")
    assert result.returncode != 0
    assert "does not match this azd environment" in result.stderr
    assert not any(call.startswith(("storage ", "tag update")) for call in calls)


def test_legacy_repair_cannot_downgrade_an_enforced_perimeter(tmp_path: Path) -> None:
    result, calls = run_repair(tmp_path, MOCK_PNA="SecuredByPerimeter")
    assert result.returncode != 0
    assert "refusing to downgrade" in result.stderr
    assert not any(call.startswith(("tag update", "storage account update")) for call in calls)
