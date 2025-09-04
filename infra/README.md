# **ARTVoice Infrastructure**

Infrastructure as Code for deploying ARTVoice Accelerator on Azure. Choose between Terraform (recommended) and Bicep deployments.

## **Deployment Options**

### **🟢 Terraform** (`/terraform/`) - **Recommended**
- **Status**: ✅ Production ready
- **Target**: Development, PoCs, and production workloads
- **Architecture**: Public endpoints with managed identity authentication
- **Security**: RBAC-based with comprehensive monitoring

### **🔵 Bicep** (`/bicep/`) - **Work in Progress**
- **Status**: 🚧 Development
- **Target**: Enterprise environments with maximum security
- **Architecture**: Hub-spoke networking with private endpoints
- **Security**: Network isolation and enterprise-grade configuration

## **Quick Start**

**Option 1: Azure Developer CLI (Recommended)**
```bash
azd up  # Complete deployment in ~15 minutes
```

**Option 2: Direct Terraform**
```bash
cd terraform/
terraform init
terraform plan
terraform apply
```

See `/terraform/README.md` for detailed instructions.
- **Enterprise Security**: Comprehensive RBAC, managed identities, and Key Vault

#### ⚠️ Known Limitations

- **ACS Integration**: Communication issues between backend and Azure Communication Services
- **Network Complexity**: Requires deep Azure networking knowledge for customization
- **APIM Configuration**: API Management internal deployment still in development
- **Manual Steps**: Some configuration requires post-deployment manual setup
- **Testing**: End-to-end call flow validation pending ACS resolution

#### 🚀 Getting Started (Bicep)

```bash
# Prerequisites: Azure CLI, Bicep CLI, Azure Developer CLI
azd auth login
azd up  # Uses Bicep templates for private deployment

# Manual steps required:
# 1. Purchase ACS phone number via Azure Portal
# 2. Configure custom domain for Speech Services
# 3. Validate private endpoint connectivity
# 4. Configure SBC for PSTN calling
```

#### 📖 Documentation
- [Bicep Architecture Details](bicep/README.md)
- [Private Networking Configuration](bicep/network.bicep)
- [Security Implementation Guide](bicep/modules/identity/)

---

## 🟢 Terraform Deployment - Simplified Public Configuration


The Terraform deployment provides a **simplified, public-facing approach** that's perfect for development, PoCs, and organizations that don't require network isolation. This is the **current recommended approach** for most use cases.


#### ✨ Key Advantages

| Feature | Benefit | Implementation |
|---------|---------|----------------|
| **Simplified Networking** | No complex VNET configuration | Public endpoints with HTTPS/TLS |
| **Rapid Deployment** | 15-minute full stack deployment | Single `terraform apply` command |
| **RBAC-First Security** | Managed identities for all services | Zero stored credentials |
| **Developer Friendly** | Easy local development setup | Direct access to services |
| **Cost Effective** | No private endpoint/VNET costs | Optimized for development and testing |

#### 🔧 Included Services

```bash
# AI & Communication
✅ Azure OpenAI (GPT-4o)           # Conversational AI
✅ Speech Services                 # STT/TTS processing  
✅ Communication Services          # Voice/messaging platform

# Data & Storage
✅ Cosmos DB (MongoDB API)         # Session data
✅ Redis Enterprise                # High-performance caching
✅ Blob Storage                    # Audio/media files
✅ Key Vault                       # Secrets management

# Compute & Monitoring  
✅ Container Apps                  # Serverless hosting
✅ Container Registry              # Image storage
✅ App Service (optional)          # Traditional web app hosting (no container required)
✅ Application Insights            # Monitoring/telemetry
✅ Log Analytics                   # Centralized logging
```

#### 🚀 Quick Start (Terraform)

```bash
# Method 1: Direct Terraform (Recommended)
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_ENV_NAME="dev"

cd infra/terraform
terraform init
terraform apply -var="environment_name=${AZURE_ENV_NAME}"

# Generate environment file and deploy apps
cd ../..
make generate_env_from_terraform
make update_env_with_secrets
make deploy_backend && make deploy_frontend

# Method 2: Using azd (Alternative)
azd auth login && azd up
```

#### 📊 Terraform vs Bicep Comparison

| Aspect | Terraform (Current) | Bicep (WIP) |
|--------|-------------------|-------------|
| **Complexity** | Simple, public endpoints | Complex, private networking |
| **Security Model** | RBAC + Managed Identity | Private endpoints + RBAC |
| **Deployment Time** | ~15 minutes | ~30+ minutes |
| **Network Isolation** | ❌ Public endpoints | ✅ Private VNets |
| **Cost** | Lower (no VNET costs) | Higher (private endpoints) |
| **Use Case** | Dev, PoC, simple prod | Enterprise production |
| **Maintenance** | Low complexity | High complexity |
| **Status** | ✅ Ready | 🚧 WIP |

#### 📖 Documentation
- [Terraform Deployment Guide](../docs/TerraformDeployment.md)
- [Terraform Configuration Details](terraform/README.md)
- [Makefile Automation](../Makefile)

---

## 🎯 Choosing Your Deployment Approach

### Choose **Terraform** if:
- ✅ You need rapid deployment and iteration
- ✅ You're building a PoC or demo application
- ✅ You don't require network isolation
- ✅ You prefer infrastructure simplicity
- ✅ You want to minimize Azure costs
- ✅ You need reliable, tested infrastructure

### Choose **Bicep** if:
- 🔄 You require enterprise-grade network security
- 🔄 You have strict compliance requirements
- 🔄 You need all services behind private endpoints
- 🔄 You can invest time in complex networking setup
- 🔄 You're willing to work with WIP components
- ❗ You can wait for ACS integration issues to be resolved

---

## 🛠️ Common Deployment Tasks

### Environment Setup
```bash
# Set required variables for both approaches
export AZURE_SUBSCRIPTION_ID="12345678-1234-1234-1234-123456789012"
export AZURE_ENV_NAME="dev"

# Authenticate with Azure
az login
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"
```

### Post-Deployment Steps
```bash
# Generate local environment files (Terraform only)
make generate_env_from_terraform
make update_env_with_secrets

# Purchase ACS phone number (both approaches)
make purchase_acs_phone_number

# Deploy applications (Terraform only)  
make deploy_backend
make deploy_frontend
```

### Monitoring & Troubleshooting
```bash
# Check deployment status
terraform output  # Terraform approach
azd env get-values  # azd approach

# View application logs
az containerapp logs show --name <app-name> --resource-group <rg-name>

# Monitor metrics
az monitor metrics list --resource <resource-id>
```

> 🔍 **Need detailed troubleshooting help?** See the comprehensive [Troubleshooting Guide](../docs/Troubleshooting.md) for common issues, diagnostic commands, and step-by-step solutions.

---

## 📚 Additional Resources

### Documentation
- [Architecture Overview](../docs/Architecture.md)
- [Deployment Guide](../docs/DeploymentGuide.md)  
- [Security Best Practices](../docs/Security.md)
- [Load Testing Guide](../docs/LoadTesting.md)

### Getting Help
- **Terraform Issues**: Check [Terraform README](terraform/README.md)
- **Bicep Issues**: Review [Bicep README](bicep/README.md)  
- **General Questions**: See main [project README](../README.md)

---

**🚀 Ready to get started? We recommend beginning with the [Terraform deployment](../docs/TerraformDeployment.md) for the fastest path to a working RTVoice Accelerator.**