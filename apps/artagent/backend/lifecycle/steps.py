"""
Lifecycle Steps - Individual startup/shutdown functions.

Each step is a self-contained unit responsible for initializing
one component of the application. Steps can be composed and
reordered as needed.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .manager import LifecycleManager

logger = get_logger("lifecycle.steps")


# ============================================================================
# Step 1: Core State (Redis, Connection Manager, Session Manager)
# ============================================================================


def register_core_state_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the core state initialization step."""
    from apps.artagent.backend.config import AppConfig
    from apps.artagent.backend.src.services import AzureRedisManager
    from src.pools.connection_manager import ThreadSafeConnectionManager
    from src.pools.session_manager import ThreadSafeSessionManager
    from src.pools.session_metrics import ThreadSafeSessionMetrics

    app_config = AppConfig()

    async def start() -> None:
        # Initialize Redis
        try:
            app.state.redis = AzureRedisManager()
        except Exception as exc:
            raise RuntimeError(f"Redis initialization failed: {exc}") from exc

        # Wire up session scenario persistence
        from apps.artagent.backend.src.orchestration.session_scenarios import set_redis_manager

        set_redis_manager(app.state.redis)

        # Import unified orchestrator to register scenario callbacks
        import apps.artagent.backend.src.orchestration.unified  # noqa: F401

        # Initialize connection manager with distributed session bus
        app.state.conn_manager = ThreadSafeConnectionManager(
            max_connections=app_config.connections.max_connections,
            queue_size=app_config.connections.queue_size,
            enable_connection_limits=app_config.connections.enable_limits,
        )
        await app.state.conn_manager.enable_distributed_session_bus(
            app.state.redis,
            channel_prefix="session",
        )

        # Initialize managers
        app.state.session_manager = ThreadSafeSessionManager()
        app.state.session_metrics = ThreadSafeSessionMetrics()
        app.state.greeted_call_ids = set()

    async def stop() -> None:
        if hasattr(app.state, "conn_manager"):
            await app.state.conn_manager.stop()

    manager.add_step("core", start, stop)


# ============================================================================
# Step 2: Speech Pools (TTS/STT with warm pooling)
# ============================================================================


def register_speech_pools_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the speech pool initialization step."""
    from apps.artagent.backend.src.services import (
        SpeechSynthesizer,
        StreamingSpeechRecognizerFromBytes,
    )
    from src.pools.warmable_pool import WarmableResourcePool

    async def start() -> None:
        from config import (
            AUDIO_FORMAT,
            RECOGNIZED_LANGUAGE,
            SILENCE_DURATION_MS,
            VAD_SEMANTIC_SEGMENTATION,
            WARM_POOL_BACKGROUND_REFRESH,
            WARM_POOL_ENABLED,
            WARM_POOL_MAX_RETRIES,
            WARM_POOL_REFRESH_INTERVAL,
            WARM_POOL_RESTART_ON_FAILURE,
            WARM_POOL_SESSION_MAX_AGE,
            WARM_POOL_STT_SIZE,
            WARM_POOL_TTS_SIZE,
            WARM_POOL_WARMUP_TIMEOUT,
        )

        # Factory functions for resource creation
        async def make_tts() -> SpeechSynthesizer:
            synth = SpeechSynthesizer(playback="always")
            if not synth.is_ready:
                logger.warning("TTS synthesizer failed - check AZURE_SPEECH_KEY/REGION")
            return synth

        async def make_stt() -> StreamingSpeechRecognizerFromBytes:
            phrase_manager = getattr(app.state, "speech_phrase_manager", None)
            initial_bias = await phrase_manager.snapshot() if phrase_manager else []
            return StreamingSpeechRecognizerFromBytes(
                use_semantic_segmentation=VAD_SEMANTIC_SEGMENTATION,
                vad_silence_timeout_ms=SILENCE_DURATION_MS,
                candidate_languages=RECOGNIZED_LANGUAGE,
                audio_format=AUDIO_FORMAT,
                initial_phrases=initial_bias,
            )

        # Warmup callbacks with timeout protection
        async def warm_tts(tts: SpeechSynthesizer) -> bool:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(tts.warm_connection), timeout=8.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"TTS warmup failed: {e}")
                return False

        async def warm_stt(stt: StreamingSpeechRecognizerFromBytes) -> bool:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(stt.warm_connection), timeout=8.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"STT warmup failed: {e}")
                return False

        # Create pools (warm or on-demand based on config)
        pool_enabled = WARM_POOL_ENABLED

        app.state.stt_pool = WarmableResourcePool(
            factory=make_stt,
            name="speech-stt",
            warm_pool_size=WARM_POOL_STT_SIZE if pool_enabled else 0,
            enable_background_warmup=WARM_POOL_BACKGROUND_REFRESH if pool_enabled else False,
            warmup_interval_sec=WARM_POOL_REFRESH_INTERVAL,
            session_awareness=False,
            warm_fn=warm_stt if pool_enabled else None,
            warmup_timeout_sec=WARM_POOL_WARMUP_TIMEOUT,
            max_warmup_retries=WARM_POOL_MAX_RETRIES,
        )

        app.state.tts_pool = WarmableResourcePool(
            factory=make_tts,
            name="speech-tts",
            warm_pool_size=WARM_POOL_TTS_SIZE if pool_enabled else 0,
            enable_background_warmup=WARM_POOL_BACKGROUND_REFRESH if pool_enabled else False,
            warmup_interval_sec=WARM_POOL_REFRESH_INTERVAL,
            session_awareness=True,
            session_max_age_sec=WARM_POOL_SESSION_MAX_AGE,
            warm_fn=warm_tts if pool_enabled else None,
            warmup_timeout_sec=WARM_POOL_WARMUP_TIMEOUT,
            max_warmup_retries=WARM_POOL_MAX_RETRIES,
        )

        # Prepare pools in parallel
        await asyncio.gather(app.state.tts_pool.prepare(), app.state.stt_pool.prepare())

        # Check warmup status (non-blocking)
        if pool_enabled:
            tts_snap = app.state.tts_pool.snapshot()
            stt_snap = app.state.stt_pool.snapshot()
            tts_ready = tts_snap.get("warm_pool_size", 0)
            stt_ready = stt_snap.get("warm_pool_size", 0)
            tts_target = tts_snap.get("warm_pool_target", 0)
            stt_target = stt_snap.get("warm_pool_target", 0)

            if tts_ready < tts_target or stt_ready < stt_target:
                logger.warning(
                    f"Speech pools partially warmed: TTS {tts_ready}/{tts_target}, "
                    f"STT {stt_ready}/{stt_target}. Using on-demand fallback."
                )

            # Only fail if completely empty AND restart configured
            if (
                WARM_POOL_RESTART_ON_FAILURE
                and tts_ready == 0
                and stt_ready == 0
                and (tts_target > 0 or stt_target > 0)
            ):
                raise RuntimeError("Complete speech pool warmup failure")

    async def stop() -> None:
        tasks = []
        if hasattr(app.state, "tts_pool"):
            tasks.append(app.state.tts_pool.shutdown())
        if hasattr(app.state, "stt_pool"):
            tasks.append(app.state.stt_pool.shutdown())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    manager.add_step("speech", start, stop)


# ============================================================================
# Step 3: Azure OpenAI Client
# ============================================================================


def register_aoai_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the Azure OpenAI client initialization step."""
    from apps.artagent.backend.src.services import AzureOpenAIClient
    from src.aoai.client_manager import AoaiClientManager

    async def start() -> None:
        session_manager = getattr(app.state, "session_manager", None)
        aoai_manager = AoaiClientManager(
            session_manager=session_manager,
            initial_client=AzureOpenAIClient(),
        )
        app.state.aoai_client_manager = aoai_manager
        app.state.aoai_client = await aoai_manager.get_client()

    manager.add_step("aoai", start)


# ============================================================================
# Step 4: Connection Warmup (Token pre-fetch, OpenAI connection)
# ============================================================================


def register_warmup_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the connection warmup step (deferred - runs in background).
    
    This step warms OpenAI and speech connections to reduce first-request latency.
    Since it's deferred, the app starts accepting requests immediately while
    warmup continues in the background.
    """
    # Initialize state so /ready endpoint can check before deferred task runs
    app.state.warmup_completed = False
    app.state.warmup_results = {}

    async def start() -> None:
        warmup_tasks = []
        warmup_results = {}

        # Speech token pre-fetch (if using managed identity)
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
                    logger.debug(f"Speech token warmup skipped: {e}")
                    return ("speech_token", False)

            warmup_tasks.append(warm_speech_token())

        # OpenAI connection warmup
        async def warm_openai():
            try:
                from src.aoai.client import warm_openai_connection

                success = await warm_openai_connection(timeout_sec=10.0)
                return ("openai", success)
            except Exception as e:
                logger.debug(f"OpenAI warmup skipped: {e}")
                return ("openai", False)

        warmup_tasks.append(warm_openai())

        # Run warmup tasks in parallel (failures are non-blocking)
        if warmup_tasks:
            results = await asyncio.gather(*warmup_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, tuple):
                    warmup_results[result[0]] = result[1]

        # Add pool status
        tts_pool = getattr(app.state, "tts_pool", None)
        stt_pool = getattr(app.state, "stt_pool", None)
        warmup_results["tts_pool"] = tts_pool.snapshot().get("warm_pool_size", 0) if tts_pool else 0
        warmup_results["stt_pool"] = stt_pool.snapshot().get("warm_pool_size", 0) if stt_pool else 0

        app.state.warmup_completed = True
        app.state.warmup_results = warmup_results

    manager.add_step("warmup", start, deferred=True)


# ============================================================================
# Step 5: External Services (Cosmos, ACS, Phrase Manager)
# ============================================================================


def register_external_services_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register external services initialization step."""
    from apps.artagent.backend.config import (
        AZURE_COSMOS_COLLECTION_NAME,
        AZURE_COSMOS_CONNECTION_STRING,
        AZURE_COSMOS_DATABASE_NAME,
    )
    from apps.artagent.backend.src.services import CosmosDBMongoCoreManager
    from apps.artagent.backend.src.services.acs.acs_caller import initialize_acs_caller_instance
    from src.speech.phrase_list_manager import (
        PhraseListManager,
        load_default_phrases_from_env,
        set_global_phrase_manager,
    )

    async def start() -> None:
        # Initialize Cosmos DB
        app.state.cosmos = CosmosDBMongoCoreManager(
            connection_string=AZURE_COSMOS_CONNECTION_STRING,
            database_name=AZURE_COSMOS_DATABASE_NAME,
            collection_name=AZURE_COSMOS_COLLECTION_NAME,
        )

        # Initialize ACS caller
        app.state.acs_caller = initialize_acs_caller_instance()

        # Initialize phrase manager for speech recognition bias
        initial_bias = load_default_phrases_from_env()
        app.state.speech_phrase_manager = PhraseListManager(initial_phrases=initial_bias)
        set_global_phrase_manager(app.state.speech_phrase_manager)

        # Hydrate phrase list from Cosmos (non-blocking)
        await _hydrate_phrases_from_cosmos(app)

    manager.add_step("services", start)


async def _hydrate_phrases_from_cosmos(app: FastAPI) -> None:
    """Load speech recognition phrases from Cosmos DB."""
    cosmos_manager = getattr(app.state, "cosmos", None)
    phrase_manager = getattr(app.state, "speech_phrase_manager", None)

    if not cosmos_manager or not phrase_manager:
        return

    def fetch_names() -> list[str]:
        limit = int(os.getenv("SPEECH_RECOGNIZER_COSMOS_BIAS_LIMIT", "500"))
        docs = cosmos_manager.query_documents(
            {"full_name": {"$exists": True, "$type": "string"}},
            projection={"full_name": 1, "institution_name": 1},
            limit=limit if limit > 0 else None,
        )
        names = set()
        for doc in docs:
            for field in ("full_name", "institution_name"):
                value = str(doc.get(field, "")).strip()
                if value:
                    names.add(value)
        return list(names)

    try:
        names = await asyncio.to_thread(fetch_names)
        if names:
            await phrase_manager.add_phrases(names)
            logger.debug(f"Loaded {len(names)} phrases from Cosmos")
    except Exception as exc:
        logger.debug(f"Phrase hydration skipped: {exc}")


# ============================================================================
# Step 6: Agents (Unified agent loading with scenario support)
# ============================================================================


def register_agents_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the agent loading step."""
    from apps.artagent.backend.registries.agentstore.loader import (
        build_agent_summaries,
        build_handoff_map,
        discover_agents,
    )

    async def start() -> None:
        scenario_name = os.getenv("AGENT_SCENARIO", "").strip()

        if scenario_name:
            # Load scenario-based configuration
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
                app.state.scenario_handoff_map = scenario.build_handoff_map()
            else:
                logger.warning(f"Scenario '{scenario_name}' not found, using defaults")
                unified_agents = discover_agents()
        else:
            unified_agents = discover_agents()

        # Build handoff map
        scenario_handoffs = getattr(app.state, "scenario_handoff_map", None)
        if scenario_handoffs:
            handoff_map = scenario_handoffs.copy()
            agent_handoffs = build_handoff_map(unified_agents)
            for tool, agent in agent_handoffs.items():
                if tool not in handoff_map:
                    handoff_map[tool] = agent
        else:
            handoff_map = build_handoff_map(unified_agents)

        app.state.unified_agents = unified_agents
        app.state.handoff_map = handoff_map
        app.state.agent_summaries = build_agent_summaries(unified_agents)

        if not hasattr(app.state, "start_agent"):
            app.state.start_agent = "Concierge"

    manager.add_step("agents", start)


# ============================================================================
# Step 7: MCP Server Validation and Tool Registration
# ============================================================================


def register_mcp_servers_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the MCP server validation and tool discovery step (deferred).
    
    Validates that configured MCP servers are reachable,
    discovers their tools, and registers them in the central tool registry
    so agents can reference them by name.
    
    For EasyAuth-protected servers, acquires tokens using Managed Identity.
    
    Since this is a deferred step, MCP tool availability is not guaranteed
    immediately at startup. Required servers are still validated but failures
    are logged as errors rather than blocking startup.
    """
    import httpx
    from apps.artagent.backend.config.settings import (
        MCP_ENABLED_SERVERS,
        MCP_REQUIRED_SERVERS,
        MCP_SERVER_TIMEOUT,
        get_enabled_mcp_servers,
    )
    from apps.artagent.backend.registries.toolstore.mcp import (
        MCPClientSession,
        MCPServerConfig,
        MCPTransport,
    )
    from apps.artagent.backend.registries.toolstore.mcp.auth import (
        get_mcp_auth_headers,
    )
    from apps.artagent.backend.registries.toolstore.registry import (
        register_mcp_tool,
        unregister_mcp_tools,
    )

    # Initialize state so /ready endpoint can check before deferred task runs
    app.state.mcp_servers_status = {}
    app.state.mcp_ready = False

    async def start() -> None:
        if not MCP_ENABLED_SERVERS:
            logger.info("No MCP servers configured, skipping MCP validation")
            app.state.mcp_servers_status = {}
            app.state.mcp_ready = True
            return

        servers = get_enabled_mcp_servers()
        if not servers:
            logger.info("No MCP servers with valid URLs configured")
            app.state.mcp_servers_status = {}
            app.state.mcp_ready = True
            return

        logger.info(f"Validating {len(servers)} MCP server(s): {[s['name'] for s in servers]}")
        
        mcp_status: dict[str, dict] = {}
        total_tools_registered = 0
        
        for server in servers:
            name = server["name"]
            url = server["url"]
            transport = server.get("transport", "streamable-http")
            timeout = server.get("timeout", 30.0)
            auth_enabled = server.get("auth_enabled", False)
            app_id = server.get("app_id", "")
            
            # Get auth headers if server requires authentication
            auth_headers: dict[str, str] = {}
            if auth_enabled:
                if not app_id:
                    logger.error(f"MCP server '{name}' has auth enabled but no app_id configured")
                else:
                    auth_headers = await get_mcp_auth_headers(app_id)
                    if auth_headers:
                        logger.info(f"Acquired auth token for MCP server '{name}'")
                    else:
                        logger.warning(f"Failed to acquire auth token for MCP server '{name}'")
            
            # First check health endpoint
            # Strip /mcp suffix - health endpoints are at root /health, not /mcp/health
            base_url = url.rstrip("/")
            if base_url.endswith("/mcp"):
                base_url = base_url[:-4]
            health_url = f"{base_url}/health"
            is_healthy = False
            tools_count = 0
            tool_names: list[str] = []
            error_msg = None
            
            try:
                async with httpx.AsyncClient(timeout=MCP_SERVER_TIMEOUT) as client:
                    response = await client.get(health_url, headers=auth_headers)
                    is_healthy = response.status_code == 200
                    
                    if is_healthy:
                        try:
                            health_data = response.json()
                            tools_count = health_data.get("tools_count", 0)
                            tool_names = health_data.get("tool_names", [])
                        except Exception:
                            pass
                    else:
                        error_msg = f"HTTP {response.status_code}"
                        
            except httpx.ConnectError as e:
                error_msg = f"Connection failed: {e}"
                logger.warning(f"MCP server '{name}' unreachable at {url}: {e}")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"MCP server '{name}' health check failed: {e}")
            
            # If healthy, connect via MCP client to discover and register tools
            if is_healthy:
                try:
                    config = MCPServerConfig(
                        name=name,
                        url=url,
                        transport=MCPTransport(transport),
                        timeout=timeout,
                    )
                    session = MCPClientSession(config)
                    
                    if await session.connect():
                        # Discover tools from MCP server
                        discovered_tools = await session.list_tools()
                        tools_count = len(discovered_tools)
                        tool_names = [f"{name}_{t.name}" for t in discovered_tools]
                        
                        # Register each tool in the central registry
                        for tool_info in discovered_tools:
                            prefixed_name = f"{name}_{tool_info.name}"
                            original_name = tool_info.name
                            server_url = url
                            server_timeout = timeout
                            
                            # Create executor that calls the MCP server's HTTP tool endpoint
                            def make_executor(
                                tool_original_name: str,
                                tool_prefixed_name: str,
                                mcp_url: str,
                                mcp_timeout: float,
                                mcp_auth_enabled: bool,
                                mcp_app_id: str,
                            ):
                                async def executor(args: dict) -> dict:
                                    """Execute MCP tool via HTTP endpoint."""
                                    import httpx
                                    from apps.artagent.backend.registries.toolstore.mcp.auth import (
                                        get_mcp_auth_headers,
                                    )
                                    
                                    # Acquire fresh auth headers if needed
                                    exec_headers: dict[str, str] = {}
                                    if mcp_auth_enabled and mcp_app_id:
                                        exec_headers = await get_mcp_auth_headers(mcp_app_id)
                                        if not exec_headers:
                                            return {
                                                "success": False,
                                                "error": "Failed to acquire auth token for MCP server",
                                            }
                                    
                                    # Try the /tools/{tool_name} endpoint with GET params
                                    # Strip /mcp suffix - REST endpoints are at /tools/*, MCP protocol at /mcp
                                    base_url = mcp_url.rstrip("/")
                                    if base_url.endswith("/mcp"):
                                        base_url = base_url[:-4]
                                    tool_endpoint = f"{base_url}/tools/{tool_original_name}"
                                    
                                    try:
                                        async with httpx.AsyncClient(timeout=mcp_timeout) as client:
                                            # Most MCP tool endpoints use GET with query params
                                            response = await client.get(tool_endpoint, params=args, headers=exec_headers)
                                            
                                            if response.status_code == 200:
                                                data = response.json()
                                                # Return the result, handling both wrapped and direct responses
                                                if "result" in data:
                                                    return {"success": True, "result": data["result"]}
                                                return {"success": True, "result": data}
                                            else:
                                                return {
                                                    "success": False,
                                                    "error": f"MCP tool returned HTTP {response.status_code}: {response.text[:200]}",
                                                }
                                    except httpx.ConnectError as e:
                                        return {
                                            "success": False,
                                            "error": f"Failed to connect to MCP server: {e}",
                                        }
                                    except Exception as e:
                                        return {
                                            "success": False,
                                            "error": f"MCP tool execution failed: {e}",
                                        }
                                return executor
                            
                            executor = make_executor(
                                original_name,
                                prefixed_name,
                                server_url,
                                server_timeout,
                                auth_enabled,
                                app_id,
                            )
                            
                            schema = {
                                "name": prefixed_name,
                                "description": tool_info.description or f"MCP tool from {name}",
                                "parameters": tool_info.input_schema or {"type": "object", "properties": {}},
                            }
                            
                            register_mcp_tool(
                                name=prefixed_name,
                                schema=schema,
                                mcp_server=name,
                                mcp_transport=transport,
                                executor=executor,
                                override=True,
                            )
                            total_tools_registered += 1
                        
                        await session.disconnect()
                        logger.info(f"MCP server '{name}' healthy at {url}, registered {tools_count} tools: {tool_names}")
                    else:
                        error_msg = "MCP client connection failed"
                        is_healthy = False
                        logger.warning(f"MCP server '{name}' health OK but client connection failed")
                        
                except Exception as e:
                    error_msg = f"Tool discovery failed: {e}"
                    logger.error(f"MCP server '{name}' tool discovery failed: {e}")
            
            mcp_status[name] = {
                "status": "healthy" if is_healthy and not error_msg else "unhealthy",
                "url": url,
                "transport": transport,
                "tools_count": tools_count,
                "tool_names": tool_names,
                "error": error_msg,
            }

        # Store status for health endpoint
        app.state.mcp_servers_status = mcp_status
        
        if total_tools_registered > 0:
            logger.info(f"Registered {total_tools_registered} MCP tool(s) in central registry")

        # Check required servers (log errors but don't block since this is deferred)
        required_set = set(s.lower() for s in MCP_REQUIRED_SERVERS)
        mcp_all_required_healthy = True
        if required_set:
            for name, status in mcp_status.items():
                if name.lower() in required_set and status["status"] != "healthy":
                    mcp_all_required_healthy = False
                    logger.error(
                        f"Required MCP server '{name}' is not healthy: {status.get('error', 'unknown error')}. "
                        f"MCP tools from this server will be unavailable."
                    )
            if mcp_all_required_healthy:
                logger.info(f"All required MCP servers healthy: {list(required_set)}")

        app.state.mcp_ready = True

    manager.add_step("mcp", start, deferred=True)


# ============================================================================
# Step 8: Event Handlers
# ============================================================================


def register_event_handlers_step(manager: LifecycleManager, app: FastAPI) -> None:
    """Register the event handler initialization step."""
    from apps.artagent.backend.api.v1.events.registration import register_default_handlers
    from apps.artagent.backend.registries.toolstore.registry import (
        initialize_tools as initialize_unified_tools,
    )

    async def start() -> None:
        # Initialize tool registry
        try:
            initialize_unified_tools()
        except Exception as exc:
            logger.debug(f"Tool registry init skipped: {exc}")

        # Register ACS event handlers
        try:
            register_default_handlers()
        except Exception as exc:
            logger.debug(f"Event handler registration skipped: {exc}")

    manager.add_step("events", start)
