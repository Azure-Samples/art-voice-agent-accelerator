# Repository Structure

This document provides a complete 5-level deep map of the ARTVoice accelerator repository, designed for engineers who need to understand the codebase architecture, locate specific components, and contribute effectively.

## Overview

The repository follows a modular, microservice-oriented structure with clear separation of concerns:

- **`apps/`** — Deployable applications (backend API, frontend UI, helper scripts)
- **`src/`** — Core business logic libraries (reusable across apps)
- **`infra/`** — Infrastructure-as-Code (Bicep, Terraform)
- **`docs/`** — Documentation and guides
- **`tests/`** — Test suites and load testing
- **`utils/`** — Cross-cutting utilities (logging, telemetry, images)

---

## Complete Repository Map (5 Levels Deep)

```
📁 gbb-ai-audio-agent/
├── 📄 azure.yaml                          # Azure Developer CLI configuration
├── 📄 CHANGELOG.md                        # Release notes and version history
├── 📄 CONTRIBUTING.md                     # Contribution guidelines
├── 📄 docker-compose.yml                  # Local development containers
├── 📄 environment.yaml                    # Conda environment specification
├── 📄 LICENSE                             # MIT license
├── 📄 Makefile                            # Automation commands (deploy, env setup)
├── 📄 mkdocs.yml                          # Documentation site configuration
├── 📄 pyproject.toml                      # Python project metadata and dependencies
├── 📄 README.md                           # Main project documentation
├── 📄 requirements.txt                    # Python dependencies (production)
├── 📄 requirements-codequality.txt        # Development tools (black, flake8, etc.)
├── 📄 requirements-docs.txt               # Documentation dependencies
├── 📄 setup.py                            # Python package setup
│
├── 📁 apps/                               # Deployable applications
│   ├── 📄 README.md                       # Apps overview and usage
│   └── 📁 rtagent/                        # Real-time voice agent application
│       ├── 📁 backend/                    # FastAPI backend service
│       │   ├── 📄 .env.example            # Environment variables template
│       │   ├── 📄 Dockerfile              # Container definition
│       │   ├── 📄 main.py                 # FastAPI application entry point
│       │   ├── 📄 Makefile                # Backend-specific commands
│       │   ├── 📄 requirements.txt       # Backend dependencies
│       │   ├── 📁 app/                    # Application logic
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📁 api/                # REST API endpoints
│       │   │   │   ├── 📄 __init__.py
│       │   │   │   ├── 📄 calls.py        # ACS call management endpoints
│       │   │   │   ├── 📄 health.py       # Health check endpoints
│       │   │   │   └── 📁 v1/             # API version 1
│       │   │   │       ├── 📄 __init__.py
│       │   │   │       ├── 📄 calls.py    # Call endpoints v1
│       │   │   │       └── 📄 speech.py   # Speech processing endpoints
│       │   │   ├── 📁 core/               # Core application logic
│       │   │   │   ├── 📄 __init__.py
│       │   │   │   ├── 📄 config.py       # Configuration management
│       │   │   │   ├── 📄 dependencies.py # Dependency injection
│       │   │   │   └── 📄 security.py     # Authentication/authorization
│       │   │   ├── 📁 models/             # Pydantic data models
│       │   │   │   ├── 📄 __init__.py
│       │   │   │   ├── 📄 call.py         # Call-related models
│       │   │   │   ├── 📄 speech.py       # Speech data models
│       │   │   │   └── 📄 response.py     # API response models
│       │   │   ├── 📁 services/           # Business logic services
│       │   │   │   ├── 📄 __init__.py
│       │   │   │   ├── 📄 call_service.py # Call orchestration logic
│       │   │   │   ├── 📄 speech_service.py # Speech processing logic
│       │   │   │   └── 📄 agent_service.py # AI agent coordination
│       │   │   └── 📁 ws/                 # WebSocket handlers
│       │   │       ├── 📄 __init__.py
│       │   │       ├── 📄 connection.py   # WebSocket connection management
│       │   │       ├── 📄 handlers.py     # WebSocket message handlers
│       │   │       └── 📄 media.py        # Real-time media streaming
│       │   └── 📁 tests/                  # Backend unit tests
│       │       ├── 📄 __init__.py
│       │       ├── 📄 conftest.py         # Test configuration
│       │       ├── 📁 api/                # API endpoint tests
│       │       ├── 📁 services/           # Service layer tests
│       │       └── 📁 ws/                 # WebSocket tests
│       │
│       ├── 📁 frontend/                   # React frontend application
│       │   ├── 📄 .env.example            # Frontend environment template
│       │   ├── 📄 Dockerfile              # Frontend container definition
│       │   ├── 📄 index.html              # Main HTML template
│       │   ├── 📄 package.json            # Node.js dependencies and scripts
│       │   ├── 📄 tsconfig.json           # TypeScript configuration
│       │   ├── 📄 vite.config.ts          # Vite build configuration
│       │   ├── 📁 public/                 # Static assets
│       │   │   ├── 📄 favicon.ico
│       │   │   └── 📁 icons/              # Application icons
│       │   ├── 📁 src/                    # React source code
│       │   │   ├── 📄 App.tsx             # Main React component
│       │   │   ├── 📄 main.tsx            # React application entry point
│       │   │   ├── 📄 vite-env.d.ts       # Vite type definitions
│       │   │   ├── 📁 components/         # Reusable React components
│       │   │   │   ├── 📄 AudioPlayer.tsx # Audio playback component
│       │   │   │   ├── 📄 CallControls.tsx # Call control buttons
│       │   │   │   ├── 📄 ChatInterface.tsx # Chat UI component
│       │   │   │   └── 📁 ui/             # Basic UI components
│       │   │   │       ├── 📄 Button.tsx
│       │   │   │       ├── 📄 Input.tsx
│       │   │   │       └── 📄 Modal.tsx
│       │   │   ├── 📁 hooks/              # React custom hooks
│       │   │   │   ├── 📄 useAudio.ts     # Audio processing hooks
│       │   │   │   ├── 📄 useWebSocket.ts # WebSocket connection hooks
│       │   │   │   └── 📄 useCall.ts      # Call state management
│       │   │   ├── 📁 pages/              # Page components
│       │   │   │   ├── 📄 Home.tsx        # Home page
│       │   │   │   ├── 📄 Demo.tsx        # Demo interface
│       │   │   │   └── 📄 NotFound.tsx    # 404 page
│       │   │   ├── 📁 services/           # API client services
│       │   │   │   ├── 📄 api.ts          # Base API client
│       │   │   │   ├── 📄 callService.ts  # Call API client
│       │   │   │   └── 📄 speechService.ts # Speech API client
│       │   │   ├── 📁 store/              # State management
│       │   │   │   ├── 📄 index.ts        # Store configuration
│       │   │   │   ├── 📄 callSlice.ts    # Call state slice
│       │   │   │   └── 📄 uiSlice.ts      # UI state slice
│       │   │   ├── 📁 types/              # TypeScript type definitions
│       │   │   │   ├── 📄 api.ts          # API response types
│       │   │   │   ├── 📄 call.ts         # Call-related types
│       │   │   │   └── 📄 speech.ts       # Speech data types
│       │   │   └── 📁 utils/              # Frontend utilities
│       │   │       ├── 📄 audio.ts        # Audio processing utilities
│       │   │       ├── 📄 websocket.ts    # WebSocket utilities
│       │   │       └── 📄 constants.ts    # Application constants
│       │   └── 📁 tests/                  # Frontend tests
│       │       ├── 📄 setup.ts            # Test setup
│       │       ├── 📁 components/         # Component tests
│       │       ├── 📁 hooks/              # Hook tests
│       │       └── 📁 utils/              # Utility tests
│       │
│       └── 📁 scripts/                    # Helper scripts and automation
│           ├── 📄 README.md               # Scripts documentation
│           ├── 📄 start-backend.sh        # Backend startup script
│           ├── 📄 start-frontend.sh       # Frontend startup script
│           ├── 📄 setup-tunnel.sh         # Dev tunnel setup
│           └── 📁 deployment/             # Deployment scripts
│               ├── 📄 deploy-backend.sh   # Backend deployment
│               ├── 📄 deploy-frontend.sh  # Frontend deployment
│               └── 📄 health-check.sh     # Post-deployment validation
│
├── 📁 src/                                # Core business logic libraries
│   ├── 📄 __init__.py                     # Package initialization
│   ├── 📁 acs/                            # Azure Communication Services
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                   # ACS client wrapper
│   │   ├── 📄 events.py                   # Event handling
│   │   ├── 📄 media.py                    # Media streaming
│   │   └── 📁 models/                     # ACS data models
│   │       ├── 📄 __init__.py
│   │       ├── 📄 call.py                 # Call models
│   │       └── 📄 participant.py          # Participant models
│   ├── 📁 agenticmemory/                  # Agent memory management
│   │   ├── 📄 __init__.py
│   │   ├── 📄 memory.py                   # Memory interfaces
│   │   ├── 📄 store.py                    # Memory storage implementations
│   │   └── 📁 adapters/                   # Memory adapter implementations
│   │       ├── 📄 __init__.py
│   │       ├── 📄 cosmos.py               # Cosmos DB adapter
│   │       └── 📄 redis.py                # Redis adapter
│   ├── 📁 aoai/                           # Azure OpenAI integration
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                   # AOAI client wrapper
│   │   ├── 📄 models.py                   # Model management
│   │   ├── 📄 streaming.py                # Streaming responses
│   │   └── 📁 tools/                      # Function calling tools
│   │       ├── 📄 __init__.py
│   │       ├── 📄 registry.py             # Tool registry
│   │       └── 📄 validators.py           # Tool validation
│   ├── 📁 blob/                           # Azure Blob Storage
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                   # Blob client wrapper
│   │   └── 📄 upload.py                   # Upload utilities
│   ├── 📁 cosmosdb/                       # Cosmos DB integration
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                   # Cosmos client wrapper
│   │   ├── 📄 models.py                   # Document models
│   │   └── 📁 collections/                # Collection managers
│   │       ├── 📄 __init__.py
│   │       ├── 📄 calls.py                # Call collection
│   │       └── 📄 sessions.py             # Session collection
│   ├── 📁 enums/                          # Enumeration definitions
│   │   ├── 📄 __init__.py
│   │   ├── 📄 call_states.py              # Call state enums
│   │   └── 📄 speech_events.py            # Speech event enums
│   ├── 📁 latency/                        # Latency measurement and optimization
│   │   ├── 📄 __init__.py
│   │   ├── 📄 tracker.py                  # Latency tracking
│   │   └── 📄 metrics.py                  # Performance metrics
│   ├── 📁 pools/                          # Connection and resource pools
│   │   ├── 📄 __init__.py
│   │   ├── 📄 speech_pool.py              # Speech service pool
│   │   └── 📄 aoai_pool.py                # AOAI service pool
│   ├── 📁 postcall/                       # Post-call processing
│   │   ├── 📄 __init__.py
│   │   ├── 📄 analytics.py                # Call analytics
│   │   └── 📄 summary.py                  # Call summarization
│   ├── 📁 prompts/                        # AI prompt templates
│   │   ├── 📄 __init__.py
│   │   ├── 📄 system.py                   # System prompts
│   │   ├── 📄 user.py                     # User prompts
│   │   └── 📁 templates/                  # Prompt templates
│   │       ├── 📄 __init__.py
│   │       ├── 📄 customer_service.py     # Customer service prompts
│   │       └── 📄 healthcare.py           # Healthcare prompts
│   ├── 📁 redis/                          # Redis integration
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                   # Redis client wrapper
│   │   ├── 📄 cache.py                    # Caching utilities
│   │   └── 📄 pubsub.py                   # Pub/sub messaging
│   ├── 📁 speech/                         # Speech processing
│   │   ├── 📄 __init__.py
│   │   ├── 📄 recognizer.py               # Speech-to-text
│   │   ├── 📄 synthesizer.py              # Text-to-speech
│   │   ├── 📄 streaming.py                # Real-time streaming
│   │   └── 📁 models/                     # Speech models
│   │       ├── 📄 __init__.py
│   │       ├── 📄 transcript.py           # Transcript models
│   │       └── 📄 audio.py                # Audio data models
│   ├── 📁 stateful/                       # Stateful processing
│   │   ├── 📄 __init__.py
│   │   ├── 📄 session.py                  # Session management
│   │   └── 📄 context.py                  # Context tracking
│   ├── 📁 tools/                          # Function calling tools
│   │   ├── 📄 __init__.py
│   │   ├── 📄 base.py                     # Base tool interface
│   │   ├── 📄 calendar.py                 # Calendar integration
│   │   ├── 📄 weather.py                  # Weather API tool
│   │   └── 📁 integrations/               # Third-party integrations
│   │       ├── 📄 __init__.py
│   │       ├── 📄 salesforce.py           # Salesforce integration
│   │       └── 📄 dynamics.py             # Dynamics 365 integration
│   └── 📁 vad/                            # Voice Activity Detection
│       ├── 📄 __init__.py
│       ├── 📄 detector.py                 # VAD implementation
│       └── 📄 silence.py                  # Silence detection
│
├── 📁 infra/                              # Infrastructure as Code
│   ├── 📄 README.md                       # Infrastructure documentation
│   ├── 📁 bicep/                          # Azure Bicep templates
│   │   ├── 📄 abbreviations.json          # Resource naming abbreviations
│   │   ├── 📄 main.bicep                  # Main infrastructure template
│   │   ├── 📄 ai-gateway.bicep            # AI Gateway configuration
│   │   ├── 📄 app.bicep                   # Application services
│   │   ├── 📄 appgw.bicep                 # Application Gateway
│   │   ├── 📄 data.bicep                  # Data services
│   │   ├── 📁 modules/                    # Reusable Bicep modules
│   │   │   ├── 📄 storage.bicep           # Storage account module
│   │   │   ├── 📄 keyvault.bicep          # Key Vault module
│   │   │   ├── 📄 cosmosdb.bicep          # Cosmos DB module
│   │   │   ├── 📄 redis.bicep             # Redis module
│   │   │   └── 📄 containerapp.bicep      # Container Apps module
│   │   └── 📁 parameters/                 # Parameter files
│   │       ├── 📄 main.parameters.json    # Main parameters
│   │       ├── 📄 dev.parameters.json     # Development parameters
│   │       └── 📄 prod.parameters.json    # Production parameters
│   └── 📁 terraform/                      # Terraform configurations
│       ├── 📄 main.tf                     # Main Terraform configuration
│       ├── 📄 variables.tf                # Variable definitions
│       ├── 📄 outputs.tf                  # Output definitions
│       ├── 📄 terraform.tfvars.example    # Variables template
│       ├── 📁 modules/                    # Terraform modules
│       │   ├── 📁 acs/                    # Azure Communication Services
│       │   │   ├── 📄 main.tf
│       │   │   ├── 📄 variables.tf
│       │   │   └── 📄 outputs.tf
│       │   ├── 📁 speech/                 # Azure Speech Services
│       │   │   ├── 📄 main.tf
│       │   │   ├── 📄 variables.tf
│       │   │   └── 📄 outputs.tf
│       │   ├── 📁 aoai/                   # Azure OpenAI
│       │   │   ├── 📄 main.tf
│       │   │   ├── 📄 variables.tf
│       │   │   └── 📄 outputs.tf
│       │   └── 📁 networking/             # Network infrastructure
│       │       ├── 📄 main.tf
│       │       ├── 📄 variables.tf
│       │       └── 📄 outputs.tf
│       └── 📁 environments/               # Environment-specific configs
│           ├── 📁 dev/                    # Development environment
│           │   ├── 📄 main.tf
│           │   └── 📄 terraform.tfvars
│           ├── 📁 staging/                # Staging environment
│           │   ├── 📄 main.tf
│           │   └── 📄 terraform.tfvars
│           └── 📁 prod/                   # Production environment
│               ├── 📄 main.tf
│               └── 📄 terraform.tfvars
│
├── 📁 docs/                               # Documentation
│   ├── 📄 README.md                       # Documentation index
│   ├── 📄 Architecture.md                 # System architecture
│   ├── 📄 AuthForHTTPandWSS.md           # Authentication guide
│   ├── 📄 CICDGuide.md                   # CI/CD setup
│   ├── 📄 DataArchitecture.md            # Data architecture
│   ├── 📄 DeploymentGuide.md             # Deployment instructions
│   ├── 📄 EventGridAuth.md               # Event Grid authentication
│   ├── 📄 HealthcareUsecases.md          # Healthcare use cases
│   ├── 📄 IntegrationPoints.md           # Integration documentation
│   ├── 📄 LoadTesting.md                 # Load testing guide
│   ├── 📄 PathToProduction.md            # Production readiness
│   ├── 📄 Troubleshooting.md             # Troubleshooting guide
│   ├── 📄 WebsocketAuth.md               # WebSocket authentication
│   ├── 📄 quickstart-local-development.md # Local development guide
│   ├── 📄 repo-structure.md              # This document
│   ├── 📁 api/                           # API documentation
│   │   ├── 📄 overview.md                # API overview
│   │   ├── 📄 speech-synthesis.md        # Speech API docs
│   │   └── 📁 endpoints/                 # Endpoint documentation
│   │       ├── 📄 calls.md               # Call endpoints
│   │       └── 📄 speech.md              # Speech endpoints
│   ├── 📁 assets/                        # Documentation assets
│   │   ├── 📄 MVPDeploy_infratf.png      # Architecture diagrams
│   │   ├── 📄 RTAudio_AWSConnect_Forward_to_Azure.png
│   │   ├── 📄 RTAudio_AWSMapped.png
│   │   └── 📄 RTAudio.v0.png
│   └── 📁 getting-started/               # Getting started guides
│       ├── 📄 installation.md            # Installation guide
│       └── 📄 quickstart.md              # Quick start guide
│
├── 📁 tests/                             # Test suites
│   ├── 📄 __init__.py                    # Test package initialization
│   ├── 📄 conftest.py                    # Pytest configuration
│   ├── 📄 apim-test.http                 # API Management tests
│   ├── 📄 backend.http                   # Backend API tests
│   ├── 📄 test_acs_events_handlers.py    # ACS event handler tests
│   ├── 📄 test_acs_media_lifecycle.py    # ACS media lifecycle tests
│   ├── 📄 test_acs_simple.py             # Simple ACS tests
│   ├── 📄 test_dtmf_validation.py        # DTMF validation tests
│   ├── 📄 test_speech_queue.py           # Speech queue tests
│   ├── 📄 test_v1_events_integration.py  # V1 events integration tests
│   ├── 📄 validate_tool_functions.py     # Tool function validation
│   └── 📁 load/                          # Load testing scripts
│       ├── 📄 README.md                  # Load testing documentation
│       ├── 📄 locustfile.py              # Locust load test script
│       ├── 📄 artillery.yml              # Artillery load test config
│       ├── 📁 scenarios/                 # Test scenarios
│       │   ├── 📄 basic_call.py          # Basic call scenario
│       │   ├── 📄 concurrent_calls.py    # Concurrent calls scenario
│       │   └── 📄 stress_test.py         # Stress test scenario
│       └── 📁 reports/                   # Test reports
│           ├── 📄 .gitkeep               # Keep directory in git
│           └── 📁 latest/                # Latest test results
│
├── 📁 utils/                             # Cross-cutting utilities
│   ├── 📄 __init__.py                    # Utilities package initialization
│   ├── 📄 azure_auth.py                  # Azure authentication utilities
│   ├── 📄 ml_logging.py                  # Machine learning logging
│   ├── 📄 telemetry_config.py            # Telemetry configuration
│   ├── 📄 trace_context.py               # Distributed tracing context
│   ├── 📁 docstringtool/                 # Documentation tools
│   │   ├── 📄 __init__.py
│   │   ├── 📄 extractor.py               # Docstring extraction
│   │   └── 📄 generator.py               # Documentation generation
│   └── 📁 images/                        # Project images and diagrams
│       ├── 📄 ARTAGENT.png               # Main logo
│       ├── 📄 RTAGENT.png                # RT Agent logo
│       ├── 📄 ARTAgentarch.png           # Architecture diagram
│       ├── 📄 LIVEVOICEApi.png           # Live Voice API diagram
│       └── 📄 RTAgentArch.png            # RT Agent architecture
│
└── 📁 samples/                           # Sample implementations
    ├── 📄 README.md                      # Samples documentation
    ├── 📁 hello_world/                   # Hello world examples
    │   ├── 📄 README.md                  # Hello world documentation
    │   ├── 📄 01-simple-speech.py        # Simple speech example
    │   ├── 📄 02-acs-integration.py      # ACS integration example
    │   ├── 📄 03-websocket-demo.py       # WebSocket demo
    │   ├── 📄 04-exploring-live-api.ipynb # Live API exploration notebook
    │   └── 📄 05-create-your-first-livevoice.ipynb # Live voice tutorial
    └── 📁 labs/                          # Advanced examples and labs
        ├── 📄 README.md                  # Labs documentation
        ├── 📁 advanced-routing/          # Advanced call routing
        │   ├── 📄 README.md
        │   ├── 📄 ivr_tree.py            # IVR tree implementation
        │   └── 📄 skill_routing.py       # Skill-based routing
        ├── 📁 custom-tools/              # Custom tool examples
        │   ├── 📄 README.md
        │   ├── 📄 crm_integration.py     # CRM tool example
        │   └── 📄 knowledge_base.py      # Knowledge base tool
        └── 📁 performance/               # Performance optimization labs
            ├── 📄 README.md
            ├── 📄 latency_optimization.py # Latency optimization
            └── 📄 throughput_testing.py   # Throughput testing
```

## Key Concepts

### Application Architecture
- **Backend** (`apps/rtagent/backend/`): FastAPI-based REST API with WebSocket support for real-time communication
- **Frontend** (`apps/rtagent/frontend/`): React + TypeScript SPA with Vite for fast development
- **Core Libraries** (`src/`): Reusable business logic that can be imported across applications

### Infrastructure Patterns
- **Multi-Cloud Support**: Both Bicep (Azure-native) and Terraform (cloud-agnostic) templates
- **Environment Separation**: Dev/staging/prod configurations with parameter files
- **Modular Design**: Reusable infrastructure modules for common services

### Code Organization
- **Domain-Driven Design**: Code organized by business domain (ACS, Speech, AI, etc.)
- **Dependency Injection**: Clean separation of concerns using FastAPI's dependency system
- **Type Safety**: Full TypeScript frontend and Python type hints in backend

### Testing Strategy
- **Unit Tests**: Co-located with source code in each module
- **Integration Tests**: In `tests/` directory for cross-module functionality
- **Load Tests**: Dedicated load testing with Locust and Artillery
- **API Tests**: HTTP files for manual and automated API testing

## Quick Navigation for Engineers

### 🔍 **Finding Components**

| What you need | Where to look |
|---------------|---------------|
| API endpoints | `apps/rtagent/backend/app/api/` |
| Business logic | `apps/rtagent/backend/app/services/` |
| WebSocket handlers | `apps/rtagent/backend/app/ws/` |
| React components | `apps/rtagent/frontend/src/components/` |
| Speech processing | `src/speech/` |
| ACS integration | `src/acs/` |
| AI/LLM logic | `src/aoai/` |
| Database models | `src/cosmosdb/models.py` |
| Infrastructure | `infra/bicep/` or `infra/terraform/` |
| Documentation | `docs/` |
| Tests | `tests/` |

### 🚀 **Getting Started Paths**

1. **Frontend Developer**: Start with `apps/rtagent/frontend/src/App.tsx`
2. **Backend Developer**: Start with `apps/rtagent/backend/main.py` 
3. **DevOps Engineer**: Start with `infra/` and `Makefile`
4. **AI Engineer**: Start with `src/aoai/` and `src/speech/`
5. **Integration Developer**: Start with `src/acs/` and `src/tools/`

### 📚 **Documentation Priority**

1. **Quick Start**: `docs/quickstart-local-development.md`
2. **Architecture**: `docs/Architecture.md` 
3. **Deployment**: `docs/DeploymentGuide.md`
4. **API Reference**: `docs/api/`
5. **Troubleshooting**: `docs/Troubleshooting.md`

This structure enables rapid navigation and understanding of the codebase while maintaining clear separation of concerns and supporting both development and production workflows.
