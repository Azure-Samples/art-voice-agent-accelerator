locals {
  corporate_condition = {
    matchVariable   = "SocketAddr"
    operator        = "ServiceTagMatch"
    matchValue      = var.allowed_service_tags
    negateCondition = true
  }
  # AFD RequestUri includes scheme/authority (and often :443), not just the path.
  acs_http_pattern = "^(https?://[^/?#]+)?/api/v1/calls/(answer|callbacks)(\\?.*)?$"
  acs_ws_pattern   = "^(https?://[^/?#]+)?/api/v1/media/stream(\\?.*)?$"
  acs_path_pattern = "^(https?://[^/?#]+)?(/api/v1/calls/(answer|callbacks)|/api/v1/media/stream)(\\?.*)?$"
  acs_paths = {
    matchVariable   = "RequestUri"
    operator        = "RegEx"
    matchValue      = [local.acs_path_pattern]
    negateCondition = true
  }
}

resource "azurerm_cdn_frontdoor_profile" "main" {
  name                     = var.name
  resource_group_name      = var.resource_group_name
  sku_name                 = "Premium_AzureFrontDoor"
  response_timeout_seconds = 120
  tags                     = var.tags
}

resource "azurerm_cdn_frontdoor_endpoint" "app" {
  for_each                 = var.origins
  name                     = "${var.name}-${each.key}"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  tags                     = var.tags
}

resource "azurerm_cdn_frontdoor_origin_group" "app" {
  for_each                 = var.origins
  name                     = each.key
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  session_affinity_enabled = true

  load_balancing {
    sample_size                 = 4
    successful_samples_required = 3
  }
  health_probe {
    interval_in_seconds = 30
    path                = each.value.health_probe_path
    protocol            = "Https"
    request_type        = "GET"
  }
}

resource "azurerm_cdn_frontdoor_origin" "app" {
  for_each                       = var.origins
  name                           = each.key
  cdn_frontdoor_origin_group_id  = azurerm_cdn_frontdoor_origin_group.app[each.key].id
  host_name                      = each.value.hostname
  origin_host_header             = each.value.hostname
  certificate_name_check_enabled = true

  private_link {
    location               = var.private_link_location
    private_link_target_id = var.environment_id
    target_type            = "managedEnvironments"
    request_message        = var.private_link_request_message
  }
}

# Use the public ARM contract for ServiceTagMatch while preserving the
# operator-supplied allowlist instead of expanding it into static IP ranges.
resource "azapi_resource" "waf" {
  for_each                  = var.origins
  type                      = "Microsoft.Network/frontDoorWebApplicationFirewallPolicies@2025-10-01"
  name                      = replace("${var.name}${each.key}", "-", "")
  parent_id                 = var.resource_group_id
  location                  = "Global"
  tags                      = var.tags
  schema_validation_enabled = false

  body = {
    sku = { name = "Premium_AzureFrontDoor" }
    properties = {
      policySettings = {
        enabledState = "Enabled"
        mode         = "Prevention"
      }
      customRules = {
        rules = concat([
          {
            name         = "BlockOutsideCorporateNetwork"
            priority     = 10
            enabledState = "Enabled"
            ruleType     = "MatchRule"
            action       = "Block"
            matchConditions = concat(
              [local.corporate_condition],
              each.value.allow_acs ? [local.acs_paths] : []
            )
          }
          ], each.value.allow_acs ? [
          {
            name         = "BlockNonPostACSCallbacks"
            priority     = 20
            enabledState = "Enabled"
            ruleType     = "MatchRule"
            action       = "Block"
            matchConditions = [
              local.corporate_condition,
              {
                matchVariable   = "RequestUri"
                operator        = "RegEx"
                matchValue      = [local.acs_http_pattern]
                negateCondition = false
              },
              {
                matchVariable   = "RequestMethod"
                operator        = "Equal"
                matchValue      = ["POST"]
                negateCondition = true
              }
            ]
          },
          {
            name         = "BlockNonGetACSMedia"
            priority     = 30
            enabledState = "Enabled"
            ruleType     = "MatchRule"
            action       = "Block"
            matchConditions = [
              local.corporate_condition,
              {
                matchVariable   = "RequestUri"
                operator        = "RegEx"
                matchValue      = [local.acs_ws_pattern]
                negateCondition = false
              },
              {
                matchVariable   = "RequestMethod"
                operator        = "Equal"
                matchValue      = ["GET"]
                negateCondition = true
              }
            ]
          }
        ] : [])
      }
      managedRules = {
        managedRuleSets = [{
          ruleSetType    = "Microsoft_DefaultRuleSet"
          ruleSetVersion = "2.1"
          ruleSetAction  = "Block"
        }]
      }
    }
  }
}

resource "azurerm_cdn_frontdoor_security_policy" "app" {
  for_each                 = var.origins
  name                     = each.key
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  security_policies {
    firewall {
      cdn_frontdoor_firewall_policy_id = azapi_resource.waf[each.key].id
      association {
        patterns_to_match = ["/*"]
        domain {
          cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.app[each.key].id
        }
      }
    }
  }
}

resource "azurerm_cdn_frontdoor_route" "app" {
  for_each                      = var.origins
  name                          = each.key
  cdn_frontdoor_endpoint_id     = azurerm_cdn_frontdoor_endpoint.app[each.key].id
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.app[each.key].id
  cdn_frontdoor_origin_ids      = [azurerm_cdn_frontdoor_origin.app[each.key].id]
  supported_protocols           = ["Http", "Https"]
  patterns_to_match             = ["/*"]
  forwarding_protocol           = "HttpsOnly"
  https_redirect_enabled        = true
  link_to_default_domain        = true

  # No cache block: enabling route caching breaks WebSocket Upgrade forwarding.
  depends_on = [azurerm_cdn_frontdoor_security_policy.app]
}

resource "azurerm_monitor_diagnostic_setting" "frontdoor" {
  name                       = "frontdoor"
  target_resource_id         = azurerm_cdn_frontdoor_profile.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "FrontDoorAccessLog"
  }
  enabled_log {
    category = "FrontDoorHealthProbeLog"
  }
  enabled_log {
    category = "FrontDoorWebApplicationFirewallLog"
  }
}
