# ============================================================================
# AZURE COMMUNICATION SERVICES EMAIL (Optional - not required for voice)
# ============================================================================

# State migration: handle existing deployments without count index
moved {
  from = azurerm_email_communication_service.main
  to   = azurerm_email_communication_service.main[0]
}

moved {
  from = azurerm_email_communication_service_domain.managed
  to   = azurerm_email_communication_service_domain.managed[0]
}

moved {
  from = azurerm_email_communication_service_domain_sender_username.default
  to   = azurerm_email_communication_service_domain_sender_username.default[0]
}

# Remove old azurerm association from state (replaced by azapi_update_resource)
# The domain link already exists in Azure, so we just forget the old resource
removed {
  from = azurerm_communication_service_email_domain_association.example
  lifecycle {
    destroy = false
  }
}

resource "azurerm_email_communication_service" "main" {
  count               = var.enable_acs_email ? 1 : 0
  name                = local.resource_names.email_service
  resource_group_name = azurerm_resource_group.main.name
  data_location       = var.acs_data_location
  tags                = local.tags
}

resource "azurerm_email_communication_service_domain" "managed" {
  count                            = var.enable_acs_email ? 1 : 0
  name                             = local.resource_names.email_domain
  email_service_id                 = azurerm_email_communication_service.main[0].id
  domain_management                = "AzureManaged"
  user_engagement_tracking_enabled = false
}


resource "azurerm_email_communication_service_domain_sender_username" "default" {
  count                   = var.enable_acs_email ? 1 : 0
  email_service_domain_id = azurerm_email_communication_service_domain.managed[0].id
  name                    = local.email_sender_username
  display_name            = local.email_sender_display_name
}


# Using azapi_update_resource to link email domain to ACS
# The azurerm_communication_service_email_domain_association has compatibility issues with azapi-managed ACS
resource "azapi_update_resource" "acs_email_domain_link" {
  count       = var.enable_acs_email ? 1 : 0
  type        = "Microsoft.Communication/communicationServices@2025-05-01-preview"
  resource_id = azapi_resource.acs.id

  body = {
    properties = {
      linkedDomains = [azurerm_email_communication_service_domain.managed[0].id]
    }
  }

  depends_on = [
    azapi_resource.acs,
    azurerm_email_communication_service_domain.managed
  ]
}

# ============================================================================
# AZURE COMMUNICATION SERVICES
# ============================================================================
resource "azapi_resource" "acs" {
  type      = "Microsoft.Communication/communicationServices@2025-05-01-preview"
  name      = local.resource_names.acs
  parent_id = azurerm_resource_group.main.id

  location = "global"
  tags     = local.tags

  ignore_missing_property = true

  identity {
    type = "SystemAssigned"
  }
  lifecycle {
    ignore_changes = [
      tags,
      identity,
    ]
  }
  body = {
    properties = {
      dataLocation        = var.acs_data_location
      disableLocalAuth    = false
      publicNetworkAccess = "Enabled"
    }
  }
}

# Retrieve ACS connection string using listKeys action (secure method).
#
# Uses the DATA SOURCE form of azapi_resource_action (not the resource form).
# The resource form triggers an azapi provider bug on 2.x where the computed
# `.exist` attribute is null during plan but true after apply, causing
# "Provider produced inconsistent result after apply" failures on every CI
# deploy. The data source form is the official pattern for read-only actions
# like listKeys / listSecrets and avoids stateful resource tracking entirely.
data "azapi_resource_action" "acs_list_keys" {
  type        = "Microsoft.Communication/communicationServices@2025-05-01-preview"
  resource_id = azapi_resource.acs.id
  action      = "listKeys"

  response_export_values = [
    "primaryConnectionString"
  ]
}

# Mark ACS connection string as sensitive locally to prevent exposure in plan output
locals {
  acs_connection_string = sensitive(data.azapi_resource_action.acs_list_keys.output.primaryConnectionString)
}

# Store the ACS connection string in Azure Key Vault as a secret
resource "azurerm_key_vault_secret" "acs_connection_string" {
  name            = "acs-connection-string"
  value           = local.acs_connection_string
  key_vault_id    = azurerm_key_vault.main.id
  content_type    = "text/plain"
  expiration_date = timeadd(timestamp(), "720h") # 30 days

  depends_on = [
    data.azapi_resource_action.acs_list_keys,
    azurerm_role_assignment.keyvault_backend_secrets,
    azurerm_role_assignment.keyvault_admin
  ]
}

# Grant the Communication Service's managed identity access to Speech Services
# This enables real-time transcription with managed identity authentication
#
# Role: "Cognitive Services User" 
# - Allows ACS to authenticate to Speech Services without API keys
# - Enables real-time STT/TTS operations
# - Required for Call Automation with speech features
#

# Allow ACS managed identity to store call recordings in the primary storage account
resource "azurerm_role_assignment" "acs_storage_blob_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.acs.output.identity.principalId

  depends_on = [
    azapi_resource.acs,
    azurerm_storage_account.main
  ]
}

# Grant the backend user-assigned managed identity access to Azure Communication
# Services so the app can authenticate Call Automation with Microsoft Entra ID
# (token audience https://communication.azure.com) instead of the access-key /
# HMAC connection string. This removes the key-rotation drift class of failures
# (e.g. ACS error 7509 "HMAC-SHA256 validation failed" from a stale key).
#
# Role: "Contributor" scoped to the ACS resource only.
# - Azure Communication Services has no granular built-in data-plane RBAC role,
#   so Contributor at the resource scope is the supported approach for managed
#   identity auth. Scope is limited to the single ACS resource (least privilege
#   at resource granularity).
resource "azurerm_role_assignment" "acs_backend_contributor" {
  scope                = azapi_resource.acs.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id

  depends_on = [
    azapi_resource.acs,
    azurerm_user_assigned_identity.backend
  ]
}

# ============================================================================
# DIAGNOSTIC SETTINGS FOR AZURE COMMUNICATION SERVICES
# ============================================================================
resource "azurerm_monitor_diagnostic_setting" "acs_diagnostics" {
  name                       = "${azapi_resource.acs.name}-diagnostics"
  target_resource_id         = azapi_resource.acs.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  # Only include categories not already configured in another diagnostic setting for this resource and workspace.
  # Remove "AuthOperational" if it is already present in another diagnostic setting named 'def'.

  # Call Automation logs
  enabled_log {
    category = "CallAutomationOperational"
  }

  enabled_log {
    category = "CallAutomationMediaSummary"
  }

  enabled_log {
    category = "CallAutomationStreamingUsage"
  }

  # Voice and Video Call logs
  enabled_log {
    category = "CallSummary"
  }

  enabled_log {
    category = "CallDiagnostics"
  }

  enabled_log {
    category = "CallClientOperations"
  }

  enabled_log {
    category = "CallClientMediaStatsTimeSeries"
  }

  enabled_log {
    category = "CallClientServiceRequestAndOutcome"
  }

  # Call Recording logs
  enabled_log {
    category = "CallRecordingOperational"
  }

  enabled_log {
    category = "CallRecordingSummary"
  }

  # Call Survey logs
  enabled_log {
    category = "CallSurvey"
  }

  # Closed Captions logs
  enabled_log {
    category = "CallClosedCaptionsSummary"
  }

  # Calling Metrics
  enabled_log {
    category = "CallingMetrics"
  }

  # SMS logs
  enabled_log {
    category = "SMSOperational"
  }

  # Chat logs
  enabled_log {
    category = "ChatOperational"
  }

  # Usage logs
  enabled_log {
    category = "Usage"
  }

  # Email logs
  enabled_log {
    category = "EmailSendMailOperational"
  }

  enabled_log {
    category = "EmailStatusUpdateOperational"
  }

  enabled_log {
    category = "EmailUserEngagementOperational"
  }

  # Advanced Messaging logs
  enabled_log {
    category = "AdvancedMessagingOperational"
  }

  # Rooms logs
  enabled_log {
    category = "RoomsOperational"
  }

  # Job Router logs
  enabled_log {
    category = "JobRouterOperational"
  }

  # Versioned logs
  enabled_log {
    category = "CallSummaryUpdates"
  }

  enabled_log {
    category = "CallDiagnosticsUpdates"
  }
}

# ============================================================================
# EVENT GRID SYSTEM TOPIC FOR ACS
# ============================================================================

resource "azurerm_eventgrid_system_topic" "acs" {
  name                = "eg-topic-acs-${local.resource_token}"
  resource_group_name = azurerm_resource_group.main.name
  location            = "global"
  source_resource_id  = azapi_resource.acs.id
  topic_type          = "Microsoft.Communication.CommunicationServices"
  tags                = local.tags
}

# # Event Grid System Topic Event Subscription for Incoming Calls
# resource "azurerm_eventgrid_system_topic_event_subscription" "incoming_call_handler" {
#   name                = "backend-incoming-call-handler"
#   system_topic        = azurerm_eventgrid_system_topic.acs.name
#   resource_group_name = azurerm_resource_group.main.name

#   webhook_endpoint {
#     url = "https://${azurerm_container_app.backend.ingress[0].fqdn}/api/call/inbound"
#   }

#   included_event_types = [
#     "Microsoft.Communication.IncomingCall"
#   ]

#   # Retry policy for webhook delivery
#   retry_policy {
#     max_delivery_attempts = 5
#     event_time_to_live    = 1440
#   }

#   depends_on = [azurerm_eventgrid_system_topic.acs]
# }

