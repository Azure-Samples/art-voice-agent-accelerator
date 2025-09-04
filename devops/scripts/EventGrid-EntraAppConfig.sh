#!/bin/bash

# NOTE: Before running this script ensure you are logged in Azure by using "az login" command.

# Configuration variables - replace with actual values
$eventGridAppId = "[REPLACE_WITH_EVENT_GRID_APP_ID]"
$webhookAppObjectId = "[REPLACE_WITH_YOUR_ID]"
$eventSubscriptionWriterAppId = "[REPLACE_WITH_YOUR_ID]"

# Event Grid role name - don't modify this
EVENT_GRID_ROLE_NAME="AzureEventGridSecureWebhookSubscriber"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to generate a new GUID
generate_guid() {
    if command -v uuidgen &> /dev/null; then
        uuidgen | tr '[:upper:]' '[:lower:]'
    else
        # Fallback for systems without uuidgen
        python3 -c "import uuid; print(str(uuid.uuid4()))"
    fi
}

# Function to log messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if service principal exists
check_service_principal() {
    local app_id=$1
    az ad sp show --id "$app_id" --query "id" -o tsv 2>/dev/null
}

# Function to check if app role exists
check_app_role() {
    local app_object_id=$1
    local role_name=$2
    az ad app show --id "$app_object_id" --query "appRoles[?displayName=='$role_name'].id" -o tsv 2>/dev/null
}

# Function to create app role
create_app_role() {
    local app_object_id=$1
    local role_name=$2
    local description=$3
    local role_id=$(generate_guid)
    
    # Get existing app roles
    local existing_roles=$(az ad app show --id "$app_object_id" --query "appRoles" -o json)
    
    # Create new role object
    local new_role=$(cat <<EOF
{
    "allowedMemberTypes": ["Application", "User"],
    "description": "$description",
    "displayName": "$role_name",
    "id": "$role_id",
    "isEnabled": true,
    "value": "$role_name"
}
EOF
)
    
    # Add new role to existing roles
    local updated_roles=$(echo "$existing_roles" | jq ". + [$new_role]")
    
    # Update the application with new roles
    az ad app update --id "$app_object_id" --app-roles "$updated_roles"
    echo "$role_id"
}

# Function to create role assignment
create_role_assignment() {
    local service_principal_id=$1
    local principal_id=$2
    local resource_id=$3
    local app_role_id=$4
    
    az ad app role assignment create \
        --assignee "$principal_id" \
        --resource-app "$resource_id" \
        --role "$app_role_id" 2>/dev/null
}

# Main execution
main() {
    log_info "Starting Event Grid App Configuration setup..."
    
    # Check if Azure CLI is installed
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if jq is installed (required for JSON manipulation)
    if ! command -v jq &> /dev/null; then
        log_error "jq is not installed. Please install it first (brew install jq on macOS, apt-get install jq on Ubuntu)."
        exit 1
    fi
    
    # Validate input parameters
    if [[ "$EVENT_GRID_APP_ID" == "[REPLACE_WITH_EVENT_GRID_APP_ID]" ]]; then
        log_error "Please replace EVENT_GRID_APP_ID with the actual Event Grid application ID"
        exit 1
    fi
    
    if [[ "$WEBHOOK_APP_OBJECT_ID" == "[REPLACE_WITH_YOUR_ID]" ]]; then
        log_error "Please replace WEBHOOK_APP_OBJECT_ID with the actual webhook application object ID"
        exit 1
    fi
    
    if [[ "$EVENT_SUBSCRIPTION_WRITER_APP_ID" == "[REPLACE_WITH_YOUR_ID]" ]]; then
        log_error "Please replace EVENT_SUBSCRIPTION_WRITER_APP_ID with the actual event subscription writer application ID"
        exit 1
    fi
    
    # Step 1: Check/Create Event Grid Service Principal
    log_info "Checking Event Grid Microsoft Entra Application..."
    
    local eventgrid_sp_id=$(check_service_principal "$EVENT_GRID_APP_ID")
    if [[ -n "$eventgrid_sp_id" ]]; then
        local display_name=$(az ad sp show --id "$EVENT_GRID_APP_ID" --query "displayName" -o tsv)
        if [[ "$display_name" == *"Microsoft.EventGrid"* ]]; then
            log_info "The Event Grid Microsoft Entra Application is already defined."
        fi
    else
        log_info "Creating the Azure Event Grid Microsoft Entra Application"
        az ad sp create --id "$EVENT_GRID_APP_ID"
        eventgrid_sp_id=$(check_service_principal "$EVENT_GRID_APP_ID")
    fi
    
    # Step 2: Get webhook application details
    log_info "Getting webhook application details..."
    
    local webhook_app=$(az ad app show --id "$WEBHOOK_APP_OBJECT_ID" --query "{appId: appId, objectId: id, appRoles: appRoles}" -o json)
    local webhook_app_id=$(echo "$webhook_app" | jq -r '.appId')
    local webhook_object_id=$(echo "$webhook_app" | jq -r '.objectId')
    
    log_info "Current app roles:"
    echo "$webhook_app" | jq -r '.appRoles[].displayName'
    
    # Step 3: Check/Create Azure Event Grid app role
    log_info "Checking Azure Event Grid role in Microsoft Entra Application: $WEBHOOK_APP_OBJECT_ID"
    
    local existing_role_id=$(check_app_role "$WEBHOOK_APP_OBJECT_ID" "$EVENT_GRID_ROLE_NAME")
    if [[ -n "$existing_role_id" ]]; then
        log_info "The Azure Event Grid role is already defined."
    else
        log_info "Creating the Azure Event Grid role in Microsoft Entra Application: $WEBHOOK_APP_OBJECT_ID"
        existing_role_id=$(create_app_role "$WEBHOOK_APP_OBJECT_ID" "$EVENT_GRID_ROLE_NAME" "Azure Event Grid Role")
    fi
    
    # Step 4: Get service principal for webhook app
    local webhook_sp_id=$(check_service_principal "$webhook_app_id")
    if [[ -z "$webhook_sp_id" ]]; then
        log_info "Creating service principal for webhook app"
        az ad sp create --id "$webhook_app_id"
        webhook_sp_id=$(check_service_principal "$webhook_app_id")
    fi
    
    # Step 5: Check/Create Event Subscription Writer Service Principal
    log_info "Checking Event Subscription Writer Microsoft Entra Application..."
    
    local writer_sp_id=$(check_service_principal "$EVENT_SUBSCRIPTION_WRITER_APP_ID")
    if [[ -z "$writer_sp_id" ]]; then
        log_info "Creating new Microsoft Entra Application for Event Subscription Writer"
        az ad sp create --id "$EVENT_SUBSCRIPTION_WRITER_APP_ID"
        writer_sp_id=$(check_service_principal "$EVENT_SUBSCRIPTION_WRITER_APP_ID")
    fi
    
    # Step 6: Create role assignment for Event Subscription Writer
    log_info "Creating the Microsoft Entra Application role assignment for Event Subscription Writer: $EVENT_SUBSCRIPTION_WRITER_APP_ID"
    
    if create_role_assignment "$writer_sp_id" "$writer_sp_id" "$webhook_app_id" "$existing_role_id"; then
        log_info "Role assignment created successfully for Event Subscription Writer"
    else
        log_warn "Role assignment may already exist for Event Subscription Writer"
    fi
    
    # Step 7: Create role assignment for Event Grid Service Principal
    log_info "Creating the service app role assignment for Event Grid Microsoft Entra Application"
    
    if create_role_assignment "$eventgrid_sp_id" "$eventgrid_sp_id" "$webhook_app_id" "$existing_role_id"; then
        log_info "Role assignment created successfully for Event Grid"
    else
        log_warn "Role assignment may already exist for Event Grid"
    fi
    
    # Step 8: Print output references
    log_info "Configuration completed successfully!"
    echo ""
    echo ">> Webhook's Microsoft Entra Application Id: $webhook_app_id"
    echo ">> Webhook's Microsoft Entra Application Object Id: $webhook_object_id"
    echo ">> Event Grid Role Id: $existing_role_id"
}

# Error handling
set -e
trap 'log_error "Script failed on line $LINENO"' ERR

# Run main function
main "$@"
