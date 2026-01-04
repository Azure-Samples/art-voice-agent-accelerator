#!/bin/bash
# ============================================================================
# 🔐 Enable EasyAuth for Azure Container App (Frontend)
# ============================================================================
# This script enables Azure Container App Authentication (EasyAuth) using
# OIDC with Federated Identity Credentials instead of client secrets.
#
# Features:
#   - Creates Microsoft Entra ID app registration
#   - Configures Federated Identity Credential (FIC) for passwordless auth
#   - Enables Container App authentication with Microsoft Entra ID
#   - Uses managed identity for secure, secret-free authentication
#
# Usage:
#   ./enable-easyauth.sh \
#     --resource-group <rg-name> \
#     --container-app <app-name> \
#     --identity-client-id <client-id>
#
# Or set environment variables:
#   AZURE_RESOURCE_GROUP, FRONTEND_CONTAINER_APP_NAME, FRONTEND_UAI_CLIENT_ID
# ============================================================================

set -eo pipefail

readonly LOG_IN_BOX="${AZD_LOG_IN_BOX:-false}"

# ============================================================================
# Configuration & Defaults
# ============================================================================

readonly SCRIPT_NAME="$(basename "$0")"
readonly LOCAL_CALLBACK="http://localhost:8051/.auth/login/aad/callback"

# Cloud-specific Token Exchange Audience URIs
get_token_audience() {
    local cloud="$1"
    case "$cloud" in
        AzureCloud)         echo "api://AzureADTokenExchange" ;;
        AzureUSGovernment)  echo "api://AzureADTokenExchangeUSGov" ;;
        USNat)              echo "api://AzureADTokenExchangeUSNat" ;;
        USSec)              echo "api://AzureADTokenExchangeUSSec" ;;
        AzureChinaCloud)    echo "api://AzureADTokenExchangeChina" ;;
        *)                  echo "" ;;
    esac
}

# ============================================================================
# Logging Functions
# ============================================================================

if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${GREEN_BOLD+x}" ]]; then GREEN_BOLD=$'\033[1;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${CYAN+x}" ]]; then CYAN=$'\033[0;36m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi
readonly BLUE GREEN GREEN_BOLD YELLOW RED CYAN DIM NC

log()          { printf '│ %s%s%s\n' "$DIM" "$*" "$NC"; }
info()         { printf '│ %s%s%s\n' "$BLUE" "$*" "$NC"; }
success()      { printf '│ %s✔%s %s\n' "$GREEN" "$NC" "$*"; }
phase_success(){ printf '│ %s✔ %s%s\n' "$GREEN_BOLD" "$*" "$NC"; }
warn()         { printf '│ %s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()         { printf '│ %s✖%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

header() {
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        printf '│ %s%s%s\n' "$CYAN" "$*" "$NC"
        return
    fi
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ ${CYAN}$*${NC}"
    echo "├─────────────────────────────────────────────────────────────"
}

footer() {
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        return
    fi
    echo "╰─────────────────────────────────────────────────────────────"
    echo ""
}

# ============================================================================
# Argument Parsing
# ============================================================================

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Enable EasyAuth for Azure Container App using OIDC (Federated Identity Credentials).

OPTIONS:
    -g, --resource-group    Resource group name (or set AZURE_RESOURCE_GROUP)
    -a, --container-app     Container app name (or set FRONTEND_CONTAINER_APP_NAME)
    -i, --identity-client-id Frontend user-assigned managed identity client ID (or set FRONTEND_UAI_CLIENT_ID)
    -n, --app-name          Entra ID app registration name (default: <container-app>-easyauth)
    -c, --cloud             Azure cloud environment (default: AzureCloud)
    -h, --help              Show this help message

EXAMPLES:
    # Using command-line arguments
    $SCRIPT_NAME -g myResourceGroup -a myContainerApp -i <frontend-uai-client-id>

    # Using environment variables (e.g., from azd env)
    export AZURE_RESOURCE_GROUP=myResourceGroup
    export FRONTEND_CONTAINER_APP_NAME=myContainerApp
    export FRONTEND_UAI_CLIENT_ID=<frontend-uai-client-id>
    $SCRIPT_NAME

    # Using azd env values directly
    $SCRIPT_NAME \\
      -g "\$(azd env get-value AZURE_RESOURCE_GROUP)" \\
      -a "\$(azd env get-value FRONTEND_CONTAINER_APP_NAME)" \\
      -i "\$(azd env get-value FRONTEND_UAI_CLIENT_ID)"

EOF
    exit 0
}

parse_args() {
    RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
    CONTAINER_APP="${FRONTEND_CONTAINER_APP_NAME:-}"
    IDENTITY_CLIENT_ID="${FRONTEND_UAI_CLIENT_ID:-}"
    APP_REG_NAME=""
    CLOUD_ENV="AzureCloud"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -g|--resource-group)
                RESOURCE_GROUP="$2"
                shift 2
                ;;
            -a|--container-app)
                CONTAINER_APP="$2"
                shift 2
                ;;
            -i|--identity-client-id)
                IDENTITY_CLIENT_ID="$2"
                shift 2
                ;;
            -n|--app-name)
                APP_REG_NAME="$2"
                shift 2
                ;;
            -c|--cloud)
                CLOUD_ENV="$2"
                shift 2
                ;;
            -h|--help)
                usage
                ;;
            *)
                fail "Unknown option: $1"
                ;;
        esac
    done

    # Validate required parameters
    [[ -z "$RESOURCE_GROUP" ]] && fail "Resource group is required (-g or AZURE_RESOURCE_GROUP)"
    [[ -z "$CONTAINER_APP" ]] && fail "Container app name is required (-a or FRONTEND_CONTAINER_APP_NAME)"
    [[ -z "$IDENTITY_CLIENT_ID" ]] && fail "Identity client ID is required (-i or FRONTEND_UAI_CLIENT_ID)"

    # Default app registration name
    [[ -z "$APP_REG_NAME" ]] && APP_REG_NAME="${CONTAINER_APP}-easyauth"

    # Validate cloud environment
    if [[ -z "$(get_token_audience "$CLOUD_ENV")" ]]; then
        fail "Invalid cloud environment: $CLOUD_ENV. Valid: AzureCloud, AzureUSGovernment, USNat, USSec, AzureChinaCloud"
    fi
}

# ============================================================================
# Azure Helpers
# ============================================================================

get_tenant_id() {
    az account show --query tenantId -o tsv
}

get_container_app_fqdn() {
    az containerapp show \
        --resource-group "$RESOURCE_GROUP" \
        --name "$CONTAINER_APP" \
        --query "properties.configuration.ingress.fqdn" \
        -o tsv 2>/dev/null || echo ""
}

get_subscription_id() {
    az account show --query id -o tsv
}

# ============================================================================
# Step 1: Create or Update App Registration
# ============================================================================

create_app_registration() {
    header "🔑 Step 1: App Registration"

    local tenant_id fqdn app_endpoint callback_url app_id existing_app

    tenant_id=$(get_tenant_id)
    fqdn=$(get_container_app_fqdn)
    
    if [[ -z "$fqdn" ]]; then
        fail "Could not get Container App FQDN. Ensure the app exists and has ingress configured."
    fi

    app_endpoint="https://${fqdn}"
    callback_url="${app_endpoint}/.auth/login/aad/callback"

    log "Tenant ID: $tenant_id"
    log "App endpoint: $app_endpoint"
    log "Callback URL: $callback_url"

    # Check if app registration already exists
    existing_app=$(az ad app list --display-name "$APP_REG_NAME" --query "[0].appId" -o tsv 2>/dev/null || echo "")

    if [[ -n "$existing_app" ]]; then
        info "App registration '$APP_REG_NAME' already exists (AppId: $existing_app)"
        APP_ID="$existing_app"
        
        # Update redirect URIs
        log "Updating redirect URIs..."
        az ad app update \
            --id "$APP_ID" \
            --web-redirect-uris "$callback_url" "$LOCAL_CALLBACK" \
            --enable-id-token-issuance true \
            --output none
    else
        log "Creating app registration '$APP_REG_NAME'..."
        
        APP_ID=$(az ad app create \
            --display-name "$APP_REG_NAME" \
            --sign-in-audience "AzureADMyOrg" \
            --web-redirect-uris "$callback_url" "$LOCAL_CALLBACK" \
            --enable-id-token-issuance true \
            --query appId \
            -o tsv)
        
        success "Created app registration: $APP_ID"
    fi

    # Ensure service principal exists
    log "Ensuring service principal exists..."
    if ! az ad sp show --id "$APP_ID" &>/dev/null; then
        az ad sp create --id "$APP_ID" --output none
        success "Created service principal"
    else
        info "Service principal already exists"
    fi

    # Store values for later steps
    TENANT_ID="$tenant_id"
    APP_ENDPOINT="$app_endpoint"
    ISSUER="https://login.microsoftonline.com/${tenant_id}/v2.0"

    footer
}

# ============================================================================
# Step 2: Configure Federated Identity Credential on App Registration
# ============================================================================

get_uami_details_from_container_app() {
    # Get the user-assigned managed identity resource ID from the container app
    local uami_resource_id
    uami_resource_id=$(az containerapp show \
        --resource-group "$RESOURCE_GROUP" \
        --name "$CONTAINER_APP" \
        --query "identity.userAssignedIdentities | keys(@) | [0]" \
        -o tsv 2>/dev/null)
    
    if [[ -z "$uami_resource_id" ]]; then
        return 1
    fi
    
    # Extract UAMI name from resource ID
    UAMI_NAME=$(echo "$uami_resource_id" | sed 's|.*/||')
    
    # Get UAMI client ID and principal ID
    local uami_details
    uami_details=$(az identity show \
        --ids "$uami_resource_id" \
        --query "{clientId:clientId, principalId:principalId}" \
        -o json 2>/dev/null)
    
    UAMI_CLIENT_ID=$(echo "$uami_details" | jq -r '.clientId')
    UAMI_PRINCIPAL_ID=$(echo "$uami_details" | jq -r '.principalId')
}

configure_federated_credential() {
    header "🔗 Step 2: Federated Identity Credential on App Registration"

    local fic_name="miAsFic"
    local audience
    audience=$(get_token_audience "$CLOUD_ENV")

    log "Cloud: $CLOUD_ENV"
    log "Audience: $audience"
    
    # Get the UAMI details from the container app
    if ! get_uami_details_from_container_app; then
        fail "Could not find user-assigned managed identity on container app"
    fi
    
    log "UAMI Name: $UAMI_NAME"
    log "UAMI Client ID: $UAMI_CLIENT_ID"
    log "UAMI Principal ID: $UAMI_PRINCIPAL_ID"
    log "Issuer: $ISSUER"
    log "Subject (UAMI Principal ID): $UAMI_PRINCIPAL_ID"

    # Check if FIC already exists on the App Registration
    local existing_fic
    existing_fic=$(az ad app federated-credential list \
        --id "$APP_ID" \
        --query "[?name=='$fic_name'].id" \
        -o tsv 2>/dev/null || echo "")

    if [[ -n "$existing_fic" ]]; then
        info "Federated credential '$fic_name' already exists on App Registration, updating..."
        
        az ad app federated-credential update \
            --id "$APP_ID" \
            --federated-credential-id "$fic_name" \
            --parameters "{
                \"name\": \"$fic_name\",
                \"issuer\": \"$ISSUER\",
                \"subject\": \"$UAMI_PRINCIPAL_ID\",
                \"audiences\": [\"$audience\"],
                \"description\": \"Managed Identity as FIC for EasyAuth\"
            }" \
            --output none
        
        success "Updated federated credential on App Registration"
    else
        log "Creating federated identity credential on App Registration..."
        
        az ad app federated-credential create \
            --id "$APP_ID" \
            --parameters "{
                \"name\": \"$fic_name\",
                \"issuer\": \"$ISSUER\",
                \"subject\": \"$UAMI_PRINCIPAL_ID\",
                \"audiences\": [\"$audience\"],
                \"description\": \"Managed Identity as FIC for EasyAuth\"
            }" \
            --output none
        
        success "Created federated credential on App Registration"
    fi

    footer
}

# ============================================================================
# Step 3: Add UAMI Client ID as Container App Secret
# ============================================================================

configure_container_app_secret() {
    header "🔒 Step 3: Container App Secret"

    local secret_name="override-use-mi-fic-assertion-client-id"
    
    log "Setting secret '$secret_name' with UAMI client ID..."
    log "UAMI Client ID: $UAMI_CLIENT_ID"
    
    # Azure Container Apps require secrets for the clientSecretSettingName
    # When using FIC, we store the UAMI's client ID as the "secret"
    az containerapp secret set \
        --resource-group "$RESOURCE_GROUP" \
        --name "$CONTAINER_APP" \
        --secrets "${secret_name}=${UAMI_CLIENT_ID}" \
        --output none 2>/dev/null || true

    success "Secret configured"
    footer
}

# ============================================================================
# Step 4: Enable Container App Authentication
# ============================================================================

enable_container_app_auth() {
    header "🛡️ Step 4: Container App Authentication"

    log "Configuring authentication..."
    log "App ID: $APP_ID"
    log "Issuer: $ISSUER"

    # Enable authentication using Azure CLI
    # Note: Using the REST API approach for full control
    local subscription_id resource_id api_version auth_config
    
    subscription_id=$(get_subscription_id)
    resource_id="/subscriptions/${subscription_id}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/containerApps/${CONTAINER_APP}"
    api_version="2024-03-01"

    auth_config=$(cat <<EOF
{
    "properties": {
        "platform": {
            "enabled": true
        },
        "globalValidation": {
            "redirectToProvider": "azureactivedirectory",
            "unauthenticatedClientAction": "RedirectToLoginPage"
        },
        "identityProviders": {
            "azureActiveDirectory": {
                "enabled": true,
                "registration": {
                    "clientId": "$APP_ID",
                    "clientSecretSettingName": "override-use-mi-fic-assertion-client-id",
                    "openIdIssuer": "$ISSUER"
                },
                "validation": {
                    "defaultAuthorizationPolicy": {
                        "allowedApplications": []
                    }
                }
            }
        },
        "login": {
            "tokenStore": {
                "enabled": false
            }
        }
    }
}
EOF
)

    # Use Azure REST API to configure auth
    az rest \
        --method PUT \
        --uri "${resource_id}/authConfigs/current?api-version=${api_version}" \
        --body "$auth_config" \
        --output none

    success "Authentication enabled"
    footer
}

# ============================================================================
# Summary
# ============================================================================

show_summary() {
    header "📋 Summary"

    log "EasyAuth has been configured for your Container App!"
    log ""
    log "Configuration:"
    log "  • Container App: $CONTAINER_APP"
    log "  • App Registration: $APP_REG_NAME"
    log "  • App ID (Client ID): $APP_ID"
    log "  • Issuer: $ISSUER"
    log "  • Authentication: OIDC with Federated Identity Credential"
    log "  • Redirect URI: ${APP_ENDPOINT}/.auth/login/aad/callback"
    log ""
    log "Federated Credential on App Registration:"
    log "  • Issuer: $ISSUER"
    log "  • Subject (UAMI Principal ID): $UAMI_PRINCIPAL_ID"
    log "  • Audience: $(get_token_audience "$CLOUD_ENV")"
    log ""
    log "User-Assigned Managed Identity:"
    log "  • UAMI Name: $UAMI_NAME"
    log "  • UAMI Client ID: $UAMI_CLIENT_ID"
    log "  • UAMI Principal ID: $UAMI_PRINCIPAL_ID"
    log ""
    log "Key benefits of FIC over client secrets:"
    log "  ✔ No secrets to manage or rotate"
    log "  ✔ Uses managed identity for authentication"
    log "  ✔ More secure (no credentials stored)"
    log ""
    log "Test the authentication:"
    log "  curl -I ${APP_ENDPOINT}"
    log ""
    log "You should see a redirect to login.microsoftonline.com"

    footer
    success "EasyAuth setup complete!"
}

# ============================================================================
# Main
# ============================================================================

main() {
    parse_args "$@"

    header "🔐 Enable EasyAuth (OIDC/FIC)"
    log "Resource Group: $RESOURCE_GROUP"
    log "Container App: $CONTAINER_APP"
    log "Identity Client ID: $IDENTITY_CLIENT_ID"
    log "App Registration: $APP_REG_NAME"
    log "Cloud Environment: $CLOUD_ENV"
    footer

    # Verify Azure CLI is logged in
    if ! az account show &>/dev/null; then
        fail "Not logged in to Azure CLI. Run 'az login' first."
    fi

    create_app_registration
    configure_federated_credential
    configure_container_app_secret
    enable_container_app_auth
    show_summary
}

main "$@"
