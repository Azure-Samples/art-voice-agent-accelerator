#!/bin/bash
# Quick test script for orchestrator validation

echo "🚀 Speech Cascade Orchestrator Quick Test"
echo "=========================================="
echo ""

# Get project root (we're in devops/scripts/misc, need to go up 3 levels)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT" || exit 1

echo "📍 Project root: $PROJECT_ROOT"
echo ""
echo "ℹ️  Configuration will be loaded from .env.local or .env file"
echo "   (Create .env.local in project root if not present)"
echo ""
echo "Starting interactive mode..."
echo ""

# Run interactive mode (will load from .env files automatically)
python3 devops/scripts/misc/test_orchestrator.py --interactive
