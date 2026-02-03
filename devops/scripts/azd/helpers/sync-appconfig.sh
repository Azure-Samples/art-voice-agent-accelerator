#!/bin/bash
# ============================================================================
# 📦 App Configuration Sync
# ============================================================================
# Syncs infrastructure keys from azd env to Azure App Configuration.
# This script syncs values that are only known after Terraform provisioning
# (e.g., service endpoints, container URLs).
#
# Usage: ./sync-appconfig.sh [--endpoint URL] [--label LABEL] [--dry-run]
# ============================================================================

set -euo pipefail

# ============================================================================
# Logging
# ============================================================================

if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${GREEN_BOLD+x}" ]]; then GREEN_BOLD=$'\033[1;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi
readonly BLUE GREEN GREEN_BOLD YELLOW RED DIM NC

log()          { printf '│ %s%s%s\n' "$DIM" "$*" "$NC"; }
info()         { printf '│ %s%s%s\n' "$BLUE" "$*" "$NC"; }
success()      { printf '│ %s✔%s %s\n' "$GREEN" "$NC" "$*"; }
phase_success(){ printf '│ %s✔ %s%s\n' "$GREEN_BOLD" "$*" "$NC"; }
warn()         { printf '│ %s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()         { printf '│ %s✖%s %s\n' "$RED" "$NC" "$*" >&2; }

# ============================================================================
# Parse Arguments
# ============================================================================

ENDPOINT=""
LABEL=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --endpoint) ENDPOINT="$2"; shift 2 ;;
        --label) LABEL="$2"; shift 2 ;;
        --config) shift 2 ;; # Ignored for backward compatibility
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--endpoint URL] [--label LABEL] [--dry-run]"
            exit 0
            ;;
        *) fail "Unknown option: $1"; exit 1 ;;
    esac
done

# Get from azd env if not provided
if [[ -z "$ENDPOINT" ]]; then
    ENDPOINT=$(azd env get-value AZURE_APPCONFIG_ENDPOINT 2>/dev/null || echo "")
fi
if [[ -z "$LABEL" ]]; then
    LABEL=$(azd env get-value AZURE_ENV_NAME 2>/dev/null || echo "")
fi

if [[ -z "$ENDPOINT" ]]; then
    fail "App Config endpoint not set. Use --endpoint or set AZURE_APPCONFIG_ENDPOINT"
    exit 1
fi

# Validate endpoint format
if [[ ! "$ENDPOINT" =~ \.azconfig\.io$ ]]; then
    fail "Invalid App Configuration endpoint format: $ENDPOINT"
    fail "Expected format: https://<name>.azconfig.io"
    exit 1
fi

# ============================================================================
# Helper Functions
# ============================================================================

# Helper to get azd env value
get_azd_value() {
    azd env get-value "$1" 2>/dev/null || echo ""
}

# Helper to set a key-value in App Config
set_kv() {
    local key="$1" value="$2" content_type="${3:-}"
    
    # Skip empty values
    [[ -z "$value" ]] && return 0
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [DRY-RUN] $key = ${value:0:50}..."
        return 0
    fi
    
    local cmd_args=(
        --endpoint "$ENDPOINT"
        --key "$key"
        --value "$value"
        --auth-mode login
        --yes
        --output none
    )
    [[ -n "$LABEL" ]] && cmd_args+=(--label "$LABEL")
    [[ -n "$content_type" ]] && cmd_args+=(--content-type "$content_type")
    
    local error_output
    if error_output=$(az appconfig kv set "${cmd_args[@]}" 2>&1); then
        return 0
    else
        fail "Failed to set key: $key"
        log "  └─ Value attempted: ${value:0:100}..."
        # Show the full error message for debugging
        local error_msg
        error_msg=$(echo "$error_output" | head -3)
        [[ -n "$error_msg" ]] && log "  └─ Error: $error_msg"
        return 1
    fi
}

# Helper to get existing App Config value (for preserving values not in azd env)
get_appconfig_value() {
    local key="$1"
    local label_arg=""
    [[ -n "$LABEL" ]] && label_arg="--label $LABEL"
    
    # shellcheck disable=SC2086
    az appconfig kv show \
        --endpoint "$ENDPOINT" \
        --key "$key" \
        $label_arg \
        --auth-mode login \
        --query value \
        --output tsv 2>/dev/null || echo ""
}

# Helper to add Key Vault reference
set_kv_ref() {
    local key="$1" secret_name="$2"
    local kv_uri
    kv_uri=$(get_azd_value AZURE_KEY_VAULT_ENDPOINT)
    
    [[ -z "$kv_uri" ]] && return 0
    
    local ref_value="{\"uri\":\"${kv_uri}secrets/${secret_name}\"}"
    set_kv "$key" "$ref_value" "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
}

# ============================================================================
# Main
# ============================================================================

echo ""
echo "╭─────────────────────────────────────────────────────────────"
echo "│ 📦 App Configuration Sync"
echo "├─────────────────────────────────────────────────────────────"
info "Endpoint: $ENDPOINT"
info "Label: ${LABEL:-<none>}"
[[ "$DRY_RUN" == "true" ]] && warn "DRY RUN - no changes will be made"
echo "├─────────────────────────────────────────────────────────────"

# ============================================================================
# Sync Infrastructure Keys from azd env
# ============================================================================
log ""
log "Syncing infrastructure keys from azd env..."

count=0
errors=0

# Azure OpenAI
set_kv "azure/openai/endpoint" "$(get_azd_value AZURE_OPENAI_ENDPOINT)" && ((++count)) || ((++errors))
set_kv "azure/openai/deployment-id" "$(get_azd_value AZURE_OPENAI_CHAT_DEPLOYMENT_ID)" && ((++count)) || ((++errors))
set_kv "azure/openai/api-version" "$(get_azd_value AZURE_OPENAI_API_VERSION)" && ((++count)) || ((++errors))

# Azure Speech
set_kv "azure/speech/endpoint" "$(get_azd_value AZURE_SPEECH_ENDPOINT)" && ((++count)) || ((++errors))
set_kv "azure/speech/region" "$(get_azd_value AZURE_SPEECH_REGION)" && ((++count)) || ((++errors))
set_kv "azure/speech/resource-id" "$(get_azd_value AZURE_SPEECH_RESOURCE_ID)" && ((++count)) || ((++errors))

# Azure Communication Services
set_kv "azure/acs/endpoint" "$(get_azd_value ACS_ENDPOINT)" && ((++count)) || ((++errors))
set_kv "azure/acs/immutable-id" "$(get_azd_value ACS_IMMUTABLE_ID)" && ((++count)) || ((++errors))
set_kv_ref "azure/acs/connection-string" "acs-connection-string" && ((++count)) || ((++errors))
set_kv "azure/acs/email-sender-address" "$(get_azd_value AZURE_EMAIL_SENDER_ADDRESS)" && ((++count)) || ((++errors))

# Redis
set_kv "azure/redis/hostname" "$(get_azd_value REDIS_HOSTNAME)" && ((++count)) || ((++errors))
set_kv "azure/redis/port" "$(get_azd_value REDIS_PORT)" && ((++count)) || ((++errors))

# Cosmos DB
# Using ++count to overcome an occasional bug in count and errors when the value is zero
set_kv "azure/cosmos/database-name" "$(get_azd_value AZURE_COSMOS_DATABASE_NAME)" && ((++count)) || ((++errors))
set_kv "azure/cosmos/collection-name" "$(get_azd_value AZURE_COSMOS_COLLECTION_NAME)" && ((++count)) || ((++errors))
# Cosmos Entra connection string (Key Vault reference with OIDC auth for managed identity)
set_kv_ref "azure/cosmos/connection-string" "cosmos-entra-connection-string" && ((++count)) || ((++errors))

# Storage
set_kv "azure/storage/account-name" "$(get_azd_value AZURE_STORAGE_ACCOUNT_NAME)" && ((++count)) || ((++errors))
set_kv "azure/storage/container-url" "$(get_azd_value AZURE_STORAGE_CONTAINER_URL)" && ((++count)) || ((++errors))

# App Insights
set_kv "azure/appinsights/connection-string" "$(get_azd_value APPLICATIONINSIGHTS_CONNECTION_STRING)" && ((++count)) || ((++errors))

# Voice Live (optional)
set_kv "azure/voicelive/endpoint" "$(get_azd_value AZURE_VOICELIVE_ENDPOINT)" && ((++count)) || ((++errors))
set_kv "azure/voicelive/model" "$(get_azd_value AZURE_VOICELIVE_MODEL)" && ((++count)) || ((++errors))
set_kv "azure/voicelive/resource-id" "$(get_azd_value AZURE_VOICELIVE_RESOURCE_ID)" && ((++count)) || ((++errors))

# AI Foundry (for Evaluations SDK)
# Derive project endpoint from project_id since azapi doesn't expose it directly
# Pattern: https://<account-name>.services.ai.azure.com/api/projects/<project-name>
ai_foundry_project_id=$(get_azd_value ai_foundry_project_id)
if [[ -n "$ai_foundry_project_id" ]]; then
    # Extract account name and project name from resource ID
    # Format: .../accounts/<account-name>/projects/<project-name>
    account_name=$(echo "$ai_foundry_project_id" | sed -n 's|.*/accounts/\([^/]*\)/projects/.*|\1|p')
    project_name=$(echo "$ai_foundry_project_id" | sed -n 's|.*/projects/\([^/]*\)$|\1|p')
    if [[ -n "$account_name" && -n "$project_name" ]]; then
        ai_foundry_project_endpoint="https://${account_name}.services.ai.azure.com/api/projects/${project_name}"
        set_kv "azure/ai-foundry/project-endpoint" "$ai_foundry_project_endpoint" && ((++count)) || ((++errors))
    fi
fi

# CardAPI MCP server endpoint (self-contained, direct Cosmos DB access)
# Priority: 1. Environment variable override, 2. azd env value, 3. Azure CLI query, 4. Existing App Config value
cardapi_url=""

# Check for environment variable override (from GitHub Actions or local)
if [[ -n "${MCP_SERVER_CARDAPI_URL:-}" ]]; then
    cardapi_url="$MCP_SERVER_CARDAPI_URL"
    info "Using MCP_SERVER_CARDAPI_URL from environment: $cardapi_url"
else
    # Try azd env value (from Terraform outputs)
    cardapi_url=$(get_azd_value CARDAPI_CONTAINER_APP_URL)
    if [[ -n "$cardapi_url" ]]; then
        info "Using CARDAPI_CONTAINER_APP_URL from azd env: $cardapi_url"
    fi
fi

# If still empty, query Azure directly for the Container App FQDN
if [[ -z "$cardapi_url" ]]; then
    resource_group=$(get_azd_value AZURE_RESOURCE_GROUP)
    if [[ -n "$resource_group" ]]; then
        # Find cardapi container app by name pattern
        cardapi_fqdn=$(az containerapp list \
            --resource-group "$resource_group" \
            --query "[?contains(name, 'cardapi')].properties.configuration.ingress.fqdn" \
            --output tsv 2>/dev/null | head -1 | tr -d '\n\r' || echo "")
        if [[ -n "$cardapi_fqdn" ]]; then
            cardapi_url="https://${cardapi_fqdn}"
            info "Discovered CardAPI MCP URL from Azure: $cardapi_url"
        fi
    fi
fi

# If still empty, preserve existing App Config value
if [[ -z "$cardapi_url" ]]; then
    existing_url=$(get_appconfig_value "app/mcp/servers/cardapi/url")
    if [[ -n "$existing_url" ]]; then
        cardapi_url="$existing_url"
        info "Preserving existing app/mcp/servers/cardapi/url: $cardapi_url"
    fi
fi

if [[ -n "$cardapi_url" ]]; then
    # Backend expects this key to load MCP_SERVER_CARDAPI_URL
    set_kv "app/mcp/servers/cardapi/url" "$cardapi_url" && ((++count)) || ((++errors))
else
    warn "CardAPI MCP URL not configured (set MCP_SERVER_CARDAPI_URL or deploy cardapi service)"
fi

# CardAPI MCP auth settings (for EasyAuth-protected deployments)
cardapi_auth_enabled=$(get_azd_value CARDAPI_MCP_AUTH_ENABLED)
cardapi_app_id=$(get_azd_value CARDAPI_MCP_APP_ID)
if [[ -n "$cardapi_auth_enabled" ]]; then
    set_kv "app/mcp/servers/cardapi/auth-enabled" "$cardapi_auth_enabled" && ((++count)) || ((++errors))
fi
if [[ -n "$cardapi_app_id" ]]; then
    set_kv "app/mcp/servers/cardapi/app-id" "$cardapi_app_id" && ((++count)) || ((++errors))
fi

# Environment metadata
set_kv "app/environment" "$(get_azd_value AZURE_ENV_NAME)" && ((++count)) || ((++errors))

# Sentinel for refresh trigger
set_kv "app/sentinel" "v$(date +%s)" && ((++count)) || ((++errors))

echo "├─────────────────────────────────────────────────────────────"
if [[ $errors -gt 0 ]]; then
    warn "Sync completed with $errors errors ($count keys synced)"
else
    success "Sync complete: $count infrastructure keys"
fi
echo "╰─────────────────────────────────────────────────────────────"
echo ""
