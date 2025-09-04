# ============================================================================
# APP SERVICE PLANS
# ============================================================================

resource "azurerm_service_plan" "frontend" {
  name                = "${var.name}-frontend-plan-${var.resource_token}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = var.frontend_config.sku_name

  tags = var.tags
}

resource "azurerm_service_plan" "backend" {
  name                = "${var.name}-backend-plan-${var.resource_token}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = var.backend_config.sku_name

  tags = var.tags
}

# ============================================================================
# FRONTEND WEB APP
# ============================================================================

resource "azurerm_linux_web_app" "frontend" {
  name                = "${var.name}-frontend-app-${var.resource_token}"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.frontend.id

  identity {
    type         = "UserAssigned"
    identity_ids = [var.frontend_identity_id]
  }

  logs {
    application_logs {
      file_system_level = "Information"
    }
    http_logs {
      file_system {
        retention_in_days = var.log_retention_days
        retention_in_mb   = var.log_retention_mb
      }
    }
    detailed_error_messages = true
    failed_request_tracing  = true
  }

  site_config {
    application_stack {
      node_version = var.frontend_config.node_version
    }

    always_on         = var.frontend_config.always_on
    app_command_line  = var.frontend_config.app_command_line
    use_32_bit_worker = var.frontend_config.use_32_bit_worker
    ftps_state        = var.frontend_config.ftps_state
    http2_enabled     = var.frontend_config.http2_enabled

    cors {
      allowed_origins     = var.frontend_cors_origins
      support_credentials = var.cors_support_credentials
    }
  }

  app_settings = merge(
    {
      "PORT"          = tostring(var.frontend_config.port)
      "WEBSITES_PORT" = tostring(var.frontend_config.port)
    },
    var.frontend_app_settings
  )

  key_vault_reference_identity_id = var.frontend_identity_id

  tags = merge(var.tags, {
    "azd-service-name" = var.frontend_config.azd_service_name
  })

  lifecycle {
    ignore_changes = [
      site_config[0].app_command_line,
      site_config[0].cors,
      tags
    ]
  }
}

# ============================================================================
# BACKEND WEB APP
# ============================================================================

resource "azurerm_linux_web_app" "backend" {
  name                = "${var.name}-backend-app-${var.resource_token}"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.backend.id

  identity {
    type         = "UserAssigned"
    identity_ids = [var.backend_identity_id]
  }

  logs {
    application_logs {
      file_system_level = "Information"
    }
    http_logs {
      file_system {
        retention_in_days = var.log_retention_days
        retention_in_mb   = var.log_retention_mb
      }
    }
    detailed_error_messages = true
    failed_request_tracing  = true
  }

  site_config {
    application_stack {
      python_version = var.backend_config.python_version
    }

    always_on        = var.backend_config.always_on
    app_command_line = var.backend_config.app_command_line

    cors {
      allowed_origins     = var.backend_cors_origins
      support_credentials = var.cors_support_credentials
    }
  }

  app_settings = merge(
    {
      "PORT"          = tostring(var.backend_config.port)
      "WEBSITES_PORT" = tostring(var.backend_config.port)
    },
    var.backend_app_settings
  )

  key_vault_reference_identity_id = var.backend_identity_id

  tags = merge(var.tags, {
    "azd-service-name" = var.backend_config.azd_service_name
  })

  lifecycle {
    ignore_changes = [
      site_config[0].app_command_line,
      site_config[0].cors,
      tags
    ]
  }
}

# ============================================================================
# DIAGNOSTIC SETTINGS
# ============================================================================

resource "azurerm_monitor_diagnostic_setting" "frontend" {
  count = var.enable_diagnostics ? 1 : 0

  name                       = "${azurerm_linux_web_app.frontend.name}-diagnostics"
  target_resource_id         = azurerm_linux_web_app.frontend.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  enabled_log {
    category = "AppServicePlatformLogs"
  }

  enabled_log {
    category = "AppServiceAppLogs"
  }
}

resource "azurerm_monitor_diagnostic_setting" "backend" {
  count = var.enable_diagnostics ? 1 : 0

  name                       = "${azurerm_linux_web_app.backend.name}-diagnostics"
  target_resource_id         = azurerm_linux_web_app.backend.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  enabled_log {
    category = "AppServicePlatformLogs"
  }

  enabled_log {
    category = "AppServiceAppLogs"
  }
}
