#!/bin/bash

# Azure Developer CLI Pre-Provisioning Script
# This script runs before azd provision to check SSL certificate configuration

echo "🔒 SSL Certificate Configuration Check"
echo "======================================"
echo ""

# Check if user is bringing their own SSL certificate
# Check if SSL certificate environment variables are already set
EXISTING_SSL_SECRET_ID=$(azd env get-values | grep AZURE_SSL_KEY_VAULT_SECRET_ID | cut -d'=' -f2 | tr -d '"')
EXISTING_USER_IDENTITY=$(azd env get-values | grep AZURE_KEY_VAULT_SECRET_USER_IDENTITY | cut -d'=' -f2 | tr -d '"')

if [[ -n "$EXISTING_SSL_SECRET_ID" && -n "$EXISTING_USER_IDENTITY" ]]; then
    echo "✅ SSL certificate configuration already found:"
    echo "   AZURE_SSL_KEY_VAULT_SECRET_ID: $EXISTING_SSL_SECRET_ID"
    echo "   AZURE_KEY_VAULT_SECRET_USER_IDENTITY: $EXISTING_USER_IDENTITY"
    
    # # Check if SSL certificate password is already set
    # EXISTING_SSL_PASSWORD=$(azd env get-values | grep AZURE_SSL_CERTIFICATE_PASSWORD | cut -d'=' -f2 | tr -d '"')
    # if [[ -n "$EXISTING_SSL_PASSWORD" ]]; then
    #     echo "   AZURE_SSL_CERTIFICATE_PASSWORD: ****** (configured)"
    # fi
    
    bring_own_cert="y"
else
    read -p "Are you bringing your own SSL certificate? (y/n): " bring_own_cert
fi

if [[ "$bring_own_cert" =~ ^[Yy]$ ]]; then
    echo ""
    echo "✅ Great! Make sure your SSL certificate is uploaded to Azure Key Vault."
    echo "   The certificate should be accessible via managed identity from your resources."
    echo ""
    echo "📝 Required environment variables:"
    echo "   - AZURE_SSL_KEY_VAULT_SECRET_ID: Secret ID (should look like 'https://<kv-name>.vault.azure.net/secrets/<secret-name>/<secret-version>')"
    echo "   - AZURE_KEY_VAULT_SECRET_USER_IDENTITY: Pre-configured Resource ID of a User Assigned Identity resource with access to the key vault secret for the app gateway"
    echo "   - AZURE_SSL_CERTIFICATE_PASSWORD: (Optional) Password for the SSL certificate if it's password-protected"
    echo ""
    # Prompt for SSL Key Vault Secret ID if not already set
    if [[ -z "$EXISTING_SSL_SECRET_ID" ]]; then
        echo "🔑 SSL Key Vault Secret ID Configuration"
        echo "======================================="
        echo ""
        echo "Example format: https://my-keyvault.vault.azure.net/secrets/my-ssl-cert/abc123def456"
        echo ""
        read -p "Enter your SSL Key Vault Secret ID: " ssl_secret_id
        
        if [[ -n "$ssl_secret_id" ]]; then
            azd env set AZURE_SSL_KEY_VAULT_SECRET_ID "$ssl_secret_id"
            echo "✅ SSL Key Vault Secret ID has been set."
        else
            echo "⚠️  No SSL Key Vault Secret ID provided. You can set it later with:"
            echo "   azd env set AZURE_SSL_KEY_VAULT_SECRET_ID '<your-ssl-secret-id>'"
        fi
        echo ""
    fi

    # Prompt for User Assigned Identity Resource ID if not already set
    if [[ -z "$EXISTING_USER_IDENTITY" ]]; then
        echo "👤 User Assigned Identity Configuration"
        echo "======================================"
        echo ""
        echo "Example format: /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/my-rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/my-identity"
        echo ""
        read -p "Enter your User Assigned Identity Resource ID: " user_identity_id
        
        if [[ -n "$user_identity_id" ]]; then
            azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY "$user_identity_id"
            echo "✅ User Assigned Identity Resource ID has been set."
        else
            echo "⚠️  No User Assigned Identity Resource ID provided. You can set it later with:"
            echo "   azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY '<your-user-identity-resource-id>'"
        fi
        echo ""
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
    #             echo "✅ SSL certificate password has been set."
    #         else
    #             echo "⚠️  No password provided. You can set it later with:"
    #             echo "   azd env set AZURE_SSL_CERTIFICATE_PASSWORD '<your-ssl-password>'"
    #         fi
    #     else
    #         echo "✅ No password required for SSL certificate."
    #     fi
    # else
    #     echo "✅ SSL certificate password already configured."
    # fi
    
    # Check if domain FQDN is already set
    EXISTING_DOMAIN_FQDN=$(azd env get-values | grep AZURE_DOMAIN_FQDN | cut -d'=' -f2 | tr -d '"')
    
    if [[ -z "$EXISTING_DOMAIN_FQDN" ]]; then
        echo ""
        echo "🌐 Domain Configuration"
        echo "======================"
        echo ""
        read -p "Enter your custom domain FQDN (e.g., app.yourdomain.com): " domain_fqdn
        
        if [[ -n "$domain_fqdn" ]]; then
            azd env set AZURE_DOMAIN_FQDN "$domain_fqdn"
            echo "✅ Domain FQDN set to: $domain_fqdn"
        else
            echo "⚠️  No domain FQDN provided. You can set it later with:"
            echo "   azd env set AZURE_DOMAIN_FQDN '<your-domain-fqdn>'"
        fi
    else
        echo "✅ Domain FQDN already configured: $EXISTING_DOMAIN_FQDN"
    fi
else
    echo ""
    echo "📋 To configure SSL certificates for your Azure App Gateway using App Service Certificates:"
    echo ""
    echo "1. 📖 Follow the official Azure documentation:"
    echo "   https://docs.microsoft.com/en-us/azure/app-service/configure-ssl-certificate"
    echo ""
    echo "2. 🔧 Steps to configure:"
    echo "   - Create/purchase an SSL certificate through Azure App Service"
    echo "   - Configure custom domain in App Service"
    echo "   - Upload certificate to Azure Key Vault"
    echo "   - Configure managed identity access to Key Vault"
    echo ""
    echo "3. 🔑 After uploading to Key Vault, set these environment variables:"
    echo "   azd env set AZURE_SSL_KEY_VAULT_SECRET_ID '<your-keyvault-secret-id>'"
    echo "   azd env set AZURE_KEY_VAULT_SECRET_USER_IDENTITY '<your-preconfigured-user-assigned-identity-with-kv-access-resource-id>'"
    echo "   azd env set AZURE_DOMAIN_FQDN '<your-custom-domain-fqdn>'"
    echo "   azd env set AZURE_SSL_CERTIFICATE_PASSWORD '<your-ssl-password>' # Only if certificate is password-protected"
    echo ""
    echo "⚠️  SSL configuration is recommended for production deployments."
    echo ""
    
    read -p "Do you want to continue without SSL configuration? (y/n): " continue_without_ssl
    
    if [[ ! "$continue_without_ssl" =~ ^[Yy]$ ]]; then
        echo "❌ Exiting. Please configure SSL certificates and run azd provision again."
        exit 1
    fi
fi

echo ""
echo "🌐 Frontend Security Configuration"
echo "================================="
echo ""
echo "⚠️  The frontend client will be publicly exposed by default."
echo "   This means anyone with the URL can access your voice agent application."
echo ""
# Check if ENABLE_EASY_AUTH is already set
EXISTING_EASY_AUTH=$(azd env get-values | grep ENABLE_EASY_AUTH | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_EASY_AUTH" ]]; then
    read -p "Would you like to enable Azure Container Apps Easy Auth (Entra) for additional security? (y/n): " enable_easy_auth

    if [[ "$enable_easy_auth" =~ ^[Yy]$ ]]; then
        echo ""
        echo "🔐 Enabling Easy Auth (Entra) for the frontend container app..."
        azd env set ENABLE_EASY_AUTH true
        echo "✅ Easy Auth (Entra) will be configured during provisioning."
        echo ""
        echo "📝 Note: You'll need to configure your identity provider (Azure AD, GitHub, etc.)"
        echo "   in the Azure portal after deployment is complete."
    else
        echo ""
        echo "⚠️  Frontend will remain publicly accessible without authentication."
        echo "   Consider enabling Easy Auth for production deployments."
        azd env set ENABLE_EASY_AUTH false
    fi
else
    echo "✅ Easy Auth configuration already found: ENABLE_EASY_AUTH = $EXISTING_EASY_AUTH"
fi


echo ""
echo "✅ Pre-provisioning checks complete. Proceeding with azd provision..."


echo ""
echo "👥 Azure Entra Group Configuration"
echo "================================="
echo ""

# Check if AZURE_ENTRA_GROUP_ID is already set
EXISTING_ENTRA_GROUP_ID=$(azd env get-values | grep AZURE_ENTRA_GROUP_ID | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_ENTRA_GROUP_ID" ]]; then
    echo "🔍 No Azure Entra Group ID found in current environment."
    echo ""
    read -p "Would you like to create a new Azure Entra group for this deployment? (y/n): " create_entra_group
    
    if [[ "$create_entra_group" =~ ^[Yy]$ ]]; then
        echo ""
        # Get environment name from azd
        AZURE_ENV_NAME=$(azd env get-values | grep AZURE_ENV_NAME | cut -d'=' -f2 | tr -d '"')
        DEFAULT_GROUP_NAME="rtaudio-apimUsers-${AZURE_ENV_NAME:-default}"
        
        read -p "Enter a name for the new Entra group [$DEFAULT_GROUP_NAME]: " group_name
        
        # Use default if no input provided
        if [[ -z "$group_name" ]]; then
            group_name="$DEFAULT_GROUP_NAME"
        fi
        
        if [[ -z "$group_name" ]]; then
            echo "❌ Group name cannot be empty. Skipping Entra group creation."
        else
            echo "🔄 Creating Azure Entra group: $group_name"
            
            # Create the Entra group and capture the object ID
            GROUP_ID=$(az ad group create \
                --display-name "$group_name" \
                --mail-nickname "$(echo "$group_name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')" \
                --description "Security group for $group_name deployment" \
                --query id -o tsv)
            if [[ -n "$GROUP_ID" ]]; then
                echo "✅ Successfully created Entra group with ID: $GROUP_ID"
                
                # Set the environment variable
                azd env set AZURE_ENTRA_GROUP_ID "$GROUP_ID"
                echo "✅ Environment variable AZURE_ENTRA_GROUP_ID set to: $GROUP_ID"
                
                echo ""
                echo "📝 Note: You can add users to this group later via:"
                echo "   az ad group member add --group '$group_name' --member-id '<user-object-id>'"
                echo ""
                echo "🔄 The post-provision script will automatically add the backend container's"
                echo "   user assigned identity to this group for proper access permissions."
            else
                echo "❌ Failed to create Entra group. Please create manually and set AZURE_ENTRA_GROUP_ID."
            fi
        fi
    else
        echo "⚠️  Skipping Entra group creation. You can set AZURE_ENTRA_GROUP_ID manually later:"
        echo "   azd env set AZURE_ENTRA_GROUP_ID '<your-group-object-id>'"
        echo ""
        echo "⚠️  Note: Without a configured Entra group, the API Management Azure OpenAI policy"
        echo "   needs to be updated manually as it currently evaluates based on group membership."
    fi
else
    echo "✅ Azure Entra Group ID already configured: $EXISTING_ENTRA_GROUP_ID"
fi

echo ""
echo "🖥️  Jumphost VM Configuration"
echo "============================="
echo ""

# Check if AZURE_JUMPHOST_VM_PASSWORD is already set
EXISTING_VM_PASSWORD=$(azd env get-values | grep AZURE_JUMPHOST_VM_PASSWORD | cut -d'=' -f2 | tr -d '"')

if [[ -z "$EXISTING_VM_PASSWORD" ]]; then
    echo "🔐 No jumphost VM password found in current environment."
    echo "🔄 Generating secure password for jumphost VM..."
    
    # Generate a secure password with at least 12 characters including uppercase, lowercase, numbers, and symbols
    VM_PASSWORD=$(openssl rand -base64 18 | tr -d "=+/" | cut -c1-16)
    # Ensure password complexity by adding required character types
    VM_PASSWORD="${VM_PASSWORD}A1!"
    
    # Set the environment variable
    azd env set AZURE_JUMPHOST_VM_PASSWORD "$VM_PASSWORD"
    echo "✅ Generated and set secure password for jumphost VM."
    echo "📝 Password has been stored in azd environment variables."
    echo ""
    echo "⚠️  Important: This password will be stored in the Key Vault provisioned by this deployment."
    # Password is securely stored in environment variables and Key Vault. Not displayed for security.
    echo ""
else
    echo "✅ Jumphost VM password already configured."
fi