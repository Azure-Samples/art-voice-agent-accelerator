# Changelog

All notable changes to the **Azure Real-Time (ART) Agent Accelerator** are documented here.

> **Format**: [Keep a Changelog](https://keepachangelog.com/en/1.0.0) · **Versioning**: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### MAI-Voice-2.1 and Voice Picker

- Added the MAI-Voice-2.1 voice family (for example `en-US-Harper:MAI-Voice-2.1-Flash`) alongside MAI-Voice-2. The voices endpoint now returns `mai_voice_regions` and a `mai_voice_catalog` so clients know whether the configured Speech region serves MAI voices.
- `BankingConcierge` and `Concierge` now default to `en-US-Harper:MAI-Voice-2.1-Flash`.
- Quick Tune, the Agent Builder, and the Advanced Builder share a new `VoiceSelector`: a searchable language list (with pinned **Multilingual** and **All languages** entries), **All / MAI / HD / Standard** family chips, and a filtered voice list. When the region doesn't serve MAI voices, the picker links to the MAI voice availability docs instead of offering voices that would fail at synthesis time.

### Quick Tune Save & Activate

- Added `POST /api/v1/scenario-builder/session/{session_id}/start-agent` (`agent_name`, optional `scenario_name`), which sets the start agent on the session's copy of the scenario without modifying the shared scenario YAML.
- Saving an agent in Quick Tune now makes it the session's active agent. The button reads **Save & activate** or, during a call, **Apply & reconnect**; the app updates the active agent optimistically and confirms it from the server.
- A fresh session now opens Quick Tune on the Banking scenario's start agent (`BankingConcierge`), matching the scenario the session actually connects with, instead of the generic `Concierge`.

### Fixed

- Quick Tune saves behind Azure Front Door no longer fail with "Failed to fetch". The Front Door WAF policy now excludes the JSON template fields `prompt`, `greeting`, `return_greeting`, and `description` from managed-rule inspection, and excludes the `session_id` query argument from session-fixation rules 943110/943120 (which also fixes the agent catalog failing to load).
- Network-level save failures, such as a WAF 403 without CORS headers, now show "The request did not reach the server…" instead of a bare `Failed to fetch`.
- Greeting and handoff-context Jinja templates are now rendered with `ImmutableSandboxedEnvironment`, matching prompt rendering, so user-editable templates cannot reach unsafe Python attributes.

- Container Apps region attribution now matches the complete DNS-label suffix,
  rejecting look-alike domains and preserving the configured region fallback.
- VoiceLive announces the initial active agent once and emits a single notification per
  agent transition, rather than repeating "Active agent" on every turn.
- Context-only VoiceLive acknowledgements no longer interrupt playback or cancel responses.
  Identical instruction updates are skipped, while changed conversation context and full
  agent/scenario configuration updates are preserved.

### Turn-Scoped Transcript Streaming

- Speech Cascade and VoiceLive now stream user transcription updates into a single turn-scoped user bubble, then finalize that same bubble when recognition completes. Any orphaned streaming partial bubble is pruned when the final lands, so the turn always settles on one recognized transcript.
- User and assistant bubbles render partial (streaming) text in italics and flip to normal text once the turn is finalized, giving a clear streaming-vs-final cue per turn.
- Streaming bubbles now render text and the live cursor inline and normalize whitespace, so a partial transcript looks identical to its final (no phantom blank line appearing only while streaming).
- Each user turn keeps one streamed assistant response bubble across tool calls and agent handoffs.
- All tool calls within a turn now collapse into a single grouped "Tool Activity" card that lists each call with its status and result; the card stays hidden until at least one call returns a response, so transient "started"/progress states no longer flash as separate bubbles.
- Frontend envelope handling now uses one deterministic turn reducer with fixed user → assistant → tools slots. Barge-in closes the prior response and in-flight tools, while late partial/final/tool envelopes from that interrupted turn are ignored instead of reopening, duplicating, or overwriting bubbles in the new turn.
- Added backend-envelope contract, barge-in race, ordering/indexing, and real `ChatBubble` rendering regression tests for both Speech Cascade and VoiceLive flows.
- Added an envelope-classifier contract test that locks every backend conversation event type (user partial/final, assistant streaming/final/greeting, barge-in cancel, tool start/progress/end) to its bubble event and asserts control/lifecycle frames are ignored, so a renamed or unrouted backend type fails loudly instead of silently dropping a bubble; plus a full end-to-end cascade session test asserting one user, one response, and one grouped tool blob per turn across a barge-in, and a cancelled-bubble render test.
- VoiceLive browser sessions now deliver tool lifecycle frames directly on the active WebSocket instead of incorrectly routing them through the ACS dashboard broadcast path.
- A VoiceLive post-tool response segment can now continue the same canonical assistant bubble after the pre-tool segment finalized; duplicate or late events from the already-closed segment remain rejected.
- The bubble reducer no longer drops user/assistant/tool events when an envelope omits `turn_id`: id-less partials coalesce into the open streaming bubble, finalize in place, and start a fresh synthetic turn per utterance, restoring resilient rendering for Speech Cascade and text-input transcripts.
- Agent response bubbles now render even when the backend stamps the response with a `turn_id` that differs from the user turn's id: the "late turn" guard only suppresses events belonging to an earlier user turn superseded by barge-in, not a fresh response whose id merely differs.
- The assistant final now settles the in-flight streaming response bubble even when the final envelope carries a different id than the streamed chunks (e.g. Speech Cascade post-tool responses), so the response no longer clones into a separate streaming + final bubble.
- Speech Cascade now emits an `assistant_cancelled` event on barge-in (parity with VoiceLive) as a best-effort UI signal sent only after the response, TTS, and orchestration are cancelled, so it can never delay the audio stop; the reducer marks the interrupted streaming bubble as cancelled even when the cancel id differs from the streamed response id.

### Telemetry and Evaluation Hardening

- Frontend session telemetry no longer emits raw operator identity fields.
- Voice metric events use a fixed low-cardinality event name with the metric label as a property.
- WebSocket URLs and audio/message payloads are no longer written to browser logs.
- The live WebSocket evaluation driver accepts an explicit `--streaming-mode` and records it in results.
- Live voice evaluations now target the active browser WebSocket, use deterministic PCM VAD padding, preserve W3C trace correlation, and produce per-mode latency summaries.
- Added local Make targets for cached input-audio generation and repeatable `realtime`/`voice_live` performance runs.

### Terraform Remote State Networking

- The public-networking helper now uses the typed Storage Account update for `publicNetworkAccess` and `defaultAction`, then verifies that public access remained enabled.
- Storage update failures now include a compact Azure CLI error instead of silently reporting only `failed/unsupported`.
- Remote Terraform state accounts discovered from the selected azd environment are handled by the same verified Storage Account path.
- If policy leaves a Storage Account, Key Vault, or Container Registry's `publicNetworkAccess` disabled after an update, the helper now merges `SecurityControl=Ignore`, retries once, and verifies the final state.
- Added `enable_public_resources` as a backwards-compatible alias for `enable_public_networking`.
- `make enable_public_resources` now asks whether to merge `SecurityControl=Ignore` onto resources opened by the helper; `--yes` leaves the tag opt-in disabled.
- Foundry accounts and projects now inherit the shared deployment tags, and existing accounts reconcile tag changes such as `SecurityControl=Ignore`.

## [2.1.0] - 2026-02-01

### 🔌 MCP Protocol & Lifecycle Management

This release updates the MCP integration to spec 2025-11-25, introduces deferred startup for non-blocking health checks, and enhances lifecycle observability.

### Added

- **Deferred Startup Pattern** — MCP validation runs asynchronously after `/health` returns 200, preventing deployment probe failures
- **Health Endpoints** — New `/api/v1/ready`, `/api/v1/readiness`, and `/api/v1/pools` endpoints for granular startup observability
- **Lifecycle Dashboard** — Background task status with pending/in-progress/completed/failed states
- **MCP Server Skill** — Comprehensive deployment guide with Container App and Function App patterns
- **Lifecycle Documentation** — New `docs/architecture/lifecycle.md` covering startup phases and health probes

### Enhanced

- **MCP Protocol** — Updated to spec 2025-11-25 with `streamable-http` as default transport (replaces `sse`)
- **FastMCP Integration** — CardAPI MCP server refactored with `@mcp.custom_route()` for health endpoints
- **Backend Indicator** — Frontend now shows deferred startup status and pending task count
- **Agent Builder** — Added Responses API toggle functionality
- **Postprovision Scripts** — Enhanced CardAPI data provisioning with improved error handling

### Fixed

- **Terraform Git Commit** — Fixed `data.external.git_commit` to output valid JSON
- **MCP Client** — Improved error handling for `streamable-http` transport connections
- **Cosmos Init** — Enhanced database initialization with better retry logic

### Infrastructure

- **Deployment Workflow** — Added CardAPI MCP test step to CI/CD template
- **VS Code Launch Config** — Updated debug configurations for MCP servers

### Documentation

- **MCP Integration Guide** — Added transport types table, deferred startup section, settings reference
- **API Documentation** — Updated with new health endpoints and MCP management section
- **Architecture README** — Added Registries and Lifecycle to deep dives table

---

## [2.0.0-beta.1] - 2026-01-04

### 🎯 Scenario Builder & Voice Handler Refactoring

This release introduces the visual **Scenario Builder** for designing multi-agent workflows, comprehensive **VoiceHandler refactoring** with unified lifecycle management, and significant improvements to deployment scripts and telemetry.

### Added

- **Scenario Builder UI** — Visual graph-based editor for designing agent workflows with drag-and-drop node placement, edge connections, and handoff condition patterns
- **Canvas Panning** — Infinite canvas navigation with drag-to-pan and reset-to-center controls
- **Handoff Condition Patterns** — Pre-built templates (Authentication, Fraud/Security, Escalation, Technical Support, etc.) for common handoff scenarios
- **Unified HandoffService** — Consolidated handoff logic across orchestrators for consistent behavior
- **Evaluation Framework** — Model evaluation playground with A/B testing capabilities and comprehensive metrics
- **VoiceHandler Migration** — Refactored MediaHandler into unified VoiceHandler with proper lifecycle management
- **Responses API Infrastructure** — Dual model configuration support with GPT-4o and GPT-4.1
- **Comprehensive Test Suite** — New tests for VoiceLive handler, cascade orchestrator, DTMF processor, and scenario orchestration contracts

### Enhanced

- **OpenTelemetry Consolidation** — Proper span hierarchy and lazy metrics initialization with shared metrics factory
- **TTS Processing** — Text sanitization and sentence boundary detection for improved audio quality
- **LiveOrchestrator** — Enhanced user message history management and context-only session updates without redundant UI broadcasts
- **Deployment Scripts** — Pre/post-provisioning hooks with Azure CLI extension checks, EasyAuth configuration, and improved preflight checks
- **Logging Consistency** — Standardized logging levels (info→debug) across connection manager, warmable pool, Redis, and speech modules
- **AZD Hook Testing** — Dev Container testing workflow with environment validation and summary reporting
- **Documentation** — Updated quickstart guide with demo profile creation, agent builder screenshots, and troubleshooting guidance

### Fixed

- **Redis Connection Handling** — Added error handling for connection issues with proper recovery
- **Duplicate UI Updates** — LiveOrchestrator now omits redundant session_updated broadcasts during context-only updates
- **Environment Logic** — Corrected pull_request event handling in Azure deployment workflow
- **Terraform State Locks** — Added troubleshooting guidance for state lock errors with remote/local fix options
- **Container Memory Formats** — Normalized memory configurations in deployment workflows

### Infrastructure

- **CI/CD Improvements** — Reusable workflow templates, parallel AZD hook testing across Linux/macOS/Windows
- **GitHub PAT Support** — Optional PAT secret with enhanced environment variable handling
- **Documentation Workflow** — Updated with deployment badges and improved navigation

### Removed

- **Deprecated Latency Tools** — Removed `latency_analytics.py`, `latency_tool.py`, `latency_tool_compat.py`, `latency_tool_v2.py` and related files (replaced by OpenTelemetry-based metrics)
- **Backend IP Restrictions** — Removed configuration and related outputs

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

