#!/bin/bash
# ============================================================================
# 📦 App Configuration Sync
# ============================================================================
# Syncs ALL configuration to Azure App Configuration:
#   1. Infrastructure keys from azd env (Azure endpoints, connection strings)
#   2. Application settings from config/appconfig.json (pools, voice, etc.)
#
# Usage: ./sync-appconfig.sh [--endpoint URL] [--label LABEL] [--config FILE]
# ============================================================================

set -euo pipefail

readonly SYNC_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_CONFIG="$SYNC_SCRIPT_DIR/../../../../config/appconfig.json"

# ============================================================================
# Logging
# ============================================================================

log()     { echo "│ $*"; }
info()    { echo "│ ℹ️  $*"; }
success() { echo "│ ✅ $*"; }
warn()    { echo "│ ⚠️  $*"; }
fail()    { echo "│ ❌ $*" >&2; }

# ============================================================================
# Parse Arguments
# ============================================================================

ENDPOINT=""
LABEL=""
CONFIG_FILE="$DEFAULT_CONFIG"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --endpoint) ENDPOINT="$2"; shift 2 ;;
        --label) LABEL="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--endpoint URL] [--label LABEL] [--config FILE] [--dry-run]"
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

if [[ ! -f "$CONFIG_FILE" ]]; then
    fail "Config file not found: $CONFIG_FILE"
    exit 1
fi

# ============================================================================
# Build Import JSON
# ============================================================================

# Create temp file for batch import
IMPORT_FILE=$(mktemp)
trap "rm -f $IMPORT_FILE" EXIT

# Initialize JSON array
echo '[]' > "$IMPORT_FILE"

# Helper to add a key-value to the import file
add_kv() {
    local key="$1" value="$2" content_type="${3:-}"
    
    # Skip empty values
    [[ -z "$value" ]] && return 0
    
    local entry
    if [[ -n "$content_type" ]]; then
        entry=$(jq -n --arg k "$key" --arg v "$value" --arg l "$LABEL" --arg ct "$content_type" \
            '{key: $k, value: $v, label: $l, content_type: $ct}')
    else
        entry=$(jq -n --arg k "$key" --arg v "$value" --arg l "$LABEL" \
            '{key: $k, value: $v, label: $l}')
    fi
    
    # Append to import file
    jq --argjson new "$entry" '. += [$new]' "$IMPORT_FILE" > "${IMPORT_FILE}.tmp" && mv "${IMPORT_FILE}.tmp" "$IMPORT_FILE"
}

# Helper to add Key Vault reference
add_kv_ref() {
    local key="$1" secret_name="$2"
    local kv_uri
    kv_uri=$(azd env get-value AZURE_KEY_VAULT_ENDPOINT 2>/dev/null || echo "")
    
    [[ -z "$kv_uri" ]] && return 0
    
    local ref_value="{\"uri\":\"${kv_uri}secrets/${secret_name}\"}"
    add_kv "$key" "$ref_value" "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
}

# Helper to get azd env value
get_azd_value() {
    azd env get-value "$1" 2>/dev/null || echo ""
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
info "Config: $CONFIG_FILE"
[[ "$DRY_RUN" == "true" ]] && warn "DRY RUN - no changes will be made"
echo "├─────────────────────────────────────────────────────────────"

# ============================================================================
# SECTION 1: Infrastructure Keys from azd env
# ============================================================================
log ""
log "Collecting infrastructure keys from azd env..."

# Azure OpenAI
add_kv "azure/openai/endpoint" "$(get_azd_value AZURE_OPENAI_ENDPOINT)"
add_kv "azure/openai/deployment-id" "$(get_azd_value AZURE_OPENAI_CHAT_DEPLOYMENT_ID)"
add_kv "azure/openai/api-version" "$(get_azd_value AZURE_OPENAI_API_VERSION)"

# Azure Speech
add_kv "azure/speech/endpoint" "$(get_azd_value AZURE_SPEECH_ENDPOINT)"
add_kv "azure/speech/region" "$(get_azd_value AZURE_SPEECH_REGION)"
add_kv "azure/speech/resource-id" "$(get_azd_value AZURE_SPEECH_RESOURCE_ID)"

# Azure Communication Services
add_kv "azure/acs/endpoint" "$(get_azd_value ACS_ENDPOINT)"
add_kv "azure/acs/immutable-id" "$(get_azd_value ACS_IMMUTABLE_ID)"
add_kv_ref "azure/acs/connection-string" "acs-connection-string"

# Redis
add_kv "azure/redis/hostname" "$(get_azd_value REDIS_HOSTNAME)"
add_kv "azure/redis/port" "$(get_azd_value REDIS_PORT)"

# Cosmos DB
add_kv "azure/cosmos/database-name" "$(get_azd_value AZURE_COSMOS_DATABASE_NAME)"
add_kv "azure/cosmos/collection-name" "$(get_azd_value AZURE_COSMOS_COLLECTION_NAME)"
add_kv "azure/cosmos/connection-string" "$(get_azd_value AZURE_COSMOS_CONNECTION_STRING)"

# Storage
add_kv "azure/storage/account-name" "$(get_azd_value AZURE_STORAGE_ACCOUNT_NAME)"
add_kv "azure/storage/container-url" "$(get_azd_value AZURE_STORAGE_CONTAINER_URL)"

# App Insights
add_kv "azure/appinsights/connection-string" "$(get_azd_value APPLICATIONINSIGHTS_CONNECTION_STRING)"

# Voice Live (optional)
add_kv "azure/voicelive/endpoint" "$(get_azd_value AZURE_VOICELIVE_ENDPOINT)"
add_kv "azure/voicelive/model" "$(get_azd_value AZURE_VOICELIVE_MODEL)"
add_kv "azure/voicelive/resource-id" "$(get_azd_value AZURE_VOICELIVE_RESOURCE_ID)"

# Environment metadata
add_kv "app/environment" "$(get_azd_value AZURE_ENV_NAME)"

log "  ✓ Collected infrastructure keys"

# ============================================================================
# SECTION 2: Application Settings from config/appconfig.json
# ============================================================================
log ""
log "Collecting application settings from config file..."

# Process each section
for section in pools connections session voice aoai warm-pool monitoring; do
    keys=$(jq -r ".[\"$section\"] // {} | keys[]" "$CONFIG_FILE" 2>/dev/null || echo "")
    for key in $keys; do
        value=$(jq -r ".[\"$section\"][\"$key\"]" "$CONFIG_FILE")
        add_kv "app/$section/$key" "$value"
    done
done

log "  ✓ Collected application settings"

# Add sentinel for refresh trigger
add_kv "app/sentinel" "v$(date +%s)"

# ============================================================================
# SECTION 3: Batch Import
# ============================================================================
log ""

count=$(jq 'length' "$IMPORT_FILE")
log "Importing $count settings in batch..."

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY-RUN] Would import:"
    jq -r '.[] | "  \(.key) = \(.value | tostring | .[0:50])"' "$IMPORT_FILE"
else
    # Import settings individually (az appconfig kv import has format issues with nested JSON)
    errors=0
    imported=0
    jq -c '.[]' "$IMPORT_FILE" | while read -r item; do
        key=$(echo "$item" | jq -r '.key')
        value=$(echo "$item" | jq -r '.value')
        label=$(echo "$item" | jq -r '.label // ""')
        ct=$(echo "$item" | jq -r '.content_type // ""')
        
        # Build command args
        cmd_args=(
            --endpoint "$ENDPOINT"
            --key "$key"
            --value "$value"
            --auth-mode login
            --yes
            --output none
        )
        [[ -n "$label" ]] && cmd_args+=(--label "$label")
        [[ -n "$ct" ]] && cmd_args+=(--content-type "$ct")
        
        if output=$(az appconfig kv set "${cmd_args[@]}" 2>&1); then
            imported=$((imported + 1))
        else
            errors=$((errors + 1))
            warn "Failed to set: $key"
            while IFS= read -r line; do
                [[ -n "$line" ]] && warn "  ↳ $line"
            done <<< "$output"
        fi
    done
    
    if [[ $errors -gt 0 ]]; then
        warn "Completed with $errors errors"
    else
        success "Imported $count settings"
    fi
fi

# ============================================================================
# SECTION 4: Feature Flags (must be set individually)
# ============================================================================
log ""
log "Syncing feature flags..."
feature_count=0
features=$(jq -r '.features // {} | keys[]' "$CONFIG_FILE" 2>/dev/null || echo "")

if [[ -n "$features" ]]; then
    for feature in $features; do
        enabled=$(jq -r ".features[\"$feature\"]" "$CONFIG_FILE")
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log "  [DRY-RUN] Would set feature: $feature = $enabled"
            continue
        fi
        
        label_arg=""
        [[ -n "$LABEL" ]] && label_arg="--label $LABEL"
        
        az appconfig feature set \
            --endpoint "$ENDPOINT" \
            --feature "$feature" \
            $label_arg \
            --auth-mode login \
            --yes \
            --output none 2>/dev/null || true
        
        if [[ "$enabled" == "true" ]]; then
            az appconfig feature enable \
                --endpoint "$ENDPOINT" \
                --feature "$feature" \
                $label_arg \
                --auth-mode login \
                --yes \
                --output none 2>/dev/null || true
        else
            az appconfig feature disable \
                --endpoint "$ENDPOINT" \
                --feature "$feature" \
                $label_arg \
                --auth-mode login \
                --yes \
                --output none 2>/dev/null || true
        fi
        
        feature_count=$((feature_count + 1))
        log "  ✓ $feature = $enabled"
    done
    success "Set $feature_count feature flags"
else
    log "  No feature flags defined"
fi

echo "├─────────────────────────────────────────────────────────────"
success "Sync complete: $count settings + $feature_count feature flags"
echo "╰─────────────────────────────────────────────────────────────"
echo ""
