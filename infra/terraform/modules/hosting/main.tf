# ============================================================================
# CONTAINER APPS MODULE
# ============================================================================

module "containers" {
  count  = var.hosting_platform == "containers" ? 1 : 0
  source = "../containers"

  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  resource_token      = var.resource_token
  tags                = var.tags

  log_analytics_workspace_id      = var.log_analytics_workspace_id
  container_registry_login_server = var.container_registry_login_server
  frontend_identity_id            = var.frontend_identity_id
  backend_identity_id             = var.backend_identity_id

  frontend_config = {
    target_port      = var.frontend_config.port
    min_replicas     = var.frontend_config.min_replicas
    max_replicas     = var.frontend_config.max_replicas
    cpu              = var.frontend_config.cpu
    memory           = var.frontend_config.memory
    default_image    = var.frontend_config.default_image
    azd_service_name = var.frontend_config.azd_service_name
  }

  backend_config = {
    target_port      = var.backend_config.port
    min_replicas     = var.backend_config.min_replicas
    max_replicas     = var.backend_config.max_replicas
    cpu              = var.backend_config.cpu
    memory           = var.backend_config.memory
    default_image    = var.backend_config.default_image
    azd_service_name = var.backend_config.azd_service_name
  }

  frontend_env_vars = var.frontend_env_vars
  backend_env_vars  = var.backend_env_vars
  secrets           = var.secrets
}

# ============================================================================
# WEB APPS MODULE
# ============================================================================

module "webapps" {
  count  = var.hosting_platform == "webapps" ? 1 : 0
  source = "../webapps"

  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  resource_token      = var.resource_token
  tags                = var.tags

  log_analytics_workspace_id = var.log_analytics_workspace_id
  frontend_identity_id       = var.frontend_identity_id
  backend_identity_id        = var.backend_identity_id

  frontend_config = {
    sku_name          = var.frontend_config.sku_name
    node_version      = var.frontend_config.node_version
    port              = var.frontend_config.port
    app_command_line  = var.frontend_config.app_command_line
    azd_service_name  = var.frontend_config.azd_service_name
    always_on         = var.frontend_config.always_on
    use_32_bit_worker = var.frontend_config.use_32_bit_worker
    ftps_state        = var.frontend_config.ftps_state
    http2_enabled     = var.frontend_config.http2_enabled
  }

  backend_config = {
    sku_name         = var.backend_config.sku_name
    python_version   = var.backend_config.python_version
    port             = var.backend_config.port
    app_command_line = var.backend_config.app_command_line
    azd_service_name = var.backend_config.azd_service_name
    always_on        = var.backend_config.always_on
  }

  # Convert env vars to app settings for webapps
  frontend_app_settings = {
    for env_var in var.frontend_env_vars : env_var.name => env_var.value
    if env_var.value != null
  }

  backend_app_settings = {
    for env_var in var.backend_env_vars : env_var.name => env_var.value
    if env_var.value != null
  }

  frontend_cors_origins    = var.frontend_cors_origins
  backend_cors_origins     = var.backend_cors_origins
  cors_support_credentials = var.cors_support_credentials
  enable_diagnostics       = var.enable_diagnostics
  log_retention_days       = var.log_retention_days
  log_retention_mb         = var.log_retention_mb
}
