---
name: deployment-guide
description: Guide azd-based deployments, including where azure.yaml and azd hook scripts live, the current deployment flow, troubleshooting docs, and regional/model availability checks for Azure OpenAI
---

# Deployment Guide Skill

Use this skill to orient users to the azd deployment setup, the hook flow, and how to validate regional/model availability.

## Key Files & Locations

- `azure.yaml` — azd config, services, and hooks (preprovision/postprovision/postdown)
- `devops/scripts/azd/preprovision.sh` — preflight checks, remote state setup, tfvars/provider config
- `devops/scripts/azd/postprovision.sh` — post-provision tasks (App Config, local env, etc.)
- `devops/scripts/azd/postdown.sh` — post-`azd down` cleanup (optional state delete + purge reminder)
- `devops/scripts/azd/helpers/preflight-checks.sh` — region + quota checks
- `infra/terraform/` — Terraform modules + params
- `infra/terraform/params/main.tfvars.*.json` — environment-specific TF vars (including model_deployments)

## Logical Flow (azd)

1. `azd up`
2. `preprovision` hook:
   - Runs preflight checks (tools/auth/providers/region/quota)
   - Resolves `AZURE_LOCATION`
   - Configures Terraform backend (remote state or local)
   - Generates `main.tfvars.json` and provider config
3. Terraform apply (infra create)
4. `postprovision` hook:
   - App Config updates
   - Local `.env.local` generation
   - Data provisioning / phone config (interactive)
5. `azd deploy` (service build/push/deploy per `azure.yaml`)
6. `azd down` → `postdown` hook (optional remote state cleanup + purge reminder)

## Troubleshooting & Docs

Direct users to:
- `docs/getting-started/quickstart.md` — first-time `azd up`
- `docs/deployment/README.md` — advanced deployment and flags
- `docs/operations/troubleshooting.md` and `TROUBLESHOOTING.md` — common errors
- `docs/getting-started/README.md` — region availability matrix

## Regional Availability & Model Checks

Use these Azure CLI commands to validate region/model availability:

```bash
# List regions
az account list-locations -o table

# Check Azure OpenAI service availability in a region
az cognitiveservices account list-skus --kind OpenAI --location <region> -o table

# Check Cognitive Services availability (Speech, etc.)
az cognitiveservices account list-skus --kind SpeechServices --location <region> -o table

# Check OpenAI quota usage for a region (requires jq)
az cognitiveservices usage list -l <region> -o json \
  | jq -r '.[] | select(.name.value | startswith("OpenAI.")) | "\(.name.value)\t\(.currentValue)/\(.limit)"'

# List deployments in a specific Azure OpenAI resource
az cognitiveservices account deployment list -g <resource-group> -n <openai-account> -o table
```

Also point to `devops/scripts/azd/helpers/preflight-checks.sh` for the exact checks used by azd.

## Custom Model Deployment Overrides

There are two layers to adjust:

1. **Provisioning (what gets created):** edit `model_deployments` in:
   - `infra/terraform/params/main.tfvars.*.json` (env-specific)
   - or `infra/terraform/terraform.tfvars.example` (reference)

2. **Runtime selection (what the app uses):** set the deployment name:
   - `AZURE_OPENAI_CHAT_DEPLOYMENT_ID` (preferred for app runtime)
   - App Config key: `azure/openai/deployment-id`

Example:
```bash
azd env set AZURE_OPENAI_CHAT_DEPLOYMENT_ID "<your-deployment-name>"
azd deploy
```

For agent-specific overrides, update `deployment_id` in:
`apps/artagent/backend/registries/agentstore/*/agent.yaml`.
