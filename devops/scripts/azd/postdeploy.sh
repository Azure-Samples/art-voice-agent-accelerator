#!/bin/bash
# Subscription validation requires the deployed backend, not the provisioning image.
set -euo pipefail
set +x
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/helpers/frontdoor.py" deploy
