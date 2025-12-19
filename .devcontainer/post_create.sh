#!/bin/bash
set -e

echo "🚀 Setting up ARTAgent development environment..."

# Detect architecture
ARCH=$(uname -m)
echo "📍 Detected architecture: $ARCH"

# Define shell profile paths
ZSHRC="$HOME/.zshrc"
BASHRC="$HOME/.bashrc"

# Add local bin to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$ZSHRC"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$BASHRC"
export PATH="$HOME/.local/bin:$PATH"

# =============================================================================
# Configure two-line zsh prompt
# =============================================================================
echo "🎨 Configuring two-line zsh prompt..."
cat >> "$ZSHRC" << 'EOF'

# Two-line prompt configuration
PROMPT='
%F{cyan}%n%f %F{blue}%~%f $(git_prompt_info)
%F{green}❯%f '
ZSH_THEME_GIT_PROMPT_PREFIX="%F{yellow}("
ZSH_THEME_GIT_PROMPT_SUFFIX=")%f"
ZSH_THEME_GIT_PROMPT_DIRTY=" %F{red}✗%f"
ZSH_THEME_GIT_PROMPT_CLEAN=" %F{green}✓%f"
EOF

# =============================================================================
# Install uv (Astral's fast Python package manager)
# =============================================================================
echo "📦 Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh

# Source uv for current session
source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"

# =============================================================================
# Install Bicep CLI (multi-arch)
# =============================================================================
# echo "📦 Installing Bicep CLI..."
# if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
#     BICEP_URL="https://github.com/Azure/bicep/releases/latest/download/bicep-linux-arm64"
# else
#     BICEP_URL="https://github.com/Azure/bicep/releases/latest/download/bicep-linux-x64"
# fi

# curl -Lo bicep "$BICEP_URL"
# chmod +x ./bicep
# sudo mv ./bicep /usr/local/bin/bicep
# echo "✅ Bicep installed: $(bicep --version)"

# =============================================================================
# Install system dependencies for Python packages
# =============================================================================
echo "📦 Installing system dependencies..."
sudo apt-get update && sudo apt-get install -y portaudio19-dev

# =============================================================================
# Setup Python environment with uv
# =============================================================================
echo "🐍 Setting up Python environment with uv..."
cd /workspaces/art-voice-agent-accelerator

# Sync all dependencies (main + dev + docs)
uv sync --extra dev --extra docs

echo ""
echo "✅ Development environment ready!"
echo ""
echo "📋 Useful commands:"
echo "  uv sync                        # Sync dependencies"
echo "  uv run pytest                  # Run tests"
echo "  uv run python -m uvicorn ...   # Run with uv"
echo "  source .venv/bin/activate      # Activate venv manually"
echo ""
echo "  az login                       # Login to Azure"
echo "  azd up                         # Deploy to Azure"
echo ""
