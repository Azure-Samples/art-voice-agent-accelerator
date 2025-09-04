# Simplified Terraform Hosting Modules

This directory contains simplified Terraform modules for deploying frontend and backend applications to Azure using either **Container Apps** or **App Service**, with flexible configuration through environment variables.

## Module Structure

```
modules/
├── containers/         # Container Apps deployment module
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── webapps/           # App Service deployment module
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── hosting/           # Platform selector module
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    └── examples/
        └── usage.tf   # Usage examples
```

## Key Features

### 🎯 **Platform Flexibility**
- Single module (`hosting`) that deploys to either Container Apps or App Service
- Switch platforms using the `hosting_platform` variable (defaults to `containers`)
- Consistent interface regardless of the underlying platform

### 🔧 **Simplified Configuration**
- **Environment Variables**: Pass arrays of environment variables instead of complex configurations
- **Secrets Management**: Automatic handling of Key Vault secrets for containers
- **Default Values**: Sensible defaults for all configuration options

### 📦 **Modular Design**
- Separate modules for containers and webapps
- Hosting module that orchestrates platform selection
- Clean separation of concerns

## Quick Start

### Basic Usage (Container Apps - Default)

```hcl
module "hosting" {
  source = "./modules/hosting"

  name                = "myapp"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  resource_token      = "abc123"

  # Infrastructure dependencies
  log_analytics_workspace_id      = azurerm_log_analytics_workspace.main.id
  container_registry_login_server = azurerm_container_registry.main.login_server
  frontend_identity_id            = azurerm_user_assigned_identity.frontend.id
  backend_identity_id             = azurerm_user_assigned_identity.backend.id

  # Simple environment variables array
  frontend_env_vars = [
    {
      name  = "VITE_BACKEND_BASE_URL"
      value = "https://api.example.com"
    },
    {
      name  = "PORT"
      value = "8080"
    }
  ]

  backend_env_vars = [
    {
      name        = "DATABASE_CONNECTION"
      secret_name = "db-connection-string"  # References container secret
    },
    {
      name  = "AZURE_CLIENT_ID"
      value = azurerm_user_assigned_identity.backend.client_id
    }
  ]

  # Secrets for containers
  secrets = [
    {
      name                = "db-connection-string"
      identity            = azurerm_user_assigned_identity.backend.id
      key_vault_secret_id = azurerm_key_vault_secret.db_connection.versionless_id
    }
  ]
}
```

### Switch to App Service

```hcl
module "hosting" {
  source = "./modules/hosting"

  # Just change this one variable!
  hosting_platform = "webapps"
  
  # All other configuration remains the same
  name                = "myapp"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  resource_token      = "abc123"

  # Infrastructure dependencies (no container registry needed)
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  frontend_identity_id       = azurerm_user_assigned_identity.frontend.id
  backend_identity_id        = azurerm_user_assigned_identity.backend.id

  # Environment variables (converted to app settings automatically)
  backend_env_vars = [
    {
      name  = "DATABASE_CONNECTION"
      value = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=db-connection)"
    }
  ]
}
```

## Module Reference

### hosting Module (Platform Selector)

| Variable | Description | Type | Default |
|----------|-------------|------|---------|
| `hosting_platform` | Platform to deploy to: `containers` or `webapps` | `string` | `"containers"` |
| `name` | Base name for resources | `string` | - |
| `frontend_env_vars` | Environment variables for frontend | `list(object)` | `[]` |
| `backend_env_vars` | Environment variables for backend | `list(object)` | `[]` |
| `secrets` | Secrets for containers (ignored for webapps) | `list(object)` | `[]` |
| `frontend_config` | Frontend configuration object | `object` | `{}` |
| `backend_config` | Backend configuration object | `object` | `{}` |

### Environment Variables Format

```hcl
env_vars = [
  {
    name         = "VARIABLE_NAME"
    value        = "variable_value"      # For regular env vars
    secret_name  = "secret-reference"    # For container secrets (containers only)
  }
]
```

### Configuration Objects

Both `frontend_config` and `backend_config` support platform-specific settings:

```hcl
frontend_config = {
  # Common settings
  port             = 8080
  azd_service_name = "frontend-app"
  
  # Container-specific (ignored for webapps)
  min_replicas     = 1
  max_replicas     = 10
  cpu              = 0.5
  memory           = "1.0Gi"
  
  # WebApp-specific (ignored for containers)
  sku_name         = "B1"
  node_version     = "22-lts"
  app_command_line = "npm run build && npm start"
}
```

## Key Differences Between Platforms

| Feature | Container Apps | App Service |
|---------|----------------|-------------|
| **Secrets** | Uses container secrets with Key Vault integration | Uses Key Vault references in app settings |
| **Scaling** | Built-in auto-scaling with min/max replicas | Vertical scaling with service plan SKUs |
| **Environment Variables** | Native container env vars | App settings |
| **Images** | Container registry required | Built-in deployment from source |
| **Networking** | Container Apps Environment | Virtual network integration |

## Outputs

The hosting module provides consistent outputs regardless of platform:

```hcl
# Common outputs
output "frontend_url"      # Frontend application URL
output "backend_url"       # Backend API URL
output "hosting_platform"  # Platform used ("containers" or "webapps")

# Platform-specific outputs
output "container_environment_id"    # Container Apps Environment (containers only)
output "frontend_service_plan_id"    # App Service Plan (webapps only)
```

## Best Practices

### 🔒 **Security**
- Use managed identities for all Azure service authentication
- Store secrets in Key Vault and reference them appropriately
- Enable diagnostic logging for monitoring

### 📊 **Configuration**
- Use environment variables arrays for clean, maintainable configuration
- Leverage default values to minimize configuration overhead
- Use consistent naming conventions with the `resource_token`

### 🚀 **Deployment**
- Start with Container Apps (default) for modern cloud-native applications
- Switch to App Service for traditional web applications or specific requirements
- Use the same configuration structure for both platforms

### 🔄 **Migration**
- Applications can be migrated between platforms by simply changing `hosting_platform`
- Adjust platform-specific settings in the config objects as needed
- Update secret management approach when switching platforms

## Examples

See the [examples/usage.tf](examples/usage.tf) file for comprehensive usage examples including:
- Container Apps deployment with secrets
- App Service deployment with Key Vault references
- Platform-specific configuration options
- Output usage patterns

## Integration with Azure Developer CLI (azd)

Both modules are designed to work seamlessly with `azd`:
- Set `azd_service_name` in the config objects
- Use appropriate lifecycle ignore rules for images (containers) or app settings (webapps)
- Configure tags for azd service identification
