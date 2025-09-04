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

PORT=8010

function check_devtunnel_installed() {
    if ! command -v devtunnel >/dev/null 2>&1; then
        echo "Error: 'devtunnel' CLI tool is not available in your PATH."
        echo "Make sure the Azure CLI dev-tunnel extension is installed:"
        echo "    az extension add --name dev-tunnel"
        exit 1
    fi
}

function host_tunnel() {
    echo "Hosting Azure Dev Tunnel on port $PORT"
    devtunnel host
}

check_devtunnel_installed
host_tunnel
