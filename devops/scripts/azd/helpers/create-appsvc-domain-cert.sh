#!/bin/bash

# Script to create App Service Domain and Certificate on Azure
# Follows Azure development best practices for resource creation

set -e  # Exit on any error

echo "=== Azure App Service Domain and Certificate Creation ==="
echo ""

# Function to validate input
validate_input() {
    local input="$1"
    local name="$2"
    if [[ -z "$input" ]]; then
        echo "Error: $name cannot be empty"
        exit 1
    fi
}

# Function to check if user is logged in to Azure
check_azure_login() {
    echo "Checking Azure login status..."
    if ! az account show &>/dev/null; then
        echo "Not logged in to Azure. Please login first:"
        az login
    fi
    
    # Display current subscription
    echo "Current subscription:"
    az account show --query "{Name:name, SubscriptionId:id, TenantId:tenantId}" -o table
    echo ""
}

# Prompt for required inputs
echo "Please provide the following information:"
echo ""

read -p "Enter domain name (e.g., mycompany.com): " DOMAIN_NAME
validate_input "$DOMAIN_NAME" "Domain name"

read -p "Enter resource group name: " RESOURCE_GROUP
validate_input "$RESOURCE_GROUP" "Resource group"

read -p "Enter Azure region (e.g., eastus, westus2): " LOCATION
validate_input "$LOCATION" "Location"

# Optional inputs with defaults
read -p "Enter contact email for domain registration: " CONTACT_EMAIL
validate_input "$CONTACT_EMAIL" "Contact email"

read -p "Enter first name for domain contact: " FIRST_NAME
validate_input "$FIRST_NAME" "First name"

read -p "Enter last name for domain contact: " LAST_NAME
validate_input "$LAST_NAME" "Last name"

read -p "Enter phone number for domain contact: " PHONE_NUMBER
validate_input "$PHONE_NUMBER" "Phone number"

read -p "Enter address line 1: " ADDRESS1
validate_input "$ADDRESS1" "Address"

read -p "Enter city: " CITY
validate_input "$CITY" "City"

read -p "Enter state/province: " STATE
validate_input "$STATE" "State"

read -p "Enter postal code: " POSTAL_CODE
validate_input "$POSTAL_CODE" "Postal code"

read -p "Enter country code (e.g., US, CA, UK): " COUNTRY
validate_input "$COUNTRY" "Country"

echo ""
read -p "Auto-renew domain? (y/n) [default: y]: " AUTO_RENEW
AUTO_RENEW=${AUTO_RENEW:-y}

read -p "Privacy protection enabled? (y/n) [default: y]: " PRIVACY_PROTECTION
PRIVACY_PROTECTION=${PRIVACY_PROTECTION:-y}

echo ""
echo "=== Configuration Summary ==="
echo "Domain Name: $DOMAIN_NAME"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Contact Email: $CONTACT_EMAIL"
echo "Auto-renew: $AUTO_RENEW"
echo "Privacy Protection: $PRIVACY_PROTECTION"
echo ""

read -p "Proceed with creation? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Operation cancelled."
    exit 0
fi

# Check Azure login
check_azure_login

echo ""
echo "=== Starting Azure Resource Creation ==="

# Create resource group if it doesn't exist
echo "Creating resource group..."
if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo "Resource group '$RESOURCE_GROUP' already exists."
else
    echo "Creating resource group '$RESOURCE_GROUP'..."
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output table
fi

echo "Resource group created/verified."

# Convert boolean inputs
if [[ "$AUTO_RENEW" == "y" || "$AUTO_RENEW" == "Y" ]]; then
    AUTO_RENEW_FLAG="true"
else
    AUTO_RENEW_FLAG="false"
fi

if [[ "$PRIVACY_PROTECTION" == "y" || "$PRIVACY_PROTECTION" == "Y" ]]; then
    PRIVACY_FLAG="true"
else
    PRIVACY_FLAG="false"
fi

# Create App Service Domain
echo ""
echo "Creating App Service Domain..."
echo "Note: This may take several minutes and will incur charges."

az appservice domain create \
    --resource-group "$RESOURCE_GROUP" \
    --hostname "$DOMAIN_NAME" \
    --contact-info "{
        \"Email\": \"$CONTACT_EMAIL\",
        \"NameFirst\": \"$FIRST_NAME\",
        \"NameLast\": \"$LAST_NAME\",
        \"Phone\": \"$PHONE_NUMBER\",
        \"AddressLine1\": \"$ADDRESS1\",
        \"City\": \"$CITY\",
        \"State\": \"$STATE\",
        \"PostalCode\": \"$POSTAL_CODE\",
        \"Country\": \"$COUNTRY\"
    }" \
    --auto-renew "$AUTO_RENEW_FLAG" \
    --privacy-protection-enabled "$PRIVACY_FLAG" \
    --output table

echo ""
echo "App Service Domain created successfully!"

# Create App Service Managed Certificate
echo ""
echo "Creating App Service Managed Certificate..."

CERT_NAME="${DOMAIN_NAME//\./-}-cert"

az webapp config ssl create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CERT_NAME" \
    --hostname "$DOMAIN_NAME" \
    --output table

echo ""
echo "=== Creation Complete ==="
echo "Domain: $DOMAIN_NAME"
echo "Certificate: $CERT_NAME"
echo "Resource Group: $RESOURCE_GROUP"
echo ""
echo "Next steps:"
echo "1. Verify domain ownership if required"
echo "2. Configure DNS settings for your applications"
echo "3. Bind the certificate to your App Service"
echo ""
echo "You can view your resources in the Azure portal:"
echo "https://portal.azure.com/#@/resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP"


echo ""
echo "=== Additional Certificate Setup Steps ==="
echo ""
echo "After domain verification is complete, follow these steps to create a complete certificate chain:"
echo ""
echo "1. Download the GoDaddy root certificate:"
echo "   wget https://certs.godaddy.com/repository/gdroot-g2.crt"
echo ""
echo "2. Download your domain certificate from GoDaddy or Azure App Service"
echo ""
echo "3. Create a complete certificate chain (fullchain.pem):"
echo "   cat your-domain-cert.crt gdroot-g2.crt > fullchain.pem"
echo ""
echo "4. Convert to password-protected PFX format:"
echo "   openssl pkcs12 -export -out ${DOMAIN_NAME//\./-}.pfx -inkey private.key -in fullchain.pem -password pass:YourSecurePassword"
echo ""
echo "5. Upload PFX to Azure Key Vault:"
echo "   az keyvault certificate import \\"
echo "     --vault-name your-keyvault-name \\"
echo "     --name ${DOMAIN_NAME//\./-}-cert \\"
echo "     --file ${DOMAIN_NAME//\./-}.pfx \\"
echo "     --password YourSecurePassword"
echo ""
echo "6. Grant your App Service access to the Key Vault certificate"
echo ""
echo "Note: Replace 'your-keyvault-name' and 'YourSecurePassword' with actual values."
echo "Store the PFX password securely in Azure Key Vault as a secret."