#!/bin/bash

# ========================================================================
# 🏗️ Terraform Remote State Storage Account Setup
# ========================================================================
# This script creates Azure Storage Account for Terraform remote state
# using fully Entra-backed authentication.

set -euo pipefail

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}ℹ️  [INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}✅ [SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}⚠️  [WARNING]${NC} $*"; }
log_error() { echo -e "${RED}❌ [ERROR]${NC} $*" >&2; }

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
    azd env get-value "$1" 2>/dev/null || echo ""
}

# Check if storage account exists and is accessible
storage_exists() {
    local account="$1"
    local rg="$2"
    az storage account show --name "$account" --resource-group "$rg" &> /dev/null
    local result
    result=$(az storage account show --name "$account" --resource-group "$rg" --query "provisioningState" -o tsv 2>/dev/null)
    log_info "Checked storage account '$account' in resource group '$rg': provisioningState=$result"
    echo "az storage account show --name \"$account\" --resource-group \"$rg\" --query \"provisioningState\" -o tsv"
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

# Generate unique resource names
generate_names() {
    local env_name="${1:-tfdev}"
    local sub_id="$2"
    local suffix=$(echo "${sub_id}${env_name}" | sha256sum | cut -c1-8)
    
    echo "tfstate${suffix}" # storage account
    echo "tfstate" # container
    echo "rg-tfstate-${env_name}-${suffix}" # resource group
}

# Create storage resources
create_storage() {
    local storage_account="$1"
    local container="$2"
    local resource_group="$3"
    local location="${4:-eastus2}"
    
    # Create resource group
    if ! az group show --name "$resource_group" &> /dev/null; then
        log_info "Creating resource group: $resource_group"
        az group create --name "$resource_group" --location "$location" --output none
    fi
    
    # Create storage account
    if ! storage_exists "$storage_account" "$resource_group"; then
        log_info "Creating storage account: $storage_account"
        az storage account create \
            --name "$storage_account" \
            --resource-group "$resource_group" \
            --location "$location" \
            --sku Standard_LRS \
            --kind StorageV2 \
            --allow-blob-public-access false \
            --min-tls-version TLS1_2 \
            --output none
            
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
    
    # Create container
    if ! az storage container show \
        --name "$container" \
        --account-name "$storage_account" \
        --auth-mode login &> /dev/null; then
        log_info "Creating storage container: $container"
        az storage container create \
            --name "$container" \
            --account-name "$storage_account" \
            --auth-mode login \
            --output none
    fi
    
    # Assign permissions
    local user_id=$(az ad signed-in-user show --query id -o tsv)
    local storage_id=$(az storage account show \
        --name "$storage_account" \
        --resource-group "$resource_group" \
        --query id -o tsv)
        
    if ! az role assignment list \
        --assignee "$user_id" \
        --scope "$storage_id" \
        --role "Storage Blob Data Contributor" \
        --query "length(@)" -o tsv | grep -q "1"; then
        log_info "Assigning storage permissions..."
        az role assignment create \
            --assignee "$user_id" \
            --role "Storage Blob Data Contributor" \
            --scope "$storage_id" \
            --output none
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

# Check if JSON file has meaningful content
has_json_content() {
    local file="$1"
    
    # If file doesn't exist or is empty, return false
    [[ ! -f "$file" ]] || [[ ! -s "$file" ]] && return 1
    
    # Remove whitespace and check if it's just empty braces
    local content=$(tr -d '[:space:]' < "$file")
    [[ "$content" == "{}" ]] && return 1
    
    # Check if file has any JSON keys
    if python3 -c "import json; data=json.load(open('$file')); exit(0 if data else 1)" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Update tfvars file only if empty or non-existent
update_tfvars() {
    local tfvars_file="./infra/terraform/main.tfvars.json"
    local env_name="${1}"
    local location="${2}"
    
    # Ensure directory exists
    mkdir -p "$(dirname "$tfvars_file")"
    
    # Check if file has actual content
    if has_json_content "$tfvars_file"; then
        log_info "tfvars file already contains values, skipping update"
        return 0
    fi
    
    log_info "Creating/updating tfvars file: $tfvars_file"
    
    # Write the tfvars content
    cat > "$tfvars_file" << EOF
{
  "environment_name": "$env_name",
  "location": "$location"
}
EOF
    log_success "Updated $tfvars_file"
}

# Main execution
main() {
    echo "========================================================================="
    echo "🏗️  Terraform Remote State Storage Setup"
    echo "========================================================================="
    
    check_dependencies
    
    # Get environment values
    local env_name=$(get_azd_env "AZURE_ENV_NAME")
    local location=$(get_azd_env "AZURE_LOCATION")
    local sub_id=$(az account show --query id -o tsv)
    
    if [[ -z "$env_name" ]]; then
        log_error "AZURE_ENV_NAME is not set in the azd environment."
        exit 1
    fi
    if [[ -z "$location" ]]; then
        log_error "AZURE_LOCATION is not set in the azd environment."
        exit 1
    fi

    # Check existing configuration
    local storage_account=$(get_azd_env "RS_STORAGE_ACCOUNT")
    local container=$(get_azd_env "RS_CONTAINER_NAME")
    local resource_group=$(get_azd_env "RS_RESOURCE_GROUP")
    
    # Only create new storage if variables are missing OR if storage doesn't actually exist
    if [[ -z "$storage_account" ]] || [[ -z "$container" ]] || [[ -z "$resource_group" ]] || ! storage_exists "$storage_account" "$resource_group"; then
        if [[ -n "$storage_account" ]] && [[ -n "$container" ]] && [[ -n "$resource_group" ]]; then
            log_warning "Storage configuration exists but storage account '$storage_account' not found."
            read -p "Do you want to create a new storage account for Terraform remote state? [y/N]: " confirm
            if [[ "$confirm" =~ ^[Yy]$ ]]; then
                log_info "Proceeding to create new storage account..."
            else
                log_info "Skipping remote state storage creation. Continuing with local state."
                return 0
            fi
        else
            log_info "Setting up new Terraform remote state storage..."
        fi
        
        read storage_account container resource_group <<< $(generate_names "$env_name" "$sub_id")
        create_storage "$storage_account" "$container" "$resource_group" "$location"
        
        # Set azd environment variables
        azd env set RS_STORAGE_ACCOUNT "$storage_account"
        azd env set RS_CONTAINER_NAME "$container"
        azd env set RS_RESOURCE_GROUP "$resource_group"
        azd env set RS_STATE_KEY "$env_name.tfstate"
    else
        log_success "Using existing remote state configuration"
        log_info "Storage Account: $storage_account"
        log_info "Container: $container" 
        log_info "Resource Group: $resource_group"
    fi

    # Update tfvars file (only if empty or doesn't exist)
    update_tfvars "$env_name" "$location"
    
    
    log_success "✅ Terraform remote state setup completed!"
    echo ""
    echo "📋 Configuration:"
    echo "   Storage Account: $storage_account"
    echo "   Container: $container"
    echo "   Resource Group: $resource_group"
    echo ""
    echo "📁 Files created/updated:"
    echo "   - infra/terraform/provider.conf.json"
    echo "   - infra/terraform/main.tfvars.json (only if empty/new)"
}

# Handle script interruption
trap 'log_error "Script interrupted"; exit 130' INT

# Run main function
main "$@"