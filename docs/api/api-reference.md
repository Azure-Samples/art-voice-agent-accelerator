# API Reference

The Real-Time Voice Agent backend provides REST and WebSocket APIs for building low-latency voice applications powered by Azure Communication Services, Azure Speech Services, and Azure OpenAI.

## 📚 Interactive Documentation

For complete API specifications with interactive testing:

**👉 [Swagger UI](/docs)** - Full OpenAPI documentation with request/response schemas, authentication details, and try-it-now functionality

## 🎯 API Components

The backend service exposes the following high-level API components:

### 🏥 Health & Monitoring
- **Health checks** - Liveness and readiness probes for load balancers
- **Agent status** - List and inspect loaded agents and configurations
- **TTS pool health** - Monitor text-to-speech service pool status

### 📞 Call Management
- **Outbound calls** - Initiate PSTN calls via Azure Communication Services
- **Inbound calls** - Handle incoming calls and Event Grid validation
- **Call lifecycle** - List, terminate, and manage active calls
- **Webhooks** - Process ACS callback events (connected, disconnected, DTMF)

### 🌐 Real-Time Communication
- **Media streaming** - Bidirectional audio WebSocket for ACS calls
- **Browser conversations** - Browser-based voice sessions with session persistence
- **Dashboard relay** - Real-time updates for monitoring dashboards

### 📊 Session & Metrics
- **Session management** - View and manage conversation sessions
- **Telemetry** - Session metrics, latency statistics, and turn-level analytics
- **Aggregated metrics** - Summary statistics across recent sessions

### 🤖 Agent & Scenario Management
- **Agent builder** - Dynamic agent creation, templates, and configuration
- **Scenario builder** - Multi-agent scenarios with handoff routing
- **Tools & voices** - List available agent tools and TTS voices

### 🧪 Demo Environment
- **Demo profiles** - Create synthetic user profiles for testing and demos

## 🚀 Getting Started

### Prerequisites & Deployment

To deploy and configure the backend service:

**👉 [Getting Started Guide](../getting-started/README.md)** - Complete setup instructions including:

- Prerequisites and tool installation
- Azure resource deployment with `azd up`
- Local development environment setup
- Configuration and environment variables
- Authentication and RBAC setup

### Quick Health Check

Once deployed, verify your backend is running:

```bash
curl -X GET https://<your-backend-url>/api/v1/health
```

> See the [Getting Started Guide](../getting-started/README.md) for your actual backend URL after deployment.

## 🔗 Related Documentation

- **[Complete Endpoint Listing](README.md)** - Detailed endpoints, WebSocket specifications, and streaming modes
- **[Getting Started](../getting-started/README.md)** - Deployment and setup guide
- **[Architecture](../architecture/README.md)** - System design and components
- **[Speech Architecture](../architecture/speech/README.md)** - Audio processing and streaming modes