# CI/CD Configuration Guide

This guide explains how to configure the deployment scripts for CI/CD environments where interactive prompts are not possible.

## Environment Detection

The scripts automatically detect CI/CD environments by checking:
- `CI` environment variable (set by most CI systems)
- `GITHUB_ACTIONS` environment variable (set by GitHub Actions)
- `AZD_SKIP_INTERACTIVE` environment variable (custom override)

## Bypass Interactive Prompts

### Method 1: Automatic Detection
Most CI/CD systems set the `CI` environment variable automatically:
```yaml
# GitHub Actions - automatically sets CI=true
# Azure DevOps - automatically sets CI=true
# Jenkins - automatically sets CI=true
```

### Method 2: Manual Override
Set the bypass flag explicitly:
```bash
export AZD_SKIP_INTERACTIVE=true
azd up
```

## Phone Number Configuration in CI/CD

### Option 1: Pre-configured Phone Number
```bash
# Set phone number via environment variable
export ACS_SOURCE_PHONE_NUMBER="+1234567890"
azd up
```

### Option 2: Auto-provision Phone Number
```bash
# Enable auto-provisioning
azd env set ACS_AUTO_PROVISION_PHONE true
azd up
```

### Option 3: Skip Phone Number
```bash
# Just run without phone number (can be added later)
azd up
```

## SSL Certificates for Bicep Deployments

For Bicep deployments requiring SSL certificates:

```bash
# Encode certificates to base64
export SSL_CERT_BASE64=$(base64 -w 0 < path/to/cert.pem)
export SSL_KEY_BASE64=$(base64 -w 0 < path/to/key.pem)
azd up
```

## GitHub Actions Example

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      
      - name: Install azd
        uses: Azure/setup-azd@v0.1.0
      
      - name: Deploy with azd
        env:
          AZURE_ENV_NAME: production
          AZURE_LOCATION: eastus
          ACS_SOURCE_PHONE_NUMBER: ${{ secrets.ACS_PHONE_NUMBER }}
          # CI is automatically set by GitHub Actions
        run: |
          azd auth login --client-id ${{ secrets.AZURE_CLIENT_ID }} \
            --client-secret ${{ secrets.AZURE_CLIENT_SECRET }} \
            --tenant-id ${{ secrets.AZURE_TENANT_ID }}
          
          azd env new $AZURE_ENV_NAME
          azd up --no-prompt
```

## Azure DevOps Pipeline Example

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  AZURE_ENV_NAME: production
  AZURE_LOCATION: eastus

steps:
  - task: AzureCLI@2
    displayName: 'Deploy Infrastructure'
    inputs:
      azureSubscription: 'Your-Service-Connection'
      scriptType: 'bash'
      scriptLocation: 'inlineScript'
      inlineScript: |
        # Install azd
        curl -fsSL https://aka.ms/install-azd.sh | bash
        
        # CI is automatically set by Azure DevOps
        export ACS_SOURCE_PHONE_NUMBER=$(ACS_PHONE_NUMBER)
        
        azd auth login --client-id $(AZURE_CLIENT_ID) \
          --client-secret $(AZURE_CLIENT_SECRET) \
          --tenant-id $(AZURE_TENANT_ID)
        
        azd env new $(AZURE_ENV_NAME)
        azd up --no-prompt
```

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `AZD_SKIP_INTERACTIVE` | Force non-interactive mode | No (auto-detected) |
| `CI` | Standard CI indicator | No (set by CI system) |
| `GITHUB_ACTIONS` | GitHub Actions indicator | No (set by GitHub) |
| `ACS_SOURCE_PHONE_NUMBER` | Pre-configured phone number | No |
| `ACS_AUTO_PROVISION_PHONE` | Auto-provision phone if missing | No |
| `SSL_CERT_BASE64` | Base64 encoded SSL certificate | No (Bicep only) |
| `SSL_KEY_BASE64` | Base64 encoded SSL private key | No (Bicep only) |

## Troubleshooting

### Scripts Still Prompting
- Ensure `CI` or `AZD_SKIP_INTERACTIVE` is set
- Check script output for "CI/CD mode detected" message

### Phone Number Not Set
- Verify `ACS_SOURCE_PHONE_NUMBER` format (+1234567890)
- Check azd environment: `azd env get-values`

### SSL Certificate Issues (Bicep)
- Ensure certificates are base64 encoded without line breaks
- Use `base64 -w 0` on Linux/Mac or `[Convert]::ToBase64String()` on PowerShell