# 🚀 GitHub Actions Deployment Automation

This directory contains GitHub Actions workflows for automated deployment of your Real-Time Audio Agent application to Azure using Azure Developer CLI (AZD).

## 🎯 Available Workflows

### 🏗️ Azure Developer CLI Deployment
**File:** [`deploy-azd.yml`](./deploy-azd.yml)

The main deployment workflow that handles both infrastructure and application deployment using Azure Developer CLI with Terraform backend.

**Features:**
- ✅ **Unified Deployment**: Infrastructure and application in one workflow
- ✅ **Flexible Actions**: Provision, deploy, up, or down operations
- ✅ **Terraform Integration**: Uses Terraform for infrastructure with AZD orchestration
- ✅ **Multiple Triggers**: Manual, push to main, and pull request support
- ✅ **Environment Support**: dev, staging, and prod environments
- ✅ **Configurable State Storage**: Customizable Terraform state location

**Available Actions:**
- `provision` - Infrastructure only
- `deploy` - Application only (requires existing infrastructure)
- `up` - Both infrastructure and application
- `down` - Destroy all resources

**Configurable Inputs:**
- Environment selection (dev/staging/prod)
- Action type selection
- Terraform state storage configuration:
  - Resource Group (default: "Default-ActivityLogAlerts")
  - Storage Account (default: "rtagent")
  - Container Name (default: "tfstate")

**Triggers:**
- ✅ Manual dispatch with full configuration options
- ✅ Push to `main` branch (auto-deploy to dev)
- ✅ Pull requests (Terraform plan preview)
- ✅ Workflow call from other workflows

### 🎯 Complete Deployment Orchestrator
**File:** [`deploy-azd-complete.yml`](./deploy-azd-complete.yml)

A simplified orchestrator workflow that calls the main deployment workflow with predefined configurations.

**Features:**
- ✅ **Simplified Interface**: Basic environment and action selection
- ✅ **Workflow Orchestration**: Calls the main deployment workflow
- ✅ **Manual Trigger Only**: Designed for on-demand deployments

**Triggers:**
- ✅ Manual dispatch only

## 🚀 Quick Start

### 1. Configure Azure Authentication
Set up the required GitHub repository secrets:
```bash
AZURE_CLIENT_ID          # Service Principal ID
AZURE_TENANT_ID          # Azure Tenant ID
AZURE_SUBSCRIPTION_ID    # Target Azure Subscription
```

### 2. Deploy Everything (Infrastructure + Application)
1. Navigate to **Actions** → **Azure Developer CLI Deployment**
2. Click **Run workflow**
3. Configure:
   - **Environment**: `dev` (recommended for first deployment)
   - **Action**: `up`
   - **Terraform State**: Use defaults or specify custom location

### 3. Infrastructure Only
```yaml
# Run deploy-azd.yml with:
Environment: dev
Action: provision
```

### 4. Application Only (requires existing infrastructure)
```yaml
# Run deploy-azd.yml with:
Environment: dev  
Action: deploy
```

## 🌍 Environment Management

### Development (`dev`)
- **Auto-deployment**: Push to `main` triggers deployment
- **Manual deployment**: Available via workflow dispatch
- **Resources**: Minimal sizing for cost efficiency
- **Purpose**: Feature development and testing

### Staging (`staging`)
- **Manual deployment**: Workflow dispatch only
- **Resources**: Production-like configuration
- **Purpose**: Integration testing and UAT

### Production (`prod`)
- **Manual deployment**: Workflow dispatch only
- **Resources**: Full production specification
- **Purpose**: Live user traffic

## 🔄 Deployment Actions

### Available Actions
- **`up`**: Deploy both infrastructure and application (recommended)
- **`provision`**: Infrastructure only
- **deploy**: Application only (requires existing infrastructure)
- **`down`**: Destroy all resources (cleanup)

### Terraform State Configuration
Customize where Terraform state is stored:
- **Resource Group**: Default "Default-ActivityLogAlerts"
- **Storage Account**: Default "rtagent"
- **Container**: Default "tfstate"

## 🔐 Security & Authentication

### OIDC Authentication
- **Federated Identity**: No client secrets required
- **Workload Identity**: GitHub-specific Azure access
- **Least Privilege**: Minimal required permissions

### Environment Protection
- **Branch Protection**: Only `main` branch can auto-deploy
- **Manual Approval**: Staging/prod require manual triggers
- **Secret Management**: Azure Key Vault for application secrets

## � Monitoring & Troubleshooting

### Workflow Monitoring
- **GitHub Actions**: Check Actions tab for deployment status
- **Detailed Logs**: Click workflow runs for step-by-step progress
- **Error Tracking**: Review failed steps for troubleshooting

### Azure Resource Monitoring
- **Azure Portal**: Monitor deployed resources and health
- **Application Insights**: Application performance and errors
- **Container Apps**: Runtime logs and scaling metrics

### Common Issues & Solutions

**Authentication Failures:**
```bash
# Verify service principal permissions
az role assignment list --assignee $AZURE_CLIENT_ID
```

**Terraform State Lock:**
```bash
# Check for concurrent deployments in GitHub Actions
# Wait for running deployments to complete
```

**Resource Quota Issues:**
```bash
# Check Azure subscription quotas
az vm list-usage --location $AZURE_LOCATION
```

## 🎯 Usage Examples

### Full Environment Setup
```yaml
# Complete dev environment deployment
Workflow: deploy-azd.yml
Environment: dev
Action: up
# Uses default state storage
```

### Production with Custom State
```yaml
# Production deployment with custom Terraform state
Workflow: deploy-azd.yml
Environment: prod  
Action: up
RS_Resource_Group: "prod-tfstate-rg"
RS_Storage_Account: "prodtfstate123"
RS_Container_Name: "terraform-state"
```

### Quick Cleanup
```yaml
# Remove dev environment resources
Workflow: deploy-azd.yml
Environment: dev
Action: down
```

## 🛠️ Local Development

### Azure Developer CLI
For local development and testing:
```bash
# Initialize project (first time)
azd init

# Deploy everything
azd up --environment dev

# Deploy only infrastructure
azd provision --environment dev

# Deploy only application  
azd deploy --environment dev

# Clean up resources
azd down --environment dev
```

### Prerequisites
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Terraform](https://terraform.io/downloads)
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- Docker for container builds

## 📋 Best Practices

### Development Workflow
1. **Feature Branches**: Create branches for new features
2. **Pull Requests**: Use PRs to review infrastructure changes
3. **Environment Progression**: dev → staging → prod
4. **Testing**: Validate in dev before promoting

### Infrastructure Management
- **State Storage**: Use consistent Terraform state location
- **Resource Naming**: Follow Azure naming conventions
- **Tagging**: Apply consistent resource tags
- **Cost Control**: Monitor and optimize resource costs

### Security Practices
- **Least Privilege**: Minimal Azure permissions
- **Secret Management**: Use Azure Key Vault
- **Network Security**: Configure appropriate access controls
- **Regular Updates**: Keep dependencies current

---

## 🔗 Related Documentation

- [Azure Developer CLI Guide](../../docs/DeploymentGuide.md)
- [Infrastructure Overview](../../docs/Architecture.md)
- [Troubleshooting Guide](../../docs/Troubleshooting.md)
- [Security Configuration](../../docs/AuthForHTTPandWSS.md)

## 🆘 Support

### Getting Help
1. **Review Logs**: Check GitHub Actions workflow logs
2. **Azure Portal**: Monitor resource status and logs
3. **Documentation**: Consult project documentation
4. **Team Support**: Reach out to the development team

### Debugging Tips
- Enable debug logging with repository variable `ACTIONS_STEP_DEBUG=true`
- Check Azure Activity Logs for resource-level issues
- Verify Terraform plan output before applying changes
- Test configurations in dev environment first

Happy deploying! 🚀
