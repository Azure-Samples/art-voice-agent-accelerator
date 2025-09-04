# ============================================================================
# AZURE COMMUNICATION SERVICES
# ============================================================================
resource "azapi_resource" "acs" {
  type      = "Microsoft.Communication/communicationServices@2025-05-01-preview"
  name      = local.resource_names.acs
  parent_id = azurerm_resource_group.main.id

  location = "global"
  tags     = local.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      dataLocation        = var.acs_data_location
      disableLocalAuth    = false
      publicNetworkAccess = "Enabled"
    }
  }
}

# Retrieve ACS connection string using listKeys action (secure method)
resource "azapi_resource_action" "acs_list_keys" {
  type        = "Microsoft.Communication/communicationServices@2025-05-01-preview"
  resource_id = azapi_resource.acs.id
  action      = "listKeys"

  response_export_values = {
    primary_connection_string = "primaryConnectionString"
  }

  depends_on = [azapi_resource.acs]
}

# Store the ACS connection string in Azure Key Vault as a secret
resource "azurerm_key_vault_secret" "acs_connection_string" {
  name            = "acs-connection-string"
  value           = azapi_resource_action.acs_list_keys.output.primary_connection_string
  key_vault_id    = azurerm_key_vault.main.id
  expiration_date = timeadd(timestamp(), "8760h") # 1 year from now

  depends_on = [
    azapi_resource_action.acs_list_keys,
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
resource "azurerm_role_assignment" "acs_speech_user" {
  scope                = azurerm_cognitive_account.speech.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azapi_resource.acs.identity[0].principal_id

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
  name                   = "eg-topic-acs-${local.resource_token}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = "global"
  source_arm_resource_id = azapi_resource.acs.id
  topic_type             = "Microsoft.Communication.CommunicationServices"
  tags                   = local.tags
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