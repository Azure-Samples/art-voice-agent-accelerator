#!/bin/bash
# Stop Card Decline API services

set -e

echo "Stopping Card Decline API services..."

# Stop backend
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
    fi
    rm .backend.pid
fi

# Stop MCP
if [ -f ".mcp.pid" ]; then
    MCP_PID=$(cat .mcp.pid)
    if ps -p $MCP_PID > /dev/null 2>&1; then
        echo "Stopping MCP server (PID: $MCP_PID)..."
        kill $MCP_PID
    fi
    rm .mcp.pid
fi

echo "Services stopped."
