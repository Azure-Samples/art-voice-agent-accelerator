#!/bin/bash
# ============================================================================
# 🔗 Azure Developer CLI Pre-Down Script
# ============================================================================
# Runs before azd down. Ensures ACS email domains are unlinked from the
# Communication Service so Terraform can delete AzureManagedDomain resources.
# ============================================================================

set -euo pipefail

if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${CYAN+x}" ]]; then CYAN=$'\033[0;36m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi
readonly BLUE GREEN YELLOW RED CYAN DIM NC

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

azd_get() {
    local key="$1" fallback="${2:-}"
    local val
    val=$(azd env get-value "$key" 2>/dev/null | head -n1 || echo "")
    [[ -z "$val" || "$val" == "null" || "$val" == ERROR* || "$val" == *"not found"* ]] && echo "$fallback" || echo "$val"
}

main() {
    header "🔗 Pre-Down ACS Email Domain Unlink"

    if ! command -v az >/dev/null 2>&1; then
        warn "Azure CLI (az) not found. Skipping ACS unlink precheck."
        footer
        return 0
    fi

    if ! command -v azd >/dev/null 2>&1; then
        warn "Azure Developer CLI (azd) not found. Skipping ACS unlink precheck."
        footer
        return 0
    fi

    if ! az account show &>/dev/null; then
        warn "Not logged in to Azure. Skipping ACS unlink precheck."
        footer
        return 0
    fi

    local acs_resource_id
    acs_resource_id=$(azd_get "ACS_RESOURCE_ID" "")

    if [[ -z "$acs_resource_id" ]]; then
        info "ACS_RESOURCE_ID not set in azd environment. Nothing to unlink."
        footer
        return 0
    fi

    local acs_uri
    acs_uri="https://management.azure.com${acs_resource_id}?api-version=2025-05-01-preview"

    local linked_domains
    linked_domains=$(az rest --method GET --uri "$acs_uri" --query "properties.linkedDomains" -o json 2>/dev/null || echo "[]")

    if [[ "$linked_domains" == "[]" || "$linked_domains" == "null" ]]; then
        info "ACS has no linked email domains."
        footer
        return 0
    fi

    log "Found linked email domains on ACS: $linked_domains"
    log "Unlinking domains before terraform destroy..."

    if az rest \
        --method PATCH \
        --uri "$acs_uri" \
        --body '{"properties":{"linkedDomains":[]}}' \
        --only-show-errors >/dev/null; then
        success "Successfully unlinked ACS email domains."
    else
        fail "Failed to unlink ACS email domains."
        fail "Run this manually, then retry 'azd down --purge --force':"
        fail "  az rest --method PATCH --uri \"$acs_uri\" --body '{\"properties\":{\"linkedDomains\":[]}}'"
        exit 1
    fi

    footer
}

main "$@"