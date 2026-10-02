"""Hermetic tests for temporary Terraform state firewall access in CI."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "devops/scripts/azd/helpers/terraform-state-access.py"
WORKFLOW = ROOT / ".github/workflows/_template-deploy-azd.yml"

AZ_STUB = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
log = pathlib.Path(os.environ["AZ_CALL_LOG"])
with log.open("a") as stream:
    stream.write(json.dumps(args) + "\n")

profile_id = os.environ.get(
    "NSP_PROFILE_ID",
    "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
    "networkSecurityPerimeters/state-nsp/profiles/state-profile",
)
storage_id = (
    "/subscriptions/sub/resourceGroups/rg-state/providers/Microsoft.Storage/"
    "storageAccounts/stateacct"
)

if args[:3] == ["storage", "account", "show"]:
    print(json.dumps({
        "id": storage_id,
        "publicNetworkAccess": os.environ.get("ACCOUNT_PNA", "Enabled"),
        "networkRuleSet": {
            "defaultAction": os.environ.get("ACCOUNT_DEFAULT", "Deny"),
            "ipRules": [
                {"ipAddressOrRange": item}
                for item in json.loads(os.environ.get("IP_RULES", "[]"))
            ],
        },
    }))
elif args[:4] == ["storage", "account", "network-rule", "add"]:
    lease = pathlib.Path(os.environ["EXPECTED_LEASE"])
    if not lease.exists():
        sys.exit(91)
elif args[:4] == ["storage", "account", "network-rule", "remove"]:
    if os.environ.get("FAIL_REMOVE") == "true":
        sys.exit(4)
elif args[:3] == ["rest", "--method", "get"]:
    url = args[args.index("--url") + 1].split("?", 1)[0]
    if url == profile_id:
        print(json.dumps({"id": os.environ.get("RETURNED_PROFILE_ID", profile_id)}))
    elif url.endswith("/resourceAssociations"):
        print(json.dumps({"value": [{
            "id": url + "/state-association",
            "properties": {
                "accessMode": os.environ.get("ASSOCIATION_MODE", "Enforced"),
                "privateLinkResource": {
                    "id": os.environ.get("ASSOCIATION_RESOURCE_ID", storage_id)
                },
                "profile": {
                    "id": os.environ.get("ASSOCIATION_PROFILE_ID", profile_id)
                },
            },
        }]}))
    elif url.endswith("/accessRules"):
        rules = [{
            "id": url + "/approved-rule",
            "properties": {
                "direction": "Inbound",
                "addressPrefixes": json.loads(os.environ.get("NSP_RULES", "[]")),
            },
        }]
        rule_file = pathlib.Path(os.environ["NSP_RULE_STATE"])
        if rule_file.exists():
            rules.append(json.loads(rule_file.read_text()))
        print(json.dumps({"value": rules}))
    else:
        sys.exit(5)
elif args[:3] == ["rest", "--method", "put"]:
    if not pathlib.Path(os.environ["EXPECTED_LEASE"]).exists():
        sys.exit(91)
    if os.environ.get("FAIL_ADD_BEFORE_WRITE") == "true":
        sys.exit(4)
    body = json.loads(args[args.index("--body") + 1])
    body["id"] = args[args.index("--url") + 1].split("?", 1)[0]
    pathlib.Path(os.environ["NSP_RULE_STATE"]).write_text(json.dumps(body))
    if os.environ.get("FAIL_ADD_AFTER_WRITE") == "true":
        sys.exit(4)
elif args[:3] == ["rest", "--method", "delete"]:
    if os.environ.get("FAIL_REMOVE") == "true":
        sys.exit(4)
    pathlib.Path(os.environ["NSP_RULE_STATE"]).unlink(missing_ok=True)
elif args[:3] == ["storage", "blob", "exists"]:
    count_path = pathlib.Path(os.environ["BLOB_COUNT"])
    count = int(count_path.read_text()) if count_path.exists() else 0
    count_path.write_text(str(count + 1))
    failures = int(os.environ.get("BLOB_FAILURES", "0"))
    if count < failures:
        sys.exit(3)
    print(os.environ.get("BLOB_EXISTS", "true"))
"""


def _environment(tmp_path: Path, **overrides: str) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    az = bin_dir / "az"
    az.write_text(AZ_STUB)
    az.chmod(az.stat().st_mode | stat.S_IXUSR)
    calls = tmp_path / "az-calls.jsonl"
    calls.unlink(missing_ok=True)
    (tmp_path / "blob-count").unlink(missing_ok=True)
    lease = tmp_path / "lease.json"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "AZ_CALL_LOG": str(calls),
        "EXPECTED_LEASE": str(lease),
        "BLOB_COUNT": str(tmp_path / "blob-count"),
        "NSP_RULE_STATE": str(tmp_path / "nsp-rule.json"),
        "TF_STATE_NSP_PROFILE_ID": "",
        "AZURE_SUBSCRIPTION_ID": "sub",
        "RS_RESOURCE_GROUP": "rg-state",
        "RS_STORAGE_ACCOUNT": "stateacct",
        "RS_CONTAINER_NAME": "tfstate",
        "RS_STATE_KEY": "dev.tfstate",
        "TF_STATE_RUNNER_IP": "203.0.113.10",
        "TF_STATE_MANAGE_RUNNER_IP": "true",
        "GITHUB_RUN_ID": "run-123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "preview",
        **overrides,
    }
    return env, calls, lease


def _run(
    tmp_path: Path,
    command: str,
    *,
    env_overrides: dict[str, str] | None = None,
    lease: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[list[str]], Path]:
    env, calls_path, default_lease = _environment(tmp_path, **(env_overrides or {}))
    lease_path = lease or default_lease
    env["EXPECTED_LEASE"] = str(lease_path)
    result = subprocess.run(
        [
            "python",
            str(HELPER),
            command,
            "--lease-file",
            str(lease_path),
            "--attempts",
            "4",
            "--delay",
            "0",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    calls = (
        [json.loads(line) for line in calls_path.read_text().splitlines()]
        if calls_path.exists()
        else []
    )
    return result, calls, lease_path


def _calls_starting(calls: list[list[str]], prefix: list[str]) -> list[list[str]]:
    return [call for call in calls if call[: len(prefix)] == prefix]


def test_opt_out_performs_zero_azure_mutations_or_reads(tmp_path: Path) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"TF_STATE_MANAGE_RUNNER_IP": "false"},
    )
    assert result.returncode == 0, result.stderr
    assert calls == []
    assert not lease.exists()
    assert "disabled" in result.stdout


@pytest.mark.parametrize("ip", ["0.0.0.0/0", "203.0.113.0/24", "not-an-ip", "2001:db8::1"])
def test_open_rejects_anything_except_one_ipv4_before_azure(tmp_path: Path, ip: str) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"TF_STATE_RUNNER_IP": ip},
    )
    assert result.returncode == 1
    assert "one IPv4" in result.stderr
    assert calls == []
    assert not lease.exists()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"ACCOUNT_PNA": "Disabled"}, "publicNetworkAccess"),
        ({"ACCOUNT_DEFAULT": "Allow"}, "defaultAction"),
    ],
)
def test_open_requires_enabled_deny_foundation_before_mutation(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    result, calls, lease = _run(tmp_path, "open", env_overrides=override)
    assert result.returncode == 1
    assert message in result.stderr
    assert len(_calls_starting(calls, ["storage", "account", "show"])) == 1
    assert not _calls_starting(calls, ["storage", "account", "network-rule"])
    assert not lease.exists()


def test_open_creates_private_matching_lease_before_add_and_polls_propagation(
    tmp_path: Path,
) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"BLOB_FAILURES": "2"},
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(lease.read_text())
    assert data == {
        "blob": "dev.tfstate",
        "container": "tfstate",
        "mode": "classic",
        "nsp_profile_id": None,
        "owns_rule": True,
        "resource_group": "rg-state",
        "rule_id": None,
        "rule_added": True,
        "run_id": "run-123",
        "runner_ip": "203.0.113.10",
        "storage_account": "stateacct",
        "subscription_id": "sub",
        "version": 2,
    }
    assert stat.S_IMODE(lease.stat().st_mode) == 0o600
    assert len(_calls_starting(calls, ["storage", "blob", "exists"])) == 3
    for call in calls:
        assert call[call.index("--subscription") + 1] == "sub"
    add = _calls_starting(calls, ["storage", "account", "network-rule", "add"])[0]
    assert add[add.index("--resource-group") + 1] == "rg-state"
    assert add[add.index("--account-name") + 1] == "stateacct"
    assert add[add.index("--ip-address") + 1] == "203.0.113.10"
    blob = _calls_starting(calls, ["storage", "blob", "exists"])[0]
    assert blob[blob.index("--auth-mode") + 1] == "login"


def test_existing_cidr_is_preserved_by_open_and_close(tmp_path: Path) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"IP_RULES": '["203.0.113.0/24"]'},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(lease.read_text())["owns_rule"] is False
    assert json.loads(lease.read_text())["rule_added"] is False
    assert not _calls_starting(calls, ["storage", "account", "network-rule", "add"])

    close_result, close_calls, _ = _run(tmp_path, "close", lease=lease)
    assert close_result.returncode == 0, close_result.stderr
    assert close_calls == []
    assert not lease.exists()


def test_close_removes_only_the_exact_rule_owned_by_the_lease(tmp_path: Path) -> None:
    opened, _, lease = _run(tmp_path, "open")
    assert opened.returncode == 0, opened.stderr

    closed, calls, _ = _run(tmp_path, "close", lease=lease)
    assert closed.returncode == 0, closed.stderr
    removes = _calls_starting(calls, ["storage", "account", "network-rule", "remove"])
    assert len(removes) == 1
    remove = removes[0]
    assert remove[remove.index("--ip-address") + 1] == "203.0.113.10"
    assert remove[remove.index("--resource-group") + 1] == "rg-state"
    assert remove[remove.index("--account-name") + 1] == "stateacct"
    assert not lease.exists()


def test_false_blob_result_fails_without_creating_alternate_state_and_remains_cleanable(
    tmp_path: Path,
) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"BLOB_EXISTS": "false"},
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr
    assert json.loads(lease.read_text())["rule_added"] is True
    assert len(_calls_starting(calls, ["storage", "blob", "exists"])) == 1
    assert all("create" not in call for call in calls)

    cleanup, cleanup_calls, _ = _run(tmp_path, "close", lease=lease)
    assert cleanup.returncode == 0, cleanup.stderr
    assert (
        len(_calls_starting(cleanup_calls, ["storage", "account", "network-rule", "remove"])) == 1
    )


def test_close_rejects_mismatched_subscription_without_mutation(tmp_path: Path) -> None:
    opened, _, lease = _run(tmp_path, "open")
    assert opened.returncode == 0, opened.stderr

    closed, calls, _ = _run(
        tmp_path,
        "close",
        lease=lease,
        env_overrides={"AZURE_SUBSCRIPTION_ID": "other-sub"},
    )
    assert closed.returncode == 1
    assert "subscription" in closed.stderr
    assert calls == []
    assert lease.exists()


def test_close_rejects_mismatched_run_without_mutation(tmp_path: Path) -> None:
    opened, _, lease = _run(tmp_path, "open")
    assert opened.returncode == 0, opened.stderr

    closed, calls, _ = _run(
        tmp_path,
        "close",
        lease=lease,
        env_overrides={"GITHUB_RUN_ID": "run-456"},
    )
    assert closed.returncode == 1
    assert "workflow run" in closed.stderr
    assert calls == []
    assert lease.exists()


def test_cleanup_propagates_azure_errors_and_retains_lease(tmp_path: Path) -> None:
    opened, _, lease = _run(tmp_path, "open")
    assert opened.returncode == 0, opened.stderr

    closed, calls, _ = _run(
        tmp_path,
        "close",
        lease=lease,
        env_overrides={"FAIL_REMOVE": "true"},
    )
    assert closed.returncode == 1
    assert "Azure CLI operation failed" in closed.stderr
    assert len(_calls_starting(calls, ["storage", "account", "network-rule", "remove"])) == 1
    assert lease.exists()


def test_secured_by_perimeter_requires_explicit_profile(tmp_path: Path) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={"ACCOUNT_PNA": "SecuredByPerimeter"},
    )
    assert result.returncode == 1
    assert "TF_STATE_NSP_PROFILE_ID" in result.stderr
    assert not _calls_starting(calls, ["rest"])
    assert not lease.exists()


def test_nsp_open_validates_enforced_association_and_creates_owned_rule(
    tmp_path: Path,
) -> None:
    profile_id = (
        "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
        "networkSecurityPerimeters/state-nsp/profiles/state-profile"
    )
    overrides = {
        "ACCOUNT_PNA": "SecuredByPerimeter",
        "TF_STATE_NSP_PROFILE_ID": profile_id,
    }
    result, calls, lease = _run(tmp_path, "open", env_overrides=overrides)
    assert result.returncode == 0, result.stderr
    data = json.loads(lease.read_text())
    assert data["mode"] == "nsp"
    assert data["nsp_profile_id"] == profile_id
    assert data["rule_added"] is True
    assert data["owns_rule"] is True
    assert data["rule_id"].startswith(f"{profile_id}/accessRules/gha-preview-")
    put = _calls_starting(calls, ["rest", "--method", "put"])[0]
    assert put[put.index("--url") + 1].startswith(data["rule_id"] + "?api-version=2024-07-01")
    assert json.loads(put[put.index("--body") + 1]) == {
        "properties": {
            "addressPrefixes": ["203.0.113.10/32"],
            "direction": "Inbound",
        }
    }

    closed, close_calls, _ = _run(
        tmp_path,
        "close",
        lease=lease,
        env_overrides=overrides,
    )
    assert closed.returncode == 0, closed.stderr
    delete = _calls_starting(close_calls, ["rest", "--method", "delete"])[0]
    assert delete[delete.index("--url") + 1].startswith(data["rule_id"] + "?api-version=2024-07-01")
    assert not lease.exists()


def test_existing_nsp_cidr_is_preserved_without_create_or_delete(tmp_path: Path) -> None:
    profile_id = (
        "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
        "networkSecurityPerimeters/state-nsp/profiles/state-profile"
    )
    overrides = {
        "ACCOUNT_PNA": "SecuredByPerimeter",
        "TF_STATE_NSP_PROFILE_ID": profile_id,
        "NSP_RULES": '["203.0.113.0/24"]',
    }
    opened, calls, lease = _run(tmp_path, "open", env_overrides=overrides)
    assert opened.returncode == 0, opened.stderr
    assert json.loads(lease.read_text())["rule_added"] is False
    assert not _calls_starting(calls, ["rest", "--method", "put"])

    closed, close_calls, _ = _run(
        tmp_path,
        "close",
        lease=lease,
        env_overrides=overrides,
    )
    assert closed.returncode == 0, closed.stderr
    assert not _calls_starting(close_calls, ["rest", "--method", "delete"])


def test_nsp_rejects_existing_all_network_rule(tmp_path: Path) -> None:
    profile_id = (
        "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
        "networkSecurityPerimeters/state-nsp/profiles/state-profile"
    )
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={
            "ACCOUNT_PNA": "SecuredByPerimeter",
            "TF_STATE_NSP_PROFILE_ID": profile_id,
            "NSP_RULES": '["0.0.0.0/0"]',
        },
    )
    assert result.returncode == 1
    assert "all-network" in result.stderr
    assert not _calls_starting(calls, ["rest", "--method", "put"])
    assert not lease.exists()


@pytest.mark.parametrize("failure", ["FAIL_ADD_BEFORE_WRITE", "FAIL_ADD_AFTER_WRITE"])
def test_failed_nsp_creation_retains_cleanup_intent(tmp_path: Path, failure: str) -> None:
    overrides = {
        "ACCOUNT_PNA": "SecuredByPerimeter",
        "TF_STATE_NSP_PROFILE_ID": (
            "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
            "networkSecurityPerimeters/state-nsp/profiles/state-profile"
        ),
        failure: "true",
    }
    result, _, lease = _run(tmp_path, "open", env_overrides=overrides)
    assert result.returncode != 0
    assert json.loads(lease.read_text())["rule_added"] is True
    result, calls, _ = _run(tmp_path, "close", env_overrides=overrides, lease=lease)
    assert result.returncode == 0, result.stderr
    deletes = _calls_starting(calls, ["rest", "--method", "delete"])
    assert bool(deletes) == (failure == "FAIL_ADD_AFTER_WRITE")
    assert not lease.exists()


def test_existing_lease_is_not_overwritten(tmp_path: Path) -> None:
    opened, _, lease = _run(tmp_path, "open")
    assert opened.returncode == 0
    original = lease.read_bytes()
    repeated, calls, _ = _run(tmp_path, "open", lease=lease)
    assert repeated.returncode != 0
    assert "lease already exists" in repeated.stderr
    assert lease.read_bytes() == original
    assert calls == []


def test_all_network_rule_is_rejected_even_after_a_covering_rule(tmp_path: Path) -> None:
    result, _, _ = _run(
        tmp_path,
        "open",
        env_overrides={"IP_RULES": '["203.0.113.0/24", "0.0.0.0/0"]'},
    )
    assert result.returncode != 0
    assert "all-network" in result.stderr


def test_read_only_validation_does_not_create_a_lease_or_rule(tmp_path: Path) -> None:
    result, calls, lease = _run(tmp_path, "validate")
    assert result.returncode == 0, result.stderr
    assert not lease.exists()
    assert not _calls_starting(calls, ["storage", "account", "network-rule"])
    assert len(_calls_starting(calls, ["storage", "blob", "exists"])) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ASSOCIATION_MODE": "Learning"}, "Enforced"),
        (
            {
                "ASSOCIATION_RESOURCE_ID": (
                    "/subscriptions/sub/resourceGroups/x/providers/Microsoft.Storage/"
                    "storageAccounts/other"
                )
            },
            "exactly one",
        ),
    ],
)
def test_nsp_rejects_nonmatching_or_non_enforced_association_before_mutation(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    profile_id = (
        "/subscriptions/sub/resourceGroups/rg-nsp/providers/Microsoft.Network/"
        "networkSecurityPerimeters/state-nsp/profiles/state-profile"
    )
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={
            "ACCOUNT_PNA": "SecuredByPerimeter",
            "TF_STATE_NSP_PROFILE_ID": profile_id,
            **overrides,
        },
    )
    assert result.returncode == 1
    assert message in result.stderr
    assert not _calls_starting(calls, ["rest", "--method", "put"])
    assert not lease.exists()


def test_nsp_profile_must_match_explicit_subscription_before_rest_calls(
    tmp_path: Path,
) -> None:
    result, calls, lease = _run(
        tmp_path,
        "open",
        env_overrides={
            "ACCOUNT_PNA": "SecuredByPerimeter",
            "TF_STATE_NSP_PROFILE_ID": (
                "/subscriptions/other/resourceGroups/rg-nsp/providers/Microsoft.Network/"
                "networkSecurityPerimeters/state-nsp/profiles/state-profile"
            ),
        },
    )
    assert result.returncode == 1
    assert "subscription" in result.stderr
    assert not _calls_starting(calls, ["rest"])
    assert not lease.exists()


def test_workflow_opens_before_state_operations_and_always_closes() -> None:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    for job_name, operation_name in (
        ("preview", "Run Preprovision Hook"),
        ("execute", "azd provision"),
    ):
        steps = workflow["jobs"][job_name]["steps"]
        open_index = next(
            index
            for index, step in enumerate(steps)
            if "Open Terraform State Access" in step["name"]
        )
        operation_index = next(
            index for index, step in enumerate(steps) if operation_name in step["name"]
        )
        cleanup = next(step for step in steps if "Close Terraform State Access" in step["name"])
        assert open_index < operation_index
        assert cleanup["if"] == "always()"
        assert "--lease-file" in cleanup["run"]
    assert workflow["jobs"]["preview"]["env"]["TF_STATE_MANAGE_RUNNER_IP"].endswith("|| 'false' }}")
    assert workflow["jobs"]["execute"]["env"]["TF_STATE_MANAGE_RUNNER_IP"].endswith("|| 'false' }}")
    assert "TF_STATE_NSP_PROFILE_ID" in workflow["jobs"]["preview"]["env"]
    assert "TF_STATE_NSP_PROFILE_ID" in workflow["jobs"]["execute"]["env"]


def test_manual_state_validation_is_available_without_deployment() -> None:
    entry = yaml.load(
        (ROOT / ".github/workflows/deploy-azd-complete.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    inputs = entry["on"]["workflow_dispatch"]["inputs"]
    assert "validate-state" in inputs["action"]["options"]
    assert "mosdev" in inputs["environment"]["options"]
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["execute"]["steps"]
    validation = next(step for step in steps if "Validate State Access with AZD" in step["name"])
    assert validation["if"] == "inputs.action == 'validate-state'"
    assert "terraform-state-access.py validate" in validation["run"]
    assert "azd env refresh" in validation["run"]
    assert "terraform -chdir=infra/terraform init" in validation["run"]
    assert "TF_DATA_DIR=" in validation["run"]
    assert "inputs.action != 'validate-state'" in workflow["jobs"]["finalize"]["if"]
    deployment_steps = [
        step
        for step in steps
        if any(
            command in step.get("run", "")
            for command in (
                "azd provision --no-prompt",
                "azd deploy --no-prompt",
                "azd down --force",
                "make enable_public_networking",
            )
        )
    ]
    assert deployment_steps
    assert all("validate-state" not in step["if"] for step in deployment_steps)
    for job_name in ("preview", "execute"):
        setup = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if step.get("uses") == "hashicorp/setup-terraform@v3"
        )
        assert setup["with"]["terraform_wrapper"] == "false"


def test_secure_workflow_cannot_silently_reopen_public_networking() -> None:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    public = next(
        step
        for step in workflow["jobs"]["execute"]["steps"]
        if "Make Resources Public" in step["name"]
    )
    assert "vars.ALLOW_LEGACY_PUBLIC_NETWORKING == 'true'" in public["if"]
    assert "TF_STATE_NSP_PROFILE_ID" in public["run"]
    assert "FRONT_DOOR_ENABLED" in public["run"]
    assert "exit 1" in public["run"]
    cors = next(
        step
        for step in workflow["jobs"]["execute"]["steps"]
        if "Repair Backend CORS" in step["name"]
    )
    assert "FRONTEND_PUBLIC_FQDN" in cors["run"]
