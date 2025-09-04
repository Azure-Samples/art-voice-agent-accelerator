# Infrastructure README - Updated

⚠️ **This infrastructure is currently a work in progress** ⚠️

This document outlines the core Azure infrastructure components required for the real-time voice agent application. The infrastructure supports multiple voice agent scenarios including health claims, benefits lookup, and billing inquiries.

## 🚧 Current Status

This is an **active development project** with several manual configuration steps still required before full functionality is achieved. Please review the manual setup requirements carefully before deployment.


## Prerequisites

Before deploying this infrastructure, ensure you have the following tools and requirements installed and configured:

### Required Tools
- **Azure Developer CLI (azd)**: Version 1.5.0 or later
  ```bash
  # Install azd
  curl -fsSL https://aka.ms/install-azd.sh | bash
  ```
- **Docker**: Required for building and running container images locally
  ```bash
  # Verify Docker installation
  docker --version
  ```
- **Azure CLI**: Version 2.50.0 or later for manual Azure operations
  ```bash
  # Install Azure CLI
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
  ```

### Azure Requirements
- **Azure Subscription**: Active subscription with sufficient credits/billing
- **Required Permissions**: Contributor or Owner role on the target subscription
- **Resource Quotas**: Ensure sufficient quota for:
  - Container Apps (minimum 2 vCPUs)
  - Application Gateway v2 instances
  - Azure OpenAI service availability in target region
  - ACS phone number availability in target region

### Development Environment
- **Node.js**: Version 18+ for frontend development
- **Python**: Version 3.11+ for backend development
- **Git**: For source code management and azd deployment

### Getting Started
1. Clone the repository and navigate to the project root
2. Run `azd auth login` to authenticate with Azure
3. Run `azd up` to provision infrastructure and deploy the application
4. Follow the manual setup requirements outlined below for complete configuration


## Core Infrastructure Components

![Real-Time Audio Agent Architecture](../docs/assets/RTAudio.v0.png)

The infrastructure consists of several interconnected Azure services that work together to provide a complete real-time voice agent solution:

### 🔊 Azure Communication Services (ACS) - Voice Gateway
- **Call Management**: Handles incoming and outgoing PSTN voice calls
- **Real-time Communication**: WebSocket connections for live audio streaming
- **Media Processing**: Audio codec handling and real-time media transport
- **Call State Management**: Session lifecycle and call routing

**Provisioning Details:**
- **ACS Resource**: Provisioned via Azure portal or CLI. Phone numbers must be manually purchased and configured.
- **Environment Variables**: ACS connection string and phone number are stored in Key Vault and injected into the backend environment.

### 🎤 Speech Services - Transcription Engine
- **Speech-to-Text (STT)**: Real-time transcription with streaming support
- **Text-to-Speech (TTS)**: Natural voice synthesis for AI responses
- **Custom Voice Models**: Support for domain-specific voice customization
- **Multi-language Support**: Configurable language detection and processing

**Provisioning Details:**
- **Speech Service**: Deployed via Bicep templates with private endpoint and DNS zone integration.
- **Custom Domain**: Requires manual DNS configuration for domain verification.

### 🤖 AI & Intelligence Layer
- **Azure OpenAI**: GPT-4o and other models for chat AI
- **API Management**: Load balancing and gateway for OpenAI endpoints
- **Event Grid**: Event-driven architecture for call state and transcript events
- **Application Insights**: Real-time monitoring and performance analytics

**Provisioning Details:**
- **OpenAI Services**: Configured via `ai-gateway.bicep` with backend pools and private endpoints.
- **API Management**: Optional, enabled via `enableAPIManagement` parameter in `ai-gateway.bicep`.
- **Event Grid**: Deployed as part of the event-driven architecture module.

### 💾 Data & State Management
- **Azure Redis Cache**: Session state, active call data, and real-time transcript storage
- **Cosmos DB**: Persistent conversation history and call analytics
- **Azure Blob Storage**: Audio recordings, call logs, and media artifacts
- **Key Vault**: Secure storage for API keys, certificates, and connection strings

**Provisioning Details:**
- **Redis Cache**: Configured via `main.bicep` with private endpoint and VNet integration.
- **Cosmos DB**: Deployed via `data.bicep` with MongoDB API and private endpoint.
- **Blob Storage**: Provisioned in `data.bicep` with secure access policies.
- **Key Vault**: Managed in `main.bicep` with RBAC and private endpoint.

### 🌐 Networking & Load Balancing
- **Application Gateway**: Layer 7 load balancer with SSL termination and WAF
- **Hub and Spoke Virtual Networks**: Private networking with dedicated subnets for each service tier
- **Private Endpoints**: Secure private connectivity to Azure PaaS services
- **Private DNS Zones**: Resolution for private endpoints of services like Blob, CosmosDB, KeyVault, etc.
- **Public IP & DNS**: Required for ACS webhook callbacks and external accessibility

**Provisioning Details:**
- **Application Gateway**: Configured via `appgw.bicep` with autoscaling, WAF, and SSL termination.
- **Hub and Spoke VNets**: Deployed via `networkv2.bicep` with subnet configurations for each service.
- **Private Endpoints**: Managed in respective modules (e.g., `data.bicep`, `ai-gateway.bicep`).
- **Private DNS Zones**: Created in `networkv2.bicep` and linked to VNets.

### 🔐 Security & Identity
- **Managed Identity**: Service-to-service authentication without stored credentials
- **Azure AD Integration**: Optional user authentication for admin interfaces
- **Network Security Groups**: Traffic filtering and access control
- **SSL/TLS Termination**: End-to-end encryption for all communications

**Provisioning Details:**
- **Managed Identity**: Configured in `main.bicep` and assigned to resources like Application Gateway and Container Apps.
- **NSGs**: Defined in `networkv2.bicep` for subnet-level traffic control.
- **SSL Certificates**: Managed via Key Vault and linked to Application Gateway.

## Manual Setup Requirements

### 1. 📞 Phone Number & PSTN Configuration
> **Note**: ACS phone number purchase is now automated [azd-postprovision.sh](../scripts/azd-postprovision.sh)

  Navigate to Azure Communication Services in portal
  1. Go to ACS resource > Phone numbers
  2. Purchase phone number with "Make and receive calls" capability
  3. Note the phone number for configuration

**SBC Configuration Steps:**
- Configure Session Border Controller settings in ACS
- Set up call routing rules for inbound/outbound traffic
- Configure media processing and supported codecs
- Test PSTN connectivity and call flow

### 2. 🌍 Custom Domain Setup for Speech Services

To enable real-time transcription with Azure Communication Services (ACS) and Speech Services integration, follow these steps:
  1. Register custom domain on the speech service
  2. Update .env for the backend configuration for AZURE_SPEECH_ENDPOINT with the domain configured endpoint


### 3. 🔗 Public Domain & Application Gateway
The ACS service requires webhook callbacks to a publicly accessible HTTPS endpoint:

#### ACS Domain requirements:
- Must be accessible from public internet
- Must have valid SSL certificate
- Must resolve to Application Gateway public IP
- Cannot use localhost, private IPs, or self-signed certificates


**Application Gateway Configuration:**
- WAF_v2 SKU for security and performance
- SSL certificate management via Key Vault
- Backend pool pointing to Container Apps
- Health probes for high availability
- Session stickiness enabled for frontend container
- Connection draining enabled for the backend websocket workers

### 4. 🔧 Container Apps Backend Configuration
The FastAPI backend must be configured for:
- WebSocket support for real-time communication
- CORS configuration for frontend access
- Environment variables from Key Vault
- Managed identity for Azure service access


### Explanation of the Architecture

1. **Internet → Application Gateway**:
   - The Application Gateway serves as the entry point for all external traffic.
   - It provides SSL termination, WAF protection, and load balancing for backend services.

2. **Container Apps (Backend/Frontend)**:
   - The backend (FastAPI) handles real-time communication, WebSocket connections, and API requests.
   - The frontend (React) provides the user interface for managing calls and transcripts.

3. **PSTN Calls → ACS**:
   - Azure Communication Services (ACS) manages PSTN calls and WebSocket connections for live audio streaming.
   - ACS integrates with the backend for call state management and media processing.

4. **ACS → Speech Services**:
   - Speech Services provide real-time transcription (STT) and text-to-speech (TTS) capabilities.
   - Custom voice models and multi-language support enhance the transcription and synthesis quality.

5. **Speech Services → Azure OpenAI**:
   - Azure OpenAI models (e.g., GPT-4o) process transcriptions and generate chat responses.
   - API Management ensures secure and scalable access to OpenAI endpoints.

6. **Call Events → Event Grid**:
   - Event Grid handles event-driven communication between services, such as call state changes and transcript updates.

7. **Redis Cache**:
   - Redis Cache stores session state, active call data, and real-time transcripts for low-latency access.

8. **Cosmos DB**:
   - Cosmos DB provides persistent storage for conversation history and call analytics.

### Key Features
- **Scalability**: Autoscaling is enabled for Container Apps and Application Gateway.
- **Security**: Managed identities, private endpoints, and Key Vault ensure secure communication.
- **Resilience**: Event Grid and Cosmos DB provide fault-tolerant and event-driven architecture.
- **Performance**: Redis Cache and Application Gateway optimize real-time communication and load balancing.

## Current Deployment Status

- [x] Core infrastructure (Hub and Spoke VNets, subnets, security groups)
- [x] Private DNS zones for private endpoint resolution
- [x] Container Apps platform with auto-scaling
- [x] Redis Cache for session management
- [x] Cosmos DB for persistent storage
- [x] Key Vault for secrets management
- [x] Azure OpenAI with API Management
- [x] Event Grid for event-driven architecture
- [x] Application Gateway with WAF protection
- [x] Phone number purchase and configuration
- [x] Custom domain setup for Speech Services
- [ ] **APIM deployment with fully internal config (currently using Standard V2 + VNet Injection)**
- [ ] **SBC configuration for PSTN calling**
- [x] SSL certificate provisioning and binding
- [ ] **End-to-end call flow testing**
- [ ] **Production security hardening**
- [x] Monitoring and alerting setup

## Known Limitations & TODOs

### Infrastructure as Code (IaC) Improvements

- **Network Configuration Modularization**: Break down network configuration from monolithic structure into reusable modules
  - Extract `networkv2.bicep` into smaller, focused modules (e.g., `vnet.bicep`, `subnets.bicep`, `nsg.bicep`, `private-endpoints.bicep`)
  - Create parameterized network modules for hub-spoke topology vs. simple public-only configurations
  - Standardize subnet delegation and address space allocation across modules
  - **Status**: Current networkv2.bicep is functional but monolithic - needs modularization for maintainability

- **Main.bicep Decomposition**: Restructure large main.bicep file into logical, manageable modules
  - Split into domain-specific modules: `compute.bicep`, `data.bicep`, `ai-services.bicep`, `security.bicep`
  - Implement consistent parameter passing and output handling across modules
  - Create environment-specific parameter files (dev, staging, prod) for cleaner deployments
  - Add module dependency management and proper `dependsOn` configurations
  - **Status**: Main.bicep currently ~500+ lines - target modular structure with <100 lines per module

- **Public-Only Network Configuration**: Add support for simplified public-only deployments
  - Create alternative network topology without private endpoints for development/demo scenarios
  - Implement conditional logic to deploy public vs. private configurations based on parameters
  - Maintain security best practices even in public-only mode (NSGs, WAF, managed identities)
  - Document trade-offs between public-only and private endpoint architectures
  - **Status**: Currently only supports private endpoint architecture - public-only option needed for flexibility

- **Load Testing Infrastructure**: Add dedicated load testing components and configurations
  - Create `loadtest.bicep` module for Azure Load Testing service provisioning
  - Configure test data generators for synthetic call traffic and concurrent user scenarios
  - Set up performance monitoring dashboards specific to load testing scenarios
  - Implement automated load test execution via Azure DevOps or GitHub Actions
  - Add capacity planning guidelines and auto-scaling validation scripts
  - **Status**: No load testing infrastructure currently provisioned - critical for production readiness validation

### Communication & Integration Issues
- **ACS Integration Failure**: Current deployment experiences communication failures between backend and Azure Communication Services
  - SSL certificate is properly configured and frontend↔backend communication is functional
  - ACS webhook callbacks may be failing due to routing or authentication issues
  - Requires investigation of ACS service configuration and webhook endpoint accessibility
  - WebSocket connections for real-time audio streaming may need troubleshooting
  - **Status**: Known issue as of 7/1/2025 handoff - pending investigation and future update

- **Azure Service Authentication**: Post-ACS resolution, comprehensive validation needed for EntraID-based service-to-service authentication
  - **AI Gateway (APIM)**: Verify managed identity credentials for Azure OpenAI API calls through API Management
  - **Cosmos DB**: Ensure backend can authenticate and access conversation history and call analytics data
  - **Redis Cache**: Validate session state management and real-time transcript storage access
  - **Speech Services**: Confirm STT/TTS operations work with EntraID authentication for transcription pipeline
  - **Status**: Authentication framework in place but requires end-to-end testing once ACS communication is stable

### Technical Debt & Improvements

- **SBC Configuration**: Session Border Controller setup still requires manual configuration and testing
- **Call Flow Validation**: End-to-end testing from PSTN → ACS → Backend → AI pipeline needs comprehensive validation
- **Service Integration Testing**: Validate complete data flow: ACS → Speech Services → Azure OpenAI → Redis/Cosmos DB storage
- **Error Handling**: Improve graceful fallbacks for ACS connection failures and service outages
- **Performance Optimization**: Fine-tune WebSocket connection pooling and audio buffer management
- **Security Hardening**: Complete production security review including network isolation and access controls

### Monitoring & Observability

- **ACS Call Analytics**: Enhanced logging and monitoring for call state transitions and media quality
- **Service Dependency Monitoring**: Track authentication success/failure rates across AI Gateway, Cosmos DB, Redis, and Speech Services
- **Real-time Dashboards**: Application Insights dashboards for live call monitoring and transcript analysis
- **Alert Configuration**: Automated alerts for ACS service failures, authentication errors, high latency, and error rates


## Local Development Notes

For local development, the infrastructure includes:
- Container Apps with development-friendly settings
- Redis Cache accessible via private endpoint
- Key Vault integration for local secret access
- Application Gateway bypass for direct Container App access

## Support & Troubleshooting

Common issues and solutions:
- **ACS Webhook Failures**: Ensure backend is accessible via public HTTPS endpoint
- **Speech Service Integration**: Verify custom domain is properly configured
- **Call Quality Issues**: Check SBC configuration and network routing
- **Authentication Errors**: Verify managed identity permissions

For additional help, check the [Architecture.md](../docs/Architecture.md) and [Integration-Points.md](../docs/Integration-Points.md) documentation.