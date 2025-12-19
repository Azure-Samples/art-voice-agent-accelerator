# 🚀 GitHub Actions Deployment Automation

This directory contains GitHub Actions workflows for automated deployment of your Real-Time Audio Agent application to Azure using Azure Developer CLI (AZD).

## 🎯 Workflows

| Workflow | File | Description |
|----------|------|-------------|
| **Deploy to Azure** | [`deploy-azd-complete.yml`](./deploy-azd-complete.yml) | Main deployment workflow - use this one |
| **Deploy Documentation** | [`docs.yml`](./docs.yml) | Builds and deploys docs to GitHub Pages |
| **Test AZD Hooks** | [`test-azd-hooks.yml`](./test-azd-hooks.yml) | Tests preprovision/postprovision hooks across platforms |
| **_template-deploy-azd** | [`_template-deploy-azd.yml`](./_template-deploy-azd.yml) | ⚠️ Internal template - do not run directly |

## 🚀 Quick Start

### Deploy Everything
1. Go to **Actions** → **Deploy to Azure**
2. Click **Run workflow**
3. Select environment (`dev`/`staging`/`prod`) and action (`up`)

### Available Actions
| Action | Description |
|--------|-------------|
| `up` | Provision infrastructure + deploy application (default) |
| `provision` | Infrastructure only (Terraform) |
| `deploy` | Application only (requires existing infrastructure) |
| `down` | Destroy all resources |

## 🏗️ Workflow Architecture

The template workflow is organized into clean, separate jobs:

```
┌──────────────────────────────────────────────────────────────┐
│                    Deploy to Azure                           │
│                 (deploy-azd-complete.yml)                    │
└──────────────────────┬───────────────────────────────────────┘
                       │ calls
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              _template-deploy-azd.yml                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐    ┌─────────────┐    ┌──────────┐             │
│  │  Setup  │───▶│   Execute   │───▶│ Finalize │             │
│  │   🔐    │    │ 🏗️📦🚀💥   │    │    📋    │             │
│  └─────────┘    └─────────────┘    └──────────┘             │
│       │                                                      │
│       │ (PRs only)                                          │
│       ▼                                                      │
│  ┌─────────┐                                                │
│  │ Preview │                                                │
│  │   📋    │                                                │
│  └─────────┘                                                │
└──────────────────────────────────────────────────────────────┘
```

### Jobs

| Job | Description |
|-----|-------------|
| **Setup** | Azure authentication (OIDC or Service Principal) |
| **Preview** | Runs `azd provision --preview` for PRs |
| **Execute** | Runs the selected azd command (`provision`/`deploy`/`up`/`down`) |
| **Finalize** | Updates GitHub environment variables, generates summary |

## 🔐 Authentication

### OIDC (Recommended)
Configure federated credentials in Azure AD:
```
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
```

### Service Principal (Fallback)
```
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
```

## ⚙️ Environment Variables

After deployment, these variables are automatically set on the GitHub environment:

| Variable | Description |
|----------|-------------|
| `AZURE_APPCONFIG_ENDPOINT` | Azure App Configuration endpoint |
| `AZURE_APPCONFIG_LABEL` | Configuration label for the environment |

These are used on subsequent deployments to maintain consistency.

## 🌍 Environments

| Environment | Trigger | Purpose |
|-------------|---------|---------|
| `dev` | Push to `main` | Development and testing |
| `staging` | Manual | Pre-production validation |
| `prod` | Manual | Production |

## 📋 Triggers

- **Push to `main`**: Auto-deploys to `dev`
- **Pull Request**: Preview infrastructure changes
- **Manual**: Run any action on any environment

## 🧪 Test AZD Hooks Workflow

The `test-azd-hooks.yml` workflow validates the AZD preprovision and postprovision hooks across multiple platforms.

### What It Tests

| Test | Description |
|------|-------------|
| **Lint** | ShellCheck analysis of all shell scripts |
| **Syntax Validation** | Bash syntax checking (`bash -n`) |
| **Logging Functions** | Verifies unified logging utilities work |
| **Location Resolution** | Tests tfvars-based location resolution |
| **Backend Configuration** | Tests Terraform backend.tf generation |
| **Regional Availability** | Validates Azure service availability checks |

### Platforms Tested

| Platform | Runner | Shell |
|----------|--------|-------|
| 🐧 Linux | `ubuntu-latest` | Bash |
| 🍎 macOS | `macos-latest` | Bash |
| 🪟 Windows | `windows-latest` | Git Bash |

### Triggers

- Push to `main` or `staging` (when hook scripts change)
- Pull requests (when hook scripts change)
- Manual dispatch with optional debug mode

### Running Locally

```bash
# Validate script syntax
bash -n devops/scripts/azd/preprovision.sh
bash -n devops/scripts/azd/postprovision.sh

# Run preflight checks
cd devops/scripts/azd/helpers
source preflight-checks.sh
run_preflight_checks

# Test with local state (no Azure required)
export LOCAL_STATE=true
export AZURE_ENV_NAME=local-test
export AZURE_LOCATION=eastus2
bash devops/scripts/azd/preprovision.sh terraform
```

## 🔗 Related Documentation

- [Azure Developer CLI Guide](../../docs/deployment/azd-guide.md)
- [Infrastructure Overview](../../docs/architecture/)
- [Troubleshooting](../../docs/operations/)

## 🛠️ Local Development

```bash
# Deploy everything
azd up --environment dev

# Infrastructure only
azd provision --environment dev

# Application only
azd deploy --environment dev

# Destroy resources
azd down --environment dev
```

### Prerequisites
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Terraform](https://terraform.io/downloads)
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- Docker for container builds

