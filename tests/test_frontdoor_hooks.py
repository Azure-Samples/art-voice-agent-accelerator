"""Hermetic lifecycle tests: every Azure and HTTP operation is a local CLI stub."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "devops/scripts/azd"
ENVIRONMENT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.App/managedEnvironments/env"
PROFILE = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Cdn/profiles/afd-test"
ACS = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Communication/communicationServices/acs"
MESSAGE = "ART Front Door afd-test-token"
SECRET = 'test-secret-"quoted"-value-with-32-plus-characters'

CLI_STUB = r"""
import json, os, stat, sys
from pathlib import Path

state_path = Path(os.environ["MOCK_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
state.setdefault("calls", []).append([tool, *args])
def save():
    state_path.write_text(json.dumps(state))
def out(value="", code=0):
    save()
    print(json.dumps(value) if isinstance(value, (dict, list)) else value)
    sys.exit(code)
def arg(name):
    return args[args.index(name) + 1]
def body():
    value = arg("--body")
    if value.startswith("@"):
        path = Path(value[1:])
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        result = json.loads(path.read_text())
    else:
        result = json.loads(value)
    state.setdefault("bodies", []).append(result)
    return result

if tool == "azd":
    if args[:2] == ["env", "get-values"]:
        out(state["env"], 1 if state.get("azd_env_failure") else 0)
    if args[:2] == ["env", "get-value"]:
        out(state["env"].get(args[2], ""), 0 if args[2] in state["env"] else 1)
    if args[:2] == ["env", "set"]:
        state["env"][args[2]] = args[3]
        out()
if tool == "sleep":
    out()
if tool == "curl":
    config = Path(arg("--config"))
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert state["secret"] in json.loads(config.read_text().split(" = ", 1)[1])
    payload = json.loads(Path(arg("--data-binary")[1:]).read_text())
    state.setdefault("probes", []).append(payload)
    assert payload[0]["topic"] == state["env"]["ACS_RESOURCE_ID"]
    codes = state.setdefault("http_codes", [200])
    code = codes.pop(0) if len(codes) > 1 else codes[0]
    if code == 0:
        out("", 7)
    response = {"validationResponse": payload[0]["data"]["validationCode"]}
    if state.get("bad_validation"):
        response = {"status": "placeholder"}
    out(json.dumps(response) + "\n" + str(code))
if tool == "az":
    if args[:3] == ["keyvault", "secret", "show"]:
        if state.get("secret_failure"):
            out("sensitive diagnostic", 1)
        out(state["secret"])
    if args[:3] == ["appconfig", "kv", "set"]:
        out("", int(state.get("appconfig_failure", False)))
    if args[:3] == ["appconfig", "kv", "show"]:
        out("")
    if args[:3] == ["containerapp", "secret", "list"]:
        out("override-use-mi-fic-assertion-client-id")
    if args[:2] == ["containerapp", "show"]:
        out("origin.azurecontainerapps.io")
    if args[:2] == ["containerapp", "list"]:
        out("")
    if args[:2] == ["account", "show"]:
        out("tenant" if arg("--query") == "tenantId" else "sub")
    if args[:3] == ["ad", "app", "list"]:
        out("app-id")
    if args[:3] in (["ad", "app", "update"], ["ad", "sp", "show"]):
        out()
    if args[:4] == ["ad", "app", "federated-credential", "list"]:
        out("actual-credential-id")
    if args[:4] == ["ad", "app", "federated-credential", "update"]:
        out()
    if args[:2] == ["provider", "show"]:
        out(state.get("provider_status", "Registered"))
    if args[:2] == ["provider", "register"]:
        out("", int(state.get("provider_failure", False)))
    if args[0] == "rest":
        url = arg("--url") if "--url" in args else arg("--uri")
        method = arg("--method")
        if state.get("rest_failure"):
            out("diagnostic-may-contain-secret", 1)
        if "/privateEndpointConnections" in url:
            if method == "PUT":
                value = body()
                connection = next(item for item in state["connections"] if item["id"] == url.split("?")[0])
                if not state.get("keep_pending"):
                    connection["properties"]["privateLinkServiceConnectionState"] = value["properties"]["privateLinkServiceConnectionState"]
                out({})
            out({"value": state.get("connections", [])})
        if "/originGroups" in url:
            if "/origins?" in url:
                out({"value": [{"properties": {
                    "provisioningState": state.get("origin_provisioning_state", "Succeeded"),
                    "sharedPrivateLinkResource": {
                    "privateLink": {"id": state["env"]["CONTAINER_APPS_ENVIRONMENT_ID"]},
                    "requestMessage": state.get("origin_message", state["env"]["FRONT_DOOR_PRIVATE_LINK_REQUEST_MESSAGE"]),
                    "status": state.get("origin_status", "Approved")
                }}}]})
            out({"value": [{"id": state["env"]["FRONT_DOOR_PROFILE_ID"] + "/originGroups/group"}]})
        if "/eventSubscriptions" in url:
            if method == "PUT":
                if state.get("subscription_put_failure"):
                    out("sensitive diagnostic", 1)
                body()
                out({"properties": {"provisioningState": "Creating"}})
            if "/eventSubscriptions?" in url:
                out({"value": state.get("subscriptions", [])})
            out({"properties": {"provisioningState": state.get("subscription_status", "Succeeded")}})
        if "/authConfigs/" in url:
            body()
            out({})
out("Unexpected mock operation: " + tool + " " + " ".join(args), 97)
"""


@pytest.fixture
def hooks(tmp_path: Path):
    """Copy only hook files and install fail-on-unexpected-operation CLI stubs."""
    scripts = tmp_path / "devops/scripts/azd"
    shutil.copytree(SCRIPTS, scripts)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for tool in ("az", "azd", "curl", "sleep"):
        path = binaries / tool
        path.write_text(f"#!{sys.executable}\n{CLI_STUB}")
        path.chmod(0o755)
    state = {
        "env": {
            "FRONT_DOOR_ENABLED": "true",
            "CONTAINER_APPS_ENVIRONMENT_ID": ENVIRONMENT,
            "FRONT_DOOR_PROFILE_ID": PROFILE,
            "FRONT_DOOR_PRIVATE_LINK_REQUEST_MESSAGE": MESSAGE,
            "ACS_RESOURCE_ID": ACS,
            "BACKEND_API_URL": "https://backend.azurefd.net",
            "FRONTEND_PUBLIC_FQDN": "frontend.azurefd.net",
            "FRONTEND_CONTAINER_APP_URL": "https://frontend.azurefd.net",
            "FRONTEND_CONTAINER_APP_FQDN": "origin.azurecontainerapps.io",
            "AZURE_KEY_VAULT_NAME": "vault",
            "EVENT_GRID_WEBHOOK_SECRET_NAME": "event-grid-webhook-secret",
            "AZURE_APPCONFIG_ENDPOINT": "https://config.azconfig.io",
            "AZURE_ENV_NAME": "test",
            "AZURE_RESOURCE_GROUP": "rg",
            "BACKEND_CONTAINER_APP_NAME": "backend",
            "FRONTEND_CONTAINER_APP_NAME": "frontend",
            "FRONTEND_UAI_CLIENT_ID": "identity-client",
        },
        "secret": SECRET,
    }
    state_path = tmp_path / "state.json"
    env = {
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "MOCK_STATE": str(state_path),
        "FRONT_DOOR_MAX_ATTEMPTS": "3",
        "FRONT_DOOR_POLL_SECONDS": "0",
        "CI": "true",
    }

    def run(command: list[str], *, overrides: dict | None = None):
        state_path.write_text(json.dumps(state))
        result = subprocess.run(
            command,
            cwd=tmp_path,
            env={**env, **(overrides or {})},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        state.clear()
        state.update(json.loads(state_path.read_text()))
        assert not list(tmp_path.glob(".frontdoor-hook-*")), "Secret scratch files leaked"
        assert SECRET not in result.stdout + result.stderr
        assert SECRET not in json.dumps(state.get("calls", []))
        return result

    return tmp_path, scripts, state, run


def connection(name: str, *, message: str = MESSAGE, status: str = "Pending") -> dict:
    """Build a Container Apps private endpoint response."""
    return {
        "id": f"{ENVIRONMENT}/privateEndpointConnections/{name}",
        "properties": {
            "privateLinkServiceConnectionState": {"description": message, "status": status}
        },
    }


def stage(hooks, name: str, **kwargs):
    """Execute the real lifecycle helper against mock CLI processes."""
    _, scripts, _, run = hooks
    return run([sys.executable, str(scripts / "helpers/frontdoor.py"), name], **kwargs)


@pytest.mark.parametrize("name", ["provision", "deploy"])
def test_opt_out_has_no_azure_or_http_calls(hooks, name):
    result = stage(hooks, name, overrides={"FRONT_DOOR_ENABLED": "false"})
    assert result.returncode == 0, result.stderr
    assert hooks[2].get("calls", []) == []


def test_environment_read_failure_does_not_silently_disable_frontdoor(hooks):
    hooks[2]["azd_env_failure"] = True
    result = stage(hooks, "provision")
    assert result.returncode != 0
    assert "azd operation failed" in result.stderr
    assert not any(call[0] in ("az", "curl") for call in hooks[2]["calls"])


def test_legacy_environment_without_resolved_output_is_opted_out(hooks):
    del hooks[2]["env"]["FRONT_DOOR_ENABLED"]
    result = stage(hooks, "provision")
    assert result.returncode == 0, result.stderr
    assert not any(call[0] in ("az", "curl") for call in hooks[2]["calls"])


def test_preflight_does_not_retarget_an_existing_environment(hooks):
    _, scripts, state, run = hooks
    state["env"]["AZURE_SUBSCRIPTION_ID"] = "expected-sub"
    result = run(
        [
            "bash",
            "-c",
            'source "$1"; configure_subscription',
            "test",
            str(scripts / "helpers/preflight-checks.sh"),
        ]
    )
    assert result.returncode != 0
    assert "does not match this azd environment" in result.stderr
    assert not any(call[:3] == ["azd", "env", "set"] for call in state["calls"])


@pytest.mark.parametrize("script", ["enable-easyauth.sh", "enable-easyauth-cardapi-mcp.sh"])
def test_existing_federated_credential_uses_resolved_identifier(hooks, script):
    _, scripts, state, run = hooks
    result = run(
        [
            "bash",
            "-c",
            'source "$1"; APP_ID=app-id; CLOUD_ENV=AzureCloud; ISSUER=https://issuer; '
            "get_uami_details_from_container_app() { UAMI_PRINCIPAL_ID=principal-id; }; "
            "configure_federated_credential",
            "test",
            str(scripts / "helpers" / script),
        ]
    )
    assert result.returncode == 0, result.stderr
    update = next(
        call
        for call in state["calls"]
        if call[:5] == ["az", "ad", "app", "federated-credential", "update"]
    )
    assert update[update.index("--federated-credential-id") + 1] == "actual-credential-id"


@pytest.mark.parametrize("value", ["yes", "1", "", "garbage"])
def test_bad_resolved_flag_fails_without_cloud_calls(hooks, value):
    result = stage(hooks, "deploy", overrides={"FRONT_DOOR_ENABLED": value})
    assert result.returncode != 0
    assert "must be true or false" in result.stderr
    assert hooks[2].get("calls", []) == []


@pytest.mark.parametrize("name", ["provision", "deploy"])
@pytest.mark.parametrize("resolved", ["true", "false"])
def test_lifecycle_gating_uses_resolved_output_not_desired_input(hooks, name, resolved):
    state = hooks[2]
    state["env"]["FRONT_DOOR_ENABLED"] = resolved
    desired = "false" if resolved == "true" else "true"
    state["env"]["ENABLE_FRONT_DOOR"] = desired
    state["connections"] = [connection("ours", status="Approved")]
    result = stage(hooks, name, overrides={"ENABLE_FRONT_DOOR": desired})
    assert result.returncode == 0, result.stderr
    assert any(call[0] == "az" for call in state["calls"]) == (resolved == "true")
    assert not any(
        call[:3] == ["azd", "env", "get-value"] and call[3] == "ENABLE_FRONT_DOOR"
        for call in state["calls"]
    )


def test_private_links_approve_only_exact_scoped_requests(hooks):
    state = hooks[2]
    state["connections"] = [
        connection("ours-1"),
        connection("ours-2"),
        connection("already", status="Approved"),
        connection("unrelated", message=MESSAGE + "-other"),
    ]
    result = stage(hooks, "provision")
    assert result.returncode == 0, result.stderr
    assert len(state["bodies"]) == 2
    assert all(
        body["properties"]["privateLinkServiceConnectionState"]["description"] == MESSAGE
        for body in state["bodies"]
    )
    assert (
        state["connections"][-1]["properties"]["privateLinkServiceConnectionState"]["status"]
        == "Pending"
    )
    assert not any("/eventSubscriptions" in str(call) for call in state["calls"])


@pytest.mark.parametrize("provisioning,success", [("Succeeded", True), ("Creating", False)])
def test_nullable_origin_link_status_requires_approved_connection_and_ready_origin(
    hooks, provisioning, success
):
    state = hooks[2]
    state["connections"] = [connection("ours", status="Approved")]
    state["origin_status"] = None
    state["origin_provisioning_state"] = provisioning
    result = stage(hooks, "provision")
    assert (result.returncode == 0) is success, result.stderr
    assert not any("/eventSubscriptions" in str(call) for call in state["calls"])


@pytest.mark.parametrize("status", ["Rejected", "Disconnected", "Unknown"])
def test_private_link_rejection_fails_without_approval(hooks, status):
    hooks[2]["connections"] = [connection("ours", status=status)]
    result = stage(hooks, "provision")
    assert result.returncode != 0
    assert status in result.stderr
    assert not hooks[2].get("bodies")


@pytest.mark.parametrize(
    "mode", ["unrelated", "pending", "origin-pending", "origin-mismatch", "az-error"]
)
def test_private_link_failures_are_bounded_and_fail_closed(hooks, mode):
    state = hooks[2]
    state["connections"] = [connection("ours")]
    if mode == "unrelated":
        state["connections"] = [connection("foreign", message="other-deployment")]
    if mode == "pending":
        state["keep_pending"] = True
    if mode == "origin-pending":
        state["origin_status"] = "Pending"
    if mode == "origin-mismatch":
        state["origin_message"] = "foreign"
    if mode == "az-error":
        state["rest_failure"] = True
    result = stage(hooks, "provision")
    assert result.returncode != 0
    assert "hook failed" in result.stderr
    assert len(state.get("bodies", [])) <= 1


def test_postdeploy_subscription_is_secret_authenticated_and_owned(hooks):
    _, scripts, state, run = hooks
    state["http_codes"] = [502, 503, 200]
    result = run(["bash", str(scripts / "postdeploy.sh")])
    assert result.returncode == 0, result.stderr
    assert len(state["probes"]) == 3
    body = state["bodies"][0]["properties"]
    assert body["eventDeliverySchema"] == "EventGridSchema"
    assert body["filter"]["includedEventTypes"] == ["Microsoft.Communication.IncomingCall"]
    destination = body["destination"]["properties"]
    assert destination["endpointUrl"] == "https://backend.azurefd.net/api/v1/calls/answer"
    assert destination["deliveryAttributeMappings"] == [
        {
            "name": "X-EventGrid-Webhook-Secret",
            "type": "Static",
            "properties": {"value": SECRET, "isSecret": True},
        }
    ]
    assert body["labels"][0].startswith("art-frontdoor-")
    write = next(call for call in state["calls"] if "PUT" in call)
    assert ACS + "/providers/Microsoft.EventGrid/eventSubscriptions/art-incoming-call-" in str(
        write
    )
    assert "2022-06-15" in str(write)


@pytest.mark.parametrize("failure", [401, 403, 404, 500, 502, 503, 0, "placeholder"])
def test_readiness_failure_never_creates_subscription(hooks, failure):
    state = hooks[2]
    if failure == "placeholder":
        state["bad_validation"] = True
    else:
        state["http_codes"] = [failure]
    result = stage(hooks, "deploy")
    assert result.returncode != 0
    assert not state.get("bodies")
    assert len(state["probes"]) == (3 if failure in (0, 404, 502, 503) else 1)


@pytest.mark.parametrize("types", [None, ["All"], ["Microsoft.Communication.IncomingCall"]])
def test_competing_incoming_subscription_is_not_deleted_or_duplicated(hooks, types):
    state = hooks[2]
    state["subscriptions"] = [
        {
            "name": "user-owned",
            "properties": {
                "filter": {"includedEventTypes": types},
                "destination": {
                    "endpointType": "WebHook",
                    "properties": {
                        "endpointUrl": "https://old-origin.azurecontainerapps.io/api/v1/calls/answer"
                    },
                },
            },
        }
    ]
    result = stage(hooks, "deploy")
    assert result.returncode != 0
    assert "Competing" in result.stderr and "user-owned" in result.stderr
    assert not state.get("bodies") and not state.get("probes")


def test_owned_subscription_can_be_updated_but_name_collision_cannot(hooks):
    import hashlib

    owner = hashlib.sha256(PROFILE.lower().encode()).hexdigest()[:20]
    state = hooks[2]
    state["subscriptions"] = [
        {
            "name": f"art-incoming-call-{owner}",
            "properties": {
                "labels": [f"art-frontdoor-{owner}"],
            },
        }
    ]
    assert stage(hooks, "deploy").returncode == 0
    state["subscriptions"][0]["properties"]["labels"] = []
    state["bodies"] = []
    result = stage(hooks, "deploy")
    assert result.returncode != 0 and "ownership" in result.stderr
    assert not state["bodies"]


@pytest.mark.parametrize(
    "values,params,expected",
    [
        (
            {"ENABLE_FRONT_DOOR": "true", "CONTAINER_APP_WORKLOAD_PROFILES_ENABLED": "TRUE"},
            {},
            True,
        ),
        ({}, {"enable_front_door": True, "container_app_workload_profiles_enabled": True}, True),
        ({"ENABLE_FRONT_DOOR": "false"}, {"enable_front_door": True}, False),
        ({}, {}, None),
    ],
)
def test_tfvars_boolean_overrides_preserve_params(hooks, values, params, expected):
    workspace, scripts, state, run = hooks
    params_dir = workspace / "infra/terraform/params"
    params_dir.mkdir(parents=True)
    (params_dir / "main.tfvars.default.json").write_text(json.dumps(params))
    result = run(
        ["bash", "-c", f'source "{scripts}/preprovision.sh"; generate_tfvars_json'],
        overrides={
            "AZURE_ENV_NAME": "test",
            "AZURE_LOCATION": "eastus2",
            "AZURE_PRINCIPAL_ID": "principal",
            **values,
        },
    )
    assert result.returncode == 0, result.stderr
    generated = json.loads((params_dir.parent / "main.tfvars.json").read_text())
    assert generated.get("enable_front_door") is expected
    if expected:
        assert generated["container_app_workload_profiles_enabled"] is True


@pytest.mark.parametrize(
    "values",
    [
        {"ENABLE_FRONT_DOOR": "tru"},
        {"ENABLE_FRONT_DOOR": ""},
        {"ENABLE_FRONT_DOOR": "true", "CONTAINER_APP_WORKLOAD_PROFILES_ENABLED": "false"},
        {"CONTAINER_APP_WORKLOAD_PROFILES_ENABLED": "1"},
    ],
)
def test_invalid_tfvars_boolean_never_writes_output(hooks, values):
    workspace, scripts, state, run = hooks
    (workspace / "infra/terraform/params").mkdir(parents=True)
    result = run(
        ["bash", "-c", f'source "{scripts}/preprovision.sh"; generate_tfvars_json'],
        overrides={
            "AZURE_ENV_NAME": "test",
            "AZURE_LOCATION": "eastus2",
            "AZURE_PRINCIPAL_ID": "principal",
            **values,
        },
    )
    assert result.returncode != 0
    assert "Invalid Front Door" in result.stderr or "must be true or false" in result.stderr
    assert not (workspace / "infra/terraform/main.tfvars.json").exists()


@pytest.mark.parametrize("resolved,desired", [("false", True), ("true", False)])
def test_resolved_output_never_overrides_new_params_input(hooks, resolved, desired):
    workspace, scripts, state, run = hooks
    state["env"]["FRONT_DOOR_ENABLED"] = resolved
    params_dir = workspace / "infra/terraform/params"
    params_dir.mkdir(parents=True)
    (params_dir / "main.tfvars.default.json").write_text(
        json.dumps({"enable_front_door": desired, "container_app_workload_profiles_enabled": True})
    )
    result = run(
        ["bash", "-c", f'source "{scripts}/preprovision.sh"; generate_tfvars_json'],
        overrides={
            "AZURE_ENV_NAME": "test",
            "AZURE_LOCATION": "eastus2",
            "AZURE_PRINCIPAL_ID": "principal",
            "FRONT_DOOR_ENABLED": resolved,
        },
    )
    assert result.returncode == 0, result.stderr
    generated = json.loads((params_dir.parent / "main.tfvars.json").read_text())
    assert generated["enable_front_door"] is desired
    assert "ENABLE_FRONT_DOOR" not in state["env"]


@pytest.mark.parametrize(
    "helper,path,action",
    [
        ("enable-easyauth.sh", "/health.txt", "RedirectToLoginPage"),
        ("enable-easyauth-cardapi-mcp.sh", "/health", "Return401"),
    ],
)
@pytest.mark.parametrize("public", [True, False])
def test_easyauth_public_redirect_proxy_health_and_fic_preserved(
    hooks, helper, path, action, public
):
    _, scripts, state, run = hooks
    public_arg = "--public-url https://frontend.azurefd.net" if public else ""
    result = run(
        [
            "bash",
            "-c",
            f"""
        source "{scripts}/helpers/{helper}"
        parse_args -g rg -a frontend -i identity {public_arg}
        create_app_registration
        enable_container_app_auth
    """,
        ]
    )
    assert result.returncode == 0, result.stderr
    properties = state["bodies"][0]["properties"]
    aad = properties["identityProviders"]["azureActiveDirectory"]
    assert (
        aad["registration"]["clientSecretSettingName"] == "override-use-mi-fic-assertion-client-id"
    )
    assert properties["globalValidation"]["unauthenticatedClientAction"] == action
    redirect = next(call for call in state["calls"] if call[:4] == ["az", "ad", "app", "update"])
    if public:
        assert "https://frontend.azurefd.net/.auth/login/aad/callback" in redirect
        assert properties["httpSettings"]["forwardProxy"]["convention"] == "Standard"
        assert properties["globalValidation"]["excludedPaths"] == [path]
    else:
        assert "https://origin.azurecontainerapps.io/.auth/login/aad/callback" in redirect
        assert "httpSettings" not in properties
        assert "excludedPaths" not in properties["globalValidation"]


def test_postprovision_does_not_swallow_critical_failures(hooks):
    _, scripts, state, run = hooks
    state["connections"] = [connection("ours", status="Approved")]
    state["appconfig_failure"] = True
    result = run(
        [
            "bash",
            "-c",
            f"""
        source "{scripts}/postprovision.sh"
        task_cardapi_provision() {{ :; }}
        task_phone_number() {{ :; }}
        main
    """,
        ]
    )
    assert result.returncode != 0
    assert "Some updates failed" in result.stdout
    assert not any("containerapp" in call for call in state["calls"])


def test_frontend_cors_uses_public_hostname(hooks):
    _, scripts, state, run = hooks
    (scripts / "helpers/update-backend-cors.sh").write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
    result = run(
        ["bash", "-c", f'source "{scripts}/postprovision.sh"; task_update_backend_cors'],
        overrides={"FRONT_DOOR_ENABLED": "true"},
    )
    assert result.returncode == 0
    assert "frontend.azurefd.net" in result.stdout
    assert "origin.azurecontainerapps.io" not in result.stdout


def test_frontend_easyauth_refreshes_when_public_url_changes(hooks):
    _, scripts, state, run = hooks
    state["env"]["EASYAUTH_ENABLED"] = "true"
    state["env"]["FRONTEND_EASYAUTH_PUBLIC_URL"] = "https://old.azurefd.net"
    (scripts / "helpers/enable-easyauth.sh").write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
    result = run(
        ["bash", "-c", f'source "{scripts}/postprovision.sh"; task_enable_easyauth'],
        overrides={"FRONT_DOOR_ENABLED": "true"},
    )
    assert result.returncode == 0, result.stderr
    assert "--public-url\nhttps://frontend.azurefd.net" in result.stdout
    assert state["env"]["FRONTEND_EASYAUTH_PUBLIC_URL"] == "https://frontend.azurefd.net"


def test_frontdoor_provider_registration_failure_propagates(hooks):
    _, scripts, state, run = hooks
    state["provider_status"] = "NotRegistered"
    state["provider_failure"] = True
    result = run(
        [
            "bash",
            "-c",
            f"""
        source "{scripts}/helpers/preflight-checks.sh"
        check_frontdoor_resource_providers
    """,
        ]
    )
    assert result.returncode != 0
    assert any("Microsoft.Cdn" in call for call in state["calls"])


@pytest.mark.parametrize("value", ["true", "false", "", "not-a-boolean"])
def test_tfvars_reads_and_validates_azd_boolean_overrides(hooks, value):
    workspace, scripts, state, run = hooks
    state["env"]["ENABLE_FRONT_DOOR"] = value
    state["env"]["CONTAINER_APP_WORKLOAD_PROFILES_ENABLED"] = "true"
    (workspace / "infra/terraform/params").mkdir(parents=True)
    result = run(
        ["bash", "-c", f'source "{scripts}/preprovision.sh"; generate_tfvars_json'],
        overrides={
            "AZURE_ENV_NAME": "test",
            "AZURE_LOCATION": "eastus2",
            "AZURE_PRINCIPAL_ID": "principal",
        },
    )
    assert (result.returncode == 0) == (value in ("true", "false"))
    if result.returncode == 0:
        body = json.loads((workspace / "infra/terraform/main.tfvars.json").read_text())
        assert body["enable_front_door"] == (value == "true")


@pytest.mark.parametrize("status", ["Failed", "AwaitingManualAction"])
def test_subscription_must_finish_validation_before_success(hooks, status):
    hooks[2]["subscription_status"] = status
    result = stage(hooks, "deploy")
    assert result.returncode != 0
    assert "subscription" in result.stderr.lower()


@pytest.mark.parametrize("failure", ["secret_failure", "subscription_put_failure"])
def test_secret_and_subscription_write_failures_propagate(hooks, failure):
    hooks[2][failure] = True
    result = stage(hooks, "deploy")
    assert result.returncode != 0
    assert "operation failed" in result.stderr
    assert "sensitive diagnostic" not in result.stderr


@pytest.mark.parametrize(
    "secret", ["", "x" * 31, "x" * 4097, "x" * 32 + "é", "x" * 16 + "\t" + "x" * 16]
)
def test_webhook_secret_matches_backend_ascii_contract(hooks, secret):
    hooks[2]["secret"] = secret
    result = stage(hooks, "deploy")
    assert result.returncode != 0
    assert "32..4096 printable ASCII" in result.stderr
    assert not hooks[2].get("probes")
    assert not hooks[2].get("bodies")


def test_matching_request_cannot_escape_environment_scope(hooks):
    hooks[2]["connections"] = [connection("foreign")]
    hooks[2]["connections"][0]["id"] = (
        ENVIRONMENT.replace("/env", "/other") + "/privateEndpointConnections/foreign"
    )
    result = stage(hooks, "provision")
    assert result.returncode != 0
    assert "outside" in result.stderr
    assert not hooks[2].get("bodies")


def test_approval_failure_aborts_postprovision_before_other_cloud_tasks(hooks):
    _, scripts, state, run = hooks
    state["connections"] = [connection("ours", status="Rejected")]
    result = run(["bash", str(scripts / "postprovision.sh")])
    assert result.returncode != 0
    assert "Rejected" in result.stderr
    assert not any(call[1:3] == ["appconfig", "kv"] for call in state["calls"])


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_sync_failure_is_critical_only_for_frontdoor(hooks, enabled):
    _, scripts, state, run = hooks
    state["appconfig_failure"] = True
    result = run(
        ["bash", str(scripts / "helpers/sync-appconfig.sh")],
        overrides={"FRONT_DOOR_ENABLED": enabled},
    )
    assert (result.returncode != 0) == (enabled == "true")
    assert not any(
        key in call
        for call in state["calls"]
        for key in ("app/backend/base-url", "app/frontend/backend-url", "app/frontend/ws-url")
    )


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_provider_registration_is_opt_in(hooks, enabled):
    _, scripts, state, run = hooks
    result = run(
        [
            "bash",
            "-c",
            f"""
            source "{scripts}/preprovision.sh"
            source "{scripts}/helpers/preflight-checks.sh"
            resolve_location() {{ :; }}
            configure_terraform_backend() {{ :; }}
            generate_tfvars_json() {{ :; }}
            provider_terraform
        """,
        ],
        overrides={
            "ENABLE_FRONT_DOOR": enabled,
            "AZURE_ENV_NAME": "test",
            "AZURE_LOCATION": "eastus2",
            "LOCAL_STATE": "true",
            "TF_VAR_environment_name": "test",
        },
    )
    assert result.returncode == 0, result.stderr
    providers = [
        call[call.index("--namespace") + 1]
        for call in state.get("calls", [])
        if call[:3] == ["az", "provider", "show"]
    ]
    assert providers == (
        ["Microsoft.Cdn", "Microsoft.Network", "Microsoft.EventGrid"] if enabled == "true" else []
    )


@pytest.mark.parametrize("fail_final", [False, True])
def test_frontdoor_urls_are_final_writes_after_manifest_sync(hooks, fail_final):
    _, scripts, state, run = hooks
    state["connections"] = [connection("ours", status="Approved")]
    result = run(
        [
            "bash",
            "-c",
            f"""
            source "{scripts}/postprovision.sh"
            task_cardapi_provision() {{ :; }}
            task_phone_number() {{ :; }}
            task_update_backend_cors() {{ :; }}
            task_generate_env_local() {{ :; }}
            task_enable_easyauth() {{ :; }}
            task_enable_easyauth_cardapi_mcp() {{ :; }}
            task_sync_appconfig() {{
                appconfig_set https://config.azconfig.io app/backend/base-url https://origin.azurecontainerapps.io test
                appconfig_set https://config.azconfig.io app/frontend/backend-url https://origin.azurecontainerapps.io test
                appconfig_set https://config.azconfig.io app/frontend/ws-url wss://origin.azurecontainerapps.io test
                {"appconfig_set() { return 1; }" if fail_final else ":"}
            }}
            show_summary() {{ :; }}
            main
            """,
        ]
    )
    if fail_final:
        assert result.returncode != 0
        assert "Some updates failed" in result.stdout
        return
    assert result.returncode == 0, result.stderr
    writes = [
        (call[call.index("--key") + 1], call[call.index("--value") + 1])
        for call in state["calls"]
        if call[:4] == ["az", "appconfig", "kv", "set"]
    ]
    final = dict(writes)
    assert final["app/backend/base-url"] == "https://backend.azurefd.net"
    assert final["app/frontend/backend-url"] == "https://backend.azurefd.net"
    assert final["app/frontend/ws-url"] == "wss://backend.azurefd.net"
    assert writes[-1][0] == "app/sentinel"
    assert any("origin.azurecontainerapps.io" in value for _, value in writes)
