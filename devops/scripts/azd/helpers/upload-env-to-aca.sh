#!/bin/bash

# Script to upload environment variables from .env file to existing Azure Container App
# Usage: ./upload-env-to-aca.sh [container-app-name] [resource-group] [env-file]

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to read environment variables from .env file
read_env_file() {
    local env_file="$1"
    
    if [[ ! -f "$env_file" ]]; then
        print_error "Environment file '$env_file' not found"
        exit 1
    fi
    
    print_info "Reading environment variables from '$env_file'..."
    
    # Clear the array first
    ENV_VARS=()
    
    # Read the .env file and process each line
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comments
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        
        # Remove leading/trailing whitespace
        line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        
        # Check if line contains =
        if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            ENV_VARS+=("$line")
            # Extract variable name for logging (before the =)
            var_name=$(echo "$line" | cut -d= -f1)
            print_info "  Found variable: $var_name"
        else
            print_warning "  Skipping invalid line: $line"
        fi
    done < "$env_file"
    
    print_success "Read ${#ENV_VARS[@]} environment variables from '$env_file'"
}

# Function to prompt for variable with default
prompt_for_variable() {
    local var_name="$1"
    local prompt_text="$2"
    local default_value="$3"
    
    if [[ -n "$default_value" ]]; then
        read -p "$prompt_text [$default_value]: " user_input
        if [[ -z "$user_input" ]]; then
            eval "$var_name=\"$default_value\""
        else
            eval "$var_name=\"$user_input\""
        fi
    else
        read -p "$prompt_text: " user_input
        eval "$var_name=\"$user_input\""
    fi
}

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    print_error "Azure CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is logged in to Azure
if ! az account show &> /dev/null; then
    print_error "Please log in to Azure CLI first: az login"
    exit 1
fi

print_info "Starting environment variable upload to Azure Container App..."

# Get parameters from command line or prompt
CONTAINER_APP_NAME="$1"
RESOURCE_GROUP="$2"
ENV_FILE="$3"

# Set defaults based on your existing script
RESOURCE_GROUP=${RESOURCE_GROUP:-ai-realtime-sandbox}
CONTAINER_APP_NAME=${CONTAINER_APP_NAME:-rtinsuranceagentserver}
ENV_FILE=${ENV_FILE:-.env}

# Prompt for missing values
if [[ -z "$CONTAINER_APP_NAME" ]]; then
    prompt_for_variable "CONTAINER_APP_NAME" "Enter Container App name" "rtinsuranceagentserver"
fi

if [[ -z "$RESOURCE_GROUP" ]]; then
    prompt_for_variable "RESOURCE_GROUP" "Enter Resource Group name" "ai-realtime-sandbox"
fi

if [[ -z "$ENV_FILE" ]]; then
    prompt_for_variable "ENV_FILE" "Enter .env file path" ".env"
fi

print_info "Configuration:"
echo "  Container App: $CONTAINER_APP_NAME"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Env File: $ENV_FILE"

# Confirm before proceeding
read -p "Continue with environment variable upload? (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    print_info "Upload cancelled"
    exit 0
fi

# Verify Container App exists
print_info "Verifying Container App exists..."
if ! az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null; then
    print_error "Container App '$CONTAINER_APP_NAME' not found in resource group '$RESOURCE_GROUP'"
    exit 1
fi
print_success "Container App '$CONTAINER_APP_NAME' found"

# Read environment variables from .env file
read_env_file "$ENV_FILE"

if [[ ${#ENV_VARS[@]} -eq 0 ]]; then
    print_warning "No environment variables found in '$ENV_FILE'"
    exit 0
fi

# Prepare environment variables for update
print_info "Preparing environment variables for upload..."

# Update Container App with new environment variables
print_info "Updating Container App with environment variables..."
print_info "Running command: az containerapp update --name \"$CONTAINER_APP_NAME\" --resource-group \"$RESOURCE_GROUP\" --set-env-vars \"${ENV_VARS[@]}\""
az containerapp update \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --set-env-vars "${ENV_VARS[@]}" \
    --output none

print_success "Environment variables uploaded successfully to Container App '$CONTAINER_APP_NAME'"

# Show current environment variables (optional)
read -p "Show current environment variables? (y/N): " show_env
if [[ $show_env =~ ^[Yy]$ ]]; then
    print_info "Current environment variables:"
    az containerapp show \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.containers[0].env" \
        --output table
fi

print_success "Script execution completed!"