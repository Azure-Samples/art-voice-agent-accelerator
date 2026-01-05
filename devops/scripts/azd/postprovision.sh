#!/bin/bash
# ============================================================================
# 🎯 Azure Developer CLI Post-Provisioning Script
# ============================================================================
# Runs after Terraform provisioning. Handles tasks that CANNOT be in Terraform:
#   1. Cosmos DB initialization (seeding data)
#   2. ACS phone number provisioning
#   3. App Config URL updates (known only after deploy)
#   4. App Config settings sync
#   5. Local development environment setup
#   6. EasyAuth configuration (optional, interactive)
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HELPERS_DIR="$SCRIPT_DIR/helpers"

# ============================================================================
# Logging (unified style - matches preprovision.sh)
# ============================================================================

is_ci() {
    [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" || "${AZD_SKIP_INTERACTIVE:-}" == "true" ]]
}

if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${GREEN_BOLD+x}" ]]; then GREEN_BOLD=$'\033[1;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${CYAN+x}" ]]; then CYAN=$'\033[0;36m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi
readonly BLUE GREEN GREEN_BOLD YELLOW RED CYAN DIM NC

log()          { printf '│ %s%s%s\n' "$DIM" "$*" "$NC"; }
info()         { printf '│ %s%s%s\n' "$BLUE" "$*" "$NC"; }
success()      { printf '│ %s✔%s %s\n' "$GREEN" "$NC" "$*"; }
phase_success(){ printf '│ %s✔ %s%s\n' "$GREEN_BOLD" "$*" "$NC"; }
pending()      { printf '│ %s⏳%s %s\n' "$YELLOW" "$NC" "$*"; }
warn()         { printf '│ %s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()         { printf '│ %s✖%s %s\n' "$RED" "$NC" "$*" >&2; }

header() {
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ ${CYAN}$*${NC}"
    echo "├─────────────────────────────────────────────────────────────"
}

footer() {
    echo "╰─────────────────────────────────────────────────────────────"
    echo ""
}

# ============================================================================
# AZD Environment Helpers
# ============================================================================

azd_get() {
    local key="$1" fallback="${2:-}"
    local val
    val=$(azd env get-value "$key" 2>/dev/null || echo "")
    [[ -z "$val" || "$val" == "null" || "$val" == ERROR* ]] && echo "$fallback" || echo "$val"
}

azd_set() {
    azd env set "$1" "$2" 2>/dev/null || warn "Failed to set $1"
}

# Update or append a single KEY=VALUE in an env file without clobbering other settings.
upsert_env_var() {
    local file="$1" key="$2" value="$3"
    local escaped="$value"
    escaped=${escaped//\\/\\\\}
    escaped=${escaped//&/\\&}
    escaped=${escaped//\//\\/}

    if grep -q "^${key}=" "$file"; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s/^${key}=.*/${key}=${escaped}/" "$file"
        else
            sed -i "s/^${key}=.*/${key}=${escaped}/" "$file"
        fi
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# ============================================================================
# App Configuration Helpers
# ============================================================================

appconfig_set() {
    local endpoint="$1" key="$2" value="$3" label="${4:-}"
    [[ -z "$endpoint" ]] && return 1
    
    local label_arg=""
    [[ -n "$label" ]] && label_arg="--label $label"
    
    az appconfig kv set --endpoint "$endpoint" --key "$key" --value "$value" $label_arg --auth-mode login --yes --output none 2>/dev/null
}

trigger_config_refresh() {
    local endpoint="$1" label="${2:-}"
    appconfig_set "$endpoint" "app/sentinel" "v$(date +%s)" "$label"
}

# ============================================================================
# Task 1: Cosmos DB Initialization
# ============================================================================

# task_cosmos_init() {
#     header "🗄️  Task 1: Cosmos DB Initialization"
    
#     local db_init
#     db_init=$(azd_get "DB_INITIALIZED" "false")
    
#     if [[ "$db_init" == "true" ]]; then
#         info "Already initialized, skipping"
#         footer
#         return 0
#     fi
    
#     local conn_string
#     conn_string=$(azd_get "AZURE_COSMOS_CONNECTION_STRING")
    
#     if [[ -z "$conn_string" ]]; then
#         warn "AZURE_COSMOS_CONNECTION_STRING not set"
#         footer
#         return 1
#     fi
    
#     export AZURE_COSMOS_CONNECTION_STRING="$conn_string"
#     export AZURE_COSMOS_DATABASE_NAME="$(azd_get "AZURE_COSMOS_DATABASE_NAME" "audioagentdb")"
#     export AZURE_COSMOS_COLLECTION_NAME="$(azd_get "AZURE_COSMOS_COLLECTION_NAME" "audioagentcollection")"
    
#     if [[ -f "$HELPERS_DIR/requirements-cosmos.txt" ]]; then
#         log "Installing Python dependencies..."
#         pip3 install -q -r "$HELPERS_DIR/requirements-cosmos.txt" 2>/dev/null || true
#     fi
    
#     log "Running initialization script..."
#     if python3 "$HELPERS_DIR/cosmos_init.py" 2>/dev/null; then
#         success "Cosmos DB initialized"
#         azd_set "DB_INITIALIZED" "true"
#     else
#         fail "Initialization failed"
#     fi
    
#     footer
# }

# ============================================================================
# Task 2: ACS Phone Number Configuration
# ============================================================================

task_phone_number() {
    header "📞 Task 2: Phone Number Configuration"
    
    local endpoint label
    endpoint=$(azd_get "AZURE_APPCONFIG_ENDPOINT")
    label=$(azd_get "AZURE_ENV_NAME")
    
    # Check if already configured
    if [[ -n "$endpoint" ]]; then
        local existing
        existing=$(az appconfig kv show --endpoint "$endpoint" --key "azure/acs/source-phone-number" --label "$label" --query "value" -o tsv 2>/dev/null || echo "")
        if [[ "$existing" =~ ^\+[0-9]{10,15}$ ]]; then
            success "Already configured: $existing"
            footer
            return 0
        fi
    fi
    
    # Check azd env (legacy)
    local phone
    phone=$(azd_get "ACS_SOURCE_PHONE_NUMBER")
    if [[ "$phone" =~ ^\+[0-9]{10,15}$ ]]; then
        info "Migrating from azd env to App Config..."
        appconfig_set "$endpoint" "azure/acs/source-phone-number" "$phone" "$label"
        trigger_config_refresh "$endpoint" "$label"
        success "Phone configured: $phone"
        footer
        return 0
    fi
    
    if is_ci; then
        if [[ -n "${ACS_SOURCE_PHONE_NUMBER:-}" && "$ACS_SOURCE_PHONE_NUMBER" =~ ^\+[0-9]{10,15}$ ]]; then
            appconfig_set "$endpoint" "azure/acs/source-phone-number" "$ACS_SOURCE_PHONE_NUMBER" "$label"
            azd_set "ACS_SOURCE_PHONE_NUMBER" "$ACS_SOURCE_PHONE_NUMBER"
            trigger_config_refresh "$endpoint" "$label"
            success "Phone set from environment"
        else
            warn "No phone configured (set ACS_SOURCE_PHONE_NUMBER env var)"
        fi
        footer
        return 0
    fi
    
    # Interactive mode
    log ""
    log "A phone number is required for voice calls."
    log "You must provision a phone number manually via Azure Portal first."
    log ""
    log "  1) Enter existing phone number (must be provisioned in Azure Portal)"
    log "  2) Skip for now (configure later)"
    log ""
    log "(Auto-skipping in 10 seconds if no input...)"
    
    if read -t 10 -rp "│ Choice (1-2): " choice; then
        : # Got input
    else
        log ""
        info "No input received, skipping phone configuration"
        choice="2"
    fi
    
    case "$choice" in
        1)
            log ""
            log "To get a phone number:"
            log "  1. Azure Portal → Communication Services → Phone numbers → + Get"
            log "  2. Select country/region and number type (toll-free or geographic)"
            log "  3. Complete the purchase and copy the number"
            log ""
            read -rp "│ Phone (E.164 format, e.g. +18001234567): " phone
            if [[ "$phone" =~ ^\+[0-9]{10,15}$ ]]; then
                appconfig_set "$endpoint" "azure/acs/source-phone-number" "$phone" "$label"
                azd_set "ACS_SOURCE_PHONE_NUMBER" "$phone"
                trigger_config_refresh "$endpoint" "$label"
                success "Phone saved: $phone"
            else
                fail "Invalid format. Phone must be in E.164 format (e.g., +18001234567)"
            fi
            ;;
        *)
            info "Skipped - configure later via Azure Portal"
            log ""
            log "To configure manually:"
            log "  1. Azure Portal → Communication Services → Phone numbers → + Get"
            log "  2. Purchase a phone number for your region"
            log "  3. Set the phone number using one of these methods:"
            log ""
            log "  Option A - Using azd (will sync on next provision):"
            log "    azd env set ACS_SOURCE_PHONE_NUMBER '+1XXXXXXXXXX'"
            log "    azd provision"
            log ""
            log "  Option B - Direct App Config update (immediate):"
            log "    az appconfig kv set \\"
            log "      --endpoint \"$endpoint\" \\"
            log "      --key \"azure/acs/source-phone-number\" \\"
            log "      --value \"+1XXXXXXXXXX\" \\"
            log "      --label \"$label\" \\"
            log "      --auth-mode login --yes"
            ;;
    esac
    
    footer
}

# ============================================================================
# Task 3: App Configuration URL Updates
# ============================================================================

task_update_urls() {
    header "🌐 Task 3: App Configuration URL Updates"
    
    local endpoint label backend_url
    endpoint=$(azd_get "AZURE_APPCONFIG_ENDPOINT")
    label=$(azd_get "AZURE_ENV_NAME")
    
    if [[ -z "$endpoint" ]]; then
        warn "App Config endpoint not available"
        footer
        return 1
    fi
    
    # Determine backend URL
    backend_url=$(azd_get "BACKEND_API_URL")
    [[ -z "$backend_url" ]] && backend_url=$(azd_get "BACKEND_CONTAINER_APP_URL")
    if [[ -z "$backend_url" ]]; then
        local fqdn
        fqdn=$(azd_get "BACKEND_CONTAINER_APP_FQDN")
        [[ -n "$fqdn" ]] && backend_url="https://${fqdn}"
    fi
    
    if [[ -z "$backend_url" ]]; then
        warn "Could not determine backend URL"
        footer
        return 1
    fi
    
    local ws_url="${backend_url/https:\/\//wss://}"
    ws_url="${ws_url/http:\/\//ws://}"
    
    info "Backend: $backend_url"
    info "WebSocket: $ws_url"
    
    local count=0
    appconfig_set "$endpoint" "app/backend/base-url" "$backend_url" "$label" && ((count++)) || true
    appconfig_set "$endpoint" "app/frontend/backend-url" "$backend_url" "$label" && ((count++)) || true
    appconfig_set "$endpoint" "app/frontend/ws-url" "$ws_url" "$label" && ((count++)) || true
    
    if [[ $count -eq 3 ]]; then
        trigger_config_refresh "$endpoint" "$label"
        success "All URLs updated ($count/3)"
    else
        warn "Some updates failed ($count/3)"
    fi
    
    footer
}

# ============================================================================
# Summary
# ============================================================================

show_summary() {
    header "📋 Summary"
    
    local db_init phone endpoint env_file easyauth_enabled
    db_init=$(azd_get "DB_INITIALIZED" "false")
    phone=$(azd_get "ACS_SOURCE_PHONE_NUMBER" "")
    endpoint=$(azd_get "AZURE_APPCONFIG_ENDPOINT" "")
    easyauth_enabled=$(azd_get "EASYAUTH_ENABLED" "false")
    env_file=".env.local"
    
    [[ "$db_init" == "true" ]] && success "Cosmos DB: initialized" || pending "Cosmos DB: pending"
    [[ -n "$phone" ]] && success "Phone: $phone" || pending "Phone: not configured"
    [[ -n "$endpoint" ]] && success "App Config: $endpoint" || pending "App Config: pending"
    [[ -f "$env_file" ]] && success "Local env: $env_file" || pending "Local env: not generated"
    [[ "$easyauth_enabled" == "true" ]] && success "EasyAuth: enabled" || pending "EasyAuth: not enabled"
    
    if ! is_ci; then
        log ""
        log "Next steps:"
        log "  • Verify: azd show"
        log "  • Health check: curl \$(azd env get-value BACKEND_CONTAINER_APP_URL)/api/v1/health"
        [[ -z "$phone" ]] && log "  • Configure phone: Azure Portal → ACS → Phone numbers"
        [[ "$easyauth_enabled" != "true" ]] && log "  • Enable EasyAuth: ./devops/scripts/azd/helpers/enable-easyauth.sh"
    fi
    
    footer
    phase_success "Post-provisioning complete!"
}

# ============================================================================
# Task 4: Sync App Configuration Settings
# ============================================================================

task_sync_appconfig() {
    header "📦 Task 4: App Configuration Settings"
    
    local sync_script="$HELPERS_DIR/sync-appconfig.sh"
    local config_file="$SCRIPT_DIR/../../../config/appconfig.json"
    
    if [[ ! -f "$sync_script" ]]; then
        warn "sync-appconfig.sh not found, skipping"
        footer
        return 0
    fi
    
    if [[ ! -f "$config_file" ]]; then
        warn "config/appconfig.json not found, skipping"
        footer
        return 0
    fi
    
    local endpoint label
    endpoint=$(azd_get "AZURE_APPCONFIG_ENDPOINT")
    label=$(azd_get "AZURE_ENV_NAME")
    
    if [[ -z "$endpoint" ]]; then
        warn "App Config endpoint not available yet"
        footer
        return 1
    fi
    
    log "Syncing app settings from config/appconfig.json..."
    if AZD_LOG_IN_BOX=true bash "$sync_script" --endpoint "$endpoint" --label "$label" --config "$config_file"; then
        success "App settings synced"
    else
        warn "Some settings may have failed"
    fi
    
    footer
}

# ============================================================================
# Task 5: Generate Local Development Environment File
# ============================================================================

task_generate_env_local() {
    header "🧑‍💻 Task 5: Local Development Environment"
    
    local setup_script="$HELPERS_DIR/local-dev-setup.sh"
    local env_file=".env.local"
    
    if [[ ! -f "$setup_script" ]]; then
        warn "local-dev-setup.sh not found, skipping"
        footer
        return 0
    fi
    
    # Source the helper to use its functions
    source "$setup_script"
    
    local appconfig_endpoint env_label
    appconfig_endpoint=$(azd_get "AZURE_APPCONFIG_ENDPOINT")
    env_label=$(azd_get "AZURE_ENV_NAME")
    
    if [[ -z "$appconfig_endpoint" ]]; then
        warn "App Config endpoint not available, cannot generate .env.local"
        footer
        return 1
    fi
    
    if [[ -f "$env_file" ]]; then
        if is_ci; then
            info "Existing .env.local found (CI mode) - updating App Config settings only"
            upsert_env_var "$env_file" "AZURE_APPCONFIG_ENDPOINT" "$appconfig_endpoint"
            [[ -n "$env_label" ]] && upsert_env_var "$env_file" "AZURE_APPCONFIG_LABEL" "$env_label"
            success "Updated App Config settings in .env.local"
        else
            log "Existing .env.local found. Update App Config settings only?"
            if read -r -p "│ Update AZURE_APPCONFIG_* in .env.local? [Y/n]: " choice; then
                : # Got input
            else
                choice="n"
            fi
            if [[ -z "$choice" || "$choice" =~ ^[Yy]$ ]]; then
                upsert_env_var "$env_file" "AZURE_APPCONFIG_ENDPOINT" "$appconfig_endpoint"
                [[ -n "$env_label" ]] && upsert_env_var "$env_file" "AZURE_APPCONFIG_LABEL" "$env_label"
                success "Updated App Config settings in .env.local"
            else
                info "Skipped .env.local update"
            fi
        fi
    else
        log "Generating .env.local for local development..."
        local prior_log_in_box="${AZD_LOG_IN_BOX:-false}"
        AZD_LOG_IN_BOX=true
        if generate_minimal_env "$env_file"; then
            success ".env.local created"
        else
            warn "Failed to generate .env.local"
        fi
        AZD_LOG_IN_BOX="$prior_log_in_box"
    fi
    
    footer
}

# ============================================================================
# Task 6: Enable EasyAuth (Optional)
# ============================================================================

task_enable_easyauth() {
    header "🔐 Task 6: Frontend Authentication (EasyAuth)"
    
    local easyauth_script="$HELPERS_DIR/enable-easyauth.sh"
    
    if [[ ! -f "$easyauth_script" ]]; then
        warn "enable-easyauth.sh not found, skipping"
        footer
        return 0
    fi
    
    # Check if EasyAuth was already enabled (via azd env)
    local easyauth_configured
    easyauth_configured=$(azd_get "EASYAUTH_ENABLED" "false")
    
    if [[ "$easyauth_configured" == "true" ]]; then
        success "EasyAuth already configured (EASYAUTH_ENABLED=true)"
        footer
        return 0
    fi
    
    local resource_group container_app uami_client_id
    resource_group=$(azd_get "AZURE_RESOURCE_GROUP")
    container_app=$(azd_get "FRONTEND_CONTAINER_APP_NAME")
    uami_client_id=$(azd_get "FRONTEND_UAI_CLIENT_ID")
    
    if [[ -z "$resource_group" || -z "$container_app" || -z "$uami_client_id" ]]; then
        warn "Missing required values for EasyAuth configuration"
        [[ -z "$resource_group" ]] && warn "  - AZURE_RESOURCE_GROUP not set"
        [[ -z "$container_app" ]] && warn "  - FRONTEND_CONTAINER_APP_NAME not set"
        [[ -z "$uami_client_id" ]] && warn "  - FRONTEND_UAI_CLIENT_ID not set"
        footer
        return 1
    fi
    
    if is_ci; then
        # In CI mode, automatically enable EasyAuth if not already enabled
        log "Enabling EasyAuth (CI mode)…"
        if AZD_LOG_IN_BOX=true bash "$easyauth_script" -g "$resource_group" -a "$container_app" -i "$uami_client_id"; then
            success "EasyAuth enabled"
            # Set azd env variable to prevent re-running
            azd_set "EASYAUTH_ENABLED" "true"
            # Output to GitHub Actions environment (if running in GitHub Actions)
            if [[ -n "${GITHUB_ENV:-}" ]]; then
                echo "EASYAUTH_ENABLED=true" >> "$GITHUB_ENV"
                info "Set EASYAUTH_ENABLED=true in GitHub Actions environment"
            fi
        else
            warn "Failed to enable EasyAuth"
        fi
        footer
        return 0
    fi
    # Interactive mode
    log ""
    log "EasyAuth adds Microsoft Entra ID authentication to your frontend."
    log "Users will need to sign in with their organizational account."
    log ""
    log "Benefits:"
    log "  • Secure access with Microsoft Entra ID"
    log "  • No secrets to manage (uses Federated Identity Credentials)"
    log "  • Works with your organization's identity policies"
    log ""
    log "Note: The backend API remains unsecured (accessible within your network)."
    log ""
    log "  1) Enable EasyAuth now"
    log "  2) Skip for now (can enable later)"
    log ""
    log "(Auto-skipping in 15 seconds if no input...)"
    
    if read -t 15 -rp "│ Choice (1-2): " choice; then
        : # Got input
    else
        log ""
        info "No input received, skipping EasyAuth configuration"
        choice="2"
    fi
    
    case "$choice" in
        1)
            log ""
            log "Enabling EasyAuth..."
            if AZD_LOG_IN_BOX=true bash "$easyauth_script" -g "$resource_group" -a "$container_app" -i "$uami_client_id"; then
                success "EasyAuth enabled successfully"
                # Set azd env variable to prevent re-running
                azd_set "EASYAUTH_ENABLED" "true"
                log ""
                log "Your frontend now requires authentication."
                log "Users will be redirected to Microsoft login."
            else
                fail "Failed to enable EasyAuth"
            fi
            ;;
        *)
            info "Skipped - you can enable EasyAuth later by running:"
            log ""
            log "  ./devops/scripts/azd/helpers/enable-easyauth.sh \\"
            log "    -g \"$resource_group\" \\"
            log "    -a \"$container_app\" \\"
            log "    -i \"$uami_client_id\""
            ;;
    esac
    
    footer
}

# ============================================================================
# Main
# ============================================================================

main() {
    header "🚀 Post-Provisioning"
    is_ci && info "CI/CD mode" || info "Interactive mode"
    footer
    
    # task_cosmos_init || true
    task_phone_number || true
    task_update_urls || true
    task_sync_appconfig || true
    task_generate_env_local || true
    task_enable_easyauth || true
    show_summary
}

main "$@"
