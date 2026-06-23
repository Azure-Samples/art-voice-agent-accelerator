#!/bin/bash
# ============================================================================
# 🌐 Dev Tunnel up — create-or-reuse + sync env files
# ============================================================================
# Ensures an Azure Dev Tunnel exists (creating one if needed, reusing the
# persisted one otherwise), guarantees the backend port is forwarded with
# anonymous access, then writes the public URL into BOTH env files:
#
#   • Backend  : .env.local                      -> BASE_URL=<url>
#   • Frontend : apps/artagent/frontend/.env     -> VITE_BACKEND_BASE_URL=<url>
#
# The resolved tunnel id/url/port are persisted to the azd environment
# (DEV_TUNNEL_ID / DEV_TUNNEL_URL / DEV_TUNNEL_PORT) so start_devtunnel_host.sh
# and subsequent runs reuse the same tunnel.
#
# Usage:
#   ./devtunnel_up.sh [--port 8010] [--host] [--tunnel-id <id>]
#
# Options:
#   -p, --port <n>        Local port to forward (default: 8010).
#   -t, --tunnel-id <id>  Use/adopt a specific tunnel id instead of azd state.
#       --host            After syncing, host the tunnel (blocks the terminal).
#   -h, --help            Show this help.
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# Paths (resolve repo root from this script's location)
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BACKEND_ENV="$REPO_ROOT/.env.local"
FRONTEND_ENV="$REPO_ROOT/apps/artagent/frontend/.env"

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
if [[ -z "${BLUE+x}" ]]; then BLUE=$'\033[0;34m'; fi
if [[ -z "${GREEN+x}" ]]; then GREEN=$'\033[0;32m'; fi
if [[ -z "${YELLOW+x}" ]]; then YELLOW=$'\033[1;33m'; fi
if [[ -z "${RED+x}" ]]; then RED=$'\033[0;31m'; fi
if [[ -z "${CYAN+x}" ]]; then CYAN=$'\033[0;36m'; fi
if [[ -z "${DIM+x}" ]]; then DIM=$'\033[2m'; fi
if [[ -z "${NC+x}" ]]; then NC=$'\033[0m'; fi

info()    { printf '%s%s%s\n' "$BLUE" "$*" "$NC"; }
success() { printf '%s✔%s %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s⚠%s  %s\n' "$YELLOW" "$NC" "$*"; }
fail()    { printf '%s✖%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }
step()    { printf '%s→%s %s\n' "$CYAN" "$NC" "$*"; }
dim()     { printf '%s%s%s\n' "$DIM" "$*" "$NC"; }

header() {
    echo ""
    echo "╭─────────────────────────────────────────────────────────────"
    echo "│ ${CYAN}$*${NC}"
    echo "╰─────────────────────────────────────────────────────────────"
}

# ----------------------------------------------------------------------------
# Args
# ----------------------------------------------------------------------------
PORT=8010
DO_HOST=false
TUNNEL_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port)       PORT="${2:-8010}"; shift 2 ;;
        -t|--tunnel-id)  TUNNEL_ID="${2:-}"; shift 2 ;;
        --host)          DO_HOST=true; shift ;;
        -h|--help)       sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

[[ "$PORT" =~ ^[0-9]+$ ]] || fail "--port must be numeric"

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------
command -v devtunnel >/dev/null 2>&1 || fail "devtunnel CLI not found. Install: brew install --cask devtunnel"

# azd is optional — used only to persist/reuse tunnel state.
azd_get() {
    command -v azd >/dev/null 2>&1 || { echo ""; return; }
    local v
    v=$(azd env get-value "$1" 2>/dev/null | tr -d '\r' || true)
    [[ "$v" == "null" || "$v" == ERROR* ]] && v=""
    echo "$v"
}
azd_set() {
    command -v azd >/dev/null 2>&1 || return 0
    azd env set "$1" "$2" >/dev/null 2>&1 || true
}

# Update or append KEY=VALUE in an env file (macOS/Linux sed compatible).
upsert_env_var() {
    local file="$1" key="$2" value="$3"
    [[ -f "$file" ]] || { mkdir -p "$(dirname "$file")"; touch "$file"; }
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^${key}=.*|${key}=${value}|" "$file"
        else
            sed -i "s|^${key}=.*|${key}=${value}|" "$file"
        fi
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

header "🌐 Dev Tunnel up (port $PORT)"

# ----------------------------------------------------------------------------
# Ensure logged in
# ----------------------------------------------------------------------------
if ! devtunnel user show 2>/dev/null | grep -qiE "logged in|@"; then
    step "Logging into devtunnel..."
    devtunnel user login
fi

# ----------------------------------------------------------------------------
# Resolve tunnel: reuse persisted one, else create a new anonymous tunnel
# ----------------------------------------------------------------------------
[[ -z "$TUNNEL_ID" ]] && TUNNEL_ID="$(azd_get DEV_TUNNEL_ID)"

if [[ -n "$TUNNEL_ID" ]] && devtunnel show "$TUNNEL_ID" >/dev/null 2>&1; then
    success "Reusing existing tunnel: $TUNNEL_ID"
else
    [[ -n "$TUNNEL_ID" ]] && warn "Tunnel '$TUNNEL_ID' not found — creating a new one"
    step "Creating new anonymous dev tunnel..."
    create_out="$(devtunnel create --allow-anonymous 2>&1)"
    # Tunnel id looks like "<name>.<cluster>" (e.g. abcd1234.use)
    TUNNEL_ID="$(printf '%s\n' "$create_out" | grep -oE '[A-Za-z0-9]+\.[a-z0-9]+' | head -1)"
    [[ -z "$TUNNEL_ID" ]] && fail "Could not determine new tunnel id from:\n$create_out"
    success "Created tunnel: $TUNNEL_ID"
fi

# ----------------------------------------------------------------------------
# Ensure the port is forwarded (idempotent)
# ----------------------------------------------------------------------------
if devtunnel port show "$TUNNEL_ID" -p "$PORT" >/dev/null 2>&1; then
    dim "Port $PORT already forwarded"
else
    step "Adding port $PORT (https)..."
    devtunnel port create "$TUNNEL_ID" -p "$PORT" --protocol https >/dev/null
    success "Port $PORT added"
fi

# ----------------------------------------------------------------------------
# Resolve the public URL for this port
# ----------------------------------------------------------------------------
TUNNEL_URL=""
if command -v jq >/dev/null 2>&1; then
    TUNNEL_URL="$(devtunnel show "$TUNNEL_ID" --json 2>/dev/null \
        | jq -r '.. | .portForwardingUris? // empty | .[]?' 2>/dev/null \
        | grep -E "\-${PORT}\.[^/]*devtunnels" | head -1)"
    TUNNEL_URL="${TUNNEL_URL%/}"
fi
if [[ -z "$TUNNEL_URL" ]]; then
    # Deterministic fallback: https://<name>-<port>.<cluster>.devtunnels.ms
    name="${TUNNEL_ID%%.*}"; cluster="${TUNNEL_ID#*.}"
    [[ "$name" != "$cluster" ]] && TUNNEL_URL="https://${name}-${PORT}.${cluster}.devtunnels.ms"
fi
[[ -z "$TUNNEL_URL" ]] && fail "Could not resolve tunnel URL for port $PORT"

success "Tunnel URL: $TUNNEL_URL"

# ----------------------------------------------------------------------------
# Sync env files
# ----------------------------------------------------------------------------
step "Updating backend env  ($BACKEND_ENV)"
upsert_env_var "$BACKEND_ENV" "BASE_URL" "$TUNNEL_URL"
success "BASE_URL=$TUNNEL_URL"

step "Updating frontend env ($FRONTEND_ENV)"
upsert_env_var "$FRONTEND_ENV" "VITE_BACKEND_BASE_URL" "$TUNNEL_URL"
success "VITE_BACKEND_BASE_URL=$TUNNEL_URL"

# Persist for start_devtunnel_host.sh and future runs.
azd_set DEV_TUNNEL_ID "$TUNNEL_ID"
azd_set DEV_TUNNEL_URL "$TUNNEL_URL"
azd_set DEV_TUNNEL_PORT "$PORT"

header "Summary"
info  "Tunnel:   $TUNNEL_ID"
info  "Port:     $PORT"
info  "URL:      $TUNNEL_URL"
dim   "Backend:  $BACKEND_ENV  (BASE_URL)"
dim   "Frontend: $FRONTEND_ENV  (VITE_BACKEND_BASE_URL)"
echo ""

# ----------------------------------------------------------------------------
# Optionally host
# ----------------------------------------------------------------------------
if $DO_HOST; then
    step "Killing any existing devtunnel host processes..."
    pkill -f "devtunnel host" 2>/dev/null || true
    sleep 1
    step "Hosting tunnel $TUNNEL_ID (Ctrl+C to stop)..."
    exec devtunnel host "$TUNNEL_ID" --allow-anonymous
else
    dim "Run 'make start_tunnel' or 'make devtunnel' to host the tunnel."
fi
