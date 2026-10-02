"""State perimeter bootstrap contracts, with no Azure operations."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_state_nsp", ROOT / "devops/scripts/azd/helpers/configure-state-nsp.py"
)
nsp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nsp)

ACCOUNT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/state"
PERIMETER = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkSecurityPerimeters/nsp-state"
PROFILE = f"{PERIMETER}/profiles/deployers"


@pytest.mark.parametrize(
    "prefixes",
    [[], ["0.0.0.0/0"], ["10.0.0.0/8"], ["::/0"], ["224.0.0.1/32"], ["8.8.8.1/24"]],
)
def test_invalid_or_overbroad_prefixes_fail_before_azure(monkeypatch, prefixes):
    monkeypatch.setattr(nsp, "azure", lambda _: pytest.fail("Azure must not be called"))
    with pytest.raises(ValueError):
        nsp.configure("sub", "rg", "state", prefixes)


def test_explicit_public_prefixes_are_canonical_and_deduplicated():
    assert nsp.vpn_prefixes(["8.8.8.8", "8.8.8.8/32"]) == ["8.8.8.8/32"]


@pytest.mark.parametrize("mode", ["Enforced", "Learning"])
def test_storage_changes_only_after_the_expected_enforced_association(monkeypatch, mode):
    calls = []
    patched = False

    def azure(args):
        nonlocal patched
        calls.append(args)
        assert args[args.index("--subscription") + 1] == "sub"
        if args[:3] == ["storage", "account", "show"]:
            return {
                "id": ACCOUNT,
                "location": "westus2",
                "networkRuleSet": {"defaultAction": "Deny"},
                "publicNetworkAccess": "SecuredByPerimeter" if patched else "Disabled",
                "allowBlobPublicAccess": False,
            }
        if args[:3] == ["deployment", "group", "create"]:
            assert "Incremental" in args
            return {
                "properties": {
                    "provisioningState": "Succeeded",
                    "outputs": {
                        "profileId": {"value": PROFILE},
                        "perimeterId": {"value": PERIMETER},
                    },
                }
            }
        if args[:3] == ["rest", "--method", "GET"]:
            return {
                "properties": {
                    "accessMode": mode,
                    "profile": {"id": PROFILE},
                    "privateLinkResource": {"id": ACCOUNT},
                }
            }
        assert args[:3] == ["rest", "--method", "PATCH"]
        body = json.loads(args[args.index("--body") + 1])
        assert body == {
            "properties": {
                "publicNetworkAccess": "SecuredByPerimeter",
                "allowBlobPublicAccess": False,
            }
        }
        patched = True
        return {}

    monkeypatch.setattr(nsp, "azure", azure)
    if mode != "Enforced":
        with pytest.raises(RuntimeError, match="enforced state association"):
            nsp.configure("sub", "rg", "state", ["8.8.8.8/32"])
        assert not patched
    else:
        result = nsp.configure("sub", "rg", "state", ["8.8.8.8/32"])
        assert result["profileId"] == PROFILE
        assert patched


def test_template_creates_the_allowlist_before_enforcement():
    template = json.loads(
        (ROOT / "infra/bootstrap/state-network-security-perimeter.json").read_text()
    )
    resources = {
        resource["type"].rsplit("/", 1)[-1]: resource for resource in template["resources"]
    }
    assert resources["resourceAssociations"]["properties"]["accessMode"] == "Enforced"
    assert "accessRules" in resources["resourceAssociations"]["dependsOn"][0]
    assert resources["accessRules"]["properties"]["direction"] == "Inbound"
    assert not any(
        resource["type"] == "Microsoft.Storage/storageAccounts"
        for resource in template["resources"]
    )
