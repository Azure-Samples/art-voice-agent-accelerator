#!/bin/bash

# ==============================================================================
# Environment File Generation from Terraform Remote State
# ==============================================================================
# This script extracts values from Terraform remote state and creates a local
# .env file matching the project's expected format.
#
# Usage:
#   ./generate-env-from-terraform.sh [environment_name] [subscription_id]
#
# Parameters:
#   environment_name    - Environment name (default: dev)
#   subscription_id     - Azure subscription ID (auto-detected if not provided)
#
# Requirements:
#   - terraform CLI installed and configured
#   - Azure CLI installed and authenticated
#   - Terraform state properly initialized with remote backend
# ==============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${PROJECT_ROOT}/infra/terraform"

# Default values
AZURE_ENV_NAME="${1:-${AZURE_ENV_NAME:-dev}}"
AZURE_SUBSCRIPTION_ID="${2:-${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv 2>/dev/null || echo "")}}"
ENV_FILE="${PROJECT_ROOT}/.env.${AZURE_ENV_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_section() {
    echo ""
    echo -e "${CYAN}🔧 $1${NC}"
    echo "============================================================"
}

# Validation functions
check_prerequisites() {
    log_section "Checking Prerequisites"
    
    # Check terraform CLI
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform CLI is not installed or not in PATH"
        exit 1
    fi
    log_info "Terraform CLI: $(terraform version | head -1)"
    
    # Check Azure CLI
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI is not installed or not in PATH"
        exit 1
    fi
    log_info "Azure CLI: $(az version --query '"azure-cli"' -o tsv)"
    
    # Check jq for JSON parsing (optional but recommended for performance)
    if command -v jq &> /dev/null; then
        log_info "jq: $(jq --version) (optimal performance mode)"
    else
        log_warning "jq not found - falling back to individual terraform output calls"
        log_warning "For better performance, install jq:"
        log_warning "  macOS: brew install jq"
        log_warning "  Ubuntu/Debian: apt-get install jq"
        log_warning "  RHEL/CentOS: yum install jq"
    fi
    
    # Check Azure CLI authentication
    if ! az account show &> /dev/null; then
        log_error "Azure CLI is not authenticated. Run 'az login' first"
        exit 1
    fi
    
    # Validate subscription ID
    if [[ -z "${AZURE_SUBSCRIPTION_ID}" ]]; then
        log_error "AZURE_SUBSCRIPTION_ID is not set"
        log_error "Please provide it as a parameter or set the environment variable"
        exit 1
    fi
    log_info "Azure Subscription: ${AZURE_SUBSCRIPTION_ID}"
    
    # Check Terraform directory
    if [[ ! -d "${TF_DIR}" ]]; then
        log_error "Terraform directory not found: ${TF_DIR}"
        exit 1
    fi
    
    # Check Terraform initialization
    if [[ ! -f "${TF_DIR}/.terraform/terraform.tfstate" ]]; then
        log_error "Terraform is not initialized in ${TF_DIR}"
        log_error "Run 'terraform init' in the terraform directory first"
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

# Get all Terraform outputs in one operation for efficiency
get_all_terraform_outputs() {
    local outputs_json
    
    # Change to terraform directory, get all outputs, then return
    pushd "${TF_DIR}" > /dev/null
    outputs_json=$(terraform output -json 2>/dev/null || echo "{}")
    popd > /dev/null
    
    echo "${outputs_json}"
}

# Extract specific output value from JSON with error handling
extract_output_value() {
    local outputs_json="$1"
    local output_name="$2"
    local default_value="${3:-}"
    
    # Try jq first if available, otherwise fallback to terraform output -raw
    if command -v jq &> /dev/null; then
        local value
        value=$(echo "${outputs_json}" | jq -r ".\"${output_name}\".value // \"${default_value}\"" 2>/dev/null || echo "${default_value}")
        echo "${value}"
    else
        # Fallback: use terraform output -raw for individual values
        pushd "${TF_DIR}" > /dev/null
        local value
        value=$(terraform output -raw "${output_name}" 2>/dev/null || echo "${default_value}")
        popd > /dev/null
        echo "${value}"
    fi
}

# Generate environment file
generate_env_file() {
    log_section "Generating Environment File from Terraform State"
    
    log_info "Extracting values from Terraform remote state..."
    log_info "Target file: ${ENV_FILE}"
    
    # Get all Terraform outputs in one operation
    log_info "Fetching all Terraform outputs..."
    local terraform_outputs
    terraform_outputs=$(get_all_terraform_outputs)
    
    # Create the environment file with header
    cat > "${ENV_FILE}" << EOF
# Generated automatically on $(date)
# Environment: ${AZURE_ENV_NAME}
# Source: Terraform remote state
# Subscription: ${AZURE_SUBSCRIPTION_ID}
# =================================================================

EOF

    # Application Insights Configuration
    cat >> "${ENV_FILE}" << EOF
# Application Insights Configuration
APPLICATIONINSIGHTS_CONNECTION_STRING=$(extract_output_value "${terraform_outputs}" "APPLICATIONINSIGHTS_CONNECTION_STRING")

EOF

    # Azure OpenAI Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure OpenAI Configuration
AZURE_OPENAI_KEY=
AZURE_OPENAI_ENDPOINT=$(extract_output_value "${terraform_outputs}" "AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=$(extract_output_value "${terraform_outputs}" "AZURE_OPENAI_API_VERSION" "2025-01-01-preview")
AZURE_OPENAI_CHAT_DEPLOYMENT_ID=$(extract_output_value "${terraform_outputs}" "AZURE_OPENAI_CHAT_DEPLOYMENT_ID" "gpt-4o")
AZURE_OPENAI_CHAT_DEPLOYMENT_VERSION=2024-10-01-preview

EOF

    # Azure Speech Services Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Speech Services Configuration
AZURE_SPEECH_ENDPOINT=$(extract_output_value "${terraform_outputs}" "AZURE_SPEECH_ENDPOINT")
AZURE_SPEECH_KEY=
AZURE_SPEECH_RESOURCE_ID=$(extract_output_value "${terraform_outputs}" "AZURE_SPEECH_RESOURCE_ID")
AZURE_SPEECH_REGION=$(extract_output_value "${terraform_outputs}" "AZURE_SPEECH_REGION")

# For local development, you can enable local playback of TTS audio.
TTS_ENABLE_LOCAL_PLAYBACK=true
EOF

    # Base URL Configuration
    cat >> "${ENV_FILE}" << EOF
# Base URL Configuration
# Prompt user for BASE_URL if not set in azd env
BASE_URL="<Set this to enable ACS callbacks to the app>"

# Backend App Service/Container App URL (from Terraform output if available)
BACKEND_APP_SERVICE_URL=$(extract_output_value "${terraform_outputs}" "BACKEND_APP_SERVICE_URL" "<Set this if using App Service deployment>")
BACKEND_CONTAINER_APP_URL=$(extract_output_value "${terraform_outputs}" "BACKEND_CONTAINER_APP_URL" "<Set this if using Container App deployment>")
EOF

    # Azure Communication Services Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Communication Services Configuration
ACS_CONNECTION_STRING=$(extract_output_value "${terraform_outputs}" "ACS_CONNECTION_STRING")
ACS_SOURCE_PHONE_NUMBER=$(extract_output_value "${terraform_outputs}" "ACS_SOURCE_PHONE_NUMBER")
ACS_ENDPOINT=$(extract_output_value "${terraform_outputs}" "ACS_ENDPOINT")

EOF

    # Redis Configuration
    cat >> "${ENV_FILE}" << EOF
# Redis Configuration
REDIS_HOST=$(extract_output_value "${terraform_outputs}" "REDIS_HOSTNAME")
REDIS_PORT=$(extract_output_value "${terraform_outputs}" "REDIS_PORT" "10000")
REDIS_PASSWORD=

EOF

    # Azure Storage Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=$(extract_output_value "${terraform_outputs}" "AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_URL=$(extract_output_value "${terraform_outputs}" "AZURE_STORAGE_CONTAINER_URL")
AZURE_STORAGE_ACCOUNT_NAME=$(extract_output_value "${terraform_outputs}" "AZURE_STORAGE_ACCOUNT_NAME")

EOF

    # Azure Cosmos DB Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Cosmos DB Configuration
AZURE_COSMOS_DATABASE_NAME=$(extract_output_value "${terraform_outputs}" "AZURE_COSMOS_DATABASE_NAME" "audioagentdb")
AZURE_COSMOS_COLLECTION_NAME=$(extract_output_value "${terraform_outputs}" "AZURE_COSMOS_COLLECTION_NAME" "audioagentcollection")
AZURE_COSMOS_CONNECTION_STRING=$(extract_output_value "${terraform_outputs}" "AZURE_COSMOS_CONNECTION_STRING")

EOF

    # Azure Identity Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Identity Configuration
AZURE_SUBSCRIPTION_ID=${AZURE_SUBSCRIPTION_ID}

EOF

    # Azure Resource Configuration
    cat >> "${ENV_FILE}" << EOF
# Azure Resource Configuration
AZURE_RESOURCE_GROUP=$(extract_output_value "${terraform_outputs}" "AZURE_RESOURCE_GROUP")
AZURE_LOCATION=$(extract_output_value "${terraform_outputs}" "AZURE_LOCATION")

EOF

    # Application Configuration
    cat >> "${ENV_FILE}" << EOF
# Application Configuration
ACS_STREAMING_MODE=media # Options: media, transcription
ENVIRONMENT=${AZURE_ENV_NAME}

EOF

#     # Logging Configuration
#     cat >> "${ENV_FILE}" << EOF
# # Logging Configuration
# LOG_LEVEL=INFO
# ENABLE_DEBUG=false
# EOF

    # Generate summary
    local var_count
    var_count=$(grep -c '^[A-Z]' "${ENV_FILE}")
    
    log_success "Environment file generated successfully: ${ENV_FILE}"
    log_info "Configuration contains ${var_count} variables"
    echo ""
    log_warning "Note: Some values like keys and connection strings may be empty"
    log_warning "These sensitive values should be retrieved separately using Azure CLI or Key Vault"
    echo ""
    log_info "Next steps:"
    echo "   1. Review the generated file: cat ${ENV_FILE}"
    echo "   2. Set missing sensitive values (keys, connection strings)"
    echo "   3. Update BASE_URL with your actual backend URL"
    echo "   4. Source the file: source ${ENV_FILE}"
}

# Update environment file with secrets from Key Vault
update_env_with_secrets() {
    log_section "Updating Environment File with Secrets from Key Vault"
    
    if [[ ! -f "${ENV_FILE}" ]]; then
        log_error "Environment file ${ENV_FILE} does not exist"
        log_error "Run this script first to generate the base file"
        exit 1
    fi
    
    log_info "Retrieving secrets from Azure Key Vault..."
    
    # Get Key Vault name from Terraform (single operation)
    local terraform_outputs
    terraform_outputs=$(get_all_terraform_outputs)
    local kv_name
    kv_name=$(extract_output_value "${terraform_outputs}" "AZURE_KEY_VAULT_NAME")
    
    if [[ -n "${kv_name}" && "${kv_name}" != "null" ]]; then
        log_info "Using Key Vault: ${kv_name}"
        
        # Helper function to update environment variable
        update_env_var() {
            local var_name="$1"
            local secret_name="$2"
            local secret_value
            
            log_info "Updating ${var_name}..."
            secret_value=$(az keyvault secret show --name "${secret_name}" --vault-name "${kv_name}" --query value -o tsv 2>/dev/null || echo "")
            
            if [[ -n "${secret_value}" ]]; then
                # Use different sed syntax for different variable types
                if [[ "${var_name}" == *"CONNECTION_STRING"* ]]; then
                    sed -i.bak "s|^${var_name}=.*|${var_name}=${secret_value}|" "${ENV_FILE}"
                else
                    sed -i.bak "s/^${var_name}=.*/${var_name}=${secret_value}/" "${ENV_FILE}"
                fi
                log_success "${var_name} updated"
            else
                log_warning "${var_name} secret not found in Key Vault"
            fi
        }
        
        # Update secrets
        update_env_var "AZURE_OPENAI_KEY" "AZURE-OPENAI-KEY"
        update_env_var "AZURE_SPEECH_KEY" "AZURE-SPEECH-KEY"
        update_env_var "ACS_CONNECTION_STRING" "ACS-CONNECTION-STRING"
        update_env_var "REDIS_PASSWORD" "REDIS-PASSWORD"
        update_env_var "AZURE_STORAGE_CONNECTION_STRING" "AZURE-STORAGE-CONNECTION-STRING"
        
        # Clean up backup file
        rm -f "${ENV_FILE}.bak"
        
        log_success "Secrets updated successfully"
    else
        log_warning "Key Vault name not found in Terraform outputs"
        log_warning "Secrets will need to be set manually"
    fi
}

# Show environment file information
show_env_file() {
    if [[ -f "${ENV_FILE}" ]]; then
        log_info "Current environment file: ${ENV_FILE}"
        local generation_date
        generation_date=$(head -1 "${ENV_FILE}" | sed 's/# Generated automatically on //')
        log_info "Generated: ${generation_date}"
        local var_count
        var_count=$(grep -c '^[A-Z]' "${ENV_FILE}")
        log_info "Variables: ${var_count}"
        echo ""
        echo "Content preview:"
        echo "================"
        head -20 "${ENV_FILE}"
        echo "... (truncated, use 'cat ${ENV_FILE}' to see full content)"
    else
        log_error "Environment file ${ENV_FILE} does not exist"
        log_error "Run this script to create it"
    fi
}

# Main execution
main() {
    local action="${3:-generate}"
    
    case "${action}" in
        "generate")
            check_prerequisites
            generate_env_file
            ;;
        "update-secrets")
            check_prerequisites
            update_env_with_secrets
            ;;
        "show")
            show_env_file
            ;;
        *)
            echo "Usage: $0 [environment_name] [subscription_id] [action]"
            echo ""
            echo "Actions:"
            echo "  generate        Generate .env file from Terraform state (default)"
            echo "  update-secrets  Update .env file with Key Vault secrets"
            echo "  show           Show current .env file information"
            echo ""
            echo "Examples:"
            echo "  $0 dev"
            echo "  $0 prod \${AZURE_SUBSCRIPTION_ID}"
            echo "  $0 dev \${AZURE_SUBSCRIPTION_ID} update-secrets"
            exit 1
            ;;
    esac
}

# Execute main function with all parameters
main "$@"
