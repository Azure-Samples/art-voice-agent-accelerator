#!/bin/bash
# ============================================================================
# 🧹 Azure Developer CLI Post-Down Script
# ============================================================================
# Runs after azd down. Optionally deletes Terraform remote state storage.
# Also reminds users about azd down --purge for redeployments.
# ============================================================================

set -euo pipefail

# ============================================================================
# Logging (unified style - matches preprovision/postprovision)
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

log()     { printf '│ %s%s%s\n' "$DIM" "$*" "$NC"; }
info()    { printf '│ %s%s%s\n' "$BLUE" "$*" "$NC"; }
success() { printf '│ %s✔%s %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '│ %s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()    { printf '│ %s✖%s %s\n' "$RED" "$NC" "$*" >&2; }

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

finish() {
    log ""
    warn "Redeploying Foundry resources?"
    warn "Use 'azd down --purge' to remove soft-deleted resources before redeploy."
    footer
}

azd_get() {
    local key="$1" fallback="${2:-}"
    local val
    val=$(azd env get-value "$key" 2>/dev/null | head -n1 || echo "")
    [[ -z "$val" || "$val" == "null" || "$val" == ERROR* || "$val" == *"not found"* ]] && echo "$fallback" || echo "$val"
}

azd_set() {
    azd env set "$1" "$2" 2>/dev/null || warn "Failed to set $1"
}

storage_exists() {
    local account="$1" rg="$2"
    az storage account show --name "$account" --resource-group "$rg" --query "provisioningState" -o tsv 2>/dev/null | grep -q "^Succeeded$"
}

main() {
    header "🧹 Post-Down Cleanup"

    local local_state
    local_state=$(azd_get "LOCAL_STATE")
    if [[ "$local_state" == "true" ]]; then
        info "LOCAL_STATE=true - no remote state storage to delete."
        finish
        return 0
    fi

    local storage_account resource_group container
    storage_account=$(azd_get "RS_STORAGE_ACCOUNT")
    resource_group=$(azd_get "RS_RESOURCE_GROUP")
    container=$(azd_get "RS_CONTAINER_NAME")

    if [[ -z "$storage_account" || -z "$resource_group" ]]; then
        info "Remote state is not configured (RS_* missing). Nothing to delete."
        finish
        return 0
    fi

    if ! command -v az >/dev/null 2>&1; then
        warn "Azure CLI (az) not found; skipping remote state deletion."
        finish
        return 0
    fi

    if ! az account show &>/dev/null; then
        warn "Not logged in to Azure. Run 'az login' to delete remote state later."
        finish
        return 0
    fi

    if ! storage_exists "$storage_account" "$resource_group"; then
        warn "Storage account not found: $storage_account (rg: $resource_group)."
        finish
        return 0
    fi

    log "Remote state storage detected:"
    log "   Resource Group:  $resource_group"
    log "   Storage Account: $storage_account"
    [[ -n "$container" ]] && log "   Container:       $container"
    log ""

    local delete_state="${AZD_DOWN_DELETE_STATE:-}"
    local choice="n"

    if is_ci; then
        if echo "$delete_state" | grep -Eiq '^(1|true|yes)$'; then
            choice="y"
            info "CI mode: AZD_DOWN_DELETE_STATE=true - deleting remote state."
        else
            info "CI/non-interactive: skipping remote state deletion."
            info "Set AZD_DOWN_DELETE_STATE=true to delete automatically."
            finish
            return 0
        fi
    else
        local input_timeout="${AZD_INPUT_TIMEOUT:-30}"
        if ! read -r -t "$input_timeout" -p "│ Delete remote state storage account? This is permanent. [y/N]: " choice; then
            info "No input received after ${input_timeout}s. Keeping remote state storage account."
            choice="n"
        fi
    fi

    if echo "$choice" | grep -Eiq '^(y|yes)$'; then
        log "Deleting storage account..."
        az storage account delete \
            --name "$storage_account" \
            --resource-group "$resource_group" \
            --yes \
            --output none
        success "Remote state storage account deleted."

        # Clear RS_* values so future azd up can recreate remote state cleanly.
        azd_set "RS_STORAGE_ACCOUNT" ""
        azd_set "RS_CONTAINER_NAME" ""
        azd_set "RS_RESOURCE_GROUP" ""
        azd_set "RS_STATE_KEY" ""
        success "Cleared RS_* values in azd environment."
    else
        info "Keeping remote state storage account."
        info "If you want to delete later, run:"
        info "  az storage account delete --name $storage_account --resource-group $resource_group --yes"
    fi

    finish
}

main "$@"
