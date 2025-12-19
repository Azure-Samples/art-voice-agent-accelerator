#!/bin/bash
# ========================================================================
# 🧑‍💻 Local Development Setup Script
# ========================================================================
# This script sets up minimal environment variables for local development.
# 
# With Azure App Configuration, most settings are fetched at runtime.
# Only a few bootstrap variables are needed locally:
#
# REQUIRED:
#   - AZURE_APPCONFIG_ENDPOINT (to connect to App Config)
#   - AZURE_TENANT_ID (for authentication)
#
# OPTIONAL (for full local dev without App Config):
#   - Source the legacy .env file if App Config is not available
#
# Usage:
#   ./local-dev-setup.sh              # Interactive setup
#   ./local-dev-setup.sh --minimal    # Just App Config endpoint
#   ./local-dev-setup.sh --legacy     # Generate full .env file (fallback)
# ========================================================================

set -e

# Use LOCAL_DEV_SCRIPT_DIR to avoid conflict when sourced from postprovision.sh
LOCAL_DEV_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Safely get azd environment value
get_azd_value() {
    local key="$1"
    local fallback="${2:-}"
    local value
    value="$(azd env get-value "$key" 2>/dev/null || echo "")"
    if [[ -z "$value" ]] || [[ "$value" == "null" ]] || [[ "$value" == ERROR* ]]; then
        echo "$fallback"
    else
        echo "$value"
    fi
}

# Generate minimal .env.local for App Config-based development
generate_minimal_env() {
    local output_file="${1:-.env.local}"
    
    log_info "Generating minimal local development environment..."
    
    local appconfig_endpoint
    local tenant_id
    local env_name
    
    appconfig_endpoint=$(get_azd_value "AZURE_APPCONFIG_ENDPOINT")
    tenant_id=$(az account show --query tenantId -o tsv 2>/dev/null || echo "")
    env_name=$(get_azd_value "AZURE_ENV_NAME" "dev")
    
    if [[ -z "$appconfig_endpoint" ]]; then
        log_warning "AZURE_APPCONFIG_ENDPOINT not found in azd environment"
        log_info "App Config may not be deployed yet. Run 'azd provision' first."
        log_info "Falling back to legacy environment file generation..."
        return 1
    fi
    
    cat > "$output_file" << EOF
# ========================================================================
# 🧑‍💻 Local Development Environment (Minimal)
# ========================================================================
# Generated: $(date)
# 
# This file contains only the bootstrap variables needed for local dev.
# All other configuration is fetched from Azure App Configuration at runtime.
#
# The Python app will:
# 1. Connect to App Configuration using DefaultAzureCredential
# 2. Fetch all settings with label="${env_name}"
# 3. Fall back to environment variables if App Config is unavailable
# ========================================================================

# Azure App Configuration (PRIMARY CONFIG SOURCE)
AZURE_APPCONFIG_ENDPOINT=${appconfig_endpoint}
AZURE_APPCONFIG_LABEL=${env_name}

# Azure Identity (for DefaultAzureCredential)
AZURE_TENANT_ID=${tenant_id}

# Local Development Overrides (optional)
# Uncomment and modify as needed for local development:

# ENVIRONMENT=local
# DEBUG_MODE=true
# LOG_LEVEL=DEBUG

# Local Base URL (required for ACS callbacks)
# BASE_URL=https://your-devtunnel-url.devtunnels.ms

# Disable cloud telemetry for local dev (optional)
# DISABLE_CLOUD_TELEMETRY=true

EOF

    chmod 644 "$output_file"
    log_success "Generated minimal environment file: $output_file"
    
    echo ""
    echo "📋 To use this configuration:"
    echo "   source $output_file"
    echo ""
    echo "💡 The app will fetch remaining config from Azure App Configuration"
    echo "   Endpoint: $appconfig_endpoint"
    echo "   Label: $env_name"
    
    return 0
}

# Generate legacy full .env file (fallback mode)
generate_legacy_env() {
    local output_file="${1:-.env.legacy}"
    
    log_info "Generating legacy full environment file..."
    
    if [[ -f "$LOCAL_DEV_SCRIPT_DIR/generate-env.sh" ]]; then
        "$LOCAL_DEV_SCRIPT_DIR/generate-env.sh" "$(get_azd_value AZURE_ENV_NAME dev)" "$output_file"
        log_success "Generated legacy environment file: $output_file"
    else
        log_error "Legacy generate-env.sh not found"
        return 1
    fi
}

# Show current configuration status
show_config_status() {
    echo ""
    echo "📊 Configuration Status"
    echo "========================"
    
    local appconfig_endpoint
    appconfig_endpoint=$(get_azd_value "AZURE_APPCONFIG_ENDPOINT")
    
    if [[ -n "$appconfig_endpoint" ]]; then
        echo "   ✅ App Configuration: $appconfig_endpoint"
    else
        echo "   ⚠️  App Configuration: Not deployed"
    fi
    
    # Check for existing env files
    for f in .env.local .env .env.dev .env.legacy; do
        if [[ -f "$f" ]]; then
            local var_count
            var_count=$(grep -c '^[A-Z]' "$f" 2>/dev/null || echo "0")
            echo "   📄 $f: $var_count variables"
        fi
    done
    
    echo ""
}

# Main
main() {
    local mode="${1:-interactive}"
    
    echo ""
    echo "🧑‍💻 Local Development Setup"
    echo "============================"
    echo ""
    
    case "$mode" in
        --minimal|-m)
            generate_minimal_env ".env.local"
            ;;
        --legacy|-l)
            generate_legacy_env ".env.legacy"
            ;;
        --status|-s)
            show_config_status
            ;;
        interactive|*)
            show_config_status
            
            echo "Select setup mode:"
            echo "  1) Minimal (App Config-based) - Recommended"
            echo "  2) Legacy (full .env file)"
            echo "  3) Show status only"
            echo ""
            echo "(Auto-selecting minimal in 10 seconds if no input...)"
            
            if read -t 10 -p "Choice (1-3): " choice; then
                : # Got input
            else
                echo ""
                log_info "No input received, using minimal (App Config-based) setup"
                choice="1"
            fi
            
            case "$choice" in
                1) generate_minimal_env ".env.local" ;;
                2) generate_legacy_env ".env.legacy" ;;
                3) show_config_status ;;
                *) log_error "Invalid choice" && generate_minimal_env ".env.local" ;;
            esac
            ;;
    esac
}

main "$@"
