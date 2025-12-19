"""
voice_agent.main
================
Entrypoint that stitches everything together:

• config / CORS
• shared objects on `app.state`  (Speech pools, Redis, ACS, dashboard-clients)
• route registration (routers package)

Configuration Loading Order:
    1. .env.local (local development overrides) - loaded FIRST
    2. Environment variables (container/cloud deployments)
    3. Azure App Configuration (if AZURE_APPCONFIG_ENDPOINT is set)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Force unbuffered output for container logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# Use stderr for startup diagnostics (Azure logs often only show stderr)
def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ============================================================================
# LOAD .env.local FIRST (BEFORE ANY OTHER CONFIG)
# ============================================================================
# This MUST happen before any os.getenv() calls or module imports that depend
# on environment variables. .env.local provides local dev overrides.
def _load_dotenv_local():
    """Load .env.local if it exists. Does NOT override existing env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        log("⚠️  python-dotenv not installed, skipping .env.local")
        return None

    backend_dir = Path(__file__).parent
    project_root = backend_dir.parent.parent.parent

    env_files = [
        backend_dir / ".env.local",
        backend_dir / ".env",
        project_root / ".env.local",
        project_root / ".env",
    ]

    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=False)
            return env_file
    return None


loaded_env_file = _load_dotenv_local()

log("")
log("🚀 Backend Startup")
log("─" * 40)
if loaded_env_file:
    log(f"   Config: {loaded_env_file.name}")

# Add parent directories to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

# ============================================================================
# BOOTSTRAP APP CONFIGURATION (MUST BE FIRST)
# ============================================================================
# Load App Configuration values into environment variables BEFORE any other
# imports that read from os.getenv() at module load time (settings.py, etc.)
try:
    from config.appconfig_provider import bootstrap_appconfig
    bootstrap_appconfig()
except Exception as e:
    log(f"❌ App Configuration failed: {e}")
    log("   Using environment variables only")

# ============================================================================
# Now safe to import modules that depend on environment variables
# ============================================================================
from src.pools.warmable_pool import WarmableResourcePool
from utils.telemetry_config import setup_azure_monitor

# Setup monitoring (configures loggers, metrics, Azure Monitor export)
setup_azure_monitor(logger_name="")

# Initialize OpenAI client
from src.aoai.client import _init_client as _init_aoai_client
_init_aoai_client()

log("✅ Initialization complete")
log("─" * 40)

from utils.ml_logging import get_logger

logger = get_logger("main")

import asyncio
import time
from collections.abc import Awaitable, Callable

StepCallable = Callable[[], Awaitable[None]]
LifecycleStep = tuple[str, StepCallable, StepCallable | None]

import uvicorn
from api.v1.endpoints import demo_env

# ─────────────────────────────────────────────────────────────────────────────
# Unified Agents (new modular structure)
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.registries.agentstore.loader import build_handoff_map, discover_agents
from apps.artagent.backend.registries.toolstore.registry import initialize_tools as initialize_unified_tools
from apps.artagent.backend.api.v1.events.registration import register_default_handlers
from apps.artagent.backend.api.v1.router import v1_router
from apps.artagent.backend.config import (
    ACS_CONNECTION_STRING,
    ACS_ENDPOINT,
    ACS_SOURCE_PHONE_NUMBER,
    ALLOWED_ORIGINS,
    AZURE_COSMOS_COLLECTION_NAME,
    AZURE_COSMOS_CONNECTION_STRING,
    AZURE_COSMOS_DATABASE_NAME,
    BASE_URL,
    DEBUG_MODE,
    DOCS_URL,
    ENABLE_AUTH_VALIDATION,
    ENABLE_DOCS,
    ENTRA_EXEMPT_PATHS,
    ENVIRONMENT,
    OPENAPI_URL,
    REDOC_URL,
    SECURE_DOCS_URL,
    AppConfig,
)
from apps.artagent.backend.src.services import (
    AzureOpenAIClient,
    AzureRedisManager,
    CosmosDBMongoCoreManager,
    SpeechSynthesizer,
    StreamingSpeechRecognizerFromBytes,
)
from apps.artagent.backend.src.services.acs.acs_caller import (
    initialize_acs_caller_instance,
)
from apps.artagent.backend.src.utils.auth import validate_entraid_token
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from src.aoai.client_manager import AoaiClientManager
from src.pools.connection_manager import ThreadSafeConnectionManager
from src.pools.session_metrics import ThreadSafeSessionMetrics
from src.speech.phrase_list_manager import (
    PhraseListManager,
    load_default_phrases_from_env,
    set_global_phrase_manager,
)


# --------------------------------------------------------------------------- #
# Agent Access Helpers
# --------------------------------------------------------------------------- #
def get_unified_agent(app: FastAPI, name: str):
    """
    Get a unified agent by name from app.state.

    Args:
        app: FastAPI application instance
        name: Agent name (e.g., "AuthAgent", "FraudAgent")

    Returns:
        UnifiedAgent or None
    """
    agents = getattr(app.state, "unified_agents", {})
    return agents.get(name)


def get_all_unified_agents(app: FastAPI):
    """Get all unified agents from app.state."""
    return getattr(app.state, "unified_agents", {})


def get_handoff_map(app: FastAPI):
    """Get the handoff map from app.state."""
    return getattr(app.state, "handoff_map", {})


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
#  Developer startup dashboard
# --------------------------------------------------------------------------- #
def _build_startup_dashboard(
    app_config: AppConfig,
    app: FastAPI,
    startup_results: list[tuple[str, float]],
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
        ("GET", "/api/v1/agents", "agent inventory"),
        ("GET", "/api/v1/agents/{agent_name}", "agent detail (optional session_id)"),
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
        " Speech Mode : on-demand resource factories",
    ]

    # Show scenario if loaded
    scenario = getattr(app.state, "scenario", None)
    if scenario:
        lines.append(f" Scenario   : {scenario.name}")
        start_agent = getattr(app.state, "start_agent", "Concierge")
        lines.append(f"   Start    : {start_agent}")

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

    # Display unified agents (new modular structure)
    unified_agents = getattr(app.state, "unified_agents", {})
    if unified_agents:
        lines.append(" Unified Agents (apps/artagent/agents/):")
        for name in sorted(unified_agents.keys()):
            agent = unified_agents[name]
            desc = getattr(agent, "description", "")[:40]
            lines.append(f"   {name:<18}{desc}")
    else:
        lines.append(" Unified Agents: (none loaded)")

    # Display legacy agents if present
    legacy_agents = []
    for attr in ["auth_agent", "fraud_agent", "agency_agent", "compliance_agent", "trading_agent"]:
        agent = getattr(app.state, attr, None)
        if agent is not None:
            legacy_agents.append(attr)

    if legacy_agents:
        lines.append("")
        lines.append(" Legacy Agents (to be migrated):")
        for attr in legacy_agents:
            lines.append(f"   {attr}")

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

    startup_steps: list[LifecycleStep] = []
    executed_steps: list[LifecycleStep] = []
    startup_results: list[tuple[str, float]] = []

    def add_step(name: str, start: StepCallable, shutdown: StepCallable | None = None) -> None:
        startup_steps.append((name, start, shutdown))

    class WarningTracker(logging.Handler):
        """In-memory handler to flag warnings emitted during a startup step."""

        def __init__(self):
            super().__init__(level=logging.WARNING)
            self.seen_warning = False

        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - signaling only
            if record.levelno >= logging.WARNING:
                self.seen_warning = True

    class StartupTicker:
        """Single-line ticker similar to pytest's dot runner."""

        def __init__(self, total: int):
            self.total = total
            self.symbols: list[str] = ["·"] * total

        def _render(self, label: str) -> None:
            bar = "".join(self.symbols)
            sys.stderr.write(f"\r[startup] [{bar}] {label:<24}")
            sys.stderr.flush()

        def mark_running(self, index: int, name: str) -> None:
            self.symbols[index] = "…"
            self._render(f"{name}…")

        def mark_done(self, index: int, symbol: str, label: str) -> None:
            self.symbols[index] = symbol
            self._render(label)

        def finalize(self, total_duration: float) -> None:
            self._render(f"done in {total_duration:.2f}s")
            sys.stderr.write("\n")
            sys.stderr.flush()

    async def run_steps(steps: list[LifecycleStep], phase: str) -> None:
        total_steps = len(steps)
        ticker = StartupTicker(total_steps)
        phase_start = time.perf_counter()

        for index, (name, start_fn, shutdown_fn) in enumerate(steps):
            ticker.mark_running(index, f"{phase}: {name}")
            stage_span_name = f"{phase}.{name}"
            warning_tracker = WarningTracker()
            root_logger = logging.getLogger()
            root_logger.addHandler(warning_tracker)
            with tracer.start_as_current_span(stage_span_name) as step_span:
                step_start = time.perf_counter()
                logger.debug(f"{phase} stage started", extra={"stage": name})
                try:
                    await start_fn()
                except Exception as exc:  # pragma: no cover - defensive path
                    step_span.record_exception(exc)
                    step_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.error(f"{phase} stage failed", extra={"stage": name, "error": str(exc)})
                    ticker.mark_done(index, "E", f"{name} failed")
                    root_logger.removeHandler(warning_tracker)
                    raise
                finally:
                    warning_seen = getattr(warning_tracker, "seen_warning", False)
                    root_logger.removeHandler(warning_tracker)
                step_duration = time.perf_counter() - step_start
                step_span.set_attribute("duration_sec", step_duration)
                rounded = round(step_duration, 2)
                logger.debug(
                    f"{phase} stage completed", extra={"stage": name, "duration_sec": rounded}
                )
                executed_steps.append((name, start_fn, shutdown_fn))
                startup_results.append((name, rounded))
                status_symbol = "W" if warning_seen else "."
                ticker.mark_done(index, status_symbol, f"{name} ({rounded:.2f}s)")

        ticker.finalize(time.perf_counter() - phase_start)

    async def run_shutdown(steps: list[LifecycleStep]) -> None:
        for name, _, shutdown_fn in reversed(steps):
            if shutdown_fn is None:
                continue
            stage_span_name = f"shutdown.{name}"
            with tracer.start_as_current_span(stage_span_name) as step_span:
                step_start = time.perf_counter()
                logger.debug("shutdown stage started", extra={"stage": name})
                try:
                    await shutdown_fn()
                except Exception as exc:  # pragma: no cover - defensive path
                    step_span.record_exception(exc)
                    step_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.error("shutdown stage failed", extra={"stage": name, "error": str(exc)})
                    continue
                step_duration = time.perf_counter() - step_start
                step_span.set_attribute("duration_sec", step_duration)
                logger.debug(
                    "shutdown stage completed",
                    extra={"stage": name, "duration_sec": round(step_duration, 2)},
                )

    app_config = AppConfig()
    logger.debug(
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

        # Set Redis manager for session scenarios (for persistence)
        from apps.artagent.backend.src.orchestration.session_scenarios import (
            set_redis_manager,
        )
        set_redis_manager(app.state.redis)

        # Ensure scenario update callback is registered by importing unified orchestrator
        # This enables live scenario updates to propagate to active adapters
        import apps.artagent.backend.src.orchestration.unified  # noqa: F401

        app.state.conn_manager = ThreadSafeConnectionManager(
            max_connections=app_config.connections.max_connections,
            queue_size=app_config.connections.queue_size,
            enable_connection_limits=app_config.connections.enable_limits,
        )
        await app.state.conn_manager.enable_distributed_session_bus(
            app.state.redis,
            channel_prefix="session",
        )
        app.state.session_manager = ThreadSafeSessionManager()
        app.state.session_metrics = ThreadSafeSessionMetrics()
        app.state.greeted_call_ids = set()
        logger.debug(
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
            logger.debug("connection manager stopped")

    add_step("core", start_core_state, stop_core_state)

    async def start_speech_pools() -> None:
        async def make_tts() -> SpeechSynthesizer:
            import os

            key = os.getenv("AZURE_SPEECH_KEY")
            region = os.getenv("AZURE_SPEECH_REGION")
            logger.debug(
                f"Creating TTS synthesizer (key={'set' if key else 'MISSING'}, "
                f"region={region or 'MISSING'})"
            )
            # Don't set voice here - voice comes from active agent at synthesis time
            synth = SpeechSynthesizer(playback="always")
            if not synth.is_ready:
                logger.error(
                    "TTS synthesizer failed to initialize - check Azure Speech credentials "
                    "(AZURE_SPEECH_KEY, AZURE_SPEECH_REGION)"
                )
            else:
                logger.debug("TTS synthesizer initialized successfully")
            return synth

        async def make_stt() -> StreamingSpeechRecognizerFromBytes:
            from config import (
                AUDIO_FORMAT,
                RECOGNIZED_LANGUAGE,
                SILENCE_DURATION_MS,
                VAD_SEMANTIC_SEGMENTATION,
            )

            phrase_manager = getattr(app.state, "speech_phrase_manager", None)
            initial_bias = []
            if phrase_manager:
                initial_bias = await phrase_manager.snapshot()

            return StreamingSpeechRecognizerFromBytes(
                use_semantic_segmentation=VAD_SEMANTIC_SEGMENTATION,
                vad_silence_timeout_ms=SILENCE_DURATION_MS,
                candidate_languages=RECOGNIZED_LANGUAGE,
                audio_format=AUDIO_FORMAT,
                initial_phrases=initial_bias,
            )

        # Import warm pool configuration
        from config import (
            WARM_POOL_BACKGROUND_REFRESH,
            WARM_POOL_ENABLED,
            WARM_POOL_REFRESH_INTERVAL,
            WARM_POOL_SESSION_MAX_AGE,
            WARM_POOL_STT_SIZE,
            WARM_POOL_TTS_SIZE,
        )

        # Define warm_fn callbacks that use Phase 2 warmup methods
        async def warm_tts_connection(tts: SpeechSynthesizer) -> bool:
            """Warm TTS connection by synthesizing minimal audio."""
            try:
                return await asyncio.to_thread(tts.warm_connection)
            except Exception as e:
                logger.warning("TTS warm_fn failed: %s", e)
                return False

        async def warm_stt_connection(stt: StreamingSpeechRecognizerFromBytes) -> bool:
            """Warm STT connection by calling prepare_start()."""
            try:
                return await asyncio.to_thread(stt.warm_connection)
            except Exception as e:
                logger.warning("STT warm_fn failed: %s", e)
                return False

        if WARM_POOL_ENABLED:
            logger.debug(
                "Initializing warm speech pools (TTS=%d, STT=%d, background=%s)",
                WARM_POOL_TTS_SIZE,
                WARM_POOL_STT_SIZE,
                WARM_POOL_BACKGROUND_REFRESH,
            )
        else:
            logger.debug("Initializing speech pools (warm pool disabled, on-demand mode)")

        # Use WarmableResourcePool for both modes. When warm_pool_size=0,
        # it behaves identically to OnDemandResourcePool.
        app.state.stt_pool = WarmableResourcePool(
            factory=make_stt,
            name="speech-stt",
            warm_pool_size=WARM_POOL_STT_SIZE if WARM_POOL_ENABLED else 0,
            enable_background_warmup=WARM_POOL_BACKGROUND_REFRESH if WARM_POOL_ENABLED else False,
            warmup_interval_sec=WARM_POOL_REFRESH_INTERVAL,
            session_awareness=False,
            warm_fn=warm_stt_connection if WARM_POOL_ENABLED else None,
        )

        app.state.tts_pool = WarmableResourcePool(
            factory=make_tts,
            name="speech-tts",
            warm_pool_size=WARM_POOL_TTS_SIZE if WARM_POOL_ENABLED else 0,
            enable_background_warmup=WARM_POOL_BACKGROUND_REFRESH if WARM_POOL_ENABLED else False,
            warmup_interval_sec=WARM_POOL_REFRESH_INTERVAL,
            session_awareness=True,
            session_max_age_sec=WARM_POOL_SESSION_MAX_AGE,
            warm_fn=warm_tts_connection if WARM_POOL_ENABLED else None,
        )

        await asyncio.gather(app.state.tts_pool.prepare(), app.state.stt_pool.prepare())

        # Log pool status
        tts_snapshot = app.state.tts_pool.snapshot()
        stt_snapshot = app.state.stt_pool.snapshot()
        logger.debug(
            "Speech pools ready (TTS warm=%s, STT warm=%s)",
            tts_snapshot.get("warm_pool_size", 0),
            stt_snapshot.get("warm_pool_size", 0),
        )

    async def stop_speech_pools() -> None:
        shutdown_tasks = []
        if hasattr(app.state, "tts_pool"):
            shutdown_tasks.append(app.state.tts_pool.shutdown())
        if hasattr(app.state, "stt_pool"):
            shutdown_tasks.append(app.state.stt_pool.shutdown())
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            logger.debug("speech pools shutdown complete")

    add_step("speech", start_speech_pools, stop_speech_pools)

    async def start_aoai_client() -> None:
        session_manager = getattr(app.state, "session_manager", None)
        aoai_manager = AoaiClientManager(
            session_manager=session_manager,
            initial_client=AzureOpenAIClient(),  # Call the function to get the client instance
        )
        app.state.aoai_client_manager = aoai_manager
        # Expose the underlying client for legacy call-sites while we migrate.
        app.state.aoai_client = await aoai_manager.get_client()
        logger.debug("Azure OpenAI client attached", extra={"manager_enabled": True})

    add_step("aoai", start_aoai_client)

    async def start_connection_warmup() -> None:
        """
        Pre-warm Azure connections to eliminate cold-start latency.

        Phase 1 warmup (this step):
        1. Azure AD token pre-fetch for Speech services (if using managed identity)
        2. Azure OpenAI HTTP/2 connection establishment

        Phase 2 warmup is now handled by WarmableResourcePool:
        - TTS/STT pools pre-warm resources during prepare() with warm_fn callbacks
        - Background warmup maintains pool levels automatically

        All warmup tasks run in parallel and are non-blocking — failures are logged
        but do not prevent application startup.
        """
        warmup_tasks = []

        # ── Phase 1: Token + OpenAI Connection ─────────────────────────────

        # 1. Speech token pre-fetch (if using Azure AD auth, not API key)
        speech_key = os.getenv("AZURE_SPEECH_KEY")
        speech_resource_id = os.getenv("AZURE_SPEECH_RESOURCE_ID")

        if not speech_key and speech_resource_id:

            async def warm_speech_token():
                try:
                    from src.speech.auth_manager import get_speech_token_manager

                    token_mgr = get_speech_token_manager()
                    success = await asyncio.to_thread(token_mgr.warm_token)
                    return ("speech_token", success)
                except Exception as e:
                    logger.warning("Speech token warmup setup failed: %s", e)
                    return ("speech_token", False)

            warmup_tasks.append(warm_speech_token())
        else:
            if speech_key:
                logger.debug("Speech token warmup skipped: using API key auth")
            else:
                logger.debug("Speech token warmup skipped: AZURE_SPEECH_RESOURCE_ID not set")

        # 2. OpenAI connection warm
        async def warm_openai():
            try:
                from src.aoai.client import warm_openai_connection

                success = await warm_openai_connection(timeout_sec=10.0)
                return ("openai_connection", success)
            except Exception as e:
                logger.error("OpenAI warmup setup failed: %s", e)
                return ("openai_connection", False)

        warmup_tasks.append(warm_openai())

        # ── Phase 2: Now handled by WarmableResourcePool ───────────────────
        # TTS/STT warming is done automatically during pool.prepare() via warm_fn
        # and maintained by background warmup task. Report pool warmup status here.

        tts_pool = getattr(app.state, "tts_pool", None)
        stt_pool = getattr(app.state, "stt_pool", None)

        pool_warmup_status = {
            "tts_pool_warmed": tts_pool.snapshot().get("warm_pool_size", 0) if tts_pool else 0,
            "stt_pool_warmed": stt_pool.snapshot().get("warm_pool_size", 0) if stt_pool else 0,
        }

        # Run all warmup tasks in parallel
        if warmup_tasks:
            results = await asyncio.gather(*warmup_tasks, return_exceptions=True)

            # Log warmup results
            warmup_results_dict = {}
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Warmup task failed with exception: %s", result)
                elif isinstance(result, tuple):
                    name, success = result
                    warmup_results_dict[name] = success
                    if success:
                        logger.debug("Warmup completed: %s", name)
                    else:
                        logger.warning("Warmup failed (non-blocking): %s", name)

            # Include pool warmup status
            warmup_results_dict.update(pool_warmup_status)

            # Store warmup status for health checks
            app.state.warmup_completed = True
            app.state.warmup_results = warmup_results_dict
        else:
            app.state.warmup_completed = True
            app.state.warmup_results = pool_warmup_status
            logger.debug("No warmup tasks configured")

    add_step("warmup", start_connection_warmup)

    async def start_external_services() -> None:
        app.state.cosmos = CosmosDBMongoCoreManager(
            connection_string=AZURE_COSMOS_CONNECTION_STRING,
            database_name=AZURE_COSMOS_DATABASE_NAME,
            collection_name=AZURE_COSMOS_COLLECTION_NAME,
        )
        app.state.acs_caller = initialize_acs_caller_instance()

        initial_bias = load_default_phrases_from_env()
        app.state.speech_phrase_manager = PhraseListManager(
            initial_phrases=initial_bias,
        )
        set_global_phrase_manager(app.state.speech_phrase_manager)

        async def hydrate_from_cosmos() -> None:
            cosmos_manager = getattr(app.state, "cosmos", None)
            if not cosmos_manager:
                return

            def fetch_existing_names() -> list[str]:
                projection = {"full_name": 1, "institution_name": 1}
                limit_raw = os.getenv("SPEECH_RECOGNIZER_COSMOS_BIAS_LIMIT", "500")
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 500

                documents = cosmos_manager.query_documents(
                    {
                        "full_name": {"$exists": True, "$type": "string"},
                    },
                    projection=projection,
                    limit=limit if limit > 0 else None,
                )
                names_set: set[str] = set()
                for document in documents:
                    for field in ("full_name", "institution_name"):
                        value = str(document.get(field, "")).strip()
                        if value:
                            names_set.add(value)
                return list(names_set)

            try:
                names = await asyncio.to_thread(fetch_existing_names)
                if not names:
                    return
                added = await app.state.speech_phrase_manager.add_phrases(names)
                logger.debug(
                    "Hydrated speech phrase list with %s entries from Cosmos",
                    added,
                )
            except Exception as exc:  # pragma: no cover - defensive logging only
                logger.warning(
                    "Unable to hydrate speech phrase list from Cosmos",
                    extra={"error": str(exc)},
                )

        await hydrate_from_cosmos()

        logger.debug("external services ready")

    add_step("services", start_external_services)

    async def start_agents() -> None:
        # ─────────────────────────────────────────────────────────────────────
        # Initialize Unified Agents (new modular structure)
        # ─────────────────────────────────────────────────────────────────────

        # Check for scenario-based configuration
        scenario_name = os.getenv("AGENT_SCENARIO", "").strip()

        if scenario_name:
            # Load agents with scenario overrides
            from apps.artagent.backend.registries.scenariostore import (
                get_scenario_agents,
                get_scenario_start_agent,
                load_scenario,
            )

            scenario = load_scenario(scenario_name)
            if scenario:
                unified_agents = get_scenario_agents(scenario_name)
                start_agent = get_scenario_start_agent(scenario_name) or "Concierge"
                app.state.scenario = scenario
                app.state.start_agent = start_agent
                # Use scenario's handoff routes as the source of truth
                app.state.scenario_handoff_map = scenario.build_handoff_map()
                logger.debug(
                    "Loaded scenario: %s",
                    scenario_name,
                    extra={
                        "start_agent": start_agent,
                        "template_vars": list(scenario.global_template_vars.keys()),
                        "scenario_handoffs": list(app.state.scenario_handoff_map.keys()),
                    },
                )
            else:
                logger.warning("Scenario '%s' not found, using default agents", scenario_name)
                unified_agents = discover_agents()
        else:
            # Standard agent loading
            unified_agents = discover_agents()

        # Build handoff_map: prefer scenario handoffs over agent-level handoff.trigger
        scenario_handoff_map = getattr(app.state, "scenario_handoff_map", None)
        if scenario_handoff_map:
            # Use scenario handoff routes as the primary source
            handoff_map = scenario_handoff_map
            # Optionally merge with agent-level triggers for agents not in scenario
            agent_handoff_map = build_handoff_map(unified_agents)
            for tool, agent in agent_handoff_map.items():
                if tool not in handoff_map:
                    handoff_map[tool] = agent
        else:
            # No scenario, use agent-level handoff.trigger
            handoff_map = build_handoff_map(unified_agents)

        from apps.artagent.backend.registries.agentstore.loader import build_agent_summaries

        agent_summaries = build_agent_summaries(unified_agents)

        app.state.unified_agents = unified_agents
        app.state.handoff_map = handoff_map
        app.state.agent_summaries = agent_summaries

        logger.debug(
            "Unified agents loaded",
            extra={
                "agent_count": len(unified_agents),
                "agents": list(unified_agents.keys()),
                "handoff_count": len(handoff_map),
                "handoff_map_keys": list(handoff_map.keys()),
                "agent_summaries": agent_summaries,
                "scenario": scenario_name or "(none)",
            },
        )

        # Set default start_agent if not set by scenario
        if not hasattr(app.state, "start_agent"):
            app.state.start_agent = "Concierge"

    add_step("agents", start_agents)

    async def start_event_handlers() -> None:
        # Initialize tool registry and event handlers defensively to avoid
        # failing the entire app startup when optional components misconfigure.
        try:
            unified_tool_count = initialize_unified_tools()
            logger.debug(
                "Unified tool registry initialized",
                extra={"tool_count": unified_tool_count},
            )
        except Exception as exc:
            logger.warning(
                "Tool registry initialization failed (non-blocking)",
                extra={"error": str(exc)},
            )

        # Register ACS webhook event handlers
        try:
            register_default_handlers()
        except Exception as exc:
            logger.warning(
                "Event handler registration failed (non-blocking)",
                extra={"error": str(exc)},
            )

        orchestrator_preset = os.getenv("ORCHESTRATOR_PRESET", "production")
        logger.debug(
            "event handlers ready",
            extra={"orchestrator_preset": orchestrator_preset},
        )

    add_step("events", start_event_handlers)

    with tracer.start_as_current_span("startup.lifespan") as startup_span:
        startup_span.set_attributes(
            {
                "service.name": "artagent-api",
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
        logger.info(f"✅ Startup complete ({duration_rounded}s)")

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
        from apps.artagent.backend.api.swagger_docs import get_description, get_tags

        tags = get_tags()
        description = get_description()
        logger.debug(f"API documentation enabled for environment: {ENVIRONMENT}")
    else:
        tags = None
        description = "Real-Time Voice Agent API"
        logger.debug(f"API documentation disabled for environment: {ENVIRONMENT}")

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
                return JSONResponse(content={"error": e.detail}, status_code=e.status_code)
            return await call_next(request)

    # app.include_router(api_router)  # legacy, if needed
    app.include_router(v1_router)
    app.include_router(demo_env.router)

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
    """Entry point for uv run artagent-server."""
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        app,  # Use app object directly
        host="0.0.0.0",  # nosec: B104
        port=port,
        reload=False,  # Don't use reload in production
    )


if __name__ == "__main__":
    main()
