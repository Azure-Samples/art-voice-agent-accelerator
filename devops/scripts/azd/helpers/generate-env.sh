#!/bin/bash

set -e

# ========================================================================
# 📄 Azure Environment Configuration Generator
# ========================================================================
#
# 📋 Usage: ./generate-env.sh [ENVIRONMENT_NAME] [OUTPUT_FILE]
# 
# 🔧 This script generates environment configuration files from AZD environment values
# Can be used independently or called from other scripts
#
# ========================================================================

# ===================
# 📋 Configuration
# ===================

# Get parameters with defaults
AZD_ENV_NAME="${1:-$(azd env get-value AZURE_ENV_NAME 2>/dev/null || echo "dev")}"
OUTPUT_FILE="${2:-.env.${AZD_ENV_NAME}}"

echo "📄 Generating Environment Configuration File"
echo "============================================="
echo ""
echo "🔧 Configuration:"
echo "   Environment: $AZD_ENV_NAME"
echo "   Output File: $OUTPUT_FILE"
echo ""

# ===================
# 🔧 Helper Functions
# ===================

# Function to safely get azd environment value with fallback
get_azd_value() {
    local key="$1"
    local fallback="$2"
    local value
    value="$(azd env get-value "$key" 2>/dev/null)"
    # If azd returns an error or empty, use fallback
    if [[ $? -ne 0 ]] || [[ "$value" == "null" ]] || [[ "$value" == ERROR* ]] || [[ -z "$value" ]]; then
        echo "$fallback"
    else
        echo "$value"
    fi
}

# Function to validate azd environment availability
validate_azd_environment() {
    echo "🔍 Validating AZD environment..."
    
    if ! command -v azd &> /dev/null; then
        echo "❌ Error: Azure Developer CLI (azd) is not installed or not in PATH"
        exit 1
    fi
    
    # Test if we can access azd environment
    if ! azd env get-value AZURE_ENV_NAME &>/dev/null; then
        echo "❌ Error: No active AZD environment found. Please run 'azd env select' or 'azd init'"
        exit 1
    fi
    
    echo "✅ AZD environment validation passed"
}

# Function to generate environment file
generate_environment_file() {
    echo "📝 Generating environment file: $OUTPUT_FILE"
    
    # Generate the environment file with all required variables
    cat > "$OUTPUT_FILE" << EOF
# Generated automatically by generate-env.sh on $(date)
# Environment: ${AZD_ENV_NAME}
# =================================================================
AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)
BACKEND_AUTH_CLIENT_ID=

# Application Insights Configuration
APPLICATIONINSIGHTS_CONNECTION_STRING=$(get_azd_value "APPLICATIONINSIGHTS_CONNECTION_STRING")

# Azure OpenAI Configuration
AZURE_OPENAI_KEY=$(get_azd_value "AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT=$(get_azd_value "AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT=$(get_azd_value "AZURE_OPENAI_CHAT_DEPLOYMENT_ID")
AZURE_OPENAI_API_VERSION=$(get_azd_value "AZURE_OPENAI_API_VERSION" "2024-10-01-preview")
AZURE_OPENAI_CHAT_DEPLOYMENT_ID=$(get_azd_value "AZURE_OPENAI_CHAT_DEPLOYMENT_ID")
AZURE_OPENAI_CHAT_DEPLOYMENT_VERSION=2024-10-01-preview

# Pool Configuration for Optimal Performance
AOAI_POOL_ENABLED=$(get_azd_value "AOAI_POOL_ENABLED" "true")
AOAI_POOL_SIZE=$(get_azd_value "AOAI_POOL_SIZE" "50")
POOL_SIZE_TTS=$(get_azd_value "POOL_SIZE_TTS" "100")
POOL_SIZE_STT=$(get_azd_value "POOL_SIZE_STT" "100")
TTS_POOL_PREWARMING_ENABLED=$(get_azd_value "TTS_POOL_PREWARMING_ENABLED" "true")
STT_POOL_PREWARMING_ENABLED=$(get_azd_value "STT_POOL_PREWARMING_ENABLED" "true")
POOL_PREWARMING_BATCH_SIZE=$(get_azd_value "POOL_PREWARMING_BATCH_SIZE" "10")
CLIENT_MAX_AGE_SECONDS=$(get_azd_value "CLIENT_MAX_AGE_SECONDS" "3600")
CLEANUP_INTERVAL_SECONDS=$(get_azd_value "CLEANUP_INTERVAL_SECONDS" "180")

# Azure Speech Services Configuration
AZURE_SPEECH_ENDPOINT=$(get_azd_value "AZURE_SPEECH_ENDPOINT")
AZURE_SPEECH_KEY=$(get_azd_value "AZURE_SPEECH_KEY")
AZURE_SPEECH_RESOURCE_ID=$(get_azd_value "AZURE_SPEECH_RESOURCE_ID")
AZURE_SPEECH_REGION=$(get_azd_value "AZURE_SPEECH_REGION")

# Base URL Configuration
# Prompt user for BASE_URL if not set in azd env
BASE_URL="<Your publicly routable URL for the backend app, e.g devtunnel host>"
TTS_ENABLE_LOCAL_PLAYBACK=true

# Azure Communication Services Configuration
ACS_CONNECTION_STRING=$(get_azd_value "ACS_CONNECTION_STRING")
ACS_SOURCE_PHONE_NUMBER=$(get_azd_value "ACS_SOURCE_PHONE_NUMBER")
ACS_ENDPOINT=$(get_azd_value "ACS_ENDPOINT")

# Redis Configuration
REDIS_HOST=$(get_azd_value "REDIS_HOSTNAME")
REDIS_PORT=$(get_azd_value "REDIS_PORT" "6380")
REDIS_PASSWORD=$(get_azd_value "REDIS_PASSWORD")

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=$(get_azd_value "AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_URL=$(get_azd_value "AZURE_STORAGE_CONTAINER_URL")
AZURE_STORAGE_ACCOUNT_NAME=$(get_azd_value "AZURE_STORAGE_ACCOUNT_NAME")

# Azure Cosmos DB Configuration
AZURE_COSMOS_DATABASE_NAME=$(get_azd_value "AZURE_COSMOS_DATABASE_NAME" "audioagentdb")
AZURE_COSMOS_COLLECTION_NAME=$(get_azd_value "AZURE_COSMOS_COLLECTION_NAME" "audioagentcollection")
AZURE_COSMOS_CONNECTION_STRING=$(get_azd_value "AZURE_COSMOS_CONNECTION_STRING")

# Azure Identity Configuration
AZURE_SUBSCRIPTION_ID=$(get_azd_value "AZURE_SUBSCRIPTION_ID")

# Azure Resource Configuration
AZURE_RESOURCE_GROUP=$(get_azd_value "AZURE_RESOURCE_GROUP")
AZURE_LOCATION=$(get_azd_value "AZURE_LOCATION")

# Application Configuration
ACS_STREAMING_MODE=media
ENVIRONMENT=$AZD_ENV_NAME

# Logging Configuration
LOG_LEVEL=$(get_azd_value "LOG_LEVEL" "INFO")
EOF

    # Set appropriate permissions
    chmod 644 "$OUTPUT_FILE" 2>/dev/null || true
    
    echo "✅ Environment file generated successfully"
}

# Function to validate generated environment file
validate_environment_file() {
    echo "🔍 Validating generated environment file..."
    
    if [[ ! -f "$OUTPUT_FILE" ]]; then
        echo "❌ Error: Environment file was not created: $OUTPUT_FILE"
        exit 1
    fi
    
    # Count non-empty configuration variables
    local var_count
    var_count=$(grep -c '^[A-Z][A-Z_]*=' "$OUTPUT_FILE" || echo "0")
    
    if [[ $var_count -eq 0 ]]; then
        echo "❌ Error: No configuration variables found in environment file"
        exit 1
    fi
    
    echo "✅ Environment file validation passed"
    echo "📊 Found $var_count configuration variables"
}

# Function to display environment file summary
show_environment_summary() {
    echo ""
    echo "📊 Environment File Summary"
    echo "=========================="
    echo "   File: $OUTPUT_FILE"
    echo "   Environment: $AZD_ENV_NAME"
    echo "   Generated: $(date)"
    echo ""
    
    # Show key configuration sections
    echo "🔧 Configuration Sections:"
    if grep -q "AZURE_OPENAI_ENDPOINT=" "$OUTPUT_FILE"; then
        echo "   ✅ Azure OpenAI"
    else
        echo "   ⚠️  Azure OpenAI (missing endpoint)"
    fi
    
    if grep -q "AZURE_SPEECH_ENDPOINT=" "$OUTPUT_FILE"; then
        echo "   ✅ Azure Speech Services"
    else
        echo "   ⚠️  Azure Speech Services (missing endpoint)"
    fi
    
    if grep -q "ACS_CONNECTION_STRING=" "$OUTPUT_FILE"; then
        echo "   ✅ Azure Communication Services"
    else
        echo "   ⚠️  Azure Communication Services (missing connection)"
    fi
    
    if grep -q "REDIS_HOST=" "$OUTPUT_FILE"; then
        echo "   ✅ Redis Cache"
    else
        echo "   ⚠️  Redis Cache (missing host)"
    fi
    
    if grep -q "AZURE_COSMOS_CONNECTION_STRING=" "$OUTPUT_FILE"; then
        echo "   ✅ Cosmos DB"
    else
        echo "   ⚠️  Cosmos DB (missing connection)"
    fi
    
    echo ""
    echo "💡 Usage:"
    echo "   Load in shell: source $OUTPUT_FILE"
    echo "   View contents: cat $OUTPUT_FILE"
    echo "   Edit manually: code $OUTPUT_FILE"
}

# ===================
# 🚀 Main Execution
# ===================

echo "🚀 Starting environment file generation..."

# Validate AZD environment
validate_azd_environment

# Generate environment file
generate_environment_file

# Validate generated file
validate_environment_file

# Show summary
show_environment_summary

echo ""
echo "✅ Environment file generation complete!"
echo "📄 Generated: $OUTPUT_FILE"