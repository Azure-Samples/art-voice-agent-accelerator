# ============================================================================
# RESOURCE GROUP
# ============================================================================

resource "azurerm_resource_group" "main" {
  name     = local.resource_names.resource_group
  location = var.location
  tags     = local.tags
}

# ============================================================================
# MANAGED IDENTITIES
# ============================================================================

# Backend user-assigned managed identity
resource "azurerm_user_assigned_identity" "backend" {
  name                = "${var.name}-backend-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# Frontend user-assigned managed identity
resource "azurerm_user_assigned_identity" "frontend" {
  name                = "${var.name}-frontend-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# ============================================================================
# LOG ANALYTICS & APPLICATION INSIGHTS
# ============================================================================

resource "azurerm_log_analytics_workspace" "main" {
  name                = local.resource_names.log_analytics
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = local.resource_names.app_insights
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# Assign "Application Insights Metrics Publisher" role to backend managed identity
# Assign "Monitoring Metrics Publisher" role to backend managed identity
resource "azurerm_role_assignment" "app_insights_metrics_backend" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

# Assign "Monitoring Metrics Publisher" role to frontend managed identity
resource "azurerm_role_assignment" "app_insights_metrics_frontend" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.frontend.principal_id
}

# Assign "Monitoring Metrics Publisher" role to an additional principal_id if needed
resource "azurerm_role_assignment" "app_insights_metrics_custom" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = local.principal_id
  principal_type       = local.principal_type
}
