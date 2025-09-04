# ============================================================================
# CONTAINER APPS ENVIRONMENT
# ============================================================================

resource "azurerm_container_app_environment" "main" {
  name                = "${var.name}-containerenv-${var.resource_token}"
  location            = var.location
  resource_group_name = var.resource_group_name

  log_analytics_workspace_id = var.log_analytics_workspace_id

  tags = var.tags
}

# ============================================================================
# FRONTEND CONTAINER APP
# ============================================================================

resource "azurerm_container_app" "frontend" {
  name                         = "${var.name}-frontend-${var.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  # Image is managed outside of terraform (i.e azd deploy)
  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.frontend_identity_id]
  }

  registry {
    server   = var.container_registry_login_server
    identity = var.frontend_identity_id
  }

  ingress {
    external_enabled = true
    target_port      = var.frontend_config.target_port
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.frontend_config.min_replicas
    max_replicas = var.frontend_config.max_replicas

    container {
      name   = "main"
      image  = var.frontend_config.default_image
      cpu    = var.frontend_config.cpu
      memory = var.frontend_config.memory

      # Dynamic environment variables
      dynamic "env" {
        for_each = var.frontend_env_vars
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }
    }
  }

  tags = merge(var.tags, {
    "azd-service-name" = var.frontend_config.azd_service_name
  })
}

# ============================================================================
# BACKEND CONTAINER APP
# ============================================================================

resource "azurerm_container_app" "backend" {
  name                         = "${var.name}-backend-${var.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  # Image is managed outside of terraform (i.e azd deploy)
  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.backend_identity_id]
  }

  registry {
    server   = var.container_registry_login_server
    identity = var.backend_identity_id
  }

  # Dynamic secrets configuration
  dynamic "secret" {
    for_each = var.secrets
    content {
      name                = secret.value.name
      identity            = secret.value.identity
      key_vault_secret_id = secret.value.key_vault_secret_id
    }
  }

  ingress {
    external_enabled = true
    target_port      = var.backend_config.target_port
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.backend_config.min_replicas
    max_replicas = var.backend_config.max_replicas

    container {
      name   = "main"
      image  = var.backend_config.default_image
      cpu    = var.backend_config.cpu
      memory = var.backend_config.memory

      # Dynamic environment variables
      dynamic "env" {
        for_each = var.backend_env_vars
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }
    }
  }

  tags = merge(var.tags, {
    "azd-service-name" = var.backend_config.azd_service_name
  })
}
