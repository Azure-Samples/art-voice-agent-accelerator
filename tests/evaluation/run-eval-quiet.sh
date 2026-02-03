#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Quiet Evaluation Runner
# ═══════════════════════════════════════════════════════════════════════════════
# Wrapper that runs evaluations with minimal log noise.
#
# Usage:
#   ./tests/evaluation/run-eval-quiet.sh <scenario.yaml>
#   ./tests/evaluation/run-eval-quiet.sh tests/evaluation/scenarios/session_based/banking_declined_card_handoff.yaml
#
# All arguments are passed through to the CLI.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Source quiet mode environment
if [[ -f "$SCRIPT_DIR/eval-quiet.env" ]]; then
    set -a
    source "$SCRIPT_DIR/eval-quiet.env"
    set +a
fi

cd "$PROJECT_ROOT"

# Run evaluations with Python logging configured to respect EVAL_LOG_LEVEL
exec python -c "
import os
import sys
import logging

# Apply EVAL_LOG_LEVEL to root logger and noisy libraries BEFORE any imports
log_level = os.environ.get('EVAL_LOG_LEVEL', 'INFO').upper()
level = getattr(logging, log_level, logging.INFO)

# Configure root logger
logging.basicConfig(level=level, format='%(levelname)s - %(name)s: %(message)s')

# Silence noisy libraries
for name in [
    'azure', 'azure.core', 'azure.identity', 'azure.ai',
    'openai', 'httpx', 'httpcore', 'urllib3',
    'asyncio', 'aiohttp', 'websockets',
    'opentelemetry', 'azure_monitor',
]:
    logging.getLogger(name).setLevel(max(level, logging.WARNING))

# Now run the actual CLI
sys.argv = ['tests.evaluation.cli'] + sys.argv[1:]
from tests.evaluation.cli.__main__ import main
sys.exit(main())
" "$@"
