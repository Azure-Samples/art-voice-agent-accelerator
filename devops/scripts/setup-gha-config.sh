#!/bin/bash

# ========================================================================
# 🚀 Setup CI/CD Configuration for Azure Developer CLI (AZD) Deployment
# ========================================================================
# This script provisions GitHub Actions secrets and variables needed for
# automated deployment using Azure Developer CLI (azd) with OIDC authentication.
#
# Based on: https://learn.microsoft.com/en-us/azure/container-apps/github-actions-cli
# Usage: ./setup-cicd-config.sh [--interactive] [--help]

set -euo pipefail

# ========================================================================
# CONFIGURATION & CONSTANTS
# ========================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly APP_REGISTRATION_NAME="GitHub-Actions-RTAudio-AZD"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Default values
INTERACTIVE_MODE=false
GITHUB_ORG=""
GITHUB_REPO=""
AZURE_LOCATION="eastus"
AZURE_ENV_NAME="dev"

# ========================================================================
# HELPER FUNCTIONS
# ========================================================================

log_info() {
    echo -e "${BLUE}ℹ️  [INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}✅ [SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}⚠️  [WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}❌ [ERROR]${NC} $*" >&2
}

log_section() {
    echo ""
    echo -e "${CYAN}🔧 $*${NC}"
    echo "========================================================================="
}

show_help() {
    cat << EOF
🚀 Setup CI/CD Configuration for Azure Developer CLI (AZD) Deployment

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --interactive    Run in interactive mode (prompts for all values)
    --help          Show this help message

DESCRIPTION:
    This script sets up GitHub Actions secrets and variables for automated
    deployment using Azure Developer CLI (azd) with OIDC authentication.

    It will:
    1. Create Azure App Registration for OIDC authentication
    2. Configure federated credentials for GitHub Actions
    3. Assign necessary Azure permissions
    4. Set up Terraform remote state storage
    5. Display the secrets/variables to configure in GitHub

PREREQUISITES:
    - Azure CLI installed and authenticated
    - GitHub CLI installed and authenticated (optional)
    - Contributor permissions on Azure subscription
    - GitHub repository already created

ENVIRONMENT VARIABLES:
    GITHUB_ORG       GitHub organization/user name
    GITHUB_REPO      GitHub repository name
    AZURE_LOCATION   Azure region (default: eastus)
    AZURE_ENV_NAME   Environment name (default: dev)

EXAMPLES:
    # Interactive mode
    $0 --interactive

    # Using environment variables
    GITHUB_ORG=myorg GITHUB_REPO=myrepo $0

    # With custom values
    AZURE_LOCATION=westus2 AZURE_ENV_NAME=prod $0

EOF
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    local deps=("az" "jq")
    local missing=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            missing+=("$dep")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_error "Please install them and try again"
        exit 1
    fi
    
    # Check if GitHub CLI is available (optional)
    if command -v "gh" &> /dev/null; then
        log_info "GitHub CLI detected (optional features available)"
    else
        log_warning "GitHub CLI not found (manual secret configuration required)"
    fi
    
    log_success "Dependencies verified"
}

check_azure_auth() {
    log_info "Checking Azure authentication..."
    
    if ! az account show &> /dev/null; then
        log_error "Azure CLI not authenticated"
        log_error "Please run 'az login' first"
        exit 1
    fi
    
    local subscription_name
    subscription_name=$(az account show --query "name" -o tsv)
    log_success "Authenticated to Azure subscription: $subscription_name"
}

prompt_for_values() {
    if [[ "$INTERACTIVE_MODE" == "true" ]] || [[ -z "$GITHUB_ORG" ]] || [[ -z "$GITHUB_REPO" ]]; then
        echo ""
        log_info "Please provide the following information:"
        
        if [[ -z "$GITHUB_ORG" ]]; then
            read -p "GitHub organization/username: " GITHUB_ORG
        fi
        
        if [[ -z "$GITHUB_REPO" ]]; then
            read -p "GitHub repository name: " GITHUB_REPO
        fi
        
        if [[ "$INTERACTIVE_MODE" == "true" ]]; then
            read -p "Azure location [$AZURE_LOCATION]: " input_location
            AZURE_LOCATION="${input_location:-$AZURE_LOCATION}"
            
            read -p "Environment name [$AZURE_ENV_NAME]: " input_env
            AZURE_ENV_NAME="${input_env:-$AZURE_ENV_NAME}"
        fi
    fi
    
    # Validate required values
    if [[ -z "$GITHUB_ORG" ]] || [[ -z "$GITHUB_REPO" ]]; then
        log_error "GitHub organization and repository name are required"
        log_error "Set GITHUB_ORG and GITHUB_REPO environment variables or use --interactive"
        exit 1
    fi
    
    log_info "Configuration:"
    log_info "  GitHub: $GITHUB_ORG/$GITHUB_REPO"
    log_info "  Azure Location: $AZURE_LOCATION"
    log_info "  Environment: $AZURE_ENV_NAME"
}

create_app_registration() {
    log_section "Creating Azure App Registration for OIDC"
    
    # Check if app registration already exists
    local existing_app_id
    existing_app_id=$(az ad app list --display-name "$APP_REGISTRATION_NAME" --query "[0].appId" -o tsv 2>/dev/null || echo "")
    
    if [[ -n "$existing_app_id" && "$existing_app_id" != "null" ]]; then
        log_warning "App registration '$APP_REGISTRATION_NAME' already exists"
        APP_ID="$existing_app_id"
    else
        log_info "Creating app registration: $APP_REGISTRATION_NAME"
        APP_ID=$(az ad app create --display-name "$APP_REGISTRATION_NAME" --query "appId" -o tsv)
        
        # Create service principal
        log_info "Creating service principal..."
        az ad sp create --id "$APP_ID" > /dev/null
        
        log_success "Created app registration: $APP_ID"
    fi
    
    # Get tenant and subscription info
    TENANT_ID=$(az account show --query "tenantId" -o tsv)
    SUBSCRIPTION_ID=$(az account show --query "id" -o tsv)
    SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query "id" -o tsv)
    
    log_info "App Registration Details:"
    log_info "  Application ID: $APP_ID"
    log_info "  Tenant ID: $TENANT_ID"
    log_info "  Subscription ID: $SUBSCRIPTION_ID"
    log_info "  Service Principal Object ID: $SP_OBJECT_ID"
}

configure_federated_credentials() {
    log_section "Configuring OIDC Federated Credentials"
    
    local credentials=(
        "main-branch:repo:$GITHUB_ORG/$GITHUB_REPO:ref:refs/heads/main:Main branch deployments"
        "cleanup-deployment:repo:$GITHUB_ORG/$GITHUB_REPO:ref:refs/heads/cleanup/deployment:Cleanup deployment branch"
        "pull-requests:repo:$GITHUB_ORG/$GITHUB_REPO:pull_request:Pull request validation"
        "workflow-dispatch:repo:$GITHUB_ORG/$GITHUB_REPO:environment:$AZURE_ENV_NAME:Manual workflow triggers"
    )
    
    for credential in "${credentials[@]}"; do
        IFS=':' read -r name subject_prefix org_repo subject_suffix description <<< "$credential"
        local full_subject="${subject_prefix}:${org_repo}:${subject_suffix}"
        
        log_info "Creating federated credential: $name"
        
        # Check if credential already exists
        local existing_cred
        existing_cred=$(az ad app federated-credential list --id "$APP_ID" --query "[?name=='$name'].name" -o tsv 2>/dev/null || echo "")
        
        if [[ -n "$existing_cred" ]]; then
            log_warning "Federated credential '$name' already exists, skipping..."
            continue
        fi
        
        # Create the federated credential
        az ad app federated-credential create \
            --id "$APP_ID" \
            --parameters "{
                \"name\": \"$name\",
                \"issuer\": \"https://token.actions.githubusercontent.com\",
                \"subject\": \"$full_subject\",
                \"description\": \"$description\",
                \"audiences\": [\"api://AzureADTokenExchange\"]
            }" > /dev/null
        
        log_success "Created federated credential: $name"
    done
}

assign_azure_permissions() {
    log_section "Assigning Azure Permissions"
    
    local roles=("Contributor" "User Access Administrator")
    
    for role in "${roles[@]}"; do
        log_info "Assigning '$role' role to service principal..."
        
        # Check if role assignment already exists
        local existing_assignment
        existing_assignment=$(az role assignment list \
            --assignee "$SP_OBJECT_ID" \
            --role "$role" \
            --scope "/subscriptions/$SUBSCRIPTION_ID" \
            --query "[0].id" -o tsv 2>/dev/null || echo "")
        
        if [[ -n "$existing_assignment" && "$existing_assignment" != "null" ]]; then
            log_warning "Role '$role' already assigned, skipping..."
            continue
        fi
        
        az role assignment create \
            --assignee "$SP_OBJECT_ID" \
            --role "$role" \
            --scope "/subscriptions/$SUBSCRIPTION_ID" > /dev/null
        
        log_success "Assigned '$role' role"
    done
}

setup_terraform_state_storage() {
    log_section "Setting up Terraform Remote State Storage"
    
    local resource_group="rg-terraform-state-${AZURE_ENV_NAME}"
    local storage_account="tfstate${AZURE_ENV_NAME}$(openssl rand -hex 4)"
    local container_name="tfstate"
    
    log_info "Creating resource group: $resource_group"
    az group create \
        --name "$resource_group" \
        --location "$AZURE_LOCATION" \
        --tags "purpose=terraform-state" "environment=$AZURE_ENV_NAME" > /dev/null
    
    log_info "Creating storage account: $storage_account"
    az storage account create \
        --name "$storage_account" \
        --resource-group "$resource_group" \
        --location "$AZURE_LOCATION" \
        --sku "Standard_LRS" \
        --encryption-services blob \
        --allow-blob-public-access false \
        --tags "purpose=terraform-state" "environment=$AZURE_ENV_NAME" > /dev/null
    
    log_info "Creating container: $container_name"
    az storage container create \
        --name "$container_name" \
        --account-name "$storage_account" \
        --auth-mode login > /dev/null
    
    # Assign permissions to service principal for state storage
    log_info "Assigning storage permissions to service principal..."
    az role assignment create \
        --assignee "$SP_OBJECT_ID" \
        --role "Storage Blob Data Contributor" \
        --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$resource_group/providers/Microsoft.Storage/storageAccounts/$storage_account" > /dev/null
    
    # Store values for later use
    TF_RESOURCE_GROUP="$resource_group"
    TF_STORAGE_ACCOUNT="$storage_account"
    TF_CONTAINER_NAME="$container_name"
    
    log_success "Terraform state storage configured"
    log_info "  Resource Group: $TF_RESOURCE_GROUP"
    log_info "  Storage Account: $TF_STORAGE_ACCOUNT"
    log_info "  Container: $TF_CONTAINER_NAME"
}

configure_github_secrets() {
    log_section "GitHub Repository Configuration"
    
    if command -v "gh" &> /dev/null && gh auth status &> /dev/null; then
        log_info "GitHub CLI detected and authenticated"
        
        # Ask if user wants to automatically configure secrets
        if [[ "$INTERACTIVE_MODE" == "true" ]]; then
            read -p "Automatically configure GitHub secrets and variables? (y/N): " configure_auto
            if [[ "$configure_auto" =~ ^[Yy]$ ]]; then
                setup_github_secrets_auto
                return
            fi
        fi
    fi
    
    # Manual configuration instructions
    show_manual_configuration
}

setup_github_secrets_auto() {
    log_info "Configuring GitHub secrets and variables automatically..."
    
    # Set repository secrets
    local secrets=(
        "AZURE_CLIENT_ID:$APP_ID"
        "AZURE_TENANT_ID:$TENANT_ID"
        "AZURE_SUBSCRIPTION_ID:$SUBSCRIPTION_ID"
        "AZURE_PRINCIPAL_ID:$SP_OBJECT_ID"
    )
    
    for secret in "${secrets[@]}"; do
        IFS=':' read -r name value <<< "$secret"
        log_info "Setting secret: $name"
        echo "$value" | gh secret set "$name" --repo "$GITHUB_ORG/$GITHUB_REPO"
    done
    
    # Set repository variables
    local variables=(
        "AZURE_LOCATION:$AZURE_LOCATION"
        "AZURE_ENV_NAME:$AZURE_ENV_NAME"
        "RS_RESOURCE_GROUP:$TF_RESOURCE_GROUP"
        "RS_STORAGE_ACCOUNT:$TF_STORAGE_ACCOUNT"
        "RS_CONTAINER_NAME:$TF_CONTAINER_NAME"
    )
    
    for variable in "${variables[@]}"; do
        IFS=':' read -r name value <<< "$variable"
        log_info "Setting variable: $name"
        echo "$value" | gh variable set "$name" --repo "$GITHUB_ORG/$GITHUB_REPO"
    done
    
    log_success "GitHub secrets and variables configured automatically!"
}

show_manual_configuration() {
    cat << EOF

${CYAN}📝 Manual GitHub Configuration Required${NC}
========================================================================

Navigate to your GitHub repository: https://github.com/$GITHUB_ORG/$GITHUB_REPO
Go to Settings → Secrets and variables → Actions

${YELLOW}Repository Secrets:${NC}
Add these under "Repository secrets":

AZURE_CLIENT_ID: $APP_ID
AZURE_TENANT_ID: $TENANT_ID
AZURE_SUBSCRIPTION_ID: $SUBSCRIPTION_ID
AZURE_PRINCIPAL_ID: $SP_OBJECT_ID

${YELLOW}Repository Variables:${NC}
Add these under "Repository variables":

AZURE_LOCATION: $AZURE_LOCATION
AZURE_ENV_NAME: $AZURE_ENV_NAME
RS_RESOURCE_GROUP: $TF_RESOURCE_GROUP
RS_STORAGE_ACCOUNT: $TF_STORAGE_ACCOUNT
RS_CONTAINER_NAME: $TF_CONTAINER_NAME

${YELLOW}Optional Secrets:${NC}
If you have an ACS phone number:

ACS_SOURCE_PHONE_NUMBER: +1234567890

EOF
}

create_summary_file() {
    local summary_file="$PROJECT_ROOT/.azd-cicd-config.txt"
    
    cat > "$summary_file" << EOF
# Azure Developer CLI (AZD) CI/CD Configuration Summary
# Generated on: $(date)
# Script: $0

## Azure App Registration
Application ID: $APP_ID
Tenant ID: $TENANT_ID
Subscription ID: $SUBSCRIPTION_ID
Service Principal Object ID: $SP_OBJECT_ID

## Terraform State Storage
Resource Group: $TF_RESOURCE_GROUP
Storage Account: $TF_STORAGE_ACCOUNT
Container: $TF_CONTAINER_NAME

## GitHub Repository
Organization/User: $GITHUB_ORG
Repository: $GITHUB_REPO
URL: https://github.com/$GITHUB_ORG/$GITHUB_REPO

## Next Steps
1. Configure GitHub secrets and variables (see output above)
2. Test the deployment workflow
3. Purchase ACS phone number if needed
4. Configure environment-specific settings

## Useful Commands
# Test authentication
az login --service-principal --username $APP_ID --tenant $TENANT_ID

# View role assignments
az role assignment list --assignee $SP_OBJECT_ID --output table

# Test azd deployment
azd auth login --client-id $APP_ID --federated-credential-provider github --tenant-id $TENANT_ID
azd up

EOF

    log_success "Configuration summary saved to: $summary_file"
}

verify_configuration() {
    log_section "Verifying Configuration"
    
    # Test service principal permissions
    log_info "Testing service principal permissions..."
    local test_result
    test_result=$(az role assignment list --assignee "$SP_OBJECT_ID" --output table 2>/dev/null | wc -l)
    
    if [[ "$test_result" -gt 1 ]]; then
        log_success "Service principal has role assignments"
    else
        log_warning "Service principal may not have proper permissions"
    fi
    
    # Test federated credentials
    log_info "Checking federated credentials..."
    local cred_count
    cred_count=$(az ad app federated-credential list --id "$APP_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
    
    if [[ "$cred_count" -gt 0 ]]; then
        log_success "Found $cred_count federated credential(s)"
    else
        log_warning "No federated credentials found"
    fi
    
    # Test storage account access
    log_info "Testing storage account access..."
    if az storage container show --name "$TF_CONTAINER_NAME" --account-name "$TF_STORAGE_ACCOUNT" --auth-mode login &> /dev/null; then
        log_success "Storage account accessible"
    else
        log_warning "Storage account access may be limited"
    fi
}

# ========================================================================
# MAIN EXECUTION
# ========================================================================

main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --interactive)
                INTERACTIVE_MODE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Set values from environment variables if provided
    GITHUB_ORG="${GITHUB_ORG:-}"
    GITHUB_REPO="${GITHUB_REPO:-}"
    AZURE_LOCATION="${AZURE_LOCATION:-eastus}"
    AZURE_ENV_NAME="${AZURE_ENV_NAME:-dev}"
    
    # Display banner
    echo -e "${CYAN}"
    echo "🚀 Azure Developer CLI (AZD) CI/CD Configuration Setup"
    echo "======================================================="
    echo -e "${NC}"
    
    # Run setup steps
    check_dependencies
    check_azure_auth
    prompt_for_values
    
    log_info "Starting CI/CD configuration setup..."
    
    create_app_registration
    configure_federated_credentials
    assign_azure_permissions
    setup_terraform_state_storage
    configure_github_secrets
    verify_configuration
    create_summary_file
    
    echo ""
    log_success "🎉 CI/CD configuration setup completed!"
    log_info "Your azd deployment workflows should now be ready to run."
    log_info "Test your setup by pushing to the main or cleanup/deployment branch."
    
    echo ""
    echo -e "${YELLOW}💡 Next Steps:${NC}"
    echo "1. Review the configuration summary file"
    echo "2. Test the GitHub Actions workflow"
    echo "3. Purchase an ACS phone number if needed"
    echo "4. Configure any additional environment-specific settings"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
