#!/bin/bash
# ============================================================================
# Podman Docker Compatibility Setup
# ============================================================================
# Sets up Docker CLI compatibility when using Podman instead of Docker.
# This allows azd and other tools expecting 'docker' command to work with Podman.
# ============================================================================

set -euo pipefail

info() { echo "ℹ️  $*"; }
success() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; }
fail() { echo "❌ $*" >&2; }

# Check if Podman is installed
if ! command -v podman &>/dev/null; then
    fail "Podman is not installed. Please install it first:"
    fail "  macOS: brew install podman"
    fail "  Linux: See https://podman.io/getting-started/installation"
    exit 1
fi

# Check if docker command already exists
if command -v docker &>/dev/null; then
    docker_version=$(docker --version 2>/dev/null || echo "unknown")
    info "Docker command already available: $docker_version"
    
    # Check if it's actually podman
    if docker --version 2>&1 | grep -q "podman"; then
        success "Docker is aliased to Podman - compatibility already configured"
        exit 0
    else
        info "Using native Docker installation"
        exit 0
    fi
fi

info "Setting up Podman Docker compatibility..."

# Get Podman socket path
PODMAN_SOCKET=$(podman info --format '{{.Host.RemoteSocket.Path}}' 2>/dev/null || echo "")

if [[ -z "$PODMAN_SOCKET" ]]; then
    warn "Could not determine Podman socket path"
    warn "You may need to start a Podman machine:"
    warn "  podman machine init"
    warn "  podman machine start"
    exit 1
fi

# Create docker symlink (requires sudo on most systems)
INSTALL_DIR="/usr/local/bin"

if [[ -w "$INSTALL_DIR" ]]; then
    ln -sf "$(command -v podman)" "$INSTALL_DIR/docker"
    success "Created docker symlink at $INSTALL_DIR/docker"
else
    info "Creating docker symlink (may require password)..."
    sudo ln -sf "$(command -v podman)" "$INSTALL_DIR/docker"
    success "Created docker symlink at $INSTALL_DIR/docker"
fi

# Set up environment variables
cat << 'EOF'

╭─────────────────────────────────────────────────────────────
│ ✅ Podman Docker Compatibility Configured
├─────────────────────────────────────────────────────────────
│
│ Add these to your shell profile (~/.zshrc, ~/.bashrc):
│
│   export DOCKER_HOST="unix:///run/podman/podman.sock"
│   alias docker=podman
│
│ Or run this command:
│   echo 'export DOCKER_HOST="unix:///run/podman/podman.sock"' >> ~/.zshrc
│   echo 'alias docker=podman' >> ~/.zshrc
│   source ~/.zshrc
│
╰─────────────────────────────────────────────────────────────
EOF

# Verify setup
if command -v docker &>/dev/null; then
    docker_version=$(docker --version 2>/dev/null)
    success "Docker command verified: $docker_version"
else
    fail "Docker symlink creation failed"
    exit 1
fi

info "Note: You may need to restart your terminal for changes to take effect"
