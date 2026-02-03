#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Streaming Evaluation Runner
# ═══════════════════════════════════════════════════════════════════════════════
# Runs evaluations while streaming structured per-turn output.
# Shows user input, tool calls, handoffs, and responses for each turn.
#
# Usage:
#   ./tests/evaluation/run-eval-stream.sh run --input <scenario.yaml>
#   ./tests/evaluation/run-eval-stream.sh run --input tests/evaluation/scenarios/session_based/banking_declined_card_handoff.yaml
#
# All arguments are passed through to the Python script.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

exec python "$SCRIPT_DIR/run-eval-stream.py" "$@"
