#!/bin/bash
# ============================================================================
# 🎯 Azure Developer CLI Pre-Provisioning Script
# ============================================================================
# Runs before azd provisions Azure resources. Handles:
#   - Terraform: Remote state setup + tfvars generation
#   - Bicep: SSL certificate configuration
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROVIDER="${1:-}"

# ============================================================================
# Logging (unified style)
# ============================================================================

is_ci() {
    [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" || "${AZD_SKIP_INTERACTIVE:-}" == "true" ]]
}

log()     { echo "│ $*"; }
info()    { echo "│ ℹ️  $*"; }
success() { echo "│ ✅ $*"; }
warn()    { echo "│ ⚠️  $*"; }
fail()    { echo "│ ❌ $*" >&2; }

header() {
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ $*"
    echo "├─────────────────────────────────────────────────────────────"
}

footer() {
    echo "╰─────────────────────────────────────────────────────────────"
    echo ""
}

# ============================================================================
# Helpers
# ============================================================================

get_deployer_identity() {
    local name=""
    
    # Try git config first
    if command -v git &>/dev/null; then
        local git_name git_email
        git_name=$(git config --get user.name 2>/dev/null || true)
        git_email=$(git config --get user.email 2>/dev/null || true)
        [[ -n "$git_name" && -n "$git_email" ]] && name="$git_name <$git_email>"
        [[ -z "$name" && -n "$git_email" ]] && name="$git_email"
    fi
    
    # Fallback to Azure CLI
    if [[ -z "$name" ]] && command -v az &>/dev/null; then
        name=$(az account show --query user.name -o tsv 2>/dev/null || true)
        [[ "$name" == "None" ]] && name=""
    fi
    
    echo "${name:-unknown}"
}

# Resolve location with fallback chain: env var → env-specific tfvars → default tfvars → prompt
resolve_location() {
    local params_dir="$SCRIPT_DIR/../../../infra/terraform/params"
    
    # 1. Already set via environment
    if [[ -n "${AZURE_LOCATION:-}" ]]; then
        info "Using AZURE_LOCATION from environment: $AZURE_LOCATION"
        return 0
    fi
    
    # 2. Try environment-specific tfvars (e.g., main.tfvars.staging.json)
    local env_tfvars="$params_dir/main.tfvars.${AZURE_ENV_NAME}.json"
    if [[ -f "$env_tfvars" ]]; then
        AZURE_LOCATION=$(jq -r '.location // empty' "$env_tfvars" 2>/dev/null || true)
        if [[ -n "$AZURE_LOCATION" ]]; then
            info "Resolved location from $env_tfvars: $AZURE_LOCATION"
            export AZURE_LOCATION
            return 0
        fi
    fi
    
    # 3. Try default tfvars
    local default_tfvars="$params_dir/main.tfvars.default.json"
    if [[ -f "$default_tfvars" ]]; then
        AZURE_LOCATION=$(jq -r '.location // empty' "$default_tfvars" 2>/dev/null || true)
        if [[ -n "$AZURE_LOCATION" ]]; then
            info "Resolved location from default tfvars: $AZURE_LOCATION"
            export AZURE_LOCATION
            return 0
        fi
    fi
    
    # 4. Interactive prompt (local dev only)
    if ! is_ci; then
        log "No location found in tfvars files."
        read -rp "│ Enter Azure location (e.g., eastus, westus2): " AZURE_LOCATION
        if [[ -n "$AZURE_LOCATION" ]]; then
            export AZURE_LOCATION
            return 0
        fi
    fi
    
    return 1
}

# Set Terraform variables using azd env (stored in .azure/<env>/.env as TF_VAR_*)
# This is the azd best practice - azd automatically exports TF_VAR_* to Terraform
set_terraform_env_vars() {
    local deployer
    deployer=$(get_deployer_identity)
    
    log "Setting Terraform variables via azd env..."
    
    # Set TF_VAR_* variables - azd stores these in .azure/<env>/.env
    # and automatically exports them when running terraform
    azd env set TF_VAR_environment_name "$AZURE_ENV_NAME"
    azd env set TF_VAR_location "$AZURE_LOCATION"
    azd env set TF_VAR_deployed_by "$deployer"
    
    info "Deployer: $deployer"
    success "Set TF_VAR_* in azd environment"
}

# Configure Terraform backend based on LOCAL_STATE environment variable
# When LOCAL_STATE=true, use local backend; otherwise use Azure Storage remote backend
configure_terraform_backend() {
    local backend_file="$SCRIPT_DIR/../../../infra/terraform/backend.tf"
    local provider_conf="$SCRIPT_DIR/../../../infra/terraform/provider.conf.json"
    local local_state="${LOCAL_STATE:-}"
    
    # Check if LOCAL_STATE is set in azd env
    if [[ -z "$local_state" ]]; then
        local_state=$(azd env get-value LOCAL_STATE 2>/dev/null || echo "")
    fi
    
    if [[ "$local_state" == "true" ]]; then
        log "Configuring Terraform for local state storage..."
        
        # Generate local backend configuration
        cat > "$backend_file" << 'EOF'
# ============================================================================
# TERRAFORM BACKEND CONFIGURATION - LOCAL STATE
# ============================================================================
# This file was auto-generated by preprovision.sh because LOCAL_STATE=true.
# State is stored locally in terraform.tfstate.
#
# WARNING: Local state is NOT shared with your team and may be lost if
# the .terraform/ directory is deleted. Use remote state for production.
#
# To switch to remote state:
#   azd env set LOCAL_STATE "false"
#   azd env set RS_RESOURCE_GROUP "<resource-group>"
#   azd env set RS_STORAGE_ACCOUNT "<storage-account>"
#   azd env set RS_CONTAINER_NAME "<container>"
#   azd hooks run preprovision

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
EOF
        
        # Remove provider.conf.json to avoid confusion
        if [[ -f "$provider_conf" ]]; then
            rm -f "$provider_conf"
            log "Removed provider.conf.json (not needed for local state)"
        fi
        
        success "Backend configured for local state"
        warn "State will be stored in infra/terraform/terraform.tfstate"
    else
        log "Configuring Terraform for Azure Storage remote state..."
        
        # Generate remote backend configuration
        cat > "$backend_file" << 'EOF'
# ============================================================================
# TERRAFORM BACKEND CONFIGURATION - AZURE REMOTE STATE
# ============================================================================
# This file was auto-generated by preprovision.sh.
# Backend values are provided via -backend-config=provider.conf.json during init.
#
# To switch to local state for development:
#   azd env set LOCAL_STATE "true"
#   azd hooks run preprovision

terraform {
  backend "azurerm" {
    use_azuread_auth = true
  }
}
EOF
        
        success "Backend configured for Azure Storage remote state"
        # Note: provider.conf.json is generated separately after initialize-terraform.sh
        # to ensure RS_* variables are set
    fi
}

# Generate provider.conf.json for remote state backend configuration
# azd uses this file to pass -backend-config values to terraform init
generate_provider_conf_json() {
    local provider_conf="$SCRIPT_DIR/../../../infra/terraform/provider.conf.json"
    
    # Get remote state configuration from azd env or environment variables
    local rs_resource_group="${RS_RESOURCE_GROUP:-}"
    local rs_storage_account="${RS_STORAGE_ACCOUNT:-}"
    local rs_container_name="${RS_CONTAINER_NAME:-}"
    
    # Try to get from azd env if not set
    if [[ -z "$rs_resource_group" ]]; then
        rs_resource_group=$(azd env get-value RS_RESOURCE_GROUP 2>/dev/null || echo "")
    fi
    if [[ -z "$rs_storage_account" ]]; then
        rs_storage_account=$(azd env get-value RS_STORAGE_ACCOUNT 2>/dev/null || echo "")
    fi
    if [[ -z "$rs_container_name" ]]; then
        rs_container_name=$(azd env get-value RS_CONTAINER_NAME 2>/dev/null || echo "")
    fi
    
    # Validate required values
    if [[ -z "$rs_resource_group" || -z "$rs_storage_account" || -z "$rs_container_name" ]]; then
        warn "Remote state variables not fully configured"
        warn "Set RS_RESOURCE_GROUP, RS_STORAGE_ACCOUNT, RS_CONTAINER_NAME via 'azd env set'"
        warn "Or run initialize-terraform.sh to create remote state storage"
        return 1
    fi
    
    # Always use environment name for state key to ensure consistency
    local rs_state_key="${AZURE_ENV_NAME}.tfstate"
    
    log "Generating provider.conf.json for remote state backend..."
    
    # Build JSON using jq for proper escaping
    local json_content
    json_content=$(jq -n \
        --arg rg "$rs_resource_group" \
        --arg sa "$rs_storage_account" \
        --arg container "$rs_container_name" \
        --arg key "$rs_state_key" \
        '{
            resource_group_name: $rg,
            storage_account_name: $sa,
            container_name: $container,
            key: $key
        }'
    )
    
    echo "$json_content" > "$provider_conf"
    success "Generated provider.conf.json"
    log "   resource_group_name: $rs_resource_group"
    log "   storage_account_name: $rs_storage_account"
    log "   container_name: $rs_container_name"
    log "   key: $rs_state_key"
}

# Generate main.tfvars.json from current azd environment
# This file is regenerated each time to stay in sync with the active azd environment
generate_tfvars_json() {
    local tfvars_json="$SCRIPT_DIR/../../../infra/terraform/main.tfvars.json"
    local deployer
    deployer=$(get_deployer_identity)
    
    log "Generating main.tfvars.json for environment: $AZURE_ENV_NAME"
    
    # Get principal ID if available
    local principal_id="${AZURE_PRINCIPAL_ID:-}"
    if [[ -z "$principal_id" ]] && command -v az &>/dev/null; then
        principal_id=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)
    fi
    
    # Build JSON using jq for proper escaping
    local json_content
    json_content=$(jq -n \
        --arg env "$AZURE_ENV_NAME" \
        --arg loc "$AZURE_LOCATION" \
        --arg deployer "$deployer" \
        --arg principal "${principal_id:-}" \
        '{
            environment_name: $env,
            location: $loc,
            deployed_by: $deployer
        } + (if $principal != "" then {principal_id: $principal} else {} end)'
    )
    
    echo "$json_content" > "$tfvars_json"
    success "Generated main.tfvars.json"
    log "   environment_name: $AZURE_ENV_NAME"
    log "   location: $AZURE_LOCATION"
    [[ -n "$principal_id" ]] && log "   principal_id: ${principal_id:0:8}..." || true
}

# ============================================================================
# Providers
# ============================================================================

provider_terraform() {
    header "🏗️  Terraform Pre-Provisioning"
    
    # Validate required variables
    if [[ -z "${AZURE_ENV_NAME:-}" ]]; then
        fail "AZURE_ENV_NAME is not set"
        footer
        exit 1
    fi
    
    # Resolve location using fallback chain
    if ! resolve_location; then
        fail "Could not resolve AZURE_LOCATION. Set it via 'azd env set AZURE_LOCATION <region>' or add to tfvars."
        footer
        exit 1
    fi
    
    info "Environment: $AZURE_ENV_NAME"
    info "Location: $AZURE_LOCATION"
    log ""
    
    # Configure backend based on LOCAL_STATE
    # This must happen before terraform init
    configure_terraform_backend
    
    # Generate main.tfvars.json from current azd environment
    # This ensures tfvars stays in sync when switching azd environments
    generate_tfvars_json
    
    # Run remote state initialization (only if not using local state)
    local local_state="${LOCAL_STATE:-}"
    if [[ -z "$local_state" ]]; then
        local_state=$(azd env get-value LOCAL_STATE 2>/dev/null) || local_state=""
    fi
    
    local tf_init="$SCRIPT_DIR/helpers/initialize-terraform.sh"
    if [[ "$local_state" != "true" ]] && [[ -f "$tf_init" ]]; then
        is_ci && export TF_INIT_SKIP_INTERACTIVE=true
        log "Setting up Terraform remote state..."
        bash "$tf_init"
        
        # Generate provider.conf.json AFTER initialize-terraform.sh
        # This ensures RS_* variables are set (either existing or newly created)
        log ""
        generate_provider_conf_json
    elif [[ "$local_state" == "true" ]]; then
        info "Using local state - skipping remote state initialization"
    else
        warn "initialize-terraform.sh not found, skipping remote state setup"
    fi
    
    log ""
    
    # Set Terraform variables via azd env
    # In CI, the workflow may pre-set TF_VAR_* - check before overwriting
    if is_ci; then
        # CI: Only set if not already configured by workflow
        if [[ -z "${TF_VAR_environment_name:-}" ]]; then
            log "Setting Terraform variables..."
            set_terraform_env_vars
        else
            info "CI mode: TF_VAR_* already set by workflow, skipping"
        fi
    else
        # Local: Always set to ensure consistency
        log "Setting Terraform variables..."
        set_terraform_env_vars
    fi
    
    footer
}

provider_bicep() {
    header "🔧 Bicep Pre-Provisioning"
    
    local ssl_script="$SCRIPT_DIR/helpers/ssl-preprovision.sh"
    
    if [[ ! -f "$ssl_script" ]]; then
        warn "ssl-preprovision.sh not found"
        footer
        return 0
    fi
    
    if is_ci; then
        info "CI/CD mode: Checking for SSL certificates..."
        if [[ -n "${SSL_CERT_BASE64:-}" && -n "${SSL_KEY_BASE64:-}" ]]; then
            echo "$SSL_CERT_BASE64" | base64 -d > "$SCRIPT_DIR/helpers/ssl-cert.pem"
            echo "$SSL_KEY_BASE64" | base64 -d > "$SCRIPT_DIR/helpers/ssl-key.pem"
            success "SSL certificates configured from environment"
        else
            warn "No SSL certificates in environment (set SSL_CERT_BASE64 and SSL_KEY_BASE64)"
        fi
    else
        log "Running SSL pre-provisioning..."
        bash "$ssl_script"
    fi
    
    footer
}

# ============================================================================
# Main
# ============================================================================

main() {
    if [[ -z "$PROVIDER" ]]; then
        fail "Usage: $0 <bicep|terraform>"
        exit 1
    fi
    
    is_ci && info "🤖 CI/CD mode detected"
    
    # Run preflight checks first (tools, auth, providers, ARM_SUBSCRIPTION_ID)
    local preflight_script="$SCRIPT_DIR/helpers/preflight-checks.sh"
    if [[ -f "$preflight_script" ]]; then
        # shellcheck source=helpers/preflight-checks.sh
        source "$preflight_script"
        if ! run_preflight_checks; then
            fail "Preflight checks failed. Please resolve the issues above before continuing."
            exit 1
        fi
    else
        warn "Preflight checks script not found, skipping environment validation"
    fi
    
    case "$PROVIDER" in
        terraform) provider_terraform ;;
        bicep)     provider_bicep ;;
        *)
            fail "Invalid provider: $PROVIDER (must be 'bicep' or 'terraform')"
            exit 1
            ;;
    esac
    
    success "Pre-provisioning complete!"
}

main "$@"
