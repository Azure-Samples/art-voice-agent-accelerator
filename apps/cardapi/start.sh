#!/bin/bash
# Local development script for Card Decline API
# The MCP server is self-contained and loads data from:
# - Local JSON (development): database/decline_codes_policy_pack.json
# - Cosmos DB (Azure): via AZURE_COSMOS_* env vars

set -e

echo "Card Decline API - Local Development"
echo "====================================="
echo ""

# Check if running from cardapi directory
if [ ! -f "database/decline_codes_policy_pack.json" ]; then
    echo "Error: Must run from apps/cardapi directory"
    exit 1
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Warning: Port $1 is already in use"
        return 1
    fi
    return 0
}

# Install dependencies if needed
echo "1. Checking dependencies..."
if [ ! -d "mcp_app/.venv" ]; then
    echo "   Creating virtual environment for MCP server..."
    cd mcp_app
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi
echo "   Dependencies OK"
echo ""

# Start MCP server
echo "2. Starting MCP Server (self-contained)..."
check_port 8001 || true
cd mcp_app
source .venv/bin/activate
export PYTHONPATH="$(cd ../../../ && pwd)"
nohup python service.py > ../mcp.log 2>&1 &
MCP_PID=$!
echo "   MCP PID: $MCP_PID"
deactivate
cd ..

# Wait for server to start
echo "   Waiting for server to start..."
sleep 2

echo ""
echo "====================================="
echo "MCP Server Started!"
echo "====================================="
echo "MCP Server:   Running (PID: $MCP_PID)"
echo ""
echo "Data source: Local JSON (database/decline_codes_policy_pack.json)"
echo "To use Azure Cosmos DB, set:"
echo "  AZURE_COSMOS_DATABASE_NAME=cardapi"
echo "  AZURE_COSMOS_COLLECTION_NAME=declinecodes"
echo ""
echo "Logs:"
echo "  MCP:     apps/cardapi/mcp.log"
echo ""
echo "To stop service:"
echo "  kill $MCP_PID"
echo "====================================="

# Save PID to file
echo "$MCP_PID" > .mcp.pid
