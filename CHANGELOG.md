# Changelog

All notable changes to the **Azure Real-Time (ART) Agent Accelerator** are documented here.

> **Format**: [Keep a Changelog](https://keepachangelog.com/en/1.0.0) · **Versioning**: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [2.0.0-beta] - 2025-12-19

### 🎉 Beta Release: Unified Agent & Scenario Framework

Beta release featuring the **YAML-driven agent system**, **multi-scenario orchestration**, and **Azure VoiceLive SDK** integration. This release represents a complete architectural evolution from v1.x.

### Added

- **Unified Agent Framework** — YAML-driven agent definitions (`agent.yaml`) with Jinja2 prompt templating and hot-reload
- **Scenario Orchestration** — Multi-agent scenarios with `orchestration.yaml` defining agent graphs, handoffs, and routing
- **Azure VoiceLive SDK** — Native integration with `gpt-4o-realtime` for ~200ms voice-to-voice latency
- **Industry Scenarios** — Banking (concierge, fraud, investment) and Insurance (FNOL, policy advisor, auth) ready-to-use
- **15+ Business Tools** — Authentication, fraud detection, knowledge search, account lookup, card recommendations
- **Streaming Mode Selector** — Frontend toggle between SpeechCascade and VoiceLive orchestrators
- **Profile Details Panel** — Real-time caller context display with tool execution visualization
- **Demo Scenarios Widget** — One-click scenario switching for demos and testing

### Enhanced

- **Package Management** — Migrated to `uv` for 10x faster installs with reproducible `uv.lock`
- **OpenTelemetry** — Full distributed tracing across LLM, Speech, and ACS with latency metrics
- **Phrase Biasing** — Dynamic per-agent phrase lists for improved domain-specific recognition
- **Agent Handoffs** — Seamless context preservation during multi-agent transfers
- **Devcontainer** — ARM64/x86 multi-arch support with optimized startup

### Fixed

- VoiceLive "already has active response" conflicts during rapid handoffs
- LLM streaming timeouts (now 90s overall, 5s per-chunk with graceful cancellation)
- Tool call index validation filtering malformed responses
- Docker build optimization removing unnecessary apt upgrades
---

## [1.5.0] - 2025-12-07

Major release featuring Azure VoiceLive SDK integration, unified agent framework, and comprehensive deployment tooling improvements.

### Added
- **Azure VoiceLive SDK Integration**: Real-time voice AI orchestration with WebSocket-based audio streaming and VAD support
- **Unified Agent Framework**: YAML-driven agent definitions with Jinja2 prompt templating and hot-reload capabilities
- **Multi-Agent Orchestration**: Speech Cascade and Live Orchestrator modes with seamless agent handoffs and context preservation
- **Comprehensive Tool System**: 15+ business tools including authentication, banking, fraud detection, and knowledge base search
- **Banking Scenario Agents**: Concierge, AuthAgent, FraudAgent, PayPalAgent, InvestmentAdvisor, and more
- **Frontend Components**: StreamingModeSelector, ProfileDetailsPanel, DemoScenariosWidget, and BackendIndicator

### Enhanced
- **Package Management**: Migrated from pip to uv for faster, reproducible builds with `uv.lock` (221 packages)
- **Devcontainer**: Multi-architecture support (ARM64/x86) with streamlined startup
- **Terraform Deployment**: Fixed deprecated properties, count dependencies, and dynamic tfvars generation
- **azd Remote State**: Simplified interactive prompts with auto-generated storage configuration
- **OpenTelemetry**: Comprehensive tracing for LLM, speech, and ACS calls with latency metrics
- **Speech Processing**: Dynamic phrase biasing and configurable transcription settings per agent

### Fixed
- **Agent Handoffs**: Resolved greeting bugs and "already has active response" conflicts in VoiceLive
- **LLM Streaming**: Added 90s overall timeout and 5s per-chunk timeout with graceful cancellation
- **Tool Calls**: Fixed index validation to filter malformed responses
- **Docker Builds**: Optimized Dockerfile for faster builds by removing unnecessary apt upgrades

### Infrastructure
- Azure VoiceLive model deployment configurations with capacity and SKU settings
- Communication services email domain resources
- Redis session persistence and CosmosDB TTL management improvements
- Staging environment parameter updates with location resolution fallback chain

---

## [1.3.0] - 2025-12-07

### Azure VoiceLive Integration

- **VoiceLive Orchestrator** — Real-time voice AI with WebSocket-based audio streaming
- **Server-side VAD** — Automatic turn detection and noise reduction via Azure
- **HD Neural Voices** — Support for `en-US-Ava:DragonHDLatestNeural` and premium voices
- **Model Deployment Configs** — Azure VoiceLive capacity and SKU settings in Terraform

### Enhanced

- Terraform deployment with dynamic tfvars generation
- azd remote state with auto-generated storage configuration
- Redis session persistence and CosmosDB TTL management

---

## [1.2.0] - 2025-10-15

### Multi-Agent Architecture

- **Agent Registry** — Centralized agent store with YAML definitions and prompt templates
- **Tool Registry** — Pluggable tool system with dependency injection
- **Handoff Service** — Agent-to-agent transfers with context preservation
- **Banking Agents** — Concierge, AuthAgent, FraudAgent, InvestmentAdvisor

### Enhanced

- Model routing between GPT-4o and GPT-4.1-mini based on complexity
- DTMF tone handling with enhanced error recovery
- Load testing framework with Locust conversation simulation

---

## [1.1.0] - 2025-09-15

### Live Voice API Preview

- **Azure Live Voice API** — Initial integration for real-time streaming
- **Audio Generation Tools** — Standalone generators for testing workflows
- **WebSocket Debugging** — Advanced response debugging and audio extraction

### Fixed

- API 400 errors in tool call processing
- Audio buffer race conditions and memory leaks
- Container App resource limits for production workloads

---

## [1.0.0] - 2025-08-18

### 🚀 Production Ready

First production release with enterprise-grade security, observability, and scalability.

### Added

- **Agent Health Monitoring** — Status endpoints for production readiness
- **Frontend UI** — Voice selection and real-time status indicators
- **Production Scripts** — Deployment automation with error handling

### Infrastructure

- Terraform with IP whitelisting and security hardening
- CI/CD pipelines with automated testing and quality gates
- Azure integration with managed identity, Key Vault, and monitoring

---

## [0.9.0] - 2025-08-13

### Deployment Automation

- Automated deployment scripts with error recovery
- IP whitelisting for network security
- Agent health check endpoints
- CI/CD pipeline testing workflows

---

## [0.8.0] - 2025-07-15

### Enterprise Observability

- **OpenTelemetry** — Distributed tracing with Azure Monitor
- **Structured Logging** — Correlation IDs and JSON output
- **Key Vault** — Secure secret management
- **WAF** — Application Gateway with Web Application Firewall

---

## [0.7.0] - 2025-06-30

### Modular Agent Framework

- Pluggable industry-specific agents (healthcare, legal, insurance)
- GPT-4o and o1-preview model support
- Intelligent model routing based on complexity
- Memory management with Redis and Cosmos DB

---

## [0.6.0] - 2025-06-15

### Infrastructure as Code

- Terraform modules for complete Azure deployment
- Azure Developer CLI (azd) integration
- Azure Communication Services for telephony
- Container Apps with KEDA auto-scaling

---

## [0.5.0] - 2025-05-30

### Real-Time Audio Processing

- Streaming speech recognition with sub-second latency
- Neural TTS with emotional expression
- Voice activity detection (VAD)
- WebSocket-based audio transmission

---

## [0.4.0] - 2025-05-15

### FastAPI Backend

- High-performance async request handling
- RESTful API for agent management
- WebSocket bidirectional communication
- Health check endpoints with dependency validation

---

## [0.3.0] - 2025-05-01

### React Frontend

- Modern component architecture
- Real-time voice interface with visual feedback
- WebSocket client with auto-reconnection
- Responsive design for all devices

---

## [0.2.0] - 2025-04-20

### Azure Speech Integration

- STT/TTS with regional optimization
- Multi-language support with dialect detection
- Audio streaming infrastructure
- Managed identity authentication

---

## [0.1.0] - 2025-04-05

### Initial Release

- Project structure and development environment
- Basic audio processing and streaming
- Initial Azure service integrations
- CI/CD pipeline foundation


