variable "enable_front_door" {
  description = "Opt in to corporate/VPN-only Front Door Premium WAF ingress, private origins, and authenticated ACS exceptions."
  type        = bool
  default     = false
}

variable "container_app_workload_profiles_enabled" {
  description = "Use a workload-profiles environment (required for Front Door Private Link). Changing this replaces a legacy consumption-only environment. Keep true when later disabling Front Door."
  type        = bool
  default     = false
}

variable "front_door_allowed_service_tags" {
  description = "Operator-approved egress service tags allowed by Front Door WAF. Supply explicitly before enabling Front Door."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "front_door_private_link_location" {
  description = "Optional supported AFD Private Link region; defaults to the app region to avoid cross-region latency."
  type        = string
  default     = null
}

resource "random_uuid" "front_door_link" {
  count = var.enable_front_door ? 1 : 0
}

module "frontdoor" {
  count  = var.enable_front_door ? 1 : 0
  source = "./modules/frontdoor"

  name                         = "afd-${var.name}-${local.resource_token}"
  resource_group_name          = azurerm_resource_group.main.name
  resource_group_id            = azurerm_resource_group.main.id
  environment_id               = azurerm_container_app_environment.main.id
  private_link_location        = coalesce(var.front_door_private_link_location, var.location)
  private_link_request_message = "ART Front Door ${random_uuid.front_door_link[0].result}"
  allowed_service_tags         = var.front_door_allowed_service_tags
  log_analytics_workspace_id   = azurerm_log_analytics_workspace.main.id
  tags                         = local.tags
  origins = {
    frontend = {
      hostname          = azurerm_container_app.frontend.ingress[0].fqdn
      health_probe_path = "/health.txt"
      allow_acs         = false
    }
    backend = {
      hostname          = azurerm_container_app.backend.ingress[0].fqdn
      health_probe_path = "/api/v1/health"
      allow_acs         = true
    }
    cardapi = {
      hostname          = azurerm_container_app.cardapi_mcp.ingress[0].fqdn
      health_probe_path = "/health"
      allow_acs         = false
    }
  }
}

locals {
  frontend_public_hostname = var.enable_front_door ? module.frontdoor[0].hostnames.frontend : azurerm_container_app.frontend.ingress[0].fqdn
  backend_public_hostname  = var.enable_front_door ? module.frontdoor[0].hostnames.backend : azurerm_container_app.backend.ingress[0].fqdn
}

resource "random_password" "event_grid_webhook" {
  count   = var.enable_front_door ? 1 : 0
  length  = 64
  special = false
}

resource "azurerm_key_vault_secret" "event_grid_webhook" {
  count        = var.enable_front_door ? 1 : 0
  name         = "event-grid-webhook-secret"
  value        = random_password.event_grid_webhook[0].result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.keyvault_admin]
}

output "FRONT_DOOR_ENABLED" {
  value = var.enable_front_door ? module.frontdoor[0].profile_id != "" : false
}

output "FRONTEND_PUBLIC_FQDN" {
  value = local.frontend_public_hostname
}

output "FRONT_DOOR_PROFILE_ID" {
  value = var.enable_front_door ? module.frontdoor[0].profile_id : ""
}

output "FRONT_DOOR_PRIVATE_LINK_REQUEST_MESSAGE" {
  value     = var.enable_front_door ? module.frontdoor[0].private_link_request_message : ""
  sensitive = true
}

output "EVENT_GRID_WEBHOOK_SECRET_NAME" {
  value = var.enable_front_door ? azurerm_key_vault_secret.event_grid_webhook[0].name : ""
}

output "CARDAPI_PUBLIC_URL" {
  value = var.enable_front_door ? "https://${module.frontdoor[0].hostnames.cardapi}" : "https://${azurerm_container_app.cardapi_mcp.ingress[0].fqdn}"
}
