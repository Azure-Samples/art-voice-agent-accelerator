#!/bin/bash
# ========================================================================
# 🎯 Azure Developer CLI Post-Provisioning Script
# ========================================================================
# This script runs after Azure resources are provisioned by azd.
# It handles:
# 1. ACS phone number setup (interactive or existing)
# 2. Environment file generation
# 3. Backend service configuration updates
#
# CI/CD Mode: Set AZD_SKIP_INTERACTIVE=true to bypass all prompts
# ========================================================================

set -e  # Exit on error (we'll handle specific failures with || true)

# ========================================================================
# 🔧 Configuration & Setup
# ========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPERS_DIR="$SCRIPT_DIR/helpers"

# Check for CI/CD mode
SKIP_INTERACTIVE="${AZD_SKIP_INTERACTIVE:-false}"
CI_MODE="${CI:-false}"
GITHUB_ACTIONS_MODE="${GITHUB_ACTIONS:-false}"

# Auto-detect CI/CD environments
if [ "$CI_MODE" = "true" ] || [ "$GITHUB_ACTIONS_MODE" = "true" ] || [ "$SKIP_INTERACTIVE" = "true" ]; then
    INTERACTIVE_MODE=false
else
    INTERACTIVE_MODE=true
fi

# Color codes for better readability (disabled in CI/CD)
if [ "$INTERACTIVE_MODE" = "true" ] && [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# ========================================================================
# 🛠️ Helper Functions
# ========================================================================

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
    echo -e "${BLUE}$1${NC}"
    echo "$(printf '=%.0s' {1..50})"
    echo ""
}

# Log CI/CD mode status
log_ci_mode() {
    if [ "$INTERACTIVE_MODE" = "false" ]; then
        log_info "Running in CI/CD mode (non-interactive)"
        [ "$CI_MODE" = "true" ] && log_info "  - CI environment detected"
        [ "$GITHUB_ACTIONS_MODE" = "true" ] && log_info "  - GitHub Actions detected"
        [ "$SKIP_INTERACTIVE" = "true" ] && log_info "  - AZD_SKIP_INTERACTIVE is set"
    else
        log_info "Running in interactive mode"
    fi
}

# Safely get azd environment values
get_azd_env_value() {
    local var_name="$1"
    local default_value="${2:-}"
    local value
    
    value=$(azd env get-value "$var_name" 2>&1 || echo "")
    
    if [[ "$value" == *ERROR* ]] || [ -z "$value" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}

# Check if running in interactive mode
is_interactive() {
    [ "$INTERACTIVE_MODE" = "true" ] && [ -t 0 ]
}

# Validate E.164 phone number format
is_valid_phone_number() {
    [[ "$1" =~ ^\+[0-9]{10,15}$ ]]
}

# ========================================================================
# 🔍 Phone Number Management Functions
# ========================================================================

check_existing_phone_number() {
    local existing_number
    existing_number=$(get_azd_env_value "ACS_SOURCE_PHONE_NUMBER")
    
    if [ -n "$existing_number" ]; then
        log_success "ACS_SOURCE_PHONE_NUMBER is already set: $existing_number"
        return 0
    else
        return 1
    fi
}

handle_phone_number_cicd() {
    log_info "CI/CD mode: Checking for predefined phone number..."
    
    # Check environment variable first
    if [ -n "${ACS_SOURCE_PHONE_NUMBER:-}" ]; then
        log_info "Found ACS_SOURCE_PHONE_NUMBER in environment"
        if is_valid_phone_number "$ACS_SOURCE_PHONE_NUMBER"; then
            azd env set ACS_SOURCE_PHONE_NUMBER "$ACS_SOURCE_PHONE_NUMBER"
            log_success "Set ACS_SOURCE_PHONE_NUMBER from environment variable"
            return 0
        else
            log_warning "Invalid phone number format in environment variable: $ACS_SOURCE_PHONE_NUMBER"
        fi
    fi
    
    # Check if auto-provisioning is enabled
    local auto_provision
    auto_provision=$(get_azd_env_value "ACS_AUTO_PROVISION_PHONE" "false")
    
    if [ "$auto_provision" = "true" ]; then
        log_info "Auto-provisioning phone number (ACS_AUTO_PROVISION_PHONE=true)"
        provision_new_phone_number
        return $?
    else
        log_warning "No phone number configured in CI/CD mode"
        log_info "To configure phone number in CI/CD:"
        log_info "  - Set ACS_SOURCE_PHONE_NUMBER environment variable"
        log_info "  - Or set ACS_AUTO_PROVISION_PHONE=true in azd environment"
        return 1
    fi
}

prompt_for_phone_number() {
    if ! is_interactive; then
        # In CI/CD mode, try alternative methods
        handle_phone_number_cicd
        return $?
    fi
    
    log_info "ACS_SOURCE_PHONE_NUMBER is not defined."
    echo "Options:"
    echo "  1) Enter an existing phone number"
    echo "  2) Provision a new phone number from Azure"
    echo "  3) Skip (configure later)"
    echo ""
    
    read -p "Your choice (1-3): " choice
    
    case "$choice" in
        1)
            read -p "Enter phone number in E.164 format (e.g., +1234567890): " user_phone
            if is_valid_phone_number "$user_phone"; then
                azd env set ACS_SOURCE_PHONE_NUMBER "$user_phone"
                log_success "Set ACS_SOURCE_PHONE_NUMBER to $user_phone"
                return 0
            else
                log_error "Invalid phone number format"
                return 1
            fi
            ;;
        2)
            # User wants to provision new number
            provision_new_phone_number || {
                log_warning "Phone number provisioning failed, continuing with other tasks..."
                return 1
            }
            ;;
        3)
            log_info "Skipping phone number configuration"
            return 3  # Return 3 for user-initiated skip
            ;;
        *)
            log_error "Invalid choice"
            return 1
            ;;
    esac
}

provision_new_phone_number() {
    log_section "📞 Provisioning New ACS Phone Number"
    
    local acs_endpoint
    acs_endpoint=$(get_azd_env_value "ACS_ENDPOINT")
    
    if [ -z "$acs_endpoint" ]; then
        log_error "ACS_ENDPOINT is not set. Cannot provision phone number."
        return 1
    fi
    
    # Ensure Azure CLI communication extension is installed
    log_info "Checking Azure CLI communication extension..."
    if ! az extension list --query "[?name=='communication']" -o tsv | grep -q communication; then
        log_info "Installing Azure CLI communication extension..."
        az extension add --name communication || {
            log_error "Failed to install communication extension"
            return 1
        }
    fi
    
    # Install required Python packages
    log_info "Installing required Python packages..."
    pip3 install -q azure-identity azure-communication-phonenumbers || {
        log_error "Failed to install required Python packages"
        return 1
    }
    
    # Run the provisioning script
    log_info "Creating new phone number..."
    local phone_number
    phone_number=$(python3 "$HELPERS_DIR/acs_phone_number_manager.py" \
        --endpoint "$acs_endpoint" purchase 2>/dev/null) || {
        log_error "Failed to provision phone number"
        return 1
    }
    
    # Extract clean phone number
    local clean_number
    clean_number=$(echo "$phone_number" | grep -o '+[0-9]\+' | head -1)
    
    if [ -z "$clean_number" ]; then
        log_error "Failed to extract phone number from provisioning output"
        return 1
    fi
    
    # Save to azd environment
    azd env set ACS_SOURCE_PHONE_NUMBER "$clean_number"
    log_success "Successfully provisioned phone number: $clean_number"
    
    # Update backend service
    update_backend_phone_number "$clean_number" || {
        log_warning "Failed to update backend service, but phone number was provisioned"
    }
    
    return 0
}

update_backend_phone_number() {
    local phone_number="$1"
    local resource_group
    local backend_name
    local backend_type=""
    
    resource_group=$(get_azd_env_value "AZURE_RESOURCE_GROUP")
    
    if [ -z "$resource_group" ]; then
        log_warning "AZURE_RESOURCE_GROUP not set. Cannot update backend."
        return 1
    fi
    
    # Check for container app
    backend_name=$(get_azd_env_value "BACKEND_CONTAINER_APP_NAME")
    if [ -n "$backend_name" ]; then
        backend_type="containerapp"
    else
        # Check for app service
        backend_name=$(get_azd_env_value "BACKEND_APP_SERVICE_NAME")
        if [ -n "$backend_name" ]; then
            backend_type="appservice"
        fi
    fi
    
    if [ -z "$backend_type" ]; then
        log_warning "No backend service found to update"
        return 1
    fi
    
    log_info "Updating $backend_type: $backend_name"
    
    case "$backend_type" in
        "containerapp")
            az containerapp update \
                --name "$backend_name" \
                --resource-group "$resource_group" \
                --set-env-vars "ACS_SOURCE_PHONE_NUMBER=$phone_number" \
                --output none || return 1
            ;;
        "appservice")
            az webapp config appsettings set \
                --name "$backend_name" \
                --resource-group "$resource_group" \
                --settings "ACS_SOURCE_PHONE_NUMBER=$phone_number" \
                --output none || return 1
            ;;
    esac
    
    log_success "Updated backend service with phone number"
    return 0
}

# ========================================================================
# 🌐 Frontend BACKEND_URL configuration
# ========================================================================

get_best_backend_url() {
    # Preference order: BACKEND_API_URL (explicit) -> BACKEND_CONTAINER_APP_URL (derived) -> build from FQDN
    local backend_api_url
    local backend_container_url
    local backend_fqdn

    backend_api_url=$(get_azd_env_value "BACKEND_API_URL")
    backend_container_url=$(get_azd_env_value "BACKEND_CONTAINER_APP_URL")
    backend_fqdn=$(get_azd_env_value "BACKEND_CONTAINER_APP_FQDN")

    if [ -n "$backend_api_url" ]; then
        echo "$backend_api_url"
        return 0
    fi

    if [ -n "$backend_container_url" ]; then
        echo "$backend_container_url"
        return 0
    fi

    if [ -n "$backend_fqdn" ]; then
        echo "https://${backend_fqdn}"
        return 0
    fi

    echo ""
    return 1
}

update_frontend_backend_url() {
    log_section "🌐 Configuring Frontend BACKEND_URL"

    local resource_group
    local frontend_name
    local chosen_url

    resource_group=$(get_azd_env_value "AZURE_RESOURCE_GROUP")
    frontend_name=$(get_azd_env_value "FRONTEND_CONTAINER_APP_NAME")
    chosen_url=$(get_best_backend_url)

    if [ -z "$frontend_name" ] || [ -z "$resource_group" ]; then
        log_warning "Frontend Container App name or resource group not found in azd environment. Skipping BACKEND_URL configuration."
        return 1
    fi

    if [ -z "$chosen_url" ]; then
        log_warning "Could not resolve backend URL from azd outputs. Skipping BACKEND_URL configuration."
        return 1
    fi

    log_info "Setting BACKEND_URL on frontend: $chosen_url"
    az containerapp update \
        --name "$frontend_name" \
        --resource-group "$resource_group" \
        --set-env-vars "BACKEND_URL=$chosen_url" \
        --output none || {
            log_error "Failed to set BACKEND_URL on frontend container app"
            return 1
        }

    log_success "Frontend BACKEND_URL updated"
    return 0
}

update_backend_base_url() {
    log_section "🧩 Configuring Backend BASE_URL"

    local resource_group
    local backend_name
    local backend_type=""
    local chosen_url

    resource_group=$(get_azd_env_value "AZURE_RESOURCE_GROUP")
    backend_name=$(get_azd_env_value "BACKEND_CONTAINER_APP_NAME")
    if [ -n "$backend_name" ]; then
        backend_type="containerapp"
    else
        backend_name=$(get_azd_env_value "BACKEND_APP_SERVICE_NAME")
        if [ -n "$backend_name" ]; then
            backend_type="appservice"
        fi
    fi

    if [ -z "$backend_type" ] || [ -z "$backend_name" ] || [ -z "$resource_group" ]; then
        log_warning "Backend service not found in azd environment. Skipping BASE_URL configuration."
        return 1
    fi

    chosen_url=$(get_best_backend_url)
    if [ -z "$chosen_url" ]; then
        log_warning "Could not resolve backend URL from azd outputs. Skipping BASE_URL configuration."
        return 1
    fi

    log_info "Setting BASE_URL on backend ($backend_type: $backend_name) to: $chosen_url"
    case "$backend_type" in
        "containerapp")
            az containerapp update \
                --name "$backend_name" \
                --resource-group "$resource_group" \
                --set-env-vars "BASE_URL=$chosen_url" \
                --output none || {
                    log_error "Failed to set BASE_URL on backend container app"
                    return 1
                }
            ;;
        "appservice")
            az webapp config appsettings set \
                --name "$backend_name" \
                --resource-group "$resource_group" \
                --settings "BASE_URL=$chosen_url" \
                --output none || {
                    log_error "Failed to set BASE_URL on backend app service"
                    return 1
                }
            ;;
    esac

    log_success "Backend BASE_URL updated"
    return 0
}

# ========================================================================
# 🚀 Main Execution
# ========================================================================

main() {
    log_section "🚀 Starting Post-Provisioning Script"
    log_ci_mode
    
    # Step 1: Handle phone number configuration
    log_section "📱 Configuring ACS Phone Number"
    
    if ! check_existing_phone_number; then
        # Store the result but don't fail the script
        if prompt_for_phone_number; then
            log_success "Phone number configured"
        else
            if [ "$INTERACTIVE_MODE" = "false" ]; then
                log_info "Phone number configuration skipped in CI/CD mode"
            else
                log_warning "Phone number configuration failed, continuing..."
            fi
        fi
    fi
    
    # Step 1b: Configure frontend BACKEND_URL for Vite runtime replacement
    update_frontend_backend_url || {
        log_warning "Frontend BACKEND_URL configuration did not complete; continue."
    }

    # Step 1c: Configure backend BASE_URL for FastAPI public URL
    update_backend_base_url || {
        log_warning "Backend BASE_URL configuration did not complete; continue."
    }

    # Step 2: Generate environment files (always runs)
    log_section "📄 Generating Environment Configuration Files"
    
    local env_name
    local env_file
    env_name=$(get_azd_env_value "AZURE_ENV_NAME" "dev")
    env_file=".env.${env_name}"
    
    if [ -f "$HELPERS_DIR/generate-env.sh" ]; then
        log_info "Generating environment file: $env_file"
        "$HELPERS_DIR/generate-env.sh" "$env_name" "$env_file" || {
            log_error "Environment file generation failed"
            # Don't exit - this is critical but we want to show summary
        }
        
        if [ -f "$env_file" ]; then
            local var_count
            var_count=$(grep -c '^[A-Z]' "$env_file" 2>/dev/null || echo "0")
            log_success "Generated environment file with $var_count variables"
        fi
    else
        log_error "generate-env.sh not found at: $HELPERS_DIR/generate-env.sh"
    fi
    
    # Step 3: Summary
    log_section "🎯 Post-Provisioning Summary"
    
    echo "📋 Generated Files:"
    [ -f "$env_file" ] && echo "  ✓ ${env_file} (Backend environment configuration)"
    echo ""
    
    if [ "$INTERACTIVE_MODE" = "true" ]; then
        echo "🔧 Next Steps:"
        echo "  1. Review the environment file: cat ${env_file}"
        echo "  2. Source the environment: source ${env_file}"
        echo "  3. Test your application"
    fi
    
    local phone_status
    phone_status=$(get_azd_env_value "ACS_SOURCE_PHONE_NUMBER")
    if [ -z "$phone_status" ]; then
        echo ""
        echo "⚠️  Note: No phone number configured. To add one later:"
        if [ "$INTERACTIVE_MODE" = "true" ]; then
            echo "     azd env set ACS_SOURCE_PHONE_NUMBER '+1234567890'"
        else
            echo "     Set ACS_SOURCE_PHONE_NUMBER environment variable"
            echo "     Or set ACS_AUTO_PROVISION_PHONE=true in azd environment"
        fi
    fi
    
    echo ""
    log_success "Post-provisioning complete!"
    
    # Always exit successfully - phone number is optional
    exit 0
}

# Run main function
main "$@"
