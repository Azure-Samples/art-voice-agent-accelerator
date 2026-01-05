#!/bin/bash
# ============================================================================
# ✔ Preflight Checks - Environment & Subscription Validation
# ============================================================================
# Validates the user's environment before provisioning:
#   - Required CLI tools are installed
#   - Azure subscription has required resource providers registered
#   - ARM_SUBSCRIPTION_ID is set correctly
#
# Configuration:
#   PREFLIGHT_LIVE_CHECKS=true|false  - Enable/disable live Azure checks
#                                       Set via: azd env set PREFLIGHT_LIVE_CHECKS false
#   PREFLIGHT_DEEP_CHECKS=true        - Enable slow quota checks (Redis, Cosmos, ACA)
#
# Usage:
#   ./preflight-checks.sh             # Interactive mode (prompts for checks)
#   PREFLIGHT_LIVE_CHECKS=true ./preflight-checks.sh   # Run all checks
#   PREFLIGHT_LIVE_CHECKS=false ./preflight-checks.sh  # Skip Azure checks
# ============================================================================

set -euo pipefail

# Only set SCRIPT_DIR if not already defined (prevents errors when sourced multiple times)
if [[ -z "${SCRIPT_DIR:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# ============================================================================
# Logging (matches parent script style)
# ============================================================================

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
# Tool Checks
# ============================================================================

check_required_tools() {
    log "Checking required CLI tools..."
    
    local missing_tools=()
    local tool_checks=(
        "az:Azure CLI:https://docs.microsoft.com/cli/azure/install-azure-cli"
        "azd:Azure Developer CLI:https://aka.ms/azd-install"
        "jq:jq (JSON processor):https://jqlang.github.io/jq/download/"
    )
    
    # Docker is optional in CI mode
    if [[ "${CI:-}" != "true" ]]; then
        tool_checks+=("docker:Docker:https://docs.docker.com/get-docker/")
    fi
    
    for tool_info in "${tool_checks[@]}"; do
        IFS=':' read -r cmd name url <<< "$tool_info"
        if command -v "$cmd" &>/dev/null; then
            local version
            case "$cmd" in
                az)     version=$(az --version 2>/dev/null | head -1 | awk '{print $2}') ;;
                azd)    version=$(azd version 2>/dev/null | head -1) ;;
                docker) version=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',') ;;
                jq)     version=$(jq --version 2>/dev/null) ;;
                *)      version="installed" ;;
            esac
            log "  ✓ $name ($version)"
        else
            log "  ✗ $name - NOT FOUND"
            missing_tools+=("$name|$url")
        fi
    done
    
    # Check Docker separately in CI mode (warn only)
    if [[ "${CI:-}" == "true" ]]; then
        if command -v docker &>/dev/null; then
            local version
            version=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')
            log "  ✓ Docker ($version)"
        else
            log "  ⚪ Docker - skipped (CI mode)"
        fi
    fi
    
    # Optional tools (warn but don't fail)
    local optional_tools=(
        "python3:Python 3.11+:https://www.python.org/downloads/"
        "node:Node.js 22+:https://nodejs.org/"
    )
    
    for tool_info in "${optional_tools[@]}"; do
        IFS=':' read -r cmd name url <<< "$tool_info"
        if command -v "$cmd" &>/dev/null; then
            local version
            case "$cmd" in
                python3) version=$(python3 --version 2>/dev/null | awk '{print $2}') ;;
                node)    version=$(node --version 2>/dev/null) ;;
                *)       version="installed" ;;
            esac
            log "  ✓ $name ($version)"
        else
            warn "  $name not found (optional for deployment, required for local dev)"
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        echo ""
        fail "Missing required tools. Please install:"
        for tool_url in "${missing_tools[@]}"; do
            IFS='|' read -r name url <<< "$tool_url"
            fail "  • $name: $url"
        done
        return 1
    fi
    
    success "All required tools installed"
    return 0
}

# ============================================================================
# Azure CLI Extensions
# ============================================================================

install_required_extensions() {
    log "Checking Azure CLI extensions..."
    
    # Extensions needed for quota checks and resource management
    # Format: name:display_name:description
    local extensions=(
        "quota:Azure Quota:Required for quota checks"
        "redisenterprise:Redis Enterprise:Required for Azure Managed Redis"
        "cosmosdb-preview:Cosmos DB Preview:Required for MongoDB vCore"
    )
    
    for ext_info in "${extensions[@]}"; do
        local ext_name display_name description
        IFS=':' read -r ext_name display_name description <<< "$ext_info"
        
        # Check if extension is installed
        if az extension show --name "$ext_name" &>/dev/null; then
            local version
            version=$(az extension show --name "$ext_name" --query version -o tsv 2>/dev/null || echo "installed")
            log "  ✓ $display_name extension ($version)"
        else
            log "  Installing $display_name extension..."
            if az extension add --name "$ext_name" --yes 2>/dev/null; then
                log "  ✓ $display_name extension installed"
            else
                warn "  ⚠ Could not install $display_name extension ($description)"
            fi
        fi
    done
    
    success "Azure CLI extensions ready"
    return 0
}

# ============================================================================
# Azure Authentication Check
# ============================================================================

check_azure_auth() {
    log "Checking Azure authentication..."
    
    # Check Azure CLI login
    if ! az account show &>/dev/null; then
        fail "Azure CLI not logged in"
        fail "Run: az login"
        return 1
    fi
    log "  ✓ Azure CLI authenticated"
    
    # Check azd auth
    if ! azd auth login --check-status &>/dev/null 2>&1; then
        fail "Azure Developer CLI not authenticated"
        fail "Run: azd auth login"
        return 1
    fi
    log "  ✓ Azure Developer CLI authenticated"
    
    success "Azure authentication verified"
    return 0
}

# ============================================================================
# Subscription & ARM_SUBSCRIPTION_ID Check
# ============================================================================

configure_subscription() {
    log "Configuring Azure subscription..."
    
    # Get current subscription from Azure CLI
    local current_sub
    current_sub=$(az account show --query id -o tsv 2>/dev/null)
    
    if [[ -z "$current_sub" ]]; then
        fail "Could not determine current Azure subscription"
        fail "Run: az login"
        return 1
    fi
    
    local sub_name
    sub_name=$(az account show --query name -o tsv 2>/dev/null)
    
    log "  Current subscription: $sub_name"
    log "  Subscription ID: $current_sub"
    
    # Set ARM_SUBSCRIPTION_ID if not already set or different
    local current_arm_sub="${ARM_SUBSCRIPTION_ID:-}"
    
    if [[ -z "$current_arm_sub" ]]; then
        export ARM_SUBSCRIPTION_ID="$current_sub"
        azd env set ARM_SUBSCRIPTION_ID "$current_sub" 2>/dev/null || true
        info "Set ARM_SUBSCRIPTION_ID to current subscription"
    elif [[ "$current_arm_sub" != "$current_sub" ]]; then
        warn "ARM_SUBSCRIPTION_ID ($current_arm_sub) differs from current az subscription ($current_sub)"
        warn "Updating ARM_SUBSCRIPTION_ID to match current subscription"
        export ARM_SUBSCRIPTION_ID="$current_sub"
        azd env set ARM_SUBSCRIPTION_ID "$current_sub" 2>/dev/null || true
    else
        log "  ✓ ARM_SUBSCRIPTION_ID already set correctly"
    fi
    
    # Also set AZURE_SUBSCRIPTION_ID for azd
    azd env set AZURE_SUBSCRIPTION_ID "$current_sub" 2>/dev/null || true
    
    success "Subscription configured: $sub_name"
    return 0
}

# ============================================================================
# Resource Provider Registration
# ============================================================================

check_resource_providers() {
    log "Checking Azure resource provider registration..."
    
    local required_providers=(
        "Microsoft.Communication"
        "Microsoft.App"
        "Microsoft.CognitiveServices"
        "Microsoft.DocumentDB"
        "Microsoft.Cache"
        "Microsoft.ContainerRegistry"
        "Microsoft.Storage"
        "Microsoft.KeyVault"
        "Microsoft.ManagedIdentity"
        "Microsoft.OperationalInsights"
    )
    
    local unregistered=()
    local registering=()
    
    for provider in "${required_providers[@]}"; do
        local state
        state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotRegistered")
        
        case "$state" in
            Registered)
                log "  ✓ $provider"
                ;;
            Registering)
                log "  ⏳ $provider (registering...)"
                registering+=("$provider")
                ;;
            *)
                log "  ✗ $provider ($state)"
                unregistered+=("$provider")
                ;;
        esac
    done
    
    # Auto-register missing providers
    if [[ ${#unregistered[@]} -gt 0 ]]; then
        info "Registering missing resource providers..."
        for provider in "${unregistered[@]}"; do
            log "  Registering $provider..."
            if az provider register --namespace "$provider" --wait false &>/dev/null; then
                registering+=("$provider")
            else
                fail "  Failed to register $provider"
            fi
        done
    fi
    
    # Wait for registering providers (with timeout)
    if [[ ${#registering[@]} -gt 0 ]]; then
        info "Waiting for provider registration (this may take a few minutes)..."
        local max_wait=300  # 5 minutes
        local wait_interval=10
        local elapsed=0
        
        while [[ $elapsed -lt $max_wait ]]; do
            local still_registering=()
            for provider in "${registering[@]}"; do
                local state
                state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "Unknown")
                if [[ "$state" != "Registered" ]]; then
                    still_registering+=("$provider")
                fi
            done
            
            if [[ ${#still_registering[@]} -eq 0 ]]; then
                break
            fi
            
            log "  Still waiting for: ${still_registering[*]}"
            sleep $wait_interval
            elapsed=$((elapsed + wait_interval))
            registering=("${still_registering[@]}")
        done
        
        if [[ ${#registering[@]} -gt 0 ]]; then
            warn "Some providers still registering: ${registering[*]}"
            warn "Deployment may fail. Check status with:"
            warn "  az provider show --namespace <provider> --query registrationState"
        fi
    fi
    
    success "Resource providers verified"
    return 0
}

# # ============================================================================
# # Docker Check - handled by azd package
# # ============================================================================

# check_docker_running() {
#     log "Checking Docker daemon..."
    
#     if ! docker info &>/dev/null; then
#         fail "Docker daemon is not running"
#         fail "Please start Docker Desktop or the Docker service"
#         return 1
#     fi
    
#     log "  ✓ Docker daemon running"
#     success "Docker ready"
#     return 0
# }

# ============================================================================
# Line Ending Fix (dos2unix)
# ============================================================================
# Fixes Windows CRLF line endings that cause "bad interpreter" errors.
# Usage: fix_line_endings [directory]
# If no directory specified, fixes all .sh files in devops/scripts/

fix_line_endings() {
    local target_dir="${1:-devops/scripts}"
    local fixed_count=0
    
    log "Checking for Windows line endings (CRLF)..."
    
    # Find all .sh files and check for CRLF
    while IFS= read -r -d '' file; do
        if file "$file" | grep -q "CRLF"; then
            log "  Fixing: $file"
            # Use sed to remove carriage returns (works on macOS and Linux)
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' 's/\r$//' "$file"
            else
                sed -i 's/\r$//' "$file"
            fi
            fixed_count=$((fixed_count + 1))
        fi
    done < <(find "$target_dir" -name "*.sh" -type f -print0 2>/dev/null)
    
    if [[ $fixed_count -gt 0 ]]; then
        success "Fixed line endings in $fixed_count file(s)"
        info "If you continue to see 'bad interpreter' errors, try:"
        log "    git config --global core.autocrlf input"
        log "    git rm --cached -r ."
        log "    git reset --hard"
    else
        log "  ✓ No CRLF line endings found"
    fi
    
    return 0
}

# Quick fix for a single file
fix_file_line_endings() {
    local file="$1"
    
    if [[ ! -f "$file" ]]; then
        fail "File not found: $file"
        return 1
    fi
    
    if file "$file" | grep -q "CRLF"; then
        log "Fixing line endings in: $file"
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' 's/\r$//' "$file"
        else
            sed -i 's/\r$//' "$file"
        fi
        success "Fixed: $file"
    else
        log "No CRLF line endings in: $file"
    fi
    
    return 0
}

# ============================================================================
# Regional Service Availability Check
# ============================================================================
# Queries Azure CLI for real-time regional availability of required services.
# Falls back to known regions for services without direct CLI support.
# Last updated: December 2024

# Check if a resource provider supports a specific region
# Usage: check_provider_region <namespace> <resource_type> <location>
# Returns 0 if the region is supported or if the service is global
check_provider_region() {
    local namespace="$1"
    local resource_type="$2"
    local location="$3"
    
    # Query the provider for available locations for this resource type
    local locations
    locations=$(az provider show \
        --namespace "$namespace" \
        --query "resourceTypes[?resourceType=='$resource_type'].locations | [0][]" \
        -o tsv 2>/dev/null || echo "")
    
    if [[ -z "$locations" ]]; then
        return 1
    fi
    
    # Check if service is global (available everywhere)
    if echo "$locations" | grep -qi "^global$"; then
        return 0
    fi
    
    # Normalize the target location (lowercase, no spaces)
    # Use awk for better zsh compatibility on macOS
    local normalized_target
    normalized_target=$(printf '%s' "$location" | awk '{gsub(/ /, ""); print tolower($0)}')
    
    # Check each location from Azure
    while IFS= read -r region; do
        [[ -z "$region" ]] && continue
        # Normalize the Azure region name
        local normalized_region
        normalized_region=$(printf '%s' "$region" | awk '{gsub(/ /, ""); print tolower($0)}')
        
        if [[ "$normalized_region" == "$normalized_target" ]]; then
            return 0
        fi
    done <<< "$locations"
    
    return 1
}

# Get available regions for a resource provider/type (formatted for display)
# Usage: get_provider_regions <namespace> <resource_type>
get_provider_regions() {
    local namespace="$1"
    local resource_type="$2"
    
    az provider show \
        --namespace "$namespace" \
        --query "resourceTypes[?resourceType=='$resource_type'].locations | [0][:10]" \
        -o tsv 2>/dev/null | paste -sd ',' - | sed 's/,$//' || echo "unable to query"
}

# Check Cognitive Services availability for a specific kind
# Usage: check_cognitive_services_region <kind> <location>
check_cognitive_services_region() {
    local kind="$1"
    local location="$2"
    
    # Use az cognitiveservices account list-skus to check availability
    local result
    result=$(az cognitiveservices account list-skus \
        --kind "$kind" \
        --location "$location" \
        --query "[0].name" \
        -o tsv 2>/dev/null || echo "")
    
    if [[ -n "$result" && "$result" != "null" ]]; then
        return 0
    fi
    return 1
}

# Check if Azure OpenAI is available in a region with specific model support
# Usage: check_openai_model_region <location> <model_pattern>
check_openai_model_region() {
    local location="$1"
    local model_pattern="${2:-}"
    
    # Check if OpenAI service is available in the region
    local skus
    skus=$(az cognitiveservices account list-skus \
        --kind "OpenAI" \
        --location "$location" \
        --query "[].name" \
        -o tsv 2>/dev/null || echo "")
    
    if [[ -n "$skus" && "$skus" != "null" ]]; then
        return 0
    fi
    return 1
}

# ============================================================================
# Quota Checking Functions
# ============================================================================
# Validates subscription quotas for required resources and SKUs.
# https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits

# Check Azure OpenAI model quota
# Usage: check_openai_quota <location> <sku_tier> <model_name> <required_capacity>
# Returns: 0 if sufficient quota, 1 if insufficient, 2 if check failed
check_openai_quota() {
    local location="$1"
    local sku_tier="$2"      # e.g., "GlobalStandard", "DataZoneStandard"
    local model_name="$3"    # e.g., "gpt-4o", "text-embedding-3-large"
    local required_capacity="$4"
    
    # Query current usage for this model
    local quota_key="OpenAI.${sku_tier}.${model_name}"
    local quota_info
    quota_info=$(az cognitiveservices usage list \
        -l "$location" \
        -o json 2>/dev/null | jq -r --arg key "$quota_key" \
        '.[] | select(.name.value == $key) | "\(.currentValue)|\(.limit)"' 2>/dev/null || echo "")
    
    if [[ -z "$quota_info" ]]; then
        return 2  # Check failed
    fi
    
    local current_value limit
    current_value=$(echo "$quota_info" | cut -d'|' -f1 | cut -d'.' -f1)
    limit=$(echo "$quota_info" | cut -d'|' -f2 | cut -d'.' -f1)
    
    if [[ -z "$current_value" || -z "$limit" ]]; then
        return 2
    fi
    
    local available=$((limit - current_value))
    
    if [[ $available -ge $required_capacity ]]; then
        echo "$available|$limit"
        return 0
    else
        echo "$available|$limit"
        return 1
    fi
}

# Check all required Azure OpenAI quotas for this accelerator
# Usage: check_all_openai_quotas <location>
check_all_openai_quotas() {
    local location="$1"
    local quota_warnings=0
    local quota_errors=0
    
    log ""
    log "  Azure OpenAI Model Quotas:"
    
    # Define required models and their capacities (from variables.tf defaults)
    # Format: "sku_tier|model_name|required_capacity|description"
    local models=(
        "DataZoneStandard|gpt-4o|150|GPT-4o (primary LLM)"
        "GlobalStandard|text-embedding-3-large|100|Text Embeddings"
        "GlobalStandard|gpt-realtime|4|GPT Realtime (Voice Live)"
        "GlobalStandard|gpt-4o-transcribe|150|GPT-4o Transcribe"
    )
    
    for model_info in "${models[@]}"; do
        IFS='|' read -r sku_tier model_name required_capacity description <<< "$model_info"
        
        local result
        result=$(check_openai_quota "$location" "$sku_tier" "$model_name" "$required_capacity")
        local check_result=$?
        
        if [[ $check_result -eq 0 ]]; then
            local available limit
            available=$(echo "$result" | cut -d'|' -f1)
            limit=$(echo "$result" | cut -d'|' -f2)
            log "    ✓ $description: $available/$limit TPM available (need $required_capacity)"
        elif [[ $check_result -eq 1 ]]; then
            local available limit
            available=$(echo "$result" | cut -d'|' -f1)
            limit=$(echo "$result" | cut -d'|' -f2)
            warn "    ⚠ $description: only $available/$limit TPM available (need $required_capacity)"
            quota_warnings=$((quota_warnings + 1))
        else
            log "    ⚪ $description: unable to check quota"
        fi
    done
    
    return $quota_warnings
}

# Check Cosmos DB MongoDB vCore quota (subscription-level check)
# Note: MongoDB vCore has per-subscription limits, not regional quotas
# Usage: check_cosmosdb_vcore_quota <location> [sku]
check_cosmosdb_vcore_quota() {
    local location="$1"
    local sku="${2:-M30}"
    
    # MongoDB vCore clusters are limited per subscription (default: 25 clusters)
    # This check can be slow (10-30s) so it's only run with PREFLIGHT_DEEP_CHECKS=true
    local deep_checks="${PREFLIGHT_DEEP_CHECKS:-false}"
    
    if [[ "$deep_checks" != "true" ]]; then
        echo "skipped"
        return 2  # Skipped
    fi
    
    # Count existing MongoDB vCore clusters
    local current_count
    current_count=$(az cosmosdb mongocluster list --query "length(@)" -o tsv 2>/dev/null || echo "")
    
    if [[ -z "$current_count" ]]; then
        echo "skipped"
        return 2
    fi
    
    local limit=25  # Default subscription limit
    local available=$((limit - current_count))
    
    echo "$current_count|$limit"
    if [[ $available -ge 1 ]]; then
        return 0
    else
        return 1
    fi
}

# Check Azure Managed Redis capacity
# Note: Redis Enterprise has subscription quotas managed via Azure Portal
# Usage: check_redis_quota <location> [sku]
check_redis_quota() {
    local location="$1"
    local sku="${2:-MemoryOptimized_M10}"
    
    # This check can be slow so it's only run with PREFLIGHT_DEEP_CHECKS=true
    local deep_checks="${PREFLIGHT_DEEP_CHECKS:-false}"
    
    if [[ "$deep_checks" != "true" ]]; then
        echo "skipped"
        return 2  # Skipped
    fi
    
    # Count existing Redis Enterprise clusters
    local current_count
    current_count=$(az redisenterprise list --query "length(@)" -o tsv 2>/dev/null || echo "")
    
    if [[ -z "$current_count" ]]; then
        echo "skipped"
        return 2
    fi
    
    local limit=10  # Default subscription limit
    local available=$((limit - current_count))
    
    echo "$current_count|$limit"
    if [[ $available -ge 1 ]]; then
        return 0
    else
        return 1
    fi
}

# Check Container Apps quota (vCPU cores per subscription per region)
# Usage: check_container_apps_quota <location> [required_vcpus]
check_container_apps_quota() {
    local location="$1"
    local required_vcpus="${2:-10}"  # Min 5 replicas * 2 vCPU = 10 vCPU minimum
    
    # This check can be slow so it's only run with PREFLIGHT_DEEP_CHECKS=true
    local deep_checks="${PREFLIGHT_DEEP_CHECKS:-false}"
    
    if [[ "$deep_checks" != "true" ]]; then
        echo "skipped"
        return 2  # Skipped
    fi
    
    # Query Container Apps vCPU usage in the region
    # Note: This requires listing all container apps and summing their vCPUs
    local total_vcpus=0
    local apps_json
    apps_json=$(az containerapp list --query "[?location=='$location'].{cpu:properties.template.containers[0].resources.cpu}" -o json 2>/dev/null || echo "[]")
    
    if [[ "$apps_json" != "[]" && -n "$apps_json" ]]; then
        total_vcpus=$(echo "$apps_json" | jq '[.[].cpu // 0 | tonumber] | add // 0' 2>/dev/null || echo "0")
    fi
    
    local limit=100  # Default regional limit
    local available=$((limit - total_vcpus))
    
    echo "$total_vcpus|$limit"
    if [[ $available -ge $required_vcpus ]]; then
        return 0
    else
        return 1
    fi
}

# Main quota checking function
check_resource_quotas() {
    log "Checking resource quotas..."
    
    local location="${AZURE_LOCATION:-}"
    if [[ -z "$location" ]]; then
        location=$(azd env get-value AZURE_LOCATION 2>/dev/null || echo "")
    fi
    
    if [[ -z "$location" ]]; then
        warn "AZURE_LOCATION not set - skipping quota checks"
        return 0
    fi
    
    local use_live_checks="${PREFLIGHT_LIVE_CHECKS:-true}"
    
    # Skip quota checks in CI unless explicitly enabled
    if [[ "${CI:-}" == "true" && "${PREFLIGHT_LIVE_CHECKS:-}" != "true" ]]; then
        info "CI mode: Skipping quota checks (set PREFLIGHT_LIVE_CHECKS=true to enable)"
        return 0
    fi
    
    local quota_warnings=0
    
    # -------------------------------------------------------------------------
    # Azure OpenAI Quotas
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        check_all_openai_quotas "$location"
        quota_warnings=$((quota_warnings + $?))
    fi
    
    # -------------------------------------------------------------------------
    # Cosmos DB MongoDB vCore Quota
    # -------------------------------------------------------------------------
    log ""
    log "  Cosmos DB MongoDB vCore:"
    local cosmos_result
    cosmos_result=$(check_cosmosdb_vcore_quota "$location")
    local cosmos_status=$?
    
    if [[ $cosmos_status -eq 2 ]]; then
        log "    ⚪ Quota check skipped (set PREFLIGHT_DEEP_CHECKS=true to enable)"
        log "    Subscription limit: ~25 clusters"
    elif [[ $cosmos_status -eq 0 ]]; then
        local cosmos_used cosmos_limit
        cosmos_used=$(echo "$cosmos_result" | cut -d'|' -f1)
        cosmos_limit=$(echo "$cosmos_result" | cut -d'|' -f2)
        log "    ✓ Using $cosmos_used/$cosmos_limit clusters"
    else
        local cosmos_used cosmos_limit
        cosmos_used=$(echo "$cosmos_result" | cut -d'|' -f1)
        cosmos_limit=$(echo "$cosmos_result" | cut -d'|' -f2)
        warn "    ⚠ Cluster limit reached: $cosmos_used/$cosmos_limit"
        quota_warnings=$((quota_warnings + 1))
    fi
    
    # -------------------------------------------------------------------------
    # Azure Managed Redis Quota
    # -------------------------------------------------------------------------
    log ""
    log "  Azure Managed Redis:"
    local redis_result
    redis_result=$(check_redis_quota "$location")
    local redis_status=$?
    
    if [[ $redis_status -eq 2 ]]; then
        log "    ⚪ Quota check skipped (set PREFLIGHT_DEEP_CHECKS=true to enable)"
        log "    Subscription limit: ~10 clusters"
    elif [[ $redis_status -eq 0 ]]; then
        local redis_used redis_limit
        redis_used=$(echo "$redis_result" | cut -d'|' -f1)
        redis_limit=$(echo "$redis_result" | cut -d'|' -f2)
        log "    ✓ Using $redis_used/$redis_limit clusters"
    else
        local redis_used redis_limit
        redis_used=$(echo "$redis_result" | cut -d'|' -f1)
        redis_limit=$(echo "$redis_result" | cut -d'|' -f2)
        warn "    ⚠ Cluster limit reached: $redis_used/$redis_limit"
        quota_warnings=$((quota_warnings + 1))
    fi
    
    # -------------------------------------------------------------------------
    # Container Apps vCPU Quota
    # -------------------------------------------------------------------------
    log ""
    log "  Azure Container Apps:"
    local aca_result
    aca_result=$(check_container_apps_quota "$location" 10)
    local aca_status=$?
    
    if [[ $aca_status -eq 2 ]]; then
        log "    ⚪ Quota check skipped (set PREFLIGHT_DEEP_CHECKS=true to enable)"
        log "    Regional limit: ~100 vCPU"
    elif [[ $aca_status -eq 0 ]]; then
        local aca_used aca_limit
        aca_used=$(echo "$aca_result" | cut -d'|' -f1)
        aca_limit=$(echo "$aca_result" | cut -d'|' -f2)
        log "    ✓ Using $aca_used/$aca_limit vCPU in $location"
    else
        local aca_used aca_limit
        aca_used=$(echo "$aca_result" | cut -d'|' -f1)
        aca_limit=$(echo "$aca_result" | cut -d'|' -f2)
        warn "    ⚠ vCPU limit may be insufficient: $aca_used/$aca_limit (need ~10)"
        quota_warnings=$((quota_warnings + 1))
    fi
    
    log ""
    
    # Summary
    if [[ $quota_warnings -gt 0 ]]; then
        warn "$quota_warnings quota warning(s) detected"
        info "You may need to request quota increases before deployment"
        info "📚 https://learn.microsoft.com/azure/quotas/quickstart-increase-quota-portal"
    else
        success "Resource quotas look sufficient"
    fi
    
    # Quota checks are informational - don't fail the build
    return 0
}

check_regional_availability() {
    log "Checking regional service availability..."
    
    # Get current target location
    local location="${AZURE_LOCATION:-}"
    if [[ -z "$location" ]]; then
        location=$(azd env get-value AZURE_LOCATION 2>/dev/null || echo "")
    fi
    
    if [[ -z "$location" ]]; then
        warn "AZURE_LOCATION not set - skipping regional availability checks"
        warn "Set location with: azd env set AZURE_LOCATION <region>"
        return 0
    fi
    
    log "  Target region: $location"
    log ""
    
    local warnings=0
    local use_live_checks="${PREFLIGHT_LIVE_CHECKS:-true}"
    
    # Skip live checks in CI unless explicitly enabled
    if [[ "${CI:-}" == "true" && "${PREFLIGHT_LIVE_CHECKS:-}" != "true" ]]; then
        use_live_checks="false"
        info "CI mode: Using cached region data (set PREFLIGHT_LIVE_CHECKS=true for live queries)"
    fi
    
    # -------------------------------------------------------------------------
    # Azure Cosmos DB - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for Cosmos DB availability..."
        if check_provider_region "Microsoft.DocumentDB" "databaseAccounts" "$location"; then
            log "  ✓ Azure Cosmos DB (live check)"
        else
            warn "  ⚠ Azure Cosmos DB may not be available in $location"
            local cosmos_regions
            cosmos_regions=$(get_provider_regions "Microsoft.DocumentDB" "databaseAccounts")
            warn "    Available: $cosmos_regions"
            warnings=$((warnings + 1))
        fi
    else
        # Fallback to known regions
        local cosmos_regions=("eastus" "eastus2" "westus" "westus2" "westus3" "centralus" "northcentralus" "southcentralus" "westcentralus" "canadacentral" "canadaeast" "brazilsouth" "northeurope" "westeurope" "uksouth" "ukwest" "francecentral" "germanywestcentral" "switzerlandnorth" "swedencentral" "norwayeast" "australiaeast" "australiasoutheast" "eastasia" "southeastasia" "japaneast" "japanwest" "koreacentral" "koreasouth" "centralindia" "southindia" "westindia" "uaenorth" "southafricanorth")
        if [[ " ${cosmos_regions[*]} " =~ " ${location} " ]]; then
            log "  ✓ Azure Cosmos DB (cached)"
        else
            warn "  ⚠ Azure Cosmos DB may not be available in $location"
            warnings=$((warnings + 1))
        fi
    fi
    
    # -------------------------------------------------------------------------
    # Azure Cognitive Services (Speech) - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for Speech Services availability..."
        if check_cognitive_services_region "SpeechServices" "$location"; then
            log "  ✓ Azure Speech Services (live check)"
        else
            warn "  ⚠ Azure Speech Services may not be available in $location"
            warnings=$((warnings + 1))
        fi
    else
        local speech_regions=("eastus" "eastus2" "westus" "westus2" "westus3" "southcentralus" "northcentralus" "westeurope" "northeurope" "swedencentral" "southeastasia" "eastasia" "australiaeast" "japaneast")
        if [[ " ${speech_regions[*]} " =~ " ${location} " ]]; then
            log "  ✓ Azure Speech Services (cached)"
        else
            warn "  ⚠ Azure Speech Services may not be available in $location"
            warnings=$((warnings + 1))
        fi
    fi
    
    # -------------------------------------------------------------------------
    # Azure OpenAI - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for OpenAI availability..."
        if check_openai_model_region "$location"; then
            log "  ✓ Azure OpenAI Service (live check)"
        else
            warn "  ⚠ Azure OpenAI may not be available in $location"
            warn "    Consider: eastus, eastus2, westus2, swedencentral, westeurope"
            warnings=$((warnings + 1))
        fi
    else
        local openai_regions=("eastus" "eastus2" "westus" "westus2" "westus3" "northcentralus" "southcentralus" "canadaeast" "westeurope" "northeurope" "swedencentral" "switzerlandnorth" "uksouth" "francecentral" "australiaeast" "japaneast" "southeastasia" "eastasia" "koreacentral" "brazilsouth")
        if [[ " ${openai_regions[*]} " =~ " ${location} " ]]; then
            log "  ✓ Azure OpenAI Service (cached)"
        else
            warn "  ⚠ Azure OpenAI may not be available in $location"
            warnings=$((warnings + 1))
        fi
    fi
    
    # -------------------------------------------------------------------------
    # Azure Voice Live API - Limited regions
    # https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voice-live
    # -------------------------------------------------------------------------
    local voice_live_regions=("eastus2" "swedencentral" "westus2" "southeastasia")
    local configured_voice_live="${TF_VAR_voice_live_location:-}"
    if [[ -z "$configured_voice_live" ]]; then
        configured_voice_live=$(azd env get-value TF_VAR_voice_live_location 2>/dev/null | head -n1 || echo "")
        [[ "$configured_voice_live" == ERROR:* ]] && configured_voice_live=""
    fi
    
    if [[ " ${voice_live_regions[*]} " =~ " ${location} " ]]; then
        log "  ✓ Azure Voice Live API"
    else
        info "  Azure Voice Live API is NOT available in $location"
        info "  Supported regions: ${voice_live_regions[*]}"
        info "  Docs: https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voice-live"
        
        if [[ -n "$configured_voice_live" ]]; then
            info "  Using configured Voice Live region: $configured_voice_live"
        elif [[ "${CI:-}" == "true" || "${AZD_SKIP_INTERACTIVE:-}" == "true" || ! -t 0 ]]; then
            info "  Default is eastus2 unless you set TF_VAR_voice_live_location"
            info "  Set via: azd env set TF_VAR_voice_live_location \"<region>\""
        else
            log ""
            log "  Select a Voice Live region:"
            for i in "${!voice_live_regions[@]}"; do
                log "    $((i + 1))) ${voice_live_regions[$i]}"
            done
            if read -r -p "│ Choice (1-${#voice_live_regions[@]}) or Enter to skip: " voice_live_choice; then
                : # Got input
            else
                voice_live_choice=""
            fi
            
            if [[ "$voice_live_choice" =~ ^[0-9]+$ ]] && \
                (( voice_live_choice >= 1 && voice_live_choice <= ${#voice_live_regions[@]} )); then
                local selected_voice_live="${voice_live_regions[$((voice_live_choice - 1))]}"
                azd env set TF_VAR_voice_live_location "$selected_voice_live" 2>/dev/null || true
                success "Voice Live region set to: $selected_voice_live"
            else
                info "Skipped Voice Live region selection (default: eastus2)"
            fi
        fi
        # Don't increment warnings - this can be configured by the user
    fi
    
    # -------------------------------------------------------------------------
    # Azure Communication Services - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for Communication Services availability..."
        if check_provider_region "Microsoft.Communication" "CommunicationServices" "$location"; then
            log "  ✓ Azure Communication Services (live check)"
        else
            warn "  ⚠ Azure Communication Services may not be available in $location"
            local acs_regions
            acs_regions=$(get_provider_regions "Microsoft.Communication" "CommunicationServices")
            warn "    Available: $acs_regions"
            warnings=$((warnings + 1))
        fi
    else
        local acs_regions=("eastus" "eastus2" "westus" "westus2" "westus3" "centralus" "northcentralus" "southcentralus" "westcentralus" "canadacentral" "canadaeast" "brazilsouth" "northeurope" "westeurope" "uksouth" "ukwest" "francecentral" "germanywestcentral" "switzerlandnorth" "swedencentral" "norwayeast" "australiaeast" "australiasoutheast" "eastasia" "southeastasia" "japaneast" "japanwest" "koreacentral" "centralindia" "southindia" "uaenorth" "southafricanorth")
        if [[ " ${acs_regions[*]} " =~ " ${location} " ]]; then
            log "  ✓ Azure Communication Services (cached)"
        else
            warn "  ⚠ Azure Communication Services may not be available in $location"
            warnings=$((warnings + 1))
        fi
    fi
    
    # -------------------------------------------------------------------------
    # Azure Container Apps - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for Container Apps availability..."
        if check_provider_region "Microsoft.App" "containerApps" "$location"; then
            log "  ✓ Azure Container Apps (live check)"
        else
            warn "  ⚠ Azure Container Apps may not be available in $location"
            local aca_regions
            aca_regions=$(get_provider_regions "Microsoft.App" "containerApps")
            warn "    Available: $aca_regions"
            warnings=$((warnings + 1))
        fi
    else
        local aca_regions=("eastus" "eastus2" "westus" "westus2" "westus3" "centralus" "northcentralus" "southcentralus" "westcentralus" "canadacentral" "canadaeast" "brazilsouth" "northeurope" "westeurope" "uksouth" "ukwest" "francecentral" "germanywestcentral" "switzerlandnorth" "swedencentral" "norwayeast" "polandcentral" "australiaeast" "australiasoutheast" "australiacentral" "eastasia" "southeastasia" "japaneast" "japanwest" "koreacentral" "koreasouth" "centralindia" "southindia" "westindia" "uaenorth" "southafricanorth" "qatarcentral")
        if [[ " ${aca_regions[*]} " =~ " ${location} " ]]; then
            log "  ✓ Azure Container Apps (cached)"
        else
            warn "  ⚠ Azure Container Apps may not be available in $location"
            warnings=$((warnings + 1))
        fi
    fi
    
    # -------------------------------------------------------------------------
    # Azure Managed Redis (Enterprise) - Query via Azure CLI
    # -------------------------------------------------------------------------
    if [[ "$use_live_checks" == "true" ]]; then
        log "  Querying Azure for Managed Redis availability..."
        if check_provider_region "Microsoft.Cache" "redisEnterprise" "$location"; then
            log "  ✓ Azure Managed Redis (live check)"
        else
            warn "  ⚠ Azure Managed Redis may not be available in $location"
            warnings=$((warnings + 1))
        fi
    else
        # Redis Enterprise is broadly available, assume it's available
        log "  ✓ Azure Managed Redis (cached)"
    fi
    
    log ""
    
    # Summary
    if [[ $warnings -gt 0 ]]; then
        warn "$warnings service(s) may have limited availability in $location"
        warn "Consider using: eastus2, swedencentral, or westus2 for best coverage"
        info "Deployment will continue, but some features may not work"
    else
        success "All services available in $location"
    fi
    
    # Regional availability is informational - don't fail the build
    return 0
}

# Recommend optimal regions based on service requirements
recommend_regions() {
    log ""
    info "📍 Recommended regions for full feature support:"
    log "   • eastus2       - Best US coverage (GPT-4o Realtime, Voice Live, all services)"
    log "   • swedencentral - Best EU coverage (GPT-4o Realtime, Voice Live, all services)"
    log "   • westus2       - Good US West coverage (GPT-4o Realtime, most services)"
    log ""
}

# ============================================================================
# Main
# ============================================================================

run_preflight_checks() {
    header "Running Preflight Checks"
    
    local failed=0
    local skip_azure_checks="${PREFLIGHT_LIVE_CHECKS:-}"

    # In CI mode without explicit PREFLIGHT_LIVE_CHECKS, skip Azure auth checks
    if [[ "${CI:-}" == "true" && "${PREFLIGHT_LIVE_CHECKS:-}" != "true" ]]; then
        skip_azure_checks="false"
    elif [[ -z "$skip_azure_checks" ]]; then
        if [[ -t 0 ]]; then
            log ""
            log "💡 To skip this prompt, run: azd env set PREFLIGHT_LIVE_CHECKS false"
            log ""
            read -r -p "Run Azure preflight checks now? [y/N]: " _run_preflight_choice
            if [[ "$_run_preflight_choice" =~ ^[Yy]$ ]]; then
                skip_azure_checks="true"
                export PREFLIGHT_LIVE_CHECKS="true"
            else
                skip_azure_checks="false"
                export PREFLIGHT_LIVE_CHECKS="false"
            fi
        else
            skip_azure_checks="true"
        fi
    fi

    if [[ -z "$skip_azure_checks" ]]; then
        skip_azure_checks="${PREFLIGHT_LIVE_CHECKS:-true}"
    fi
    
    # 1. Check required tools
    if ! check_required_tools; then
        failed=1
    fi
    log ""
    
    # # 2. Check Docker is running (skip in CI - may not have Docker)
    # if [[ "${CI:-}" == "true" ]]; then
    #     info "Skipping Docker check (CI mode)"
    # elif ! check_docker_running; then
    #     warn "Docker not running - some features may not work"
    #     # Don't fail for Docker in CI
    # fi
    # log ""
    
    # 3-5. Azure auth checks (skip in CI mode without credentials)
    if [[ "$skip_azure_checks" == "false" ]]; then
        info "Skipping Azure authentication checks (CI mode, PREFLIGHT_LIVE_CHECKS=false)"
        log ""
    else
        # 3. Check Azure authentication
        if ! check_azure_auth; then
            failed=1
        fi
        log ""
        
        # 3b. Install required Azure CLI extensions
        install_required_extensions
        log ""
        
        # 4. Configure subscription and ARM_SUBSCRIPTION_ID
        if ! configure_subscription; then
            failed=1
        fi
        log ""
        
        # 5. Check and register resource providers
        if ! check_resource_providers; then
            failed=1
        fi
        log ""
    fi
    
    # 6. Check regional service availability (informational, non-blocking)
    check_regional_availability
    
    # 7. Check resource quotas (informational, non-blocking)
    check_resource_quotas
    
    recommend_regions
    
    footer
    
    if [[ $failed -ne 0 ]]; then
        fail "Preflight checks failed. Please resolve the issues above."
        return 1
    fi
    
    phase_success "All preflight checks passed!"
    return 0
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_preflight_checks "$@"
fi
