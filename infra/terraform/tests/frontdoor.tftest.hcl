# Mocked plans never contact Azure or the configured state backend.
mock_provider "azurerm" {}
mock_provider "azapi" {}

variables {
  name                         = "afd-test-12345678"
  resource_group_name          = "rg-test"
  resource_group_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test"
  environment_id               = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.App/managedEnvironments/cae-test"
  log_analytics_workspace_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"
  private_link_location        = "eastus"
  private_link_request_message = "ART Front Door 34112ac2-e9dc-43d0-bb91-393b72af5136"
  # Synthetic values for mocked plans, not service tags to deploy to Azure.
  allowed_service_tags = ["ExampleApprovedEgress", "ExampleVpnEgress"]
  origins = {
    frontend = {
      hostname          = "frontend.example.azurecontainerapps.io"
      health_probe_path = "/health.txt"
      allow_acs         = false
    }
    backend = {
      hostname          = "backend.example.azurecontainerapps.io"
      health_probe_path = "/api/v1/health"
      allow_acs         = true
    }
    cardapi = {
      hostname          = "cardapi.example.azurecontainerapps.io"
      health_probe_path = "/health"
      allow_acs         = false
    }
  }
}

run "private_origins_and_corporate_policy" {
  command = plan
  module {
    source = "./modules/frontdoor"
  }

  assert {
    condition     = azurerm_cdn_frontdoor_profile.main.sku_name == "Premium_AzureFrontDoor"
    error_message = "ServiceTagMatch and Private Link require Premium."
  }
  assert {
    condition = alltrue([
      for origin in azurerm_cdn_frontdoor_origin.app :
      origin.private_link[0].private_link_target_id == var.environment_id &&
      origin.private_link[0].target_type == "managedEnvironments" &&
      origin.certificate_name_check_enabled
    ])
    error_message = "Every origin must use the managed-environment Private Link and TLS name checking."
  }
  assert {
    condition = alltrue([
      for route in azurerm_cdn_frontdoor_route.app :
      length(route.cache) == 0 && route.forwarding_protocol == "HttpsOnly" &&
      route.https_redirect_enabled && contains(route.patterns_to_match, "/*")
    ])
    error_message = "All routes must be HTTPS with caching disabled for WebSockets."
  }
  assert {
    condition = alltrue([
      for policy in azapi_resource.waf :
      policy.type == "Microsoft.Network/frontDoorWebApplicationFirewallPolicies@2025-10-01" &&
      policy.body.properties.policySettings.mode == "Prevention" &&
      policy.body.properties.customRules.rules[0].action == "Block" &&
      policy.body.properties.customRules.rules[0].matchConditions[0].matchVariable == "SocketAddr" &&
      policy.body.properties.customRules.rules[0].matchConditions[0].operator == "ServiceTagMatch" &&
      policy.body.properties.customRules.rules[0].matchConditions[0].negateCondition &&
      tolist(policy.body.properties.customRules.rules[0].matchConditions[0].matchValue) == var.allowed_service_tags
    ])
    error_message = "Raw corporate tags must enforce a negated SocketAddr Block in Prevention mode."
  }
  assert {
    condition = alltrue(flatten([
      for policy in azapi_resource.waf : [
        for rule in policy.body.properties.customRules.rules : [
          for condition in rule.matchConditions :
          condition.operator != "RegEx" || length(condition.matchValue) == 1
        ]
      ]
    ]))
    error_message = "Azure WAF accepts exactly one matchValue for each RegEx condition."
  }
  assert {
    condition = alltrue([
      for name in ["frontend", "cardapi"] :
      length(azapi_resource.waf[name].body.properties.customRules.rules) == 1 &&
      length(azapi_resource.waf[name].body.properties.customRules.rules[0].matchConditions) == 1
    ])
    error_message = "Only the backend may have telephony exceptions."
  }
  assert {
    condition = (
      length(azapi_resource.waf["backend"].body.properties.customRules.rules) == 3 &&
      alltrue([for rule in azapi_resource.waf["backend"].body.properties.customRules.rules : rule.action == "Block"]) &&
      azapi_resource.waf["backend"].body.properties.customRules.rules[1].matchConditions[2].matchValue[0] == "POST" &&
      azapi_resource.waf["backend"].body.properties.customRules.rules[2].matchConditions[2].matchValue[0] == "GET"
    )
    error_message = "ACS exceptions must be method-scoped, with no WAF Allow bypass."
  }
  assert {
    condition = alltrue([
      for path in [
        "/api/v1/calls/answer",
        "/api/v1/calls/callbacks",
        "/api/v1/calls/callbacks?call_id=123",
        "/api/v1/media/stream?call_connection_id=123",
        "https://backend.azurefd.net:443/api/v1/calls/answer",
        "https://backend.azurefd.net/api/v1/calls/callbacks?call_id=123",
        "https://backend.azurefd.net:443/api/v1/media/stream?call_connection_id=123"
        ] : anytrue([
          for pattern in azapi_resource.waf["backend"].body.properties.customRules.rules[0].matchConditions[1].matchValue :
          can(regex(pattern, path))
      ])
    ])
    error_message = "Required ACS callback and media paths (including queries) must be exempt from the network gate."
  }
  assert {
    condition = alltrue([
      for path in [
        "/api/v1/calls",
        "/api/v1/calls/answer/admin",
        "/api/v1/calls/callbacks-evil",
        "/api/v1/media/stream/extra",
        "/api/v1/browser/conversation",
        "/api/v1/health",
        "/api/v1/agents",
        "https://backend.azurefd.net:443/api/v1/calls/answer/admin",
        "https://backend.azurefd.net/api/v1/calls/callbacks-evil",
        "https://backend.azurefd.net/api/v1/media/stream/extra",
        "https://backend.azurefd.net/admin?path=/api/v1/calls/answer"
        ] : !anytrue([
          for pattern in azapi_resource.waf["backend"].body.properties.customRules.rules[0].matchConditions[1].matchValue :
          can(regex(pattern, path))
      ])
    ])
    error_message = "User APIs, browser media, and path-prefix lookalikes must never match ACS exemptions."
  }
  assert {
    condition = alltrue([
      for policy in azurerm_cdn_frontdoor_security_policy.app :
      contains(tolist(policy.security_policies[0].firewall[0].association[0].patterns_to_match), "/*")
    ])
    error_message = "WAF must be associated with all paths on every endpoint."
  }
}

run "empty_allowlist_rejected" {
  command = plan
  module {
    source = "./modules/frontdoor"
  }
  variables {
    allowed_service_tags = []
  }
  expect_failures = [var.allowed_service_tags]
}

run "wildcard_allowlist_rejected" {
  command = plan
  module {
    source = "./modules/frontdoor"
  }
  variables {
    allowed_service_tags = ["*"]
  }
  expect_failures = [var.allowed_service_tags]
}
