#!/bin/bash
# Local development script for Card Decline API

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
if [ ! -d "backend/venv" ]; then
    echo "   Creating virtual environment for backend..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi

if [ ! -d "mcp/venv" ]; then
    echo "   Creating virtual environment for MCP server..."
    cd mcp
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi

echo "   Dependencies OK"
echo ""

# Start backend
echo "2. Starting Backend API (port 8000)..."
check_port 8000 || true
cd backend
source venv/bin/activate
nohup python main.py > ../backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
deactivate
cd ..

# Wait for backend to start
echo "   Waiting for backend to start..."
sleep 3

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "   Error: Backend failed to start"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi
echo "   Backend started successfully"
echo ""

# Start MCP server
echo "3. Starting MCP Server (port 8001)..."
check_port 8001 || true
cd mcp
source venv/bin/activate
export CARDAPI_BACKEND_URL=http://localhost:8000
nohup python service.py > ../mcp.log 2>&1 &
MCP_PID=$!
echo "   MCP PID: $MCP_PID"
deactivate
cd ..

echo ""
echo "====================================="
echo "Services Started!"
echo "====================================="
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/docs"
echo "MCP Server:   Running (PID: $MCP_PID)"
echo ""
echo "Logs:"
echo "  Backend: apps/cardapi/backend.log"
echo "  MCP:     apps/cardapi/mcp_app.log"
echo ""
echo "To stop services:"
echo "  kill $BACKEND_PID $MCP_PID"
echo ""
echo "To test the API:"
echo "  python test_api.py"
echo "====================================="

# Save PIDs to file
echo "$BACKEND_PID" > .backend.pid
echo "$MCP_PID" > .mcp.pid
