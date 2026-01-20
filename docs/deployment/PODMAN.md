# 🐳 Using Podman Instead of Docker

This project supports **Podman** as an alternative to Docker for container operations during development and deployment with `azd`.

## ✅ Quick Setup

### 1. Install Podman (if not already installed)

**macOS:**
```bash
brew install podman
```

**Linux:**
```bash
# Fedora/RHEL/CentOS
sudo dnf install podman

# Ubuntu/Debian
sudo apt install podman
```

### 2. Initialize Podman Machine (macOS/Windows)

```bash
podman machine init
podman machine start
```

### 3. Set Up Docker Compatibility

Run the provided setup script:
```bash
./devops/scripts/azd/helpers/setup-podman-docker-compat.sh
```

Or manually add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
export DOCKER_HOST="unix:///run/podman/podman.sock"
alias docker=podman
```

Then reload your shell:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

### 4. Verify Setup

```bash
docker --version
# Should output: podman version X.X.X

podman info
# Should show running Podman machine
```

## 🚀 Usage with azd

Once configured, all `azd` commands work seamlessly:

```bash
# Deploy with Podman (no changes needed)
azd up

# Build containers with Podman
azd package

# Deploy just the apps
azd deploy
```

## 🔧 How It Works

The preflight checks in `devops/scripts/azd/helpers/preflight-checks.sh` have been updated to:

1. **Detect container runtime**: Checks for either `docker` or `podman` commands
2. **Auto-configure**: Sets up Docker compatibility if using Podman
3. **Seamless integration**: `azd` uses the container runtime transparently

## 🐛 Troubleshooting

### Podman machine not running

```bash
podman machine list
podman machine start
```

### Docker command not found after setup

Reload your shell:
```bash
exec $SHELL
# or
source ~/.zshrc
```

### azd still looking for Docker

Ensure environment variable is set:
```bash
echo $DOCKER_HOST
# Should output: unix:///run/podman/podman.sock

export DOCKER_HOST="unix:///run/podman/podman.sock"
```

### Permission issues with Podman socket

Check Podman socket permissions:
```bash
ls -la /run/podman/podman.sock
# or on macOS:
ls -la ~/Library/Containers/*/Data/run/podman/podman.sock
```

## 📚 Additional Resources

- [Podman Documentation](https://docs.podman.io/)
- [Docker to Podman Migration](https://podman.io/docs/migration)
- [Azure Developer CLI with Podman](https://learn.microsoft.com/azure/developer/azure-developer-cli/)

## 🔄 Switching Back to Docker

If you need to switch back to Docker:

1. Remove/comment out the Podman configuration from your shell profile
2. Install Docker Desktop
3. Restart your terminal

The preflight checks will automatically detect and use Docker.
