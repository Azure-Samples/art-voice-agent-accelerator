#!/bin/bash


# ================# Helper functions
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

set -euo pipefail

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Constants
readonly SCRIPT_NAME="$(basename "$0")"
readonly REQUIRED_COMMANDS=("az" "azd" "rsync" "zip" "curl")

# Configuration
readonly AGENT="${1:-ARTAgent}"
readonly AGENT_BACKEND="apps/$AGENT/backend"
readonly BACKEND_DIRS=("src" "utils")
readonly REQUIRED_FILES=("requirements.txt")
readonly EXCLUDE_PATTERNS=("__pycache__" "*.pyc" ".pytest_cache" "*.log" ".coverage" "htmlcov" ".DS_Store" ".git" "node_modules" "*.tmp" "*.temp")

echo "🚀 Deploying $AGENT to App Service"

# Get AZD variables and validate
RG=$(azd env get-value AZURE_RESOURCE_GROUP)
BACKEND_APP=$(azd env get-value BACKEND_APP_SERVICE_NAME)
AZD_ENV=$(azd env get-value AZURE_ENV_NAME)

[[ -z "$RG" || -z "$BACKEND_APP" || -z "$AZD_ENV" ]] && { echo "❌ Missing AZD environment variables"; exit 1; }

echo "✅ Validated: $BACKEND_APP in $RG (env: $AZD_ENV)"

# Prepare deployment package
TEMP_DIR=".azure/$AZD_ENV/backend"
echo "� Preparing deployment in: $TEMP_DIR"
rm -rf "$TEMP_DIR" && mkdir -p "$TEMP_DIR"


# Check if required commands exist
check_dependencies() {
    local missing_commands=()
    
    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        log_error "Please install missing dependencies and try again."
        exit 1
    fi
}

# Get azd environment variable value
get_azd_env_value() {
    local key="$1"
    local value
    
    if value=$(azd env get-value "$key" 2>/dev/null); then
        echo "$value"
    else
        echo ""
    fi
}

# 🚀 Azure App Service Deployment Script
# ========================================================================
# This script deploys backend applications to Azure App Service with
# configurable file inclusion/exclusion patterns and automatic validation.
#
# Usage: ./appsvc-deploy.sh [AGENT_NAME]
#
# ========================================================================


# Copy files with exclusions
copy_with_excludes() {
    local src="$1"
    local dest="$2"
    
    if [[ ! -d "$src" ]]; then
        log_warning "Source directory not found: $src"
        return 1
    fi
    
    log_info "Copying: $src -> $dest"
    
    # Build exclude arguments
    local exclude_args=()
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_args+=(--exclude="$pattern")
    done
    
    rsync -a "${exclude_args[@]}" "$src/" "$dest/"
}

# Prepare deployment package
prepare_deployment_package() {
    local temp_dir="$1"
    
    log_info "Preparing deployment package..."
    
    # Clean and create temp deployment directory
    rm -rf "$temp_dir" && mkdir -p "$temp_dir"
    
    # Copy agent backend
    mkdir -p "$temp_dir/$AGENT_BACKEND"
    copy_with_excludes "$AGENT_BACKEND" "$temp_dir/$AGENT_BACKEND"
    
    # Copy shared directories
    for dir in "${BACKEND_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            copy_with_excludes "$dir" "$temp_dir/$dir"
        else
            log_warning "Configured directory not found: $dir"
        fi
    done
    
    # Copy required files
    for file in "${REQUIRED_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            log_info "Copying required file: $file"
            cp "$file" "$temp_dir/"
        else
            log_error "Required file missing: $file"
            exit 1
        fi
    done
    
    log_success "Deployment package prepared successfully"
}

# Create deployment zip
create_deployment_zip() {
    local temp_dir="$1"
    
    log_info "Creating deployment zip..."
    
    cd "$temp_dir"
    
    # Build zip exclusion arguments
    local zip_exclude_args=()
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        zip_exclude_args+=(-x "$pattern")
    done
    
    zip -rq backend.zip . "${zip_exclude_args[@]}"
    
    if [[ ! -f "backend.zip" ]]; then
        log_error "Failed to create backend.zip"
        exit 1
    fi
    
    local zip_size
    zip_size=$(du -h backend.zip | cut -f1)
    log_success "Deployment zip created successfully (size: $zip_size)"
    
    cd - > /dev/null
}

# Configure App Service settings
configure_app_service() {
    log_info "Configuring App Service settings..."

    # Get current backend app service URL from azd
    BACKEND_APP_SERVICE_URL=$(azd env get-value BACKEND_APP_SERVICE_URL)
    if [[ -z "$BACKEND_APP_SERVICE_URL" ]]; then
        log_warning "BACKEND_APP_SERVICE_URL not set in azd environment"
        BACKEND_APP_SERVICE_URL="https://$BACKEND_APP.azurewebsites.net"
    fi

    # Set startup command
    az webapp config set \
        --resource-group "$RG" \
        --name "$BACKEND_APP" \
        --startup-file "python -m uvicorn rtagents.${AGENT}.backend.main:app --host 0.0.0.0 --port 8000" \
        --output none

    # Set BASE_URL environment variable for the web app
    az webapp config appsettings set \
        --resource-group "$RG" \
        --name "$BACKEND_APP" \
        --settings \
            "PYTHONPATH=/home/site/wwwroot" \
            "SCM_DO_BUILD_DURING_DEPLOYMENT=true" \
            "ENABLE_ORYX_BUILD=true" \
            "ORYX_APP_TYPE=webapps" \
            "WEBSITES_PORT=8000" \
            "BASE_URL=$BACKEND_APP_SERVICE_URL" \
        --output none

    log_success "App Service configured successfully"
}
deploy_to_app_service() {
    local temp_dir="$1"
    
    log_info "Deploying to Azure App Service..."
    
    cd "$temp_dir"
    
    # Attempt deployment with timeout handling
    local deployment_status=0
    local deployment_output
    
    if deployment_output=$(az webapp deploy \
        --resource-group "$RG" \
        --name "$BACKEND_APP" \
        --src-path "backend.zip" \
        --type zip 2>&1); then
        log_success "Deployment command completed successfully"
        deployment_status=0
    else
        local exit_code=$?
        log_warning "Deployment command returned exit code: $exit_code"
        
        # Check if it's likely a timeout or server-side issue
        if echo "$deployment_output" | grep -qi -E "(timeout|timed out|request timeout|gateway timeout|502|503|504)"; then
            log_warning "Deployment appears to have timed out on client side"
            log_info "This doesn't necessarily mean the deployment failed on the server"
            log_info "Will continue to check deployment status..."
            deployment_status=2  # Timeout/uncertain status
        elif echo "$deployment_output" | grep -qi -E "(conflict|409|deployment.*progress|another deployment)"; then
            log_warning "Another deployment may be in progress"
            log_info "Will continue to check deployment status..."
            deployment_status=2  # Concurrent deployment
        else
            log_error "Deployment command failed with actual error:"
            echo "$deployment_output" | head -10  # Show first 10 lines of error
            deployment_status=1  # Actual failure
        fi
    fi
    
    cd - > /dev/null
    return $deployment_status
}

# Wait for app to be ready and verify deployment
wait_for_app_ready() {
    log_info "Waiting for app to be ready..."
    
    local max_attempts=30
    local deployment_verified=false
    
    for i in $(seq 1 $max_attempts); do
        local app_state
        app_state=$(az webapp show --resource-group "$RG" --name "$BACKEND_APP" --query "state" -o tsv 2>/dev/null || echo "Unknown")
        
        if [[ "$app_state" == "Running" ]]; then
            log_success "App is running and ready"
            deployment_verified=true
            break
        elif [[ "$app_state" == "Stopped" ]]; then
            log_warning "App is stopped, attempting to start..."
            az webapp start --resource-group "$RG" --name "$BACKEND_APP" --output none 2>/dev/null || true
        fi
        
        echo "   App state: $app_state (attempt $i/$max_attempts)"
        sleep 5
    done
    
    if [[ "$deployment_verified" == "true" ]]; then
        return 0
    else
        log_warning "App state verification timed out after $((max_attempts * 5)) seconds"
        return 1
    fi
}

# Perform health check
perform_health_check() {
    local app_url="$1"
    
    log_info "Performing health check..."
    
    if curl -sf --max-time 5 "https://$app_url/health" >/dev/null 2>&1; then
        log_success "Health endpoint is responding"
    else
        log_warning "Health endpoint not responding (application may be starting up)"
    fi
}

# Cleanup deployment artifacts
cleanup_deployment() {
    local temp_dir="$1"
    log_info "Cleaning up deployment artifacts..."

    if [[ -f "$temp_dir/backend.zip" ]]; then
        rm "$temp_dir/backend.zip"
    fi

    if [[ -d "$temp_dir" ]]; then
        rm -rf "$temp_dir"
    fi
    
    log_success "Cleanup completed"
}

# Display deployment summary
show_deployment_summary() {
    local app_url="$1"
    local deployment_status="$2"
    
    echo ""
    echo "========================================================================="
    
    case "$deployment_status" in
        "success")
            log_success "Deployment completed successfully!"
            ;;
        "uncertain")
            log_warning "Deployment completed with uncertain status"
            echo "   The deployment command timed out, but the app appears to be running."
            echo "   This is common with large deployments and usually indicates success."
            ;;
        *)
            log_success "Deployment process completed!"
            ;;
    esac
    
    echo ""
    echo "📊 Deployment Summary:"
    echo "   Agent: $AGENT"
    echo "   App Service: $BACKEND_APP"
    echo "   Resource Group: $RG"
    echo "   Environment: $AZD_ENV"
    echo "   App URL: https://$app_url"
    echo "   Status: $deployment_status"
    echo ""
    echo "🌐 Test your deployment at: https://$app_url"
    echo "========================================================================="
}

# Main function
main() {
    echo "========================================================================="
    echo "🚀 Azure App Service Deployment for $AGENT backend"
    echo "========================================================================="
    # Prompt user for confirmation before deploying
    read -p "Are you sure you want to deploy '$AGENT' to App Service '$BACKEND_APP' in resource group '$RG'? [y/N]: " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_warning "$AGENT backend deployment cancelled by user."
        exit 0
    fi
    # Check dependencies
    check_dependencies
    
    # Set deployment directory
    local temp_dir=".azure/$AZD_ENV/backend"
    log_info "Using deployment directory: $temp_dir"
    
    # Prepare deployment
    prepare_deployment_package "$temp_dir"
    create_deployment_zip "$temp_dir"
    
    # Configure and deploy
    configure_app_service
    
    # Attempt deployment with spinner for long-running operation
    local deployment_result
    local spinner_pid

    # Spinner function
    spinner() {
        local chars="/-\|"
        local i=0
        while :; do
            printf "\r⏳ Deploying... %c" "${chars:i++%${#chars}:1}"
            sleep 0.2
        done
    }

    spinner &
    spinner_pid=$!

    if deploy_to_app_service "$temp_dir"; then
        deployment_result="success"
        kill "$spinner_pid" >/dev/null 2>&1
        printf "\r"
        log_success "Deployment completed successfully"
    else
        local deploy_exit_code=$?
        kill "$spinner_pid" >/dev/null 2>&1
        printf "\r"
        if [[ $deploy_exit_code -eq 2 ]]; then
            deployment_result="uncertain"
            log_warning "Deployment status uncertain due to timeout/server issues"
            log_info "Continuing with verification steps..."
        else
            deployment_result="failed"
            log_error "Deployment failed with actual error"
            log_error "Exiting due to deployment failure"
            exit 1
        fi
    fi
    # Wait for app and get URL
    wait_for_app_ready
    local app_url
    app_url=$(az webapp show --resource-group "$RG" --name "$BACKEND_APP" --query "defaultHostName" -o tsv)
    
    # Health check and cleanup
    perform_health_check "$app_url"
    cleanup_deployment "$temp_dir"
    
    # Show summary
    show_deployment_summary "$app_url" "$deployment_result"
}

# Handle script interruption
trap 'log_error "Script interrupted by user"; exit 130' INT

# Run main function
main "$@"