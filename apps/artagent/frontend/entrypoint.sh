#!/bin/sh
set -e

echo "🚀 Starting frontend container..."

# ============================================================================
# Azure App Configuration Integration
# ============================================================================
# If AZURE_APPCONFIG_ENDPOINT is set, fetch configuration from App Config
# using managed identity. Otherwise, fall back to environment variables.
#
# NOTE: Azure Container Apps uses IDENTITY_ENDPOINT/IDENTITY_HEADER, NOT IMDS.

# Get access token for Azure Container Apps (or IMDS fallback)
get_access_token() {
    local resource="https://azconfig.io"
    local client_id="${AZURE_CLIENT_ID:-}"
    
    # Check if running in Azure Container Apps (uses IDENTITY_ENDPOINT)
    if [ -n "$IDENTITY_ENDPOINT" ] && [ -n "$IDENTITY_HEADER" ]; then
        echo "   Using Azure Container Apps managed identity" >&2
        
        # Build the Container Apps identity URL
        local identity_url="${IDENTITY_ENDPOINT}?api-version=2019-08-01&resource=${resource}"
        
        # Add client_id for user-assigned managed identity
        if [ -n "$client_id" ]; then
            identity_url="${identity_url}&client_id=${client_id}"
        fi
        
        # Request token from Container Apps identity endpoint
        local response
        response=$(curl -s -H "X-IDENTITY-HEADER: ${IDENTITY_HEADER}" "$identity_url" 2>/dev/null) || return 1
        
        # Extract access_token from JSON response
        echo "$response" | jq -r '.access_token // empty' 2>/dev/null
        return
    fi
    
    # Fallback to Azure IMDS (for VMs, App Service, etc.)
    echo "   Falling back to IMDS" >&2
    local api_version="2019-08-01"
    local imds_url="http://169.254.169.254/metadata/identity/oauth2/token?api-version=${api_version}&resource=${resource}"
    
    # Add client_id if using user-assigned managed identity
    if [ -n "$client_id" ]; then
        imds_url="${imds_url}&client_id=${client_id}"
    fi
    
    # Request token from IMDS
    local response
    response=$(curl -s -H "Metadata: true" "$imds_url" 2>/dev/null) || return 1
    
    # Extract access_token from JSON response
    echo "$response" | jq -r '.access_token // empty' 2>/dev/null
}

# Fetch a configuration value from Azure App Configuration
fetch_from_appconfig() {
    local key="$1"
    local label="${AZURE_APPCONFIG_LABEL:-}"
    local endpoint="${AZURE_APPCONFIG_ENDPOINT}"
    local token="$2"
    
    if [ -z "$endpoint" ] || [ -z "$token" ]; then
        return 1
    fi
    
    # URL-encode the key (replace / with %2F)
    local encoded_key
    encoded_key=$(echo "$key" | sed 's|/|%2F|g')
    
    # Build the App Config REST API URL
    local url="${endpoint}/kv/${encoded_key}?api-version=1.0"
    if [ -n "$label" ]; then
        url="${url}&label=${label}"
    fi
    
    # Fetch the configuration value
    local response
    response=$(curl -s -H "Authorization: Bearer ${token}" "$url" 2>/dev/null) || return 1
    
    # Extract value from JSON response
    echo "$response" | jq -r '.value // empty' 2>/dev/null
}

# Try to get configuration from App Configuration
if [ -n "$AZURE_APPCONFIG_ENDPOINT" ]; then
    echo "📦 Azure App Configuration detected: $AZURE_APPCONFIG_ENDPOINT"
    echo "   Label: ${AZURE_APPCONFIG_LABEL:-<none>}"
    echo "   IDENTITY_ENDPOINT: ${IDENTITY_ENDPOINT:-<not set>}"
    echo "   AZURE_CLIENT_ID: ${AZURE_CLIENT_ID:-<not set>}"
    
    # Get access token using managed identity
    echo "🔐 Acquiring access token via managed identity..."
    ACCESS_TOKEN=$(get_access_token)
    
    if [ -n "$ACCESS_TOKEN" ]; then
        echo "✅ Access token acquired (length: ${#ACCESS_TOKEN})"
        
        # Fetch backend URL from App Config
        echo "   Fetching app/frontend/backend-url..."
        appconfig_backend_url=$(fetch_from_appconfig "app/frontend/backend-url" "$ACCESS_TOKEN")
        if [ -n "$appconfig_backend_url" ] && [ "$appconfig_backend_url" != "null" ] && [ "$appconfig_backend_url" != "https://placeholder.azurecontainerapps.io" ]; then
            echo "✅ Fetched backend-url from App Config: $appconfig_backend_url"
            BACKEND_URL="$appconfig_backend_url"
        else
            echo "⚠️  Could not fetch backend-url from App Config (got: '$appconfig_backend_url')"
            echo "   This usually means postprovision hasn't run yet"
        fi
        
        # Fetch WS URL from App Config
        echo "   Fetching app/frontend/ws-url..."
        appconfig_ws_url=$(fetch_from_appconfig "app/frontend/ws-url" "$ACCESS_TOKEN")
        if [ -n "$appconfig_ws_url" ] && [ "$appconfig_ws_url" != "null" ] && [ "$appconfig_ws_url" != "wss://placeholder.azurecontainerapps.io" ]; then
            echo "✅ Fetched ws-url from App Config: $appconfig_ws_url"
            WS_URL="$appconfig_ws_url"
        else
            echo "⚠️  Could not fetch ws-url from App Config (got: '$appconfig_ws_url')"
        fi
    else
        echo "❌ Could not acquire access token, falling back to env vars"
        echo "   Check that the frontend managed identity has 'App Configuration Data Reader' role"
    fi
else
    echo "ℹ️  App Configuration not configured, using environment variables"
fi

# Replace placeholder with actual backend URL from environment variable
# Replace backend placeholder used by the REST client
if [ -n "$BACKEND_URL" ]; then
    echo "📝 Replacing __BACKEND_URL__ with: $BACKEND_URL"
    find /app/dist -type f -name "*.js" -exec sed -i "s|__BACKEND_URL__|${BACKEND_URL}|g" {} \;
    find /app/dist -type f -name "*.html" -exec sed -i "s|__BACKEND_URL__|${BACKEND_URL}|g" {} \;
else
    echo "⚠️  BACKEND_URL environment variable not set, using placeholder"
fi

# Determine WS URL (prefer explicit WS_URL, otherwise derive from BACKEND_URL)
derive_ws_url() {
    input="$1"
    case "$input" in
        https://*) echo "${input/https:\/\//wss://}" ;;
        http://*) echo "${input/http:\/\//ws://}" ;;
        *) echo "$input" ;;
    esac
}

if [ -z "$WS_URL" ] && [ -n "$BACKEND_URL" ]; then
    # Only derive if WS_URL wasn't already set (from App Config or env)
    WS_URL="$(derive_ws_url "$BACKEND_URL")"
fi

if [ -n "$WS_URL" ]; then
    echo "📝 Replacing __WS_URL__ with: $WS_URL"
    find /app/dist -type f -name "*.js" -exec sed -i "s|__WS_URL__|${WS_URL}|g" {} \;
    find /app/dist -type f -name "*.html" -exec sed -i "s|__WS_URL__|${WS_URL}|g" {} \;
else
    echo "⚠️  WS_URL not set and BACKEND_URL unavailable; leaving __WS_URL__ placeholder"
fi

# Start the application
echo "🌟 Starting serve..."
exec "$@"
