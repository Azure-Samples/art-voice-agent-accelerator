"""Root wiring contracts complement the Front Door module's mocked Terraform plans."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "terraform"


def test_front_door_is_opt_in_and_has_no_application_gateway() -> None:
    """The active Terraform path must not silently acquire a second gateway."""
    source = (INFRA / "frontdoor.tf").read_text()
    flag = source.split('variable "enable_front_door" {', 1)[1].split("\n}", 1)[0]
    assert "default     = false" in flag
    assert "var.enable_front_door ? 1 : 0" in source
    resolved = source.split('output "FRONT_DOOR_ENABLED" {', 1)[1].split("\n}", 1)[0]
    assert "module.frontdoor[0].profile_id" in resolved
    for path in INFRA.glob("*.tf"):
        assert 'resource "azurerm_application_gateway"' not in path.read_text()


def test_front_door_allowlist_is_explicit_and_sensitive() -> None:
    source = (INFRA / "frontdoor.tf").read_text()
    allowlist = source.split('variable "front_door_allowed_service_tags" {', 1)[1].split(
        "\n}", 1
    )[0]
    assert "default     = []" in allowlist
    assert "sensitive   = true" in allowlist
    module_variables = (INFRA / "modules/frontdoor/variables.tf").read_text()
    assert "length(var.allowed_service_tags) > 0" in module_variables
    workflow = (ROOT / ".github/workflows/_template-deploy-azd.yml").read_text()
    assert workflow.count(
        "TF_VAR_front_door_allowed_service_tags: "
        "${{ secrets.FRONT_DOOR_ALLOWED_SERVICE_TAGS || '[]' }}"
    ) == 2


def test_private_environment_requires_explicit_workload_profile_migration() -> None:
    """Fail the plan rather than attempting unsupported legacy Private Link."""
    source = (INFRA / "containers.tf").read_text()
    assert 'public_network_access = var.enable_front_door ? "Disabled" : "Enabled"' in source
    assert "!var.enable_front_door || var.container_app_workload_profiles_enabled" in source
    assert 'dynamic "workload_profile"' in source
    assert "var.container_app_workload_profiles_enabled ? [1] : []" in source
    assert source.count('var.container_app_workload_profiles_enabled ? "Consumption" : null') == 2
    assert (
        'var.container_app_workload_profiles_enabled ? "Consumption" : null'
        in (INFRA / "cardapi.tf").read_text()
    )


def test_public_urls_and_cors_follow_front_door_but_origin_names_remain() -> None:
    """Consumers must not continue to point browsers at the locked origin."""
    source = (INFRA / "containers.tf").read_text()
    for name, local_name in [
        ("FRONTEND_CONTAINER_APP_URL", "frontend_public_hostname"),
        ("BACKEND_CONTAINER_APP_URL", "backend_public_hostname"),
        ("BACKEND_API_URL", "backend_public_hostname"),
    ]:
        output = source.split(f'output "{name}" {{', 1)[1].split("\n}", 1)[0]
        assert f"https://${{local.{local_name}}}" in output
    assert re.search(
        r'allowedOrigins\s*=\s*\["https://\$\{local.frontend_public_hostname\}"\]', source
    )
    for service in ("frontend", "backend"):
        output = source.split(f'output "{service.upper()}_CONTAINER_APP_FQDN" {{', 1)[1].split(
            "\n}", 1
        )[0]
        assert f"azurerm_container_app.{service}.ingress[0].fqdn" in output


def test_backend_auth_bootstrap_is_managed_and_secret_backed() -> None:
    """Reprovisioning must update security config, not ignore all env changes."""
    source = (INFRA / "containers.tf").read_text()
    backend = source.split('resource "azurerm_container_app" "backend" {', 1)[1].split(
        "# STICKY SESSIONS", 1
    )[0]
    assert "template[0].container[0].env" not in backend
    assert 'name  = "ENABLE_FRONT_DOOR"' in backend
    assert "value = tostring(var.enable_front_door)" in backend
    assert "azapi_resource.acs.output.properties.immutableResourceId" in backend
    assert "ACS_ARM_RESOURCE_ID" in backend
    assert 'name        = "EVENT_GRID_WEBHOOK_SECRET"' in backend
    assert 'secret_name = "event-grid-webhook-secret"' in backend
    assert "azurerm_key_vault_secret.event_grid_webhook[0].versionless_id" in backend


def test_all_environment_apps_have_a_guarded_front_door_origin() -> None:
    """Disabling public access is environment-wide, including CardAPI."""
    source = (INFRA / "frontdoor.tf").read_text()
    assert "azurerm_container_app.frontend.ingress[0].fqdn" in source
    assert "azurerm_container_app.backend.ingress[0].fqdn" in source
    assert "azurerm_container_app.cardapi_mcp.ingress[0].fqdn" in source
    assert source.count("allow_acs         = true") == 1
    assert source.count("allow_acs         = false") == 2


def test_private_link_approval_marker_is_not_derived_from_public_names() -> None:
    """An unrelated Front Door must not be able to guess the automatic approval marker."""
    source = (INFRA / "frontdoor.tf").read_text()
    assert 'resource "random_uuid" "front_door_link"' in source
    assert "ART Front Door ${random_uuid.front_door_link[0].result}" in source
    output = source.split('output "FRONT_DOOR_PRIVATE_LINK_REQUEST_MESSAGE" {', 1)[1]
    assert "sensitive = true" in output.split("\n}", 1)[0]


def test_replacement_images_can_preserve_the_deployed_application_version() -> None:
    """Image ignore_changes alone would recreate apps with placeholder images."""
    containers = (INFRA / "containers.tf").read_text()
    cardapi = (INFRA / "cardapi.tf").read_text()
    for service, source in [
        ("frontend", containers),
        ("backend", containers),
        ("cardapi", cardapi),
    ]:
        assert f'lookup(var.container_images, "{service}",' in source


def test_cardapi_reprovisioning_preserves_hook_managed_auth_secret() -> None:
    source = (INFRA / "cardapi.tf").read_text()
    app = source.split('resource "azurerm_container_app" "cardapi_mcp" {', 1)[1]
    lifecycle = app.split("lifecycle {", 1)[1].split("\n  }", 1)[0]
    assert "template[0].container[0].image" in lifecycle
    assert re.search(r"^\s+secret\s*$", lifecycle, flags=re.MULTILINE)


def test_mosdev_ci_parameters_preserve_the_migrated_environment() -> None:
    params = json.loads((INFRA / "params/main.tfvars.mosdev.json").read_text())
    assert params["location"] == "westus2"
    assert params["enable_front_door"] is True
    assert params["container_app_workload_profiles_enabled"] is True
