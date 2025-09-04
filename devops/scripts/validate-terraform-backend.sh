#!/bin/bash

# validate-terraform-backend.sh
# Script to validate Terraform backend configuration

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info "Validating Terraform Backend Configuration"
echo "=========================================="

# Check if we're in the right directory
if [[ ! -f "Makefile" ]] || [[ ! -d "infra/terraform" ]]; then
    print_error "This script must be run from the project root directory"
    exit 1
fi

# Check required environment variables
if [[ -z "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
    print_error "AZURE_SUBSCRIPTION_ID environment variable is not set"
    echo "Please set it with: export AZURE_SUBSCRIPTION_ID=<your-subscription-id>"
    exit 1
fi

AZURE_ENV_NAME=${AZURE_ENV_NAME:-dev}
print_info "Environment: $AZURE_ENV_NAME"
print_info "Subscription: $AZURE_SUBSCRIPTION_ID"

# Check Azure CLI authentication
print_info "Checking Azure CLI authentication..."
if ! az account show --output none 2>/dev/null; then
    print_error "Not logged in to Azure CLI"
    echo "Please run: az login"
    exit 1
fi

# Validate current subscription
CURRENT_SUB=$(az account show --query id -o tsv)
if [[ "$CURRENT_SUB" != "$AZURE_SUBSCRIPTION_ID" ]]; then
    print_warning "Current subscription ($CURRENT_SUB) doesn't match AZURE_SUBSCRIPTION_ID"
    print_info "Setting subscription to $AZURE_SUBSCRIPTION_ID"
    az account set --subscription "$AZURE_SUBSCRIPTION_ID"
fi

print_success "Azure CLI authentication validated"

# Check Terraform installation
print_info "Checking Terraform installation..."
if ! command -v terraform &> /dev/null; then
    print_error "Terraform is not installed or not in PATH"
    echo "Please install Terraform: https://developer.hashicorp.com/terraform/downloads"
    exit 1
fi

TERRAFORM_VERSION=$(terraform version -json | jq -r '.terraform_version')
print_success "Terraform $TERRAFORM_VERSION is available"

# Check if Terraform is initialized
print_info "Checking Terraform initialization status..."
if [[ ! -f "infra/terraform/.terraform/terraform.tfstate" ]]; then
    print_warning "Terraform is not initialized"
    print_info "You can initialize it with: make terraform_init"
else
    print_success "Terraform is initialized"
    
    # Check backend type
    BACKEND_TYPE=$(grep '"type"' infra/terraform/.terraform/terraform.tfstate | head -1 | cut -d'"' -f4)
    if [[ "$BACKEND_TYPE" == "azurerm" ]]; then
        print_success "Remote backend (azurerm) is configured"
        
        # Extract backend configuration
        STORAGE_ACCOUNT=$(grep '"storage_account_name"' infra/terraform/.terraform/terraform.tfstate | cut -d'"' -f4)
        RESOURCE_GROUP=$(grep '"resource_group_name"' infra/terraform/.terraform/terraform.tfstate | cut -d'"' -f4)
        CONTAINER=$(grep '"container_name"' infra/terraform/.terraform/terraform.tfstate | cut -d'"' -f4)
        
        print_info "Backend Configuration:"
        echo "  Storage Account: $STORAGE_ACCOUNT"
        echo "  Resource Group:  $RESOURCE_GROUP"
        echo "  Container:       $CONTAINER"
        
        # Validate remote resources exist
        print_info "Validating remote backend resources..."
        
        if az group show --name "$RESOURCE_GROUP" --output none 2>/dev/null; then
            print_success "Resource group '$RESOURCE_GROUP' exists"
        else
            print_error "Resource group '$RESOURCE_GROUP' does not exist"
            echo "Run: make configure_terraform_remote_state"
            exit 1
        fi
        
        if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
            print_success "Storage account '$STORAGE_ACCOUNT' exists"
        else
            print_error "Storage account '$STORAGE_ACCOUNT' does not exist"
            echo "Run: make configure_terraform_remote_state"
            exit 1
        fi
        
        if az storage container show --name "$CONTAINER" --account-name "$STORAGE_ACCOUNT" --auth-mode login --output none 2>/dev/null; then
            print_success "Storage container '$CONTAINER' exists"
        else
            print_error "Storage container '$CONTAINER' does not exist"
            echo "Run: make configure_terraform_remote_state"
            exit 1
        fi
        
    elif [[ "$BACKEND_TYPE" == "local" ]]; then
        print_warning "Local backend is configured (not recommended for production)"
        print_info "Consider configuring remote state with: make configure_terraform_remote_state"
    else
        print_warning "Unknown backend type: $BACKEND_TYPE"
    fi
fi

# Test terraform commands
print_info "Testing basic Terraform operations..."
cd infra/terraform

if terraform validate; then
    print_success "Terraform configuration is valid"
else
    print_error "Terraform configuration validation failed"
    exit 1
fi

if terraform fmt -check; then
    print_success "Terraform formatting is correct"
else
    print_warning "Terraform files need formatting (run: terraform fmt)"
fi

print_success "All validations passed!"
echo ""
print_info "Your Terraform backend is properly configured and ready for use."
