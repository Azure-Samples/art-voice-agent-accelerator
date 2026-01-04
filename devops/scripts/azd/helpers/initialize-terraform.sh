#!/bin/bash

# ========================================================================
# 🏗️ Terraform Remote State Storage Account Setup
# ========================================================================
# This script creates Azure Storage Account for Terraform remote state
# using fully Entra-backed authentication.

set -euo pipefail

readonly LOG_IN_BOX="${AZD_LOG_IN_BOX:-false}"

# Logging (matches preprovision formatting)
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

log_info()    { info "$@"; }
log_success() { success "$@"; }
log_warning() { warn "$@"; }
log_error()   { fail "$@"; }

header() {
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        printf '│ %s%s%s\n' "$CYAN" "$*" "$NC"
        return
    fi
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ ${CYAN}$*${NC}"
    echo "├─────────────────────────────────────────────────────────────"
}

footer() {
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        return
    fi
    echo "╰─────────────────────────────────────────────────────────────"
    echo ""
}

prompt() {
    local prompt_text="$1"
    local __var="$2"
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        read -rp "│ ${prompt_text}" "$__var"
    else
        read -rp "${prompt_text}" "$__var"
    fi
}

# Check dependencies
check_dependencies() {
    local deps=("az" "azd")
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Missing required command: $cmd"
            exit 1
        fi
    done
    
    if ! az account show &> /dev/null; then
        log_error "Not logged in to Azure. Please run 'az login' first."
        exit 1
    fi
}

# Get azd environment variable value
get_azd_env() {
    local value
    # Get only the first line to avoid capturing warning messages from azd
    value=$(azd env get-value "$1" 2>/dev/null | head -n1)
    local exit_code=${PIPESTATUS[0]}
    
    # Return empty string if:
    # - Command failed (non-zero exit code)
    # - Value is empty
    # - Value contains error messages (starts with ERROR: or contains 'not found')
    if [[ $exit_code -ne 0 ]] || [[ -z "$value" ]] || [[ "$value" == ERROR:* ]] || [[ "$value" == *"not found"* ]]; then
        echo ""
    else
        echo "$value"
    fi
}

# Check if storage account exists and is accessible
storage_exists() {
    local account="$1"
    local rg="$2"
    local result
    result=$(az storage account show --name "$account" --resource-group "$rg" --query "provisioningState" -o tsv 2>/dev/null)
    if [[ "$result" == "Succeeded" ]]; then
        log_info "Storage account '$account' in resource group '$rg' exists and is provisioned."
        return 0
    else
        log_info "Storage account '$account' in resource group '$rg' does not exist or is not provisioned (provisioningState=$result)."
        return 1
    fi
}

# Generate unique resource names (returns space-separated: storage container rg)
generate_names() {
    local env_name="${1:-tfdev}"
    local sub_id="$2"
    local suffix=$(echo "${sub_id}${env_name}" | sha256sum | cut -c1-8)
    # Clean environment name (remove special chars, convert to lowercase)
    local clean_env=$(echo "$env_name" | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')

    # Calculate remaining space: 24 (max) - 7 (tfstate) - 8 (suffix) = 9 chars for env name
    local max_env_length=9
    local short_env="${clean_env:0:$max_env_length}"
    
    # Output space-separated for proper read parsing
    echo "tfstate${short_env}${suffix} tfstate rg-tfstate-${short_env}-${suffix}"
}

# Create storage resources
create_storage() {
    local storage_account="$1"
    local container="$2"
    local resource_group="$3"
    local location="$4"
    
    # Create resource group
    if ! az group show --name "$resource_group" &> /dev/null; then
        log_info "Creating resource group: $resource_group"
        az group create --name "$resource_group" --location "$location" \
            --tags "SecurityControl=Ignore" \
            --output none
    fi
    
    # Create storage account
    if ! storage_exists "$storage_account" "$resource_group" "$location"; then
        log_info "Creating storage account: $storage_account"
        az storage account create \
            --name "$storage_account" \
            --resource-group "$resource_group" \
            --location "$location" \
            --sku Standard_LRS \
            --kind StorageV2 \
            --allow-blob-public-access false \
            --min-tls-version TLS1_2 \
            --tags "SecurityControl=Ignore" \
            --output none
        
        # Wait for storage account to be fully provisioned
        log_info "Waiting for storage account to be ready..."
        local max_wait=60
        local waited=0
        while [[ $waited -lt $max_wait ]]; do
            local state
            state=$(az storage account show --name "$storage_account" --resource-group "$resource_group" --query "provisioningState" -o tsv 2>/dev/null || echo "")
            if [[ "$state" == "Succeeded" ]]; then
                log_success "Storage account is ready"
                break
            fi
            log_info "Storage account provisioning state: $state (waiting...)"
            sleep 5
            waited=$((waited + 5))
        done
        
        if [[ $waited -ge $max_wait ]]; then
            log_warning "Storage account may not be fully ready after ${max_wait}s, proceeding anyway"
        fi
            
        # Enable versioning and change feed (best-effort)
        # Some Azure CLI versions/extensions may hit InvalidApiVersionParameter; do not fail setup.
        if ! az storage account blob-service-properties update \
            --account-name "$storage_account" \
            --resource-group "$resource_group" \
            --enable-versioning true \
            --enable-change-feed true \
            --output none 2>/tmp/blob_props_err.txt; then
            log_warning "Could not update blob service properties (versioning/change feed)."
            if grep -q "InvalidApiVersionParameter" /tmp/blob_props_err.txt; then
                log_warning "Azure API version not supported by your CLI for this operation. Skipping this step."
                log_warning "You can enable Versioning and Change Feed later in the Azure Portal under Storage Account > Data management."
            else
                log_warning "Reason: $(tr -d '\n' < /tmp/blob_props_err.txt)"
            fi
        fi
    fi
    
    # Assign permissions
    local user_id=$(az ad signed-in-user show --query id -o tsv)
    local storage_id=$(az storage account show \
        --name "$storage_account" \
        --resource-group "$resource_group" \
        --query id -o tsv)
    
    local role_exists
    role_exists=$(az role assignment list \
        --assignee "$user_id" \
        --scope "$storage_id" \
        --role "Storage Blob Data Contributor" \
        --query "length(@)" -o tsv 2>/dev/null || echo "0")
        
    if [[ "$role_exists" != "1" ]]; then
        log_info "Assigning storage permissions..."
        az role assignment create \
            --assignee "$user_id" \
            --role "Storage Blob Data Contributor" \
            --scope "$storage_id" \
            --output none
        
        # Wait for RBAC role assignment to propagate
        # Azure RBAC can take 1-5 minutes to propagate; we wait up to 90 seconds
        log_info "Waiting for RBAC role assignment to propagate..."
        local max_rbac_wait=90
        local rbac_waited=0
        local rbac_ready=false
        
        while [[ $rbac_waited -lt $max_rbac_wait ]]; do
            # Test if we can actually access the storage with the new role
            if az storage container list \
                --account-name "$storage_account" \
                --auth-mode login \
                -o none 2>/dev/null; then
                log_success "RBAC role assignment is active"
                rbac_ready=true
                break
            fi
            log_info "RBAC propagation in progress... (${rbac_waited}s/${max_rbac_wait}s)"
            sleep 10
            rbac_waited=$((rbac_waited + 10))
        done
        
        if [[ "$rbac_ready" != "true" ]]; then
            log_warning "RBAC role may not be fully propagated after ${max_rbac_wait}s"
            log_warning "If you encounter permission errors, wait a few minutes and retry"
        fi
    else
        log_info "Storage permissions already assigned"
    fi
    
    # Create container
    if ! az storage container show \
        --name "$container" \
        --account-name "$storage_account" \
        --auth-mode login &> /dev/null; then
        log_info "Creating storage container: $container"
        
        # Retry container creation a few times in case RBAC is still propagating
        local container_created=false
        local container_retries=3
        for ((i=1; i<=container_retries; i++)); do
            if az storage container create \
                --name "$container" \
                --account-name "$storage_account" \
                --auth-mode login \
                --output none 2>/dev/null; then
                container_created=true
                log_success "Storage container created"
                break
            else
                if [[ $i -lt $container_retries ]]; then
                    log_warning "Container creation failed (attempt $i/$container_retries), retrying in 10s..."
                    sleep 10
                fi
            fi
        done
        
        if [[ "$container_created" != "true" ]]; then
            log_error "Failed to create storage container after $container_retries attempts"
            log_error "This may be due to RBAC propagation delay. Please wait a few minutes and run:"
            log_error "  az storage container create --name $container --account-name $storage_account --auth-mode login"
            return 1
        fi
    else
        log_info "Storage container already exists"
    fi
}

# Attempt to obtain the current public IP using multiple strategies
get_public_ip() {
    local ip=""
    # Try DNS-based discovery (often works without HTTPS egress restrictions)
    if command -v dig >/dev/null 2>&1; then
        ip=$(dig +short myip.opendns.com @resolver1.opendns.com 2>/dev/null || echo "")
    fi
    # Fallbacks via HTTPS services
    if [ -z "$ip" ] && command -v curl >/dev/null 2>&1; then
        ip=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "")
    fi
    if [ -z "$ip" ] && command -v curl >/dev/null 2>&1; then
        ip=$(curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo "")
    fi
    # Final sanity check: ensure it matches IPv4 format
    if echo "$ip" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
        echo "$ip"
        return 0
    else
        echo ""
        return 1
    fi
}

# Check if we can list containers using Azure AD auth; returns 0 on success
can_access_storage_containers() {
    local account="$1"; local rg="$2"
    az storage container list \
        --account-name "$account" \
        --resource-group "$rg" \
        --auth-mode login \
        -o none 2>/tmp/storage_list_err.txt && return 0
    return 1
}

# Determine if current azd environment is a dev/sandbox context
is_dev_sandbox() {
    local env_name sandbox
    env_name=$(get_azd_env "AZURE_ENV_NAME")
    sandbox=$(get_azd_env "SANDBOX_MODE")
    # Explicit override via SANDBOX_MODE=true/1/yes
    if echo "${sandbox}" | grep -Eiq '^(1|true|yes)$'; then

        log_info "Detected dev/sandbox environment: ${env_name}"
        return 0
    fi
    # Heuristic based on environment name
    if echo "${env_name}" | grep -Eiq '^(dev|local|sandbox)$'; then
        return 0
    fi
    return 1
}

# Main execution
main() {
    header "🏗️  Terraform Remote State Storage Setup"
    
    check_dependencies

    # Check if LOCAL_STATE is set to true - skip remote state setup
    local local_state=$(get_azd_env "LOCAL_STATE")
    if [[ "$local_state" == "true" ]]; then
        log_info "LOCAL_STATE=true is set in azd environment"
        log_info "Skipping remote state setup - using local state instead"
        log ""
        log_warning "Your Terraform state will be stored locally in the project directory."
        log_warning "This means:"
        log_warning "  • State is NOT shared with your team"
        log_warning "  • State may be lost if .terraform/ is deleted"
        log_warning "  • NOT recommended for production or shared environments"
        log ""
        log_info "To switch to remote state:"
        log_info "  azd env set LOCAL_STATE \"false\""
        log_info "  azd hooks run preprovision"
        log ""
        footer
        return 0
    fi

    # Get environment values (check shell env first, then azd env)
    local env_name="${AZURE_ENV_NAME:-$(get_azd_env "AZURE_ENV_NAME")}"
    local location="${AZURE_LOCATION:-$(get_azd_env "AZURE_LOCATION")}"
    local sub_id=$(az account show --query id -o tsv)
    
    if [[ -z "$env_name" ]]; then
        log_error "AZURE_ENV_NAME is not set in the azd environment."
        exit 1
    fi
    if [[ -z "$location" ]]; then
        log_error "AZURE_LOCATION is not set in the azd environment."
        exit 1
    fi

    log_info "Using environment: $env_name, location: $location"
    log_info "Terraform variables will be provided via TF_VAR_* environment variables from preprovision.sh"

    # Check existing configuration
    local storage_account=$(get_azd_env "RS_STORAGE_ACCOUNT")
    local container=$(get_azd_env "RS_CONTAINER_NAME")
    local resource_group=$(get_azd_env "RS_RESOURCE_GROUP")
    local state_key=$(get_azd_env "RS_STATE_KEY")
    
    # If all 4 remote state config values are set, skip setup entirely
    if [[ -n "$storage_account" ]] && [[ -n "$container" ]] && [[ -n "$resource_group" ]] && [[ -n "$state_key" ]]; then
        log_success "Remote state already configured - skipping setup"
        log_info "  Storage Account: $storage_account"
        log_info "  Container: $container" 
        log_info "  Resource Group: $resource_group"
        log_info "  State Key: $state_key"
        return 0
    fi
    
    # Partial or no config - need to set up
    if [[ -n "$storage_account" ]] && [[ -n "$container" ]] && [[ -n "$resource_group" ]] && storage_exists "$storage_account" "$resource_group"; then
        log_success "Using existing remote state configuration"
        log_info "Storage Account: $storage_account"
        log_info "Container: $container" 
        log_info "Resource Group: $resource_group"
    else
        # Fresh setup or storage doesn't exist - need to create
        log_info "Setting up Terraform remote state storage..."
        
        # Generate default names
        read gen_storage gen_container gen_resource_group <<< $(generate_names "$env_name" "$sub_id")
        
        # Use existing values if set, otherwise use generated
        storage_account="${storage_account:-$gen_storage}"
        container="${container:-$gen_container}"
        resource_group="${resource_group:-$gen_resource_group}"
        
        log ""
        log "📋 Proposed remote state configuration:"
        log "   Resource Group:   $resource_group"
        log "   Storage Account:  $storage_account"
        log "   Container:        $container"
        log "   Location:         $location"
        log ""
        
        # In CI/non-interactive mode, auto-accept defaults
        local choice="Y"
        if [[ "${TF_INIT_SKIP_INTERACTIVE:-}" != "true" ]]; then
            prompt "Use these values? [Y]es / [n]o (use local state) / [e]xisting: " choice
        else
            log_info "CI mode: auto-accepting proposed configuration"
        fi
        case "$choice" in
            [Nn]*)
                log ""
                log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                log_warning "USING LOCAL TERRAFORM STATE"
                log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                log ""
                log_warning "Your Terraform state will be stored locally in the project directory."
                log_warning "This means:"
                log_warning "  • State is NOT shared with your team"
                log_warning "  • State may be lost if .terraform/ is deleted"
                log_warning "  • NOT recommended for production or shared environments"
                log ""
                
                # Set LOCAL_STATE flag to indicate local backend should be used
                azd env set LOCAL_STATE "true"
                log_info "Set LOCAL_STATE=true in azd environment"
                log ""
                
                log_info "To switch to remote state later, run:"
                log_info "  azd env set LOCAL_STATE \"false\""
                log_info "  azd env set RS_RESOURCE_GROUP \"<resource-group-name>\""
                log_info "  azd env set RS_STORAGE_ACCOUNT \"<storage-account-name>\""
                log_info "  azd env set RS_CONTAINER_NAME \"<container-name>\""
                log_info "  azd hooks run preprovision"
                log ""
                footer
                return 0
                ;;
            [Ee]*)
                log ""
                log_info "Enter existing values (press Enter to keep default):"
                log ""
                prompt "   Resource Group [$resource_group]: " custom_rg
                resource_group="${custom_rg:-$resource_group}"
                
                prompt "   Storage Account [$storage_account]: " custom_sa
                storage_account="${custom_sa:-$storage_account}"
                
                prompt "   Container [$container]: " custom_container
                container="${custom_container:-$container}"
                
                log ""
                log_info "Using existing remote state configuration:"
                log_info "   Resource Group:  $resource_group"
                log_info "   Storage Account: $storage_account"
                log_info "   Container:       $container"
                
                # For existing resources, just set the variables and let Terraform validate
                # Don't try to create anything - the user says these already exist
                azd env set RS_STORAGE_ACCOUNT "$storage_account"
                azd env set RS_CONTAINER_NAME "$container"
                azd env set RS_RESOURCE_GROUP "$resource_group"
                azd env set RS_STATE_KEY "$env_name.tfstate"
                
                log_success "Remote state configuration saved"
                log ""
                log_info "Terraform will validate connectivity during 'terraform init'"
                log_info "If you see authentication errors, ensure you have 'Storage Blob Data Contributor'"
                log_info "role on the storage account."
                log ""
                
                # Skip create_storage - jump directly to success
                log ""
                log_success "Terraform remote state setup completed!"
                log ""
                log "📋 Configuration:"
                log "   Storage Account: $storage_account"
                log "   Container: $container"
                log "   Resource Group: $resource_group"
                log ""
                log "📁 Files created/updated:"
                log "   - infra/terraform/provider.conf.json"
                log ""
                log "💡 Terraform variables (environment_name, location) are provided via"
                log "   TF_VAR_* environment variables from preprovision.sh"
                footer
                return 0
                ;;
        esac
        
        # Create the storage resources (only for "Y" option - new resources)
        create_storage "$storage_account" "$container" "$resource_group" "$location"
        
        # Set azd environment variables
        azd env set RS_STORAGE_ACCOUNT "$storage_account"
        azd env set RS_CONTAINER_NAME "$container"
        azd env set RS_RESOURCE_GROUP "$resource_group"
        azd env set RS_STATE_KEY "$env_name.tfstate"
    fi

    
    log_success "Terraform remote state setup completed!"
    log ""
    log "📋 Configuration:"
    log "   Storage Account: $storage_account"
    log "   Container: $container"
    log "   Resource Group: $resource_group"
    log ""
    log "📁 Files created/updated:"
    log "   - infra/terraform/provider.conf.json"
    log ""
    log "💡 Terraform variables (environment_name, location) are provided via"
    log "   TF_VAR_* environment variables from preprovision.sh"
    footer
}

# Handle script interruption
trap 'log_error "Script interrupted"; exit 130' INT

# Run main function
main "$@"
