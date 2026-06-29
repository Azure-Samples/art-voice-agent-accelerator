#!/bin/bash
# ============================================================================
# 🌐 Make azd-deployed resources publicly accessible
# ============================================================================
# Flips the data-plane network exposure of resources provisioned by `azd up`
# from Private -> Public (publicNetworkAccess = Enabled, defaultAction = Allow).
#
# Intended for development / demo environments where private endpoints or
# network ACLs were applied and you need quick public access again (e.g. to
# seed Cosmos DB, push images, or reach Key Vault from a laptop).
#
# ⚠️  DO NOT run against production. Opening data planes to the public internet
#     removes a key network control. This is a convenience, not a best practice.
#
# Usage:
#   ./make-resources-public.sh [options]
#
# Options:
#   -g, --resource-group <name>   Target resource group (default: from azd env
#                                 AZURE_RESOURCE_GROUP).
#   --subscription <id>           Subscription id (default: selected azd env,
#                                 then current az context).
#   --skip-remote-state           Do not include the azd Terraform state storage
#                                 account recorded in the selected azd env.
#   --dry-run                     Print what would change without applying.
#   -j, --max-jobs <n>            Max parallel az updates (default: 10).
#   -y, --yes                     Skip the confirmation prompt.
#   -h, --help                    Show this help.
#
# Resolution order for the resource group:
#   1. --resource-group flag
#   2. AZURE_RESOURCE_GROUP environment variable
#   3. `azd env get-value AZURE_RESOURCE_GROUP`
#
# Remote Terraform state is included by default when the selected azd env has
# RS_RESOURCE_GROUP and RS_STORAGE_ACCOUNT configured and LOCAL_STATE != true.
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${CYAN+x}" ]]; then CYAN=$'\033[0;36m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi

info()    { printf '%s%s%s\n' "$BLUE" "$*" "$NC"; }
success() { printf '%s✔%s %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()    { printf '%s✖%s %s\n' "$RED" "$NC" "$*" >&2; }
step()    { printf '%s→%s %s\n' "$CYAN" "$NC" "$*"; }
dim()     { printf '%s%s%s\n' "$DIM" "$*" "$NC"; }

header() {
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ ${CYAN}$*${NC}"
    echo "╰─────────────────────────────────────────────────────────────"
}

# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------
RESOURCE_GROUP=""
SUBSCRIPTION=""
DRY_RUN=false
ASSUME_YES=false
MAX_JOBS=10
INCLUDE_REMOTE_STATE=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        -g|--resource-group) RESOURCE_GROUP="${2:-}"; shift 2 ;;
        --subscription)      SUBSCRIPTION="${2:-}"; shift 2 ;;
        --skip-remote-state) INCLUDE_REMOTE_STATE=false; shift ;;
        --dry-run)           DRY_RUN=true; shift ;;
        -j|--max-jobs)       MAX_JOBS="${2:-10}"; shift 2 ;;
        -y|--yes)            ASSUME_YES=true; shift ;;
        -h|--help)           sed -n '2,42p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "Unknown argument: $1"; exit 1 ;;
    esac
done

[[ "$MAX_JOBS" =~ ^[0-9]+$ && "$MAX_JOBS" -ge 1 ]] || { fail "--max-jobs must be a positive integer."; exit 1; }

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------
command -v az >/dev/null 2>&1 || { fail "Azure CLI (az) is required but not installed."; exit 1; }

get_azd_env() {
    local line output value=""
    command -v azd >/dev/null 2>&1 || { echo ""; return 0; }
    if ! output=$(azd env get-value "$1" 2>/dev/null); then
        echo ""
        return 0
    fi
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        [[ "$line" == "Update available:"* ]] && continue
        [[ "$line" == "To update,"* ]] && continue
        value="$line"
        break
    done <<< "$output"
    if [[ -z "$value" ]] || [[ "$value" == "null" ]] || [[ "$value" == ERROR* ]] || [[ "$value" == *"not found"* ]]; then
        echo ""
    else
        echo "$value"
    fi
}

if [[ -z "$RESOURCE_GROUP" ]]; then
    RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
fi
if [[ -z "$RESOURCE_GROUP" ]]; then
    RESOURCE_GROUP="$(get_azd_env AZURE_RESOURCE_GROUP)"
fi
if [[ -z "$RESOURCE_GROUP" ]]; then
    fail "Could not resolve a resource group. Pass --resource-group or set AZURE_RESOURCE_GROUP."
    exit 1
fi

if [[ -z "$SUBSCRIPTION" ]]; then
    SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:-}"
fi
if [[ -z "$SUBSCRIPTION" ]]; then
    SUBSCRIPTION="$(get_azd_env AZURE_SUBSCRIPTION_ID)"
fi

AZ_SUB_ARGS=()
[[ -n "$SUBSCRIPTION" ]] && AZ_SUB_ARGS=(--subscription "$SUBSCRIPTION")

APP_RESOURCE_GROUP_EXISTS=true
if ! az group show "${AZ_SUB_ARGS[@]}" --name "$RESOURCE_GROUP" --output none 2>/dev/null; then
    APP_RESOURCE_GROUP_EXISTS=false
fi

REMOTE_STATE_ID=""
REMOTE_STATE_TYPE="Microsoft.Storage/storageAccounts"
REMOTE_STATE_LABEL=""

resolve_remote_state_storage() {
    $INCLUDE_REMOTE_STATE || return 0

    local local_state="${LOCAL_STATE:-}"
    [[ -z "$local_state" ]] && local_state="$(get_azd_env LOCAL_STATE)"
    if [[ "$local_state" == "true" ]]; then
        dim "Terraform remote state: skipped (LOCAL_STATE=true)."
        return 0
    fi

    local env_name="${AZURE_ENV_NAME:-}"
    [[ -z "$env_name" ]] && env_name="$(get_azd_env AZURE_ENV_NAME)"

    local rs_resource_group="${RS_RESOURCE_GROUP:-}"
    local rs_storage_account="${RS_STORAGE_ACCOUNT:-}"
    local rs_container_name="${RS_CONTAINER_NAME:-}"
    local rs_state_key="${RS_STATE_KEY:-}"
    [[ -z "$rs_resource_group" ]] && rs_resource_group="$(get_azd_env RS_RESOURCE_GROUP)"
    [[ -z "$rs_storage_account" ]] && rs_storage_account="$(get_azd_env RS_STORAGE_ACCOUNT)"
    [[ -z "$rs_container_name" ]] && rs_container_name="$(get_azd_env RS_CONTAINER_NAME)"
    [[ -z "$rs_state_key" ]] && rs_state_key="$(get_azd_env RS_STATE_KEY)"
    [[ -z "$rs_state_key" && -n "$env_name" ]] && rs_state_key="$env_name.tfstate"

    if [[ -z "$rs_resource_group" || -z "$rs_storage_account" ]]; then
        warn "Terraform remote state not found in the selected azd env; app resource group only."
        return 0
    fi

    local storage_id
    storage_id=$(az storage account show "${AZ_SUB_ARGS[@]}" \
        --name "$rs_storage_account" \
        --resource-group "$rs_resource_group" \
        --query id -o tsv 2>/dev/null || true)

    if [[ -z "$storage_id" ]]; then
        warn "Terraform remote state storage account '$rs_storage_account' not found in '$rs_resource_group'; skipping it."
        return 0
    fi

    REMOTE_STATE_ID="$storage_id"
    REMOTE_STATE_LABEL="$rs_storage_account in $rs_resource_group"
    [[ -n "$rs_container_name" || -n "$rs_state_key" ]] && \
        REMOTE_STATE_LABEL+=" (${rs_container_name:-?}/${rs_state_key:-?})"
}

resolve_remote_state_storage

if ! $APP_RESOURCE_GROUP_EXISTS && [[ -z "$REMOTE_STATE_ID" ]]; then
    fail "Resource group '$RESOURCE_GROUP' not found and no remote Terraform state storage was resolved."
    exit 1
fi

header "🌐 Make resources public — $RESOURCE_GROUP"
$DRY_RUN && warn "DRY RUN — no changes will be applied."
! $APP_RESOURCE_GROUP_EXISTS && warn "App resource group '$RESOURCE_GROUP' not found; app resources will be skipped."
[[ -n "$REMOTE_STATE_LABEL" ]] && dim "Includes Terraform remote state: $REMOTE_STATE_LABEL"

if ! $DRY_RUN && ! $ASSUME_YES; then
    warn "This opens data-plane network access to the public internet for the target resources."
    read -r -p "Continue? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
fi

# ----------------------------------------------------------------------------
# Parallel execution scaffolding
# ----------------------------------------------------------------------------
# Per-job results land here as TSV lines: <status>\t<name>\t<detail>
# Short single-printf appends are atomic on POSIX, so parallel workers are safe.
RESULT_DIR="$(mktemp -d)"
RESULTS="$RESULT_DIR/results.tsv"
RESOURCES="$RESULT_DIR/resources.tsv"
: > "$RESULTS"
trap 'rm -rf "$RESULT_DIR"' EXIT

# Resource types we know how to open, and the parallel discovery that finds them.
SUPPORTED_TYPES=(
    "Microsoft.CognitiveServices/accounts"
    "Microsoft.DocumentDB/databaseAccounts"
    "Microsoft.Storage/storageAccounts"
    "Microsoft.KeyVault/vaults"
    "Microsoft.AppConfiguration/configurationStores"
    "Microsoft.Cache/Redis"
    "Microsoft.Cache/redisEnterprise"
    "Microsoft.ContainerRegistry/registries"
    "Microsoft.Search/searchServices"
)

is_supported() {
    local t
    for t in "${SUPPORTED_TYPES[@]}"; do [[ "$1" == "$t" ]] && return 0; done
    return 1
}

# Block until a worker slot frees up (bash 3.2 compatible — no `wait -n`).
wait_for_slot() {
    while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do
        sleep 0.2
    done
}

emit() { printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" >> "$RESULTS"; }

# Open a single resource's data plane. Runs inside a background job; emits one
# result line. Type-specific where needed, generic publicNetworkAccess otherwise.
flip_one() {
    local type="$1" id="$2" name="${id##*/}"

    if $DRY_RUN; then emit DRY "$name" "$type"; return 0; fi

    case "$type" in
        Microsoft.DocumentDB/databaseAccounts)
            if az cosmosdb update "${AZ_SUB_ARGS[@]}" --ids "$id" \
                    --public-network-access ENABLED --output none 2>/dev/null; then
                emit OK "$name"
            else
                emit SKIP "$name" "$type"
            fi
            ;;
        Microsoft.ContainerRegistry/registries)
            if az acr update "${AZ_SUB_ARGS[@]}" --ids "$id" \
                    --public-network-enabled true --output none 2>/dev/null; then
                az acr update "${AZ_SUB_ARGS[@]}" --ids "$id" \
                    --default-action Allow --output none 2>/dev/null || true
                emit OK "$name"
            else
                emit SKIP "$name" "$type"
            fi
            ;;
        *)
            # Primary, universal control: publicNetworkAccess=Enabled.
            if az resource update "${AZ_SUB_ARGS[@]}" --ids "$id" \
                    --set properties.publicNetworkAccess=Enabled --output none 2>/dev/null; then
                local detail=""
                # Best-effort: relax network-ACL default action where it exists.
                case "$type" in
                    Microsoft.CognitiveServices/accounts|Microsoft.Storage/storageAccounts|Microsoft.KeyVault/vaults)
                        if az resource update "${AZ_SUB_ARGS[@]}" --ids "$id" \
                                --set properties.networkAcls.defaultAction=Allow \
                                --output none 2>/dev/null; then
                            detail="acl=Allow"
                        fi
                        ;;
                esac
                emit OK "$name" "$detail"
            else
                emit SKIP "$name" "$type"
            fi
            ;;
    esac
}

# ----------------------------------------------------------------------------
# Execute
# ----------------------------------------------------------------------------
step "Discovering app resources in $RESOURCE_GROUP ..."

DISPATCHED=0
# Single discovery query for the app resource group, plus the selected azd env's
# remote Terraform state storage account when it lives outside that group.
: > "$RESOURCES"
if $APP_RESOURCE_GROUP_EXISTS; then
    if ! az resource list "${AZ_SUB_ARGS[@]}" \
            --resource-group "$RESOURCE_GROUP" \
            --query "[].[id, type]" -o tsv 2>/dev/null > "$RESOURCES"; then
        fail "Could not list resources in '$RESOURCE_GROUP' (check subscription / az login)."
        exit 1
    fi
fi

if [[ -n "$REMOTE_STATE_ID" ]] && ! awk -F '\t' -v id="$REMOTE_STATE_ID" '$1 == id { found=1 } END { exit !found }' "$RESOURCES"; then
    printf '%s\t%s\n' "$REMOTE_STATE_ID" "$REMOTE_STATE_TYPE" >> "$RESOURCES"
fi

# Fan out updates.
while IFS=$'\t' read -r id rtype; do
    [[ -z "$id" ]] && continue
    is_supported "$rtype" || continue
    wait_for_slot
    flip_one "$rtype" "$id" &
    DISPATCHED=$((DISPATCHED + 1))
done < "$RESOURCES"

# Wait for all in-flight updates to complete.
wait

if [[ "$DISPATCHED" -eq 0 ]]; then
    warn "No supported private-capable resources found."
fi

# ----------------------------------------------------------------------------
# Summary (deterministic order regardless of completion order)
# ----------------------------------------------------------------------------
CHANGED=0
SKIPPED=0
echo ""
while IFS=$'\t' read -r st name detail; do
    [[ -z "$st" ]] && continue
    case "$st" in
        OK)   success "$name${detail:+  ($detail)}"; CHANGED=$((CHANGED + 1)) ;;
        DRY)  dim "would enable public access: $name ($detail)" ;;
        SKIP) warn "$name — failed/unsupported, skipped"; SKIPPED=$((SKIPPED + 1)) ;;
    esac
done < <(sort -t$'\t' -k2,2 "$RESULTS")

header "Summary"
if $DRY_RUN; then
    dim "Dry run — $DISPATCHED resource(s) would be updated (max $MAX_JOBS parallel)."
else
    success "Updated: $CHANGED resource(s)  (max $MAX_JOBS parallel)"
    [[ "$SKIPPED" -gt 0 ]] && warn "Skipped: $SKIPPED resource(s)"
fi
echo ""
