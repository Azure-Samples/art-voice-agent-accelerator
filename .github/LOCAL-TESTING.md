# 🧪 Testing GitHub Actions Locally

This guide shows you how to test your GitHub Actions workflows locally before pushing to GitHub.

## 🎯 Why Test Locally?

- **Faster Feedback**: No need to push/wait for GitHub runners
- **Cost Effective**: No GitHub Actions minutes consumed
- **Debugging**: Easier to debug issues locally
- **Iteration**: Quick iteration on workflow changes

---

## 🚀 Option 1: Act (Recommended)

Act runs your GitHub Actions workflows locally using Docker.

### Installation

```bash
# macOS
brew install act

# Linux
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Windows (using Chocolatey)
choco install act-cli
```

### Basic Usage

```bash
# List all workflows
act -l

# Run all workflows on push event
act push

# Run specific workflow
act -W .github/workflows/deploy-azd.yml

# Run specific job
act -j azd-deployment

# Dry run (just show what would run)
act -n
```

### Advanced Usage

```bash
# Use specific Docker image size
act -P ubuntu-latest=catthehacker/ubuntu:act-latest

# Run with secrets file
act --secret-file .secrets

# Run with environment variables
act --env-file .env

# Run specific event
act workflow_dispatch

# Interactive mode
act -i
```

### Example: Test Your AZD Workflow

```bash
# Test the infrastructure deployment workflow
act workflow_dispatch \
  -W .github/workflows/deploy-azd.yml \
  --input environment=dev \
  --input action=provision \
  -s AZURE_CLIENT_ID=test \
  -s AZURE_TENANT_ID=test \
  -s AZURE_SUBSCRIPTION_ID=test
```

---

## 🔧 Option 2: Manual Script Testing

Create local scripts that mimic your workflow steps.

### Create Test Script

```bash
#!/bin/bash
# test-azd-workflow.sh

set -e

echo "🧪 Testing AZD Workflow Locally"

# Simulate workflow environment
export AZURE_ENV_NAME="test-local"
export AZURE_LOCATION="eastus"
export AZD_SKIP_INTERACTIVE="true"
export CI="true"

# Test azd commands (requires actual Azure login)
echo "📋 Checking azd installation..."
if ! command -v azd &> /dev/null; then
    echo "❌ Azure Developer CLI not installed"
    exit 1
fi

echo "✅ Azure Developer CLI found"

# Test environment creation
echo "🏁 Testing environment setup..."
azd env list || echo "No environments found"

# Test configuration
echo "🔧 Testing configuration..."
if [ -f "azure.yaml" ]; then
    echo "✅ azure.yaml found"
    cat azure.yaml
else
    echo "❌ azure.yaml not found"
    exit 1
fi

echo "🎉 Local tests passed!"
```

### Make it executable and run:

```bash
chmod +x test-azd-workflow.sh
./test-azd-workflow.sh
```

---

## 🐳 Option 3: Docker-based Testing

Create a Docker container that mimics the GitHub Actions environment.

### Create Dockerfile for Testing

```dockerfile
# Dockerfile.test
FROM mcr.microsoft.com/azure-cli:latest

# Install additional tools
RUN apk add --no-cache \
    curl \
    jq \
    bash \
    git

# Install Azure Developer CLI
RUN curl -fsSL https://aka.ms/install-azd.sh | bash

# Set working directory
WORKDIR /workspace

# Copy your project
COPY . .

# Set entrypoint
ENTRYPOINT ["/bin/bash"]
```

### Build and run:

```bash
# Build test container
docker build -f Dockerfile.test -t azd-test .

# Run test container
docker run -it --rm \
  -v $(pwd):/workspace \
  -e AZURE_ENV_NAME=test \
  azd-test
```

---

## 📁 Configuration Files

### .secrets (for Act)

Create a `.secrets` file for local testing (don't commit this!):

```bash
# .secrets
AZURE_CLIENT_ID=your-test-client-id
AZURE_TENANT_ID=your-test-tenant-id
AZURE_SUBSCRIPTION_ID=your-test-subscription-id
TF_STATE_RESOURCE_GROUP=test-rg
TF_STATE_STORAGE_ACCOUNT=testst
TF_STATE_CONTAINER_NAME=tfstate
AZURE_PRINCIPAL_ID=test-principal-id
ACS_SOURCE_PHONE_NUMBER=+1234567890
```

### .actrc (Act configuration)

Create `.actrc` file in your project root:

```bash
# .actrc
-P ubuntu-latest=catthehacker/ubuntu:act-latest
--secret-file .secrets
--env-file .env.test
--container-daemon-socket -
```

### .env.test (Test environment variables)

```bash
# .env.test
AZURE_LOCATION=eastus
AZD_SKIP_INTERACTIVE=true
CI=true
GITHUB_ACTIONS=true
```

---

## 🧪 Practical Testing Examples

### 1. Test Workflow Syntax

```bash
# Check workflow syntax
act -n -v

# Check specific workflow
act -n -W .github/workflows/deploy-azd.yml
```

### 2. Test Individual Jobs

```bash
# Test terraform-plan job
act pull_request -j terraform-plan

# Test azd-deployment job
act workflow_dispatch -j azd-deployment
```

### 3. Test with Different Events

```bash
# Test push event
act push

# Test pull request event
act pull_request

# Test manual dispatch
act workflow_dispatch
```

### 4. Debug Workflow Issues

```bash
# Verbose output
act -v

# Very verbose output
act -vv

# Debug with shell access
act --container-options="--entrypoint=/bin/bash"
```

---

## 🚫 Limitations & Considerations

### What Act Cannot Test

- **Azure Authentication**: OIDC won't work locally
- **GitHub Context**: Some GitHub-specific contexts unavailable
- **Secrets**: Real secrets shouldn't be used locally
- **Large Runners**: Limited to available Docker resources

### Workarounds

```bash
# Mock Azure login
export AZURE_CLI_DISABLE_CONNECTION_VERIFICATION=1

# Use test/dummy values for secrets
# Use smaller resource configurations
# Test logic rather than actual deployments
```

---

## 🔍 Testing Strategy

### 1. Syntax & Structure Testing
```bash
# Test workflow file syntax
act -n

# Test job dependencies
act -l
```

### 2. Logic Testing
```bash
# Test workflow logic with dummy data
act --secret-file .secrets.test

# Test environment variable handling
act --env AZURE_ENV_NAME=test
```

### 3. Integration Testing
```bash
# Test with real Azure CLI (but dummy operations)
act -s AZURE_CLIENT_ID=real-client-id --dry-run
```

### 4. End-to-End Testing
```bash
# Test complete workflow in development environment
act workflow_dispatch \
  --input environment=dev \
  --input action=provision
```

---

## 📋 Testing Checklist

Before pushing your workflow changes:

- [ ] **Syntax Check**: `act -n` passes without errors
- [ ] **Job Dependencies**: All jobs have correct dependencies
- [ ] **Environment Variables**: All required env vars are set
- [ ] **Secrets**: All required secrets are configured
- [ ] **File Paths**: All file references are correct
- [ ] **Commands**: All shell commands are valid
- [ ] **Conditions**: All `if` conditions work as expected
- [ ] **Outputs**: Job outputs are correctly defined

---

## 🛠️ Quick Start Script

Create this script to quickly test your workflows:

```bash
#!/bin/bash
# quick-test.sh

echo "🧪 Quick Workflow Test"

# Check Act installation
if ! command -v act &> /dev/null; then
    echo "Installing Act..."
    brew install act
fi

# Create test secrets if they don't exist
if [ ! -f .secrets ]; then
    echo "Creating test secrets file..."
    cat > .secrets << EOF
AZURE_CLIENT_ID=test-client-id
AZURE_TENANT_ID=test-tenant-id
AZURE_SUBSCRIPTION_ID=test-subscription-id
TF_STATE_RESOURCE_GROUP=test-rg
TF_STATE_STORAGE_ACCOUNT=testst
TF_STATE_CONTAINER_NAME=tfstate
AZURE_PRINCIPAL_ID=test-principal-id
ACS_SOURCE_PHONE_NUMBER=+1234567890
EOF
fi

# Test workflow syntax
echo "🔍 Testing workflow syntax..."
act -n

# List available workflows
echo "📋 Available workflows:"
act -l

echo "✅ Quick test complete!"
echo "💡 Run 'act workflow_dispatch' to test deployment workflow"
```

### Make it executable:
```bash
chmod +x quick-test.sh
./quick-test.sh
```

---

## 🎯 Next Steps

1. **Install Act**: `brew install act`
2. **Create Test Files**: `.secrets`, `.env.test`, `.actrc`
3. **Test Syntax**: `act -n`
4. **Test Logic**: `act workflow_dispatch --input environment=dev`
5. **Iterate**: Make changes and test locally before pushing

This approach will save you significant time and GitHub Actions minutes while ensuring your workflows work correctly! 🚀
