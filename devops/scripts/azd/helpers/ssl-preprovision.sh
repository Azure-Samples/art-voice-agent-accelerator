#!/bin/bash

# Azure Developer CLI Pre-Provisioning Script
# This script runs before azd provision to check SSL certificate configuration

readonly LOG_IN_BOX="${AZD_LOG_IN_BOX:-false}"

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
fail()         { printf '│ %s✖%s %s\n' "$RED" "$NC" "$*" >&2; }

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

prompt() {
    local prompt_text="$1"
    local __var="$2"
    if [[ "$LOG_IN_BOX" == "true" ]]; then
        read -rp "│ ${prompt_text}" "$__var"
    else
        read -rp "${prompt_text}" "$__var"
    fi
}

header "🔒 SSL Certificate Configuration Check"
log "======================================"
log ""

# Check if user is bringing their own SSL certificate
# Check if SSL certificate environment variables are already set
EXISTING_SSL_SECRET_ID=$(azd env get-values | grep AZURE_SSL_KEY_VAULT_SECRET_ID | cut -d'=' -f2 | tr -d '"')
EXISTING_USER_IDENTITY=$(azd env get-values | grep AZURE_KEY_VAULT_SECRET_USER_IDENTITY | cut -d'=' -f2 | tr -d '"')

if [[ -n "$EXISTING_SSL_SECRET_ID" && -n "$EXISTING_USER_IDENTITY" ]]; then
    success "SSL certificate configuration already found:"
    log "   AZURE_SSL_KEY_VAULT_SECRET_ID: $EXISTING_SSL_SECRET_ID"
    log "   AZURE_KEY_VAULT_SECRET_USER_IDENTITY: $EXISTING_USER_IDENTITY"
    
    # # Check if SSL certificate password is already set
    # EXISTING_SSL_PASSWORD=$(azd env get-values | grep AZURE_SSL_CERTIFICATE_PASSWORD | cut -d'=' -f2 | tr -d '"')
    # if [[ -n "$EXISTING_SSL_PASSWORD" ]]; then
    #     echo "   AZURE_SSL_CERTIFICATE_PASSWORD: ****** (configured)"
    # fi
    
    bring_own_cert="y"
else
    prompt "Are you bringing your own SSL certificate? (y/n): " bring_own_cert
fi

if [[ "$bring_own_cert" =~ ^[Yy]$ ]]; then
    log ""
    success "Great! Make sure your SSL certificate is uploaded to Azure Key Vault."
    log "   The certificate should be accessible via managed identity from your resources."
    log ""
    log "📝 Required environment variables:"
    log "   - AZURE_SSL_KEY_VAULT_SECRET_ID: Secret ID (should look like 'https://<kv-name>.vault.azure.net/secrets/<secret-name>/<secret-version>')"
    log "   - AZURE_KEY_VAULT_SECRET_USER_IDENTITY: Pre-configured Resource ID of a User Assigned Identity resource with access to the key vault secret for the app gateway"
    log "   - AZURE_SSL_CERTIFICATE_PASSWORD: (Optional) Password for the SSL certificate if it's password-protected"
    log ""
    # Prompt for SSL Key Vault Secret ID if not already set
    if [[ -z "$EXISTING_SSL_SECRET_ID" ]]; then
        log "🔑 SSL Key Vault Secret ID Configuration"
        log "======================================="
        log ""
        log "Example format: https://my-keyvault.vault.azure.net/secrets/my-ssl-cert/abc123def456"
        log ""
        prompt "Enter your SSL Key Vault Secret ID: " ssl_secret_id
        
        if [[ -n "$ssl_secret_id" ]]; then
            azd env set AZURE_SSL_KEY_VAULT_SECRET_ID "$ssl_secret_id"
            success "SSL Key Vault Secret ID has been set."
        else
            log "⚠️  No SSL Key Vault Secret ID provided. You can set it later with:"
            log "   azd env set AZURE_SSL_KEY_VAULT_SECRET_ID '<your-ssl-secret-id>'"
        fi
        log ""
    fi

    # Prompt for User Assigned Identity Resource ID if not already set
    if [[ -z "$EXISTING_USER_IDENTITY" ]]; then
        log "👤 User Assigned Identity Configuration"
        log "======================================"
        log ""
        log "Example format: /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/my-rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/my-identity"
        log ""
        prompt "Enter your User Assigned Identity Resource ID: " user_identity_id
        
        if [[ -n "$user_identity_id" ]]; then
            azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY "$user_identity_id"
            success "User Assigned Identity Resource ID has been set."
        else
            log "⚠️  No User Assigned Identity Resource ID provided. You can set it later with:"
            log "   azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY '<your-user-identity-resource-id>'"
        fi
        log ""
    fi
    # # Check if SSL certificate password is needed
    # EXISTING_SSL_PASSWORD=$(azd env get-values | grep AZURE_SSL_CERTIFICATE_PASSWORD | cut -d'=' -f2 | tr -d '"')
    
    # if [[ -z "$EXISTING_SSL_PASSWORD" ]]; then
    #     echo "🔐 SSL Certificate Password Configuration"
    #     echo "======================================="
    #     echo ""
    #     read -p "Is your SSL certificate password-protected? (y/n): " has_password
        
    #     if [[ "$has_password" =~ ^[Yy]$ ]]; then
    #         read -s -p "Enter the SSL certificate password: " ssl_password
    #         echo ""
            
    #         if [[ -n "$ssl_password" ]]; then
    #             azd env set AZURE_SSL_CERTIFICATE_PASSWORD "$ssl_password"
    #             echo "✔ SSL certificate password has been set."
    #         else
    #             echo "⚠️  No password provided. You can set it later with:"
    #             echo "   azd env set AZURE_SSL_CERTIFICATE_PASSWORD '<your-ssl-password>'"
    #         fi
    #     else
    #         echo "✔ No password required for SSL certificate."
    #     fi
    # else
    #     echo "✔ SSL certificate password already configured."
    # fi
    
    # Check if domain FQDN is already set
    EXISTING_DOMAIN_FQDN=$(azd env get-values | grep AZURE_DOMAIN_FQDN | cut -d'=' -f2 | tr -d '"')
    
    if [[ -z "$EXISTING_DOMAIN_FQDN" ]]; then
        log ""
        log "🌐 Domain Configuration"
        log "======================"
        log ""
        prompt "Enter your custom domain FQDN (e.g., app.yourdomain.com): " domain_fqdn
        
        if [[ -n "$domain_fqdn" ]]; then
            azd env set AZURE_DOMAIN_FQDN "$domain_fqdn"
            success "Domain FQDN set to: $domain_fqdn"
        else
            log "⚠️  No domain FQDN provided. You can set it later with:"
            log "   azd env set AZURE_DOMAIN_FQDN '<your-domain-fqdn>'"
        fi
    else
        success "Domain FQDN already configured: $EXISTING_DOMAIN_FQDN"
    fi
else
    log ""
    log "📋 To configure SSL certificates for your Azure App Gateway using App Service Certificates:"
    log ""
    log "1. 📖 Follow the official Azure documentation:"
    log "   https://docs.microsoft.com/en-us/azure/app-service/configure-ssl-certificate"
    log ""
    log "2. 🔧 Steps to configure:"
    log "   - Create/purchase an SSL certificate through Azure App Service"
    log "   - Configure custom domain in App Service"
    log "   - Upload certificate to Azure Key Vault"
    log "   - Configure managed identity access to Key Vault"
    log ""
    log "3. 🔑 After uploading to Key Vault, set these environment variables:"
    log "   azd env set AZURE_SSL_KEY_VAULT_SECRET_ID '<your-keyvault-secret-id>'"
    log "   azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY '<your-preconfigured-user-assigned-identity-with-kv-access-resource-id>'"
    log "   azd env set AZURE_DOMAIN_FQDN '<your-custom-domain-fqdn>'"
    log "   azd env set AZURE_SSL_CERTIFICATE_PASSWORD '<your-ssl-password>' # Only if certificate is password-protected"
    log ""
    log "⚠️  SSL configuration is recommended for production deployments."
    log ""
    
    prompt "Do you want to continue without SSL configuration? (y/n): " continue_without_ssl
    
    if [[ ! "$continue_without_ssl" =~ ^[Yy]$ ]]; then
        fail "Exiting. Please configure SSL certificates and run azd provision again."
        footer
        exit 1
    fi
fi

log ""
log "🌐 Frontend Security Configuration"
log "================================="
log ""
log "⚠️  The frontend client will be publicly exposed by default."
log "   This means anyone with the URL can access your voice agent application."
log ""
# Check if ENABLE_EASY_AUTH is already set
EXISTING_EASY_AUTH=$(azd env get-values | grep ENABLE_EASY_AUTH | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_EASY_AUTH" ]]; then
    prompt "Would you like to enable Azure Container Apps Easy Auth (Entra) for additional security? (y/n): " enable_easy_auth

    if [[ "$enable_easy_auth" =~ ^[Yy]$ ]]; then
        log ""
        log "🔐 Enabling Easy Auth (Entra) for the frontend container app..."
        azd env set ENABLE_EASY_AUTH true
        success "Easy Auth (Entra) will be configured during provisioning."
        log ""
        log "📝 Note: You'll need to configure your identity provider (Azure AD, GitHub, etc.)"
        log "   in the Azure portal after deployment is complete."
    else
        log ""
        log "⚠️  Frontend will remain publicly accessible without authentication."
        log "   Consider enabling Easy Auth for production deployments."
        azd env set ENABLE_EASY_AUTH false
    fi
else
    success "Easy Auth configuration already found: ENABLE_EASY_AUTH = $EXISTING_EASY_AUTH"
fi


log ""
phase_success "Pre-provisioning checks complete. Proceeding with azd provision..."


log ""
log "👥 Azure Entra Group Configuration"
log "================================="
log ""

# Check if AZURE_ENTRA_GROUP_ID is already set
EXISTING_ENTRA_GROUP_ID=$(azd env get-values | grep AZURE_ENTRA_GROUP_ID | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_ENTRA_GROUP_ID" ]]; then
    log "🔍 No Azure Entra Group ID found in current environment."
    log ""
    prompt "Would you like to create a new Azure Entra group for this deployment? (y/n): " create_entra_group
    
    if [[ "$create_entra_group" =~ ^[Yy]$ ]]; then
        log ""
        # Get environment name from azd
        AZURE_ENV_NAME=$(azd env get-values | grep AZURE_ENV_NAME | cut -d'=' -f2 | tr -d '"')
        DEFAULT_GROUP_NAME="rtaudio-apimUsers-${AZURE_ENV_NAME:-default}"
        
        prompt "Enter a name for the new Entra group [$DEFAULT_GROUP_NAME]: " group_name
        
        # Use default if no input provided
        if [[ -z "$group_name" ]]; then
            group_name="$DEFAULT_GROUP_NAME"
        fi
        
        if [[ -z "$group_name" ]]; then
            warn "Group name cannot be empty. Skipping Entra group creation."
        else
            log "🔄 Creating Azure Entra group: $group_name"
            
            # Create the Entra group and capture the object ID
            GROUP_ID=$(az ad group create \
                --display-name "$group_name" \
                --mail-nickname "$(echo "$group_name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')" \
                --description "Security group for $group_name deployment" \
                --query id -o tsv)
            if [[ -n "$GROUP_ID" ]]; then
                success "Successfully created Entra group with ID: $GROUP_ID"
                
                # Set the environment variable
                azd env set AZURE_ENTRA_GROUP_ID "$GROUP_ID"
                success "Environment variable AZURE_ENTRA_GROUP_ID set to: $GROUP_ID"
                
                log ""
                log "📝 Note: You can add users to this group later via:"
                log "   az ad group member add --group '$group_name' --member-id '<user-object-id>'"
                log ""
                log "🔄 The post-provision script will automatically add the backend container's"
                log "   user assigned identity to this group for proper access permissions."
            else
                warn "Failed to create Entra group. Please create manually and set AZURE_ENTRA_GROUP_ID."
            fi
        fi
    else
        log "⚠️  Skipping Entra group creation. You can set AZURE_ENTRA_GROUP_ID manually later:"
        log "   azd env set AZURE_ENTRA_GROUP_ID '<your-group-object-id>'"
        log ""
        log "⚠️  Note: Without a configured Entra group, the API Management Azure OpenAI policy"
        log "   needs to be updated manually as it currently evaluates based on group membership."
    fi
else
    success "Azure Entra Group ID already configured: $EXISTING_ENTRA_GROUP_ID"
fi

log ""
log "🖥️  Jumphost VM Configuration"
log "============================="
log ""

# Check if AZURE_JUMPHOST_VM_PASSWORD is already set
EXISTING_VM_PASSWORD=$(azd env get-values | grep AZURE_JUMPHOST_VM_PASSWORD | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_VM_PASSWORD" ]]; then
    log "🔐 No jumphost VM password found in current environment."
    log "🔄 Generating secure password for jumphost VM..."
    
    # Generate a secure password with at least 12 characters including uppercase, lowercase, numbers, and symbols
    VM_PASSWORD=$(openssl rand -base64 18 | tr -d "=+/" | cut -c1-16)
    # Ensure password complexity by adding required character types
    VM_PASSWORD="${VM_PASSWORD}A1!"
    
    # Set the environment variable
    azd env set AZURE_JUMPHOST_VM_PASSWORD "$VM_PASSWORD"
    success "Generated and set secure password for jumphost VM."
    log "📝 Password has been stored in azd environment variables."
    log ""
    log "⚠️  Important: This password will be stored in the Key Vault provisioned by this deployment."
    # Password is securely stored in environment variables and Key Vault. Not displayed for security.
    log ""
else
    success "Jumphost VM password already configured."
fi

footer
