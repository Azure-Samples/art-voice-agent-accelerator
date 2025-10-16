# :material-rocket: Getting Started

!!! success "Real-Time Voice AI Accelerator"
    Get your voice agent running with Azure Communication Services, Speech Services, and AI in just a few steps.

## :material-check-circle: Prerequisites

=== "System Requirements"
    - **Python**: 3.11 or higher
    - **Operating System**: Windows 10+, macOS 10.15+, or Linux
    - **Memory**: Minimum 4GB RAM (8GB recommended)
    - **Network**: Internet connectivity for Azure services

=== "Azure Requirements"
    - **Azure Subscription**: [Create one for free](https://azure.microsoft.com/free/) if you don't have one
    - **Azure CLI**: [Install Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) for resource management
    
    !!! tip "Microsoft Learn Resources"
        - **[Azure Free Account Setup](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/create-free-services)** - Step-by-step account creation
        - **[Azure CLI Fundamentals](https://learn.microsoft.com/en-us/cli/azure/get-started-with-azure-cli)** - Essential CLI commands

## :material-school: Learning Paths

=== "🚀 Quick Start (15 minutes)"
    **Get up and running fast**:
    
    1. **[Local Development Guide](local-development.md)** - Complete setup with raw commands
    2. **[Architecture Overview](../architecture/README.md)** - Understand the system design
    3. **[API Reference](../api/README.md)** - Explore available endpoints
    
    **Best for**: Developers who want to see the accelerator in action immediately

=== "🏗️ Infrastructure First"
    **Set up Azure resources properly**:
    
    1. **[Production Deployment](../deployment/production.md)** - Infrastructure provisioning
    2. **[Configuration Details](configuration.md)** - Advanced configuration options
    3. **[Local Development Guide](local-development.md)** - Connect to your infrastructure
    
    **Best for**: Architects and teams planning production deployments

=== "🔧 Deep Dive"
    **Understand the complete system**:
    
    1. **[Architecture Overview](../architecture/README.md)** - System design and patterns
    2. **[Data Flow Patterns](../architecture/data-flows.md)** - Processing pipeline architecture
    3. **[LLM Orchestration](../architecture/llm-orchestration.md)** - AI routing and conversation management
    4. **[Operations Guide](../operations/monitoring.md)** - Monitoring and troubleshooting
    
    **Best for**: Technical leads and teams building custom voice applications

## :material-microsoft-azure: Azure Setup Requirements

!!! note "Required Azure Resources"
    The accelerator requires these Azure services for full functionality:

| Service | Purpose | Required For |
|---------|---------|--------------|
| **Speech Services** | Text-to-Speech, Speech-to-Text | All voice features |
| **Communication Services** | Phone calls, WebSocket media | Phone integration |
| **AI Foundry / OpenAI** | Conversation intelligence | AI agent responses |
| **Redis Cache** | Session state management | Multi-turn conversations |
| **Cosmos DB** | Conversation persistence | Analytics, compliance |

**Quick Azure Setup**:
```bash
# Clone the repository
git clone https://github.com/Azure-Samples/art-voice-agent-accelerator.git
cd art-voice-agent-accelerator

# Deploy infrastructure (choose one)
azd provision  # Azure Developer CLI (recommended)
# or use Terraform/Bicep directly
```

## :material-compass: Development Approaches

=== "🏃‍♂️ Fast Track"
    **Start developing immediately**:
    
    - **Goal**: Voice agent running locally in 15 minutes
    - **Path**: [Local Development Guide](local-development.md)
    - **Infrastructure**: Minimal (Speech Services only)
    - **Best for**: Proof of concepts, learning, simple demos

=== "🏭 Production Ready"
    **Enterprise deployment preparation**:
    
    - **Goal**: Scalable, secure, monitored deployment
    - **Path**: [Production Deployment](../deployment/production.md) → [Local Development](local-development.md)
    - **Infrastructure**: Complete (all Azure services)
    - **Best for**: Production applications, enterprise environments

=== "🔬 Custom Development"
    **Extend and customize the accelerator**:
    
    - **Goal**: Build custom voice applications
    - **Path**: [Architecture Deep Dive](../architecture/README.md) → [Local Development](local-development.md)
    - **Infrastructure**: As needed for your use case
    - **Best for**: Custom voice solutions, specialized industries

## :material-help: Getting Help

!!! info "Community & Support Resources"
    
    **Documentation**:
    - **[Troubleshooting Guide](../operations/troubleshooting.md)** - Common issues and solutions
    - **[API Reference](../api/README.md)** - Complete endpoint documentation
    - **[Examples & Samples](../examples/README.md)** - Practical implementation examples
    
    **Community**:
    - **[GitHub Issues](https://github.com/Azure-Samples/art-voice-agent-accelerator/issues)** - Report bugs and request features
    - **[GitHub Discussions](https://github.com/Azure-Samples/art-voice-agent-accelerator/discussions)** - Community Q&A
    - **[Microsoft Q&A](https://learn.microsoft.com/en-us/answers/topics/azure-speech.html)** - Official Microsoft support

---

## :material-arrow-right: What's Next?

Choose your path above and start building your voice-powered applications! Most developers find success starting with the **[Local Development Guide](local-development.md)** to see the accelerator in action immediately.

!!! tip "New to Voice AI?"
    Check out the **[Architecture Overview](../architecture/README.md)** first to understand how real-time voice processing works with Azure Communication Services and Speech Services.