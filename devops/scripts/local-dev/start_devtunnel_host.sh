#!/bin/bash

# ============================================================
# Script: start_devtunnel_host.sh
# Purpose: Host the Azure Dev Tunnel on port 8010.
# ============================================================

: """
🧠 Azure Dev Tunnels – Get Started

This script helps you host an Azure Dev Tunnel for your local FastAPI server.

1. 📦 Prerequisite: Azure CLI must be installed.
   ➤ https://learn.microsoft.com/en-us/cli/azure/install-azure-cli

2. 🧪 First time setup? Run:
   ➤ az extension add --name dev-tunnel

3. 🌐 If tunnel hasn't been created yet:
   ➤ az devtunnel create --allow-anonymous --port 8010 --instrumentation-type http

4. 🚀 This script hosts the tunnel:
   ➤ devtunnel host --port 8010

5. 🔗 Once running, copy the generated URL (e.g., https://<id>.dev.tunnels.azure.com)

6. 📝 Then set:
   ➤ backend/.env → BASE_URL=<your-public-url>
   ➤ ACS (Azure Communication Services) → Voice Callback URL = <your-public-url>/api/callback

💬 Dev Tunnels forward HTTP/WebSocket traffic, enabling outbound PSTN calls and remote testing 
    without firewall/NAT changes. Ideal for local development of voice-enabled agents.
"""

set -e

function check_azd_installed() {
    if ! command -v azd >/dev/null 2>&1; then
        echo "Error: 'azd' CLI tool is not available in your PATH."
        echo "Install the Azure Developer CLI: https://aka.ms/install-azd"
        exit 1
    fi
}

function prompt_for_value() {
    local prompt_message=$1
    local default_value=$2
    local input=""

    while [[ -z "${input}" ]]; do
        if [[ -n "${default_value}" ]]; then
            read -r -p "${prompt_message} [${default_value}]: " input
            input=${input:-${default_value}}
        else
            read -r -p "${prompt_message}: " input
        fi
    done

    echo "${input}"
}

function get_config_value() {
    local key=$1
    local prompt_message=$2
    local default_value=$3
    local value

    value=$(azd env get-value "${key}" 2>/dev/null | tr -d '\r')

    if [[ -n "${value}" ]]; then
        echo "${value}"
        return
    fi

    value=$(prompt_for_value "${prompt_message}" "${default_value}")
    azd env set "${key}" "${value}" >/dev/null
    echo "${value}"
}

check_azd_installed

PORT=$(get_config_value "DEV_TUNNEL_PORT" "Enter the local port to expose" "8000")
TUNNEL_ID=$(get_config_value "DEV_TUNNEL_ID" "Enter the Azure Dev Tunnel ID")
TUNNEL_URL=$(get_config_value "DEV_TUNNEL_URL" "Enter the Azure Dev Tunnel URL")

function check_devtunnel_installed() {
    if ! command -v devtunnel >/dev/null 2>&1; then
        echo "Error: 'devtunnel' CLI tool is not available in your PATH."
        echo "Make sure the Azure CLI dev-tunnel extension is installed:"
        echo "    az extension add --name dev-tunnel"
        exit 1
    fi
}

function kill_existing_tunnels() {
    echo "🔪 Killing any existing devtunnel host processes..."
    pkill -f "devtunnel host" 2>/dev/null || true
    sleep 1
}

function host_tunnel() {
    echo "🚀 Hosting Azure Dev Tunnel: $TUNNEL_ID on port $PORT"
    echo "🔗 URL: $TUNNEL_URL"
    echo ""
    devtunnel host $TUNNEL_ID --allow-anonymous
}

check_devtunnel_installed
kill_existing_tunnels
host_tunnel
