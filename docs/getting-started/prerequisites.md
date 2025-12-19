# :material-checkbox-marked-circle: Prerequisites

!!! tip "One-Time Setup"
    Complete these prerequisites **once** before starting any guide in this documentation.

---

## :material-tools: Required Tools

Install these tools on your development machine:

| Tool | Purpose | Install | Verify |
|------|---------|---------|--------|
| **Azure CLI** | Azure resource management | [:material-download: Install](https://docs.microsoft.com/cli/azure/install-azure-cli) | `az --version` |
| **Azure Developer CLI** | One-command deployment | [:material-download: Install](https://aka.ms/azd-install) | `azd version` |
| **Docker** | Container builds | [:material-download: Install](https://docs.docker.com/get-docker/) | `docker --version` |
| **Python 3.11+** | Backend runtime | [:material-download: Install](https://www.python.org/downloads/) | `python --version` |
| **Node.js 22+** | Frontend build | [:material-download: Install](https://nodejs.org/) | `node --version` |
| **jq** | JSON processing for scripts | [:material-download: Install](https://jqlang.github.io/jq/download/) | `jq --version` |

---

## :material-package-down: Quick Install Scripts

=== ":material-linux: Linux / WSL"

    ```bash
    # Azure CLI
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    
    # Azure Developer CLI
    curl -fsSL https://aka.ms/install-azd.sh | bash
    
    # Python 3.11 (Ubuntu/Debian)
    sudo apt update && sudo apt install python3.11 python3.11-venv
    
    # Node.js 22 (via NodeSource)
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
    
    # jq (JSON processor)
    sudo apt install -y jq
    
    # Docker
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    ```

=== ":material-apple: macOS"

    ```bash
    # Using Homebrew
    brew install azure-cli
    brew install azd
    brew install python@3.11
    brew install node@22
    brew install jq
    brew install --cask docker
    ```

=== ":material-microsoft-windows: Windows"

    ```powershell
    # Using winget
    winget install Microsoft.AzureCLI
    winget install Microsoft.Azd
    winget install Python.Python.3.11
    winget install OpenJS.NodeJS.LTS
    winget install jqlang.jq
    winget install Docker.DockerDesktop
    ```

---

## :material-account-key: Azure Requirements

### Subscription Access

You need an Azure subscription with **Contributor** access.

```bash
# Verify your subscription
az login
az account show --query "{Name:name, ID:id, State:state}" -o table
```

??? question "Don't have a subscription?"
    Create a free account: [:material-open-in-new: Azure Free Account](https://azure.microsoft.com/free/)

### Required Permissions

| Permission | Required For |
|------------|--------------|
| **Contributor** | Creating resources (OpenAI, ACS, Cosmos DB, etc.) |
| **User Access Administrator** | Assigning managed identity roles |

??? warning "Permission Denied Errors?"
    If you see permission errors during deployment:
    
    1. Contact your Azure administrator
    2. Request **Contributor** + **User Access Administrator** on your subscription
    3. Or request a dedicated resource group with these permissions

---

## :material-check-all: Verification Checklist

Run this script to verify all prerequisites:

```bash
#!/bin/bash
echo "🔍 Checking prerequisites..."

# Check each tool
for cmd in az azd docker python3 node jq; do
  if command -v $cmd &> /dev/null; then
    echo "✅ $cmd: $(command -v $cmd)"
  else
    echo "❌ $cmd: NOT FOUND"
  fi
done

# Check Azure login
if az account show &> /dev/null; then
  echo "✅ Azure CLI: Logged in"
else
  echo "❌ Azure CLI: Not logged in (run 'az login')"
fi

# Check azd auth
if azd auth login --check-status &> /dev/null; then
  echo "✅ Azure Developer CLI: Authenticated"
else
  echo "❌ Azure Developer CLI: Not authenticated (run 'azd auth login')"
fi

echo "🏁 Done!"
```

---

## :material-arrow-right: Next Steps

Once prerequisites are installed:

| Goal | Guide |
|------|-------|
| **Deploy to Azure** (recommended first step) | [Quickstart](quickstart.md) |
| **Run locally** (after deployment) | [Local Development](local-development.md) |
| **Try the demo** | [Demo Guide](demo-guide.md) |

---

!!! info "Terraform Note"
    Terraform is **automatically installed** by `azd` during deployment. You don't need to install it separately.
