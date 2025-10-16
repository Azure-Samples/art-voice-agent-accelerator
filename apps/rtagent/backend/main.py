"""
voice_agent.main
================
Entrypoint that stitches everything together:

• config / CORS
• shared objects on `app.state`  (Speech pools, Redis, ACS, dashboard-clients)
• route registration (routers package)
"""

from __future__ import annotations

import sys
import os

# Add parent directories to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.pools.async_pool import AsyncPool
from utils.telemetry_config import setup_azure_monitor

# ---------------- Monitoring ------------------------------------------------
setup_azure_monitor(logger_name="rtagent")

from utils.ml_logging import get_logger

logger = get_logger("main")

import time
import asyncio
from typing import Awaitable, Callable, List, Optional, Tuple

StepCallable = Callable[[], Awaitable[None]]
LifecycleStep = Tuple[str, StepCallable, Optional[StepCallable]]

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from src.pools.connection_manager import ThreadSafeConnectionManager
from src.pools.session_metrics import ThreadSafeSessionMetrics
from config.app_config import AppConfig
from config.app_settings import (
    AGENT_AUTH_CONFIG,
    AGENT_CLAIM_INTAKE_CONFIG,
    AGENT_GENERAL_INFO_CONFIG,
    ALLOWED_ORIGINS,
    ACS_CONNECTION_STRING,
    ACS_ENDPOINT,
    ACS_SOURCE_PHONE_NUMBER,
    AZURE_COSMOS_COLLECTION_NAME,
    AZURE_COSMOS_CONNECTION_STRING,
    AZURE_COSMOS_DATABASE_NAME,

    ENTRA_EXEMPT_PATHS,
    ENABLE_AUTH_VALIDATION,
    # Documentation settings
    ENABLE_DOCS,
    DOCS_URL,
    REDOC_URL,
    OPENAPI_URL,
    SECURE_DOCS_URL,
    ENVIRONMENT,
    DEBUG_MODE,
    BASE_URL,
)

from apps.rtagent.backend.src.agents.artagent.base import ARTAgent
from apps.rtagent.backend.src.utils.auth import validate_entraid_token
from apps.rtagent.backend.src.agents.artagent.prompt_store.prompt_manager import PromptManager

# from apps.rtagent.backend.src.routers import router as api_router
from apps.rtagent.backend.api.v1.router import v1_router
from apps.rtagent.backend.src.services import (
    AzureRedisManager,
    CosmosDBMongoCoreManager,
    SpeechSynthesizer,
    StreamingSpeechRecognizerFromBytes,
)
from apps.rtagent.backend.src.services.acs.acs_caller import (
    initialize_acs_caller_instance,
)

from apps.rtagent.backend.api.v1.events.registration import register_default_handlers


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
#  Developer startup dashboard
# --------------------------------------------------------------------------- #
def _build_startup_dashboard(
    app_config: AppConfig,
    app: FastAPI,
    startup_results: List[Tuple[str, float]],
) -> str:
    """Construct a concise ASCII dashboard for developers."""

    header = "=" * 68
    base_url = BASE_URL or f"http://localhost:{os.getenv('PORT', '8080')}"
    auth_status = "ENABLED" if ENABLE_AUTH_VALIDATION else "DISABLED"

    required_acs = {
        "ACS_ENDPOINT": ACS_ENDPOINT,
        "ACS_CONNECTION_STRING": ACS_CONNECTION_STRING,
        "ACS_SOURCE_PHONE_NUMBER": ACS_SOURCE_PHONE_NUMBER,
    }
    missing = [name for name, value in required_acs.items() if not value]
    if missing:
        acs_line = f"[warn] telephony disabled (missing {', '.join(missing)})"
    else:
        acs_line = f"[ok] telephony ready (source {ACS_SOURCE_PHONE_NUMBER})"

    docs_enabled = ENABLE_DOCS

    endpoints = [
        ("GET", "/api/v1/health", "liveness"),
        ("GET", "/api/v1/readiness", "dependency readiness"),
        ("GET", "/api/info", "environment metadata"),
        ("POST", "/api/v1/calls/initiate", "outbound call"),
        ("POST", "/api/v1/calls/answer", "ACS inbound webhook"),
        ("POST", "/api/v1/calls/callbacks", "ACS events"),
        ("WS", "/api/v1/media/stream", "ACS media bridge"),
        ("WS", "/api/v1/realtime/conversation", "Direct audio streaming channel"),
    ]

    telemetry_disabled = os.getenv("DISABLE_CLOUD_TELEMETRY", "false").lower() == "true"
    telemetry_line = "DISABLED (DISABLE_CLOUD_TELEMETRY=true)" if telemetry_disabled else "ENABLED"

    lines = [
        "",
        header,
        " Real-Time Voice Agent :: Developer Console",
        header,
        f" Environment : {ENVIRONMENT} | Debug: {'ON' if DEBUG_MODE else 'OFF'}",
        f" Base URL    : {base_url}",
        f" Auth Guard  : {auth_status}",
        f" Telemetry   : {telemetry_line}",
        f" ACS         : {acs_line}",
        (
            " Speech Pools: "
            f"TTS={app_config.speech_pools.tts_pool_size}, "
            f"STT={app_config.speech_pools.stt_pool_size}"
        ),
    ]

    if docs_enabled:
        lines.append(" Docs       : ENABLED")
        if DOCS_URL:
            lines.append(f"   Swagger  : {DOCS_URL}")
        if REDOC_URL:
            lines.append(f"   ReDoc    : {REDOC_URL}")
        if SECURE_DOCS_URL:
            lines.append(f"   Secure   : {SECURE_DOCS_URL}")
        if OPENAPI_URL:
            lines.append(f"   OpenAPI  : {OPENAPI_URL}")
    else:
        lines.append(" Docs       : DISABLED (set ENABLE_DOCS=true)")

    lines.append("")
    lines.append(" Startup Stage Durations (sec):")
    for stage_name, stage_duration in startup_results:
        lines.append(f"   {stage_name:<13}{stage_duration:.2f}")

    lines.append("")
    agent_configs = [
        ("auth", "auth_agent", AGENT_AUTH_CONFIG),
        ("claim-intake", "claim_intake_agent", AGENT_CLAIM_INTAKE_CONFIG),
        ("general-info", "general_info_agent", AGENT_GENERAL_INFO_CONFIG),
    ]
    loaded_agents: List[str] = []
    for label, attr, config_path in agent_configs:
        agent = getattr(app.state, attr, None)
        if agent is None:
            loaded_agents.append(f"   {label:<13}missing (check {os.path.basename(config_path)})")
        else:
            loaded_agents.append(
                f"   {label:<13}{agent.__class__.__name__} from {os.path.basename(config_path)}"
            )

    lines.append("")
    lines.append(" Loaded Agents:")
    lines.extend(loaded_agents)

    lines.append("")
    lines.append(" Key API Endpoints:")
    lines.append("   METHOD PATH                           NOTES")
    for method, path, note in endpoints:
        lines.append(f"   {method:<6}{path:<32}{note}")

    lines.append(header)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Lifecycle Management
# --------------------------------------------------------------------------- #
async def lifespan(app: FastAPI):
    """
    Manage complete application lifecycle including startup and shutdown events.

    This function handles the initialization and cleanup of all application components
    including speech pools, Redis connections, Cosmos DB, Azure OpenAI clients, and
    ACS agents. It provides comprehensive resource management with proper tracing and
    error handling for production deployment.

    :param app: The FastAPI application instance requiring lifecycle management.
    :return: AsyncGenerator yielding control to the application runtime.
    :raises RuntimeError: If critical startup components fail to initialize.
    """
    tracer = trace.get_tracer(__name__)

    startup_steps: List[LifecycleStep] = []
    executed_steps: List[LifecycleStep] = []
    startup_results: List[Tuple[str, float]] = []

    def add_step(name: str, start: StepCallable, shutdown: Optional[StepCallable] = None) -> None:
        startup_steps.append((name, start, shutdown))

    async def run_steps(steps: List[LifecycleStep], phase: str) -> None:
        for name, start_fn, shutdown_fn in steps:
            stage_span_name = f"{phase}.{name}"
            with tracer.start_as_current_span(stage_span_name) as step_span:
                step_start = time.perf_counter()
                logger.info(f"{phase} stage started", extra={"stage": name})
                try:
                    await start_fn()
                except Exception as exc:  # pragma: no cover - defensive path
                    step_span.record_exception(exc)
                    step_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.error(f"{phase} stage failed", extra={"stage": name, "error": str(exc)})
                    raise
                step_duration = time.perf_counter() - step_start
                step_span.set_attribute("duration_sec", step_duration)
                rounded = round(step_duration, 2)
                logger.info(f"{phase} stage completed", extra={"stage": name, "duration_sec": rounded})
                executed_steps.append((name, start_fn, shutdown_fn))
                startup_results.append((name, rounded))

    async def run_shutdown(steps: List[LifecycleStep]) -> None:
        for name, _, shutdown_fn in reversed(steps):
            if shutdown_fn is None:
                continue
            stage_span_name = f"shutdown.{name}"
            with tracer.start_as_current_span(stage_span_name) as step_span:
                step_start = time.perf_counter()
                logger.info("shutdown stage started", extra={"stage": name})
                try:
                    await shutdown_fn()
                except Exception as exc:  # pragma: no cover - defensive path
                    step_span.record_exception(exc)
                    step_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.error("shutdown stage failed", extra={"stage": name, "error": str(exc)})
                    continue
                step_duration = time.perf_counter() - step_start
                step_span.set_attribute("duration_sec", step_duration)
                logger.info("shutdown stage completed", extra={"stage": name, "duration_sec": round(step_duration, 2)})

    app_config = AppConfig()
    logger.info(
        "Configuration loaded",
        extra={
            "tts_pool": app_config.speech_pools.tts_pool_size,
            "stt_pool": app_config.speech_pools.stt_pool_size,
            "max_connections": app_config.connections.max_connections,
        },
    )

    from src.pools.session_manager import ThreadSafeSessionManager

    async def start_core_state() -> None:
        try:
            app.state.redis = AzureRedisManager()
        except Exception as exc:
            raise RuntimeError(f"Azure Managed Redis initialization failed: {exc}")

        app.state.conn_manager = ThreadSafeConnectionManager(
            max_connections=app_config.connections.max_connections,
            queue_size=app_config.connections.queue_size,
            enable_connection_limits=app_config.connections.enable_limits,
        )
        app.state.session_manager = ThreadSafeSessionManager()
        app.state.session_metrics = ThreadSafeSessionMetrics()
        app.state.greeted_call_ids = set()
        logger.info(
            "core state ready",
            extra={
                "max_connections": app_config.connections.max_connections,
                "queue_size": app_config.connections.queue_size,
                "limits_enabled": app_config.connections.enable_limits,
            },
        )

    async def stop_core_state() -> None:
        if hasattr(app.state, "conn_manager"):
            await app.state.conn_manager.stop()
            logger.info("connection manager stopped")

    add_step("core", start_core_state, stop_core_state)

    async def start_speech_pools() -> None:
        async def make_tts() -> SpeechSynthesizer:
            return SpeechSynthesizer(voice=app_config.voice.default_voice, playback="always")

        async def make_stt() -> StreamingSpeechRecognizerFromBytes:
            from config.app_settings import (
                VAD_SEMANTIC_SEGMENTATION,
                SILENCE_DURATION_MS,
                RECOGNIZED_LANGUAGE,
                AUDIO_FORMAT,
            )

            return StreamingSpeechRecognizerFromBytes(
                use_semantic_segmentation=VAD_SEMANTIC_SEGMENTATION,
                vad_silence_timeout_ms=SILENCE_DURATION_MS,
                candidate_languages=RECOGNIZED_LANGUAGE,
                audio_format=AUDIO_FORMAT,
            )

        logger.info("Initializing Speech pools")
        # STT Pool: Session-agnostic design for maximum flexibility
        # Speech-to-text recognizers can float between sessions since they only
        # consume audio input and produce text transcriptions. Each STT instance
        # is stateless and can be safely shared across different call sessions
        # without resource conflicts or session-specific state contamination.
        app.state.stt_pool = AsyncPool(
            factory=make_stt,
            size=app_config.speech_pools.stt_pool_size,
            enable_session_awareness=False,  # STT instances can serve any session
            enable_prewarming=False,  # Simple on-demand allocation
            enable_cleanup=False,     # Minimal lifecycle management
            acquire_timeout=2.0,
        )
        
        # TTS Pool: Session-aware design for voice consistency and state preservation
        # Text-to-speech synthesizers maintain voice characteristics, prosody state,
        # and conversation context that must remain consistent within a session.
        # Dedicated session assignment prevents voice drift and ensures natural
        # conversation flow by preserving speaker-specific synthesis parameters.
        app.state.tts_pool = AsyncPool(
            factory=make_tts,
            size=app_config.speech_pools.tts_pool_size,
            enable_session_awareness=True,  # Each session gets dedicated TTS instance
            max_dedicated_resources=app_config.connections.max_connections,
            enable_prewarming=True,         # Pre-allocate for low latency
            prewarming_batch_size=5,
            enable_cleanup=True,            # Manage long-lived session resources
            cleanup_interval_seconds=180,
            resource_max_age_seconds=1800,
            acquire_timeout=2.0,
        )

        await asyncio.gather(app.state.tts_pool.prepare(), app.state.stt_pool.prepare())
        logger.info(
            "speech pools prepared",
            extra={
                "tts_pool": app_config.speech_pools.tts_pool_size,
                "stt_pool": app_config.speech_pools.stt_pool_size,
            },
        )

    async def stop_speech_pools() -> None:
        shutdown_tasks = []
        if hasattr(app.state, "tts_pool"):
            shutdown_tasks.append(app.state.tts_pool.shutdown())
        if hasattr(app.state, "stt_pool"):
            shutdown_tasks.append(app.state.stt_pool.shutdown())
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            logger.info("speech pools shutdown complete")

    add_step("speech", start_speech_pools, stop_speech_pools)

    async def start_aoai_pool() -> None:
        from src.pools.aoai_pool import get_aoai_pool

        if os.getenv("AOAI_POOL_ENABLED", "true").lower() != "true":
            app.state.aoai_pool = None
            logger.info("AOAI pool disabled")
            return

        aoai_pool = await get_aoai_pool()
        if aoai_pool:
            app.state.aoai_pool = aoai_pool
            logger.info("AOAI pool initialized", extra={"clients": len(aoai_pool.clients)})
        else:
            app.state.aoai_pool = None
            logger.warning("AOAI pool initialization returned None")

    add_step("aoai", start_aoai_pool)

    async def start_external_services() -> None:
        app.state.cosmos = CosmosDBMongoCoreManager(
            connection_string=AZURE_COSMOS_CONNECTION_STRING,
            database_name=AZURE_COSMOS_DATABASE_NAME,
            collection_name=AZURE_COSMOS_COLLECTION_NAME,
        )
        app.state.acs_caller = initialize_acs_caller_instance()
        logger.info("external services ready")

    add_step("services", start_external_services)

    async def start_agents() -> None:
        app.state.auth_agent = ARTAgent(config_path=AGENT_AUTH_CONFIG)
        app.state.claim_intake_agent = ARTAgent(config_path=AGENT_CLAIM_INTAKE_CONFIG)
        app.state.general_info_agent = ARTAgent(config_path=AGENT_GENERAL_INFO_CONFIG)
        app.state.promptsclient = PromptManager()
        logger.info("agents initialized")

    add_step("agents", start_agents)

    async def start_event_handlers() -> None:
        register_default_handlers()
        orchestrator_preset = os.getenv("ORCHESTRATOR_PRESET", "production")
        logger.info("event handlers registered", extra={"orchestrator_preset": orchestrator_preset})

    add_step("events", start_event_handlers)

    with tracer.start_as_current_span("startup.lifespan") as startup_span:
        startup_span.set_attributes(
            {
                "service.name": "rtagent-api",
                "service.version": "1.0.0",
                "startup.stage": "lifecycle",
            }
        )
        startup_begin = time.perf_counter()
        await run_steps(startup_steps, "startup")
        startup_duration = time.perf_counter() - startup_begin
        startup_span.set_attributes(
            {
                "startup.duration_sec": startup_duration,
                "startup.stage": "complete",
                "startup.success": True,
            }
        )
        duration_rounded = round(startup_duration, 2)
        logger.info("startup complete", extra={"duration_sec": duration_rounded})
        logger.info(f"startup duration: {duration_rounded}s")
        
    logger.info(_build_startup_dashboard(app_config, app, startup_results))

    # ---- Run app ----
    yield

    with tracer.start_as_current_span("shutdown.lifespan") as shutdown_span:
        logger.info("🛑 shutdown…")
        shutdown_begin = time.perf_counter()
        await run_shutdown(executed_steps)

        shutdown_span.set_attribute("shutdown.duration_sec", time.perf_counter() - shutdown_begin)
        shutdown_span.set_attribute("shutdown.success", True)


# --------------------------------------------------------------------------- #
#  App factory with Dynamic Documentation
# --------------------------------------------------------------------------- #
def create_app() -> FastAPI:
    """Create FastAPI app with configurable documentation."""

    # Conditionally get documentation based on settings
    if ENABLE_DOCS:
        from apps.rtagent.backend.api.swagger_docs import get_tags, get_description

        tags = get_tags()
        description = get_description()
        logger.info(f"📚 API documentation enabled for environment: {ENVIRONMENT}")
    else:
        tags = None
        description = "Real-Time Voice Agent API"
        logger.info(f"📚 API documentation disabled for environment: {ENVIRONMENT}")

    app = FastAPI(
        title="Real-Time Voice Agent API",
        description=description,
        version="1.0.0",
        contact={"name": "Real-Time Voice Agent Team", "email": "support@example.com"},
        license_info={
            "name": "MIT License",
            "url": "https://opensource.org/licenses/MIT",
        },
        openapi_tags=tags,
        lifespan=lifespan,
        docs_url=DOCS_URL,
        redoc_url=REDOC_URL,
        openapi_url=OPENAPI_URL,
    )

    # Add secure docs endpoint if configured and docs are enabled
    if SECURE_DOCS_URL and ENABLE_DOCS:
        from fastapi.openapi.docs import get_swagger_ui_html
        from fastapi.responses import HTMLResponse

        @app.get(SECURE_DOCS_URL, include_in_schema=False)
        async def secure_docs():
            """Secure documentation endpoint."""
            return get_swagger_ui_html(
                openapi_url=OPENAPI_URL or "/openapi.json",
                title=f"{app.title} - Secure Docs",
            )

        logger.info(f"🔒 Secure docs endpoint available at: {SECURE_DOCS_URL}")

    return app


# --------------------------------------------------------------------------- #
#  App Initialization with Dynamic Documentation
# --------------------------------------------------------------------------- #
def setup_app_middleware_and_routes(app: FastAPI):
    """
    Configure comprehensive middleware stack and route registration for the application.

    This function sets up CORS middleware for cross-origin requests, implements
    authentication middleware for Entra ID validation, and registers all API
    routers including v1 endpoints for health, calls, media, and real-time features.

    :param app: The FastAPI application instance to configure with middleware and routes.
    :return: None (modifies the application instance in place).
    :raises HTTPException: If authentication validation fails during middleware setup.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=86400,
    )

    if ENABLE_AUTH_VALIDATION:

        @app.middleware("http")
        async def entraid_auth_middleware(request: Request, call_next):
            """
            Validate Entra ID authentication tokens for protected API endpoints.

            This middleware function checks incoming requests for valid authentication
            tokens, exempts specified paths from validation, and ensures proper
            security enforcement across the API surface area.

            :param request: The incoming HTTP request requiring authentication validation.
            :param call_next: The next middleware or endpoint handler in the chain.
            :return: HTTP response from the next handler or authentication error response.
            :raises HTTPException: If authentication token validation fails.
            """
            path = request.url.path
            if any(path.startswith(p) for p in ENTRA_EXEMPT_PATHS):
                return await call_next(request)
            try:
                await validate_entraid_token(request)
            except HTTPException as e:
                return JSONResponse(
                    content={"error": e.detail}, status_code=e.status_code
                )
            return await call_next(request)

    # app.include_router(api_router)  # legacy, if needed
    app.include_router(v1_router)

    # Health endpoints are now included in v1_router at /api/v1/health

    # Add environment and docs status info endpoint
    @app.get("/api/info", tags=["System"], include_in_schema=ENABLE_DOCS)
    async def get_system_info():
        """Get system environment and documentation status."""
        return {
            "environment": ENVIRONMENT,
            "debug_mode": DEBUG_MODE,
            "docs_enabled": ENABLE_DOCS,
            "docs_url": DOCS_URL,
            "redoc_url": REDOC_URL,
            "openapi_url": OPENAPI_URL,
            "secure_docs_url": SECURE_DOCS_URL,
        }


# Create the app
app = None


def initialize_app():
    """Initialize app with configurable documentation."""
    global app
    app = create_app()
    setup_app_middleware_and_routes(app)

    return app


# Initialize the app
app = initialize_app()


# --------------------------------------------------------------------------- #
#  Main entry point for uv run
# --------------------------------------------------------------------------- #
def main():
    """Entry point for uv run rtagent-server."""
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        app,  # Use app object directly
        host="0.0.0.0",  # nosec: B104
        port=port,
        reload=False,  # Don't use reload in production
    )
