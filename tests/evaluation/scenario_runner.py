"""
Scenario Runner
===============

Runs evaluation scenarios from YAML files.

Design principles:
- Simple and focused - just load YAML and run turns
- Delegates to existing components (EventRecorder, Wrapper, Scorer)
- No duplication of orchestrator logic
- Supports both single scenarios and A/B comparisons

Azure AI Foundry Integration
----------------------------
Supports exporting evaluation results to Azure AI Foundry format via the
`foundry_export` configuration in scenario YAML:

```yaml
foundry_export:
  enabled: true
  evaluators:
    - id: builtin.relevance
      init_params:
        deployment_name: gpt-4o
    - id: builtin.coherence
  context_source: evidence
```
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# =============================================================================
# Early Bootstrap: Set up paths and load .env.local BEFORE any app imports
# This ensures AZURE_APPCONFIG_ENDPOINT is available for bootstrap_appconfig()
# =============================================================================

os.environ.setdefault("EVAL_USE_REAL_AOAI", "1")

_project_root = Path(__file__).resolve().parent.parent.parent
_backend_dir = _project_root / "apps" / "artagent" / "backend"

if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Load .env.local before any imports that depend on environment variables
_env_local = _project_root / ".env.local"
_env_file = _project_root / ".env"
try:
    from dotenv import load_dotenv
    if _env_local.exists():
        load_dotenv(_env_local, override=False)
    elif _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass

# =============================================================================
# Now safe to import app modules
# =============================================================================

import copy
import time
import json
from dataclasses import replace
from typing import Any

import yaml

from tests.evaluation.mocks import MockMemoManager
from tests.evaluation.recorder import EventRecorder
from tests.evaluation.schemas import (
    FoundryExportConfig,
    ModelProfile,
    RunSummary,
    SessionAgentConfig,
)
from tests.evaluation.scorer import MetricsScorer
from tests.evaluation.wrappers import EvaluationOrchestratorWrapper
from apps.artagent.backend.registries.agentstore.base import ModelConfig
from apps.artagent.backend.registries.agentstore.loader import (
    build_handoff_map,
    discover_agents,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    set_session_agent,
    remove_session_agent,
)
from apps.artagent.backend.voice.shared.base import OrchestratorContext
from apps.artagent.backend.voice.shared.config_resolver import (
    OrchestratorConfigResult,
    resolve_orchestrator_config,
)
from apps.artagent.backend.voice.speech_cascade.orchestrator import (
    CascadeOrchestratorAdapter,
)
from apps.artagent.backend.registries.scenariostore.loader import (
    ScenarioConfig,
    GenericHandoffConfig,
    HandoffConfig as ScenarioHandoffConfig,
)
from utils.ml_logging import get_logger


_runtime_bootstrapped = False


def _bootstrap_runtime() -> None:
    """Load env/App Config to mirror runtime defaults for evaluations."""

    global _runtime_bootstrapped
    if _runtime_bootstrapped:
        return

    try:
        from apps.artagent.backend.lifecycle import bootstrap as lifecycle_bootstrap
        from config.appconfig_provider import bootstrap_appconfig, get_provider_status
    except Exception as exc:  # noqa: BLE001 - keep evals running even if missing
        logger.warning("Bootstrap modules unavailable: %s", exc)
        _runtime_bootstrapped = True
        return

    try:
        env_file = lifecycle_bootstrap.load_environment()
        if env_file:
            logger.info("Environment loaded from %s", env_file)
    except Exception as exc:  # noqa: BLE001 - fallback to ambient env
        logger.warning("Environment load skipped: %s", exc)

    try:
        appconfig_loaded = bootstrap_appconfig()
        status = get_provider_status()
        loaded = appconfig_loaded and status.get("loaded", False)
        logger.info(
            "App Config status | enabled=%s loaded=%s endpoint=%s label=%s",
            status.get("enabled"),
            loaded,
            status.get("endpoint"),
            status.get("label"),
        )
    except Exception as exc:  # noqa: BLE001 - proceed with env vars only
        logger.warning("App Config load failed: %s", exc)

    _runtime_bootstrapped = True

logger = get_logger(__name__)


class _MockModel:
    """Minimal model holder used for extracting config in the wrapper."""

    def __init__(self, override: dict[str, Any] | None = None):
        override = override or {}
        self.deployment_id = override.get("deployment_id", "mock-eval-model")
        self.model_family = override.get("model_family")
        self.endpoint_preference = override.get("endpoint_preference", "chat")
        self.temperature = override.get("temperature")
        self.top_p = override.get("top_p")
        self.max_tokens = override.get("max_tokens")
        self.max_completion_tokens = override.get("max_completion_tokens")
        self.reasoning_effort = override.get("reasoning_effort")
        self.include_reasoning = override.get("include_reasoning")
        self.min_p = override.get("min_p")
        self.typical_p = override.get("typical_p")


class _MockAgent:
    """Lightweight agent container that exposes a model attribute."""

    def __init__(self, model: _MockModel):
        self.model = model


class _MockOrchestratorResult:
    """Return type compatible with the evaluation wrapper."""

    def __init__(self, response_text: str, response_tokens: int | None = None):
        self.response_text = response_text
        self.response_tokens = response_tokens
        self.input_tokens = None
        self.error: str | None = None


class _MockOrchestrator:
    """Async orchestrator stub that simulates tool calls from expectations."""

    def __init__(self, agent_name: str, model_override: dict[str, Any] | None):
        self._active_agent = agent_name
        self.agents = {agent_name: _MockAgent(_MockModel(model_override))}

    async def process_turn(
        self,
        context: Any,
        on_tts_chunk=None,
        on_tool_start=None,
        on_tool_end=None,
        **_: Any,
    ) -> _MockOrchestratorResult:
        expected_tools = context.metadata.get("expected_tools", [])

        for tool in expected_tools:
            if on_tool_start:
                await on_tool_start(tool, {"source": "expectations"})

            if on_tool_end:
                await on_tool_end(tool, {"status": "success"})

        response_text = f"[mock:{self._active_agent}] {context.user_text}"
        return _MockOrchestratorResult(
            response_text=response_text,
            response_tokens=len(response_text.split()),
        )


def _apply_model_override(agent: Any, override: dict[str, Any]) -> None:
    """DEPRECATED: Model overrides now handled via session state.

    This function is kept for backward compatibility but should not be used.
    Overrides are stored in memo_manager.corememory['eval_model_override'] and
    applied dynamically by the orchestrator during LLM requests.
    """
    pass  # No-op - overrides handled via session state


def _apply_model_override_to_all(
    agents: dict[str, Any], override: dict[str, Any]
) -> list[str]:
    """DEPRECATED: Model overrides now handled via session state.

    Returns empty list for backward compatibility.
    """
    return []


class ScenarioRunner:
    """
    Runs evaluation scenarios from YAML files.

    Handles:
    - Loading YAML scenario definitions
    - Setting up mock dependencies
    - Running multi-turn conversations
    - Delegating to EventRecorder for recording
    - Delegating to MetricsScorer for scoring
    """

    def __init__(
        self,
        scenario_path: Path,
        output_dir: Path | None = None,
    ):
        """
        Initialize scenario runner.

        Args:
            scenario_path: Path to YAML scenario file
            output_dir: Output directory for results (default: runs/)
        """
        _bootstrap_runtime()

        self.scenario_path = scenario_path
        self.scenario = self._load_scenario(scenario_path)
        self.output_dir = output_dir or Path("runs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_scenario(self, path: Path) -> dict[str, Any]:
        """Load and validate scenario YAML."""
        logger.info(f"Loading scenario from: {path}")

        with open(path, encoding="utf-8") as f:
            scenario = yaml.safe_load(f)

        # Basic validation - fall back to 'name' if 'scenario_name' not provided
        if "scenario_name" not in scenario:
            if "name" in scenario:
                scenario["scenario_name"] = scenario["name"]
            else:
                raise ValueError("Scenario must have 'scenario_name' or 'name' field")

        if "turns" not in scenario:
            # Check if this looks like an orchestration config rather than eval scenario
            if "agents" in scenario or "handoffs" in scenario:
                raise ValueError(
                    f"'{path.name}' appears to be an orchestration config, not an evaluation scenario. "
                    f"Evaluation scenarios require a 'turns' field with test cases. "
                    f"See tests/evaluation/scenarios/ for examples."
                )
            raise ValueError("Scenario must have 'turns' field with test cases")

        # Validate session_config if present
        if "session_config" in scenario:
            session_config = scenario["session_config"]
            if not isinstance(session_config, dict):
                raise ValueError("session_config must be a dictionary")
            if "start_agent" not in session_config:
                raise ValueError("session_config must have 'start_agent' field")

            # Log session_config details
            agents_spec = session_config.get("agents", "all")
            start_agent = session_config.get("start_agent")
            handoffs_count = len(session_config.get("handoffs", []))
            logger.info(
                f"Session-based scenario | agents={agents_spec} start={start_agent} handoffs={handoffs_count}"
            )

        logger.info(f"Loaded scenario: {scenario['scenario_name']}")

        # Phase 4: Expand template variables and generators in turns
        scenario = self._expand_turns(scenario)

        return scenario

    def _expand_turns(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Return scenario unchanged (template expansion removed for simplicity)."""
        return scenario

    def _normalize_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Convert legacy/template formats to normalized session_config format.

        Phase 2: Provides backward compatibility for legacy single-agent scenarios.

        Returns:
            Normalized scenario dict with session_config.
        """
        if "session_config" in scenario:
            return scenario  # Already normalized

        # Legacy single-agent format: { agent: "...", model_override: {...} }
        if "agent" in scenario:
            agent = scenario["agent"]
            normalized = {
                **scenario,
                "session_config": {
                    "agents": [agent],
                    "start_agent": agent,
                },
            }
            logger.info(f"Normalized legacy single-agent scenario: {agent}")
            return normalized

        return scenario

    def _create_orchestrator(
        self,
        agent_name: str,
        session_id: str,
        model_override: dict[str, Any] | None = None,
        scenario_name: str | None = None,
    ) -> tuple[Any, str]:
        """Create orchestrator with scenario-aware agent mapping; fallback to mock.

        Note: model_override is NOT applied here. It's stored in session state
        and read by the orchestrator at LLM request time.
        """

        # If agent is unknown, let resolver pick start_agent to avoid warnings
        start_override = agent_name if agent_name and agent_name != "unknown" else None

        config = resolve_orchestrator_config(
            session_id=session_id,
            scenario_name=scenario_name,
            start_agent=start_override,
        )

        agents = config.agents or discover_agents()
        if not agents:
            logger.warning("No agents discovered; falling back to mock orchestrator")
            return _MockOrchestrator(agent_name=agent_name, model_override=model_override), agent_name

        start_agent = config.start_agent or start_override or next(iter(agents.keys()))
        if start_agent not in agents:
            logger.warning("Agent '%s' not found; using first available agent", start_agent)
            start_agent = next(iter(agents.keys()))

        handoff_map = config.handoff_map or build_handoff_map(agents)

        # Log what model WOULD be used without override (for debugging)
        default_deployment = "unknown"
        if hasattr(agents.get(start_agent), "get_model_for_mode"):
            try:
                default_model = agents[start_agent].get_model_for_mode("cascade")
                default_deployment = getattr(default_model, "deployment_id", "unknown")
            except Exception:
                pass

        override_deployment = model_override.get("deployment_id") if model_override else None
        logger.info(
            "Creating CascadeOrchestratorAdapter | start_agent=%s default_model=%s override=%s scenario=%s",
            start_agent,
            default_deployment,
            override_deployment or "(none)",
            config.scenario_name,
        )

        adapter = CascadeOrchestratorAdapter.create(
            start_agent=start_agent,
            session_id=session_id,
            agents=agents,
            handoff_map=handoff_map,
            streaming=False,
        )

        return adapter, start_agent

    def _create_orchestrator_with_overrides(
        self,
        agent_name: str,
        session_id: str,
        model_override: dict[str, Any] | None = None,
        agent_overrides: list[dict[str, Any]] | None = None,
        scenario_name: str | None = None,
    ) -> tuple[Any, str]:
        """
        Create orchestrator with session-scoped agent overrides.

        This uses the agent_builder pattern: creates modified agent copies
        and stores them in the session registry. The orchestrator then
        naturally picks them up via get_session_agent().
        """
        # If agent is unknown, let resolver pick start_agent to avoid warnings
        start_override = agent_name if agent_name and agent_name != "unknown" else None

        config = resolve_orchestrator_config(
            session_id=session_id,
            scenario_name=scenario_name,
            start_agent=start_override,
        )

        base_agents = config.agents or discover_agents()
        if not base_agents:
            logger.warning("No agents discovered; falling back to mock orchestrator")
            return _MockOrchestrator(agent_name=agent_name, model_override=model_override), agent_name

        # Create session-scoped agents with model overrides applied
        # This stores them in the session registry for the orchestrator to pick up
        agents = self._create_session_agents_with_overrides(
            session_id, agent_overrides or [], base_agents
        )

        start_agent = config.start_agent or start_override or next(iter(agents.keys()))
        if start_agent not in agents:
            logger.warning("Agent '%s' not found; using first available agent", start_agent)
            start_agent = next(iter(agents.keys()))

        handoff_map = config.handoff_map or build_handoff_map(agents)

        # Log what model will be used (after override)
        actual_deployment = "unknown"
        if hasattr(agents.get(start_agent), "get_model_for_mode"):
            try:
                actual_model = agents[start_agent].get_model_for_mode("cascade")
                actual_deployment = getattr(actual_model, "deployment_id", "unknown")
            except Exception:
                pass

        logger.info(
            "Creating CascadeOrchestratorAdapter with overrides | start_agent=%s model=%s scenario=%s overrides=%d",
            start_agent,
            actual_deployment,
            config.scenario_name,
            len(agent_overrides or []),
        )

        adapter = CascadeOrchestratorAdapter.create(
            start_agent=start_agent,
            session_id=session_id,
            agents=agents,
            handoff_map=handoff_map,
            streaming=False,
        )

        return adapter, start_agent

    def _create_session_agents_with_overrides(
        self,
        session_id: str,
        agent_overrides: list[dict[str, Any]],
        base_agents: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create session-scoped agent copies with model overrides applied.

        Uses the same mechanism as agent_builder to store per-session agent configs.
        The orchestrator will automatically pick these up via get_session_agent().

        Args:
            session_id: The evaluation session ID
            agent_overrides: List of {agent: name, model_override: {...}} dicts
            base_agents: The discovered agents dict to clone from

        Returns:
            Modified agents dict with overrides applied (also stored in session registry)
        """
        if not agent_overrides:
            return base_agents

        # Create a copy of agents dict so we can modify it
        modified_agents = dict(base_agents)

        for entry in agent_overrides:
            agent_name = entry.get("agent")
            override = entry.get("model_override")

            if not agent_name or not override:
                continue

            if agent_name not in base_agents:
                logger.warning(
                    "Agent '%s' not found in discovered agents; skipping override",
                    agent_name,
                )
                continue

            base_agent = base_agents[agent_name]

            # Create ModelConfig from override dict
            override_model = ModelConfig.from_dict(override)

            # Create a modified copy of the agent with overridden cascade_model
            # Using dataclasses.replace() for immutable update
            modified_agent = replace(
                base_agent,
                model=override_model,
                cascade_model=override_model,
                # Preserve existing metadata but add eval context
                metadata={
                    **base_agent.metadata,
                    "eval_override": True,
                    "eval_session_id": session_id,
                    "original_model": base_agent.cascade_model.deployment_id if base_agent.cascade_model else None,
                },
            )

            # Store in session registry - orchestrator will pick this up
            set_session_agent(session_id, modified_agent)

            # Also update our local agents dict for the orchestrator creation
            modified_agents[agent_name] = modified_agent

            logger.info(
                "Created session agent with override | session=%s agent=%s model=%s->%s",
                session_id,
                agent_name,
                base_agent.cascade_model.deployment_id if base_agent.cascade_model else "unknown",
                override_model.deployment_id,
            )

        return modified_agents

    def _create_orchestrator_from_session_config(
        self,
        session_config: SessionAgentConfig,
        session_id: str,
        agent_overrides: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, str]:
        """
        Create orchestrator using session_config like scenariostore orchestrator.yml.

        This allows evaluation scenarios to define their own agent list, handoffs,
        and routing without needing a pre-defined scenario in scenariostore.

        Args:
            session_config: SessionAgentConfig with agents, start_agent, handoffs
            session_id: The evaluation session ID
            agent_overrides: Optional model overrides for specific agents

        Returns:
            Tuple of (orchestrator, start_agent_name)
        """
        # Discover all available agents
        all_agents = discover_agents()
        if not all_agents:
            logger.warning("No agents discovered; falling back to mock orchestrator")
            return _MockOrchestrator(
                agent_name=session_config.start_agent,
                model_override=None,
            ), session_config.start_agent

        # Filter agents based on session_config
        agent_list = session_config.get_agent_list(all_agents)
        if not agent_list:
            logger.warning(
                "Session config filtered all agents; using all discovered agents"
            )
            agent_list = list(all_agents.keys())

        logger.info(
            "Session-based scenario | agents=%s start=%s handoffs=%d",
            agent_list,
            session_config.start_agent,
            len(session_config.handoffs),
        )

        # Filter to just the agents we need
        filtered_agents = {k: v for k, v in all_agents.items() if k in agent_list}

        # Apply model overrides if provided
        if agent_overrides:
            filtered_agents = self._create_session_agents_with_overrides(
                session_id, agent_overrides, filtered_agents
            )

        # Validate start agent
        start_agent = session_config.start_agent
        if start_agent not in filtered_agents:
            logger.warning(
                "start_agent '%s' not in filtered agents; using first available",
                start_agent,
            )
            start_agent = agent_list[0] if agent_list else next(iter(filtered_agents.keys()))

        # Build handoff map from session_config handoffs
        handoff_map: dict[str, str] = {}
        for h in session_config.handoffs:
            if h.tool and h.to_agent:
                handoff_map[h.tool] = h.to_agent

        # Also build from agent declarations (handoff.trigger) for agents in our list
        for agent_name, agent in filtered_agents.items():
            if hasattr(agent, "handoff") and hasattr(agent.handoff, "trigger"):
                trigger = agent.handoff.trigger
                if trigger and trigger not in handoff_map:
                    handoff_map[trigger] = agent_name

        # If generic_handoff enabled, ensure handoff_to_agent is available
        generic_config = session_config.generic_handoff or {}
        if generic_config.get("enabled", False):
            # The handoff_to_agent tool handles routing dynamically
            # We just need to ensure all agents are reachable
            logger.info(
                "Generic handoff enabled | allowed_targets=%s",
                generic_config.get("allowed_targets", "(all)"),
            )

        logger.info(
            "Creating CascadeOrchestratorAdapter from session_config | "
            "start=%s agents=%d handoff_routes=%d",
            start_agent,
            len(filtered_agents),
            len(handoff_map),
        )

        adapter = CascadeOrchestratorAdapter.create(
            start_agent=start_agent,
            session_id=session_id,
            agents=filtered_agents,
            handoff_map=handoff_map,
            streaming=False,
        )

        # NOTE: ScenarioConfig injection temporarily disabled to debug empty responses
        # TODO: Re-enable once root cause is found
        # Build ScenarioConfig from session_config for HandoffService
        # This enables generic handoffs in evaluation scenarios
        # scenario_handoffs = []
        # for h in session_config.handoffs:
        #     scenario_handoffs.append(ScenarioHandoffConfig(
        #         from_agent=h.from_agent,
        #         to_agent=h.to_agent,
        #         tool=h.tool,
        #         type=h.type or "announced",
        #         share_context=h.share_context if h.share_context is not None else True,
        #     ))

        # generic_cfg = GenericHandoffConfig(
        #     enabled=generic_config.get("enabled", False),
        #     allowed_targets=generic_config.get("allowed_targets", []),
        #     default_type=generic_config.get("default_type", "announced"),
        #     share_context=generic_config.get("share_context", True),
        # )

        # scenario_obj = ScenarioConfig(
        #     name=f"eval_{session_id}",
        #     agents=list(filtered_agents.keys()),
        #     start_agent=start_agent,
        #     handoff_type=session_config.handoff_type or "announced",
        #     handoffs=scenario_handoffs,
        #     generic_handoff=generic_cfg,
        # )

        # Inject cached config so HandoffService uses our scenario
        # adapter._cached_orchestrator_config = OrchestratorConfigResult(
        #     start_agent=start_agent,
        #     agents=filtered_agents,
        #     handoff_map=handoff_map,
        #     scenario=scenario_obj,
        #     scenario_name=f"eval_{session_id}",
        # )

        return adapter, start_agent

    async def run(self) -> RunSummary:
        """
        Run the scenario and return summary.

        Supports three scenario types:
        1. scenario_template - References a scenariostore orchestration config
        2. session_config - Inline orchestration config (like orchestrator.yml)
        3. Legacy - Simple agent + model_override for single-agent scenarios

        Returns:
            RunSummary with aggregated metrics
        """
        scenario_name = self.scenario["scenario_name"]
        scenario_template = self.scenario.get("scenario_template")
        session_config_data = self.scenario.get("session_config")
        agent_name = self.scenario.get("agent", "unknown")

        logger.info(f"Running scenario: {scenario_name}")

        # Create mock dependencies
        session_id = self.scenario.get("metadata", {}).get("session_id", f"eval_{scenario_name}")
        context_vars = self.scenario.get("metadata", {}).get("context", {})
        memo_manager = MockMemoManager(session_id, context_vars)
        if scenario_template:
            memo_manager.set_value_in_corememory("scenario_name", scenario_template)

        # Get agent overrides from scenario
        agent_overrides = self.scenario.get("agent_overrides", [])

        # For backward compat, extract first override as the "primary" for metadata
        model_override = None
        if agent_overrides:
            model_override = agent_overrides[0].get("model_override")
        else:
            # Legacy: single model_override for all agents
            model_override = self.scenario.get("model_override")

        # Create recorder
        run_id = f"{scenario_name}_{int(time.time())}"
        recorder = EventRecorder(run_id=run_id, output_dir=self.output_dir)

        # Determine which orchestrator creation method to use
        if session_config_data:
            # New: Session-based scenario with inline orchestration config
            logger.info("Using session_config for orchestrator creation")
            try:
                session_config = SessionAgentConfig.model_validate(session_config_data)
            except Exception as e:
                logger.error(f"Invalid session_config: {e}")
                raise ValueError(f"Invalid session_config in scenario: {e}") from e

            orchestrator, start_agent = self._create_orchestrator_from_session_config(
                session_config,
                session_id,
                agent_overrides,
            )
            # Store session_config name for context
            memo_manager.set_value_in_corememory("session_config", True)
        else:
            # Existing: Use scenario_template or legacy approach
            orchestrator, start_agent = self._create_orchestrator_with_overrides(
                agent_name,
                session_id,
                model_override,
                agent_overrides,
                scenario_name=scenario_template,
            )

        # Ensure we track the resolved start agent for histories/context
        agent_name = start_agent
        use_mock = isinstance(orchestrator, _MockOrchestrator)

        eval_orchestrator = EvaluationOrchestratorWrapper(
            orchestrator=orchestrator,
            recorder=recorder,
        )

        # Run turns
        for turn_data in self.scenario["turns"]:
            turn_id = turn_data["turn_id"]
            user_input = turn_data["user_input"]
            turn_expectations = turn_data.get("expectations", {})
            expected_tools = turn_expectations.get("tools_called", [])

            logger.info(f"Turn {turn_id}: {user_input[:50]}...")

            # Build context with memo_manager
            context = OrchestratorContext(
                session_id=session_id,
                user_text=user_input,
                turn_id=turn_id,
                conversation_history=memo_manager.get_history(agent_name),
                metadata={
                    "memo_manager": memo_manager,
                    "scenario_name": scenario_name,
                    "scenario_template": scenario_template,
                    "model_override": model_override,
                    "run_id": f"{scenario_name}:{turn_id}",
                    "turn_id": turn_id,
                    "expected_tools": expected_tools,
                    **context_vars,
                },
            )

            # Run turn (this will be recorded automatically)
            result = await eval_orchestrator.process_turn(context)

            # Update mock history if we aren't using the real orchestrator
            if use_mock:
                memo_manager.append_to_history(agent_name, "user", user_input)
                memo_manager.append_to_history(agent_name, "assistant", result.response_text)

            logger.info(f"Turn {turn_id} complete: {len(result.response_text)} chars")

        # Clean up session agents after run
        remove_session_agent(session_id)

        # Score the results
        scorer = MetricsScorer()
        events = scorer.load_events(self.output_dir / f"{run_id}_events.jsonl")

        summary = scorer.generate_summary(
            events,
            scenario_name=scenario_name,
            expectations=self.scenario,
        )

        # Save summary
        summary_path = self.output_dir / run_id / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary.model_dump_json(indent=2))

        # Persist a lightweight session manifest for replay/reference
        session_manifest = {
            "run_id": run_id,
            "scenario_name": scenario_name,
            "scenario_template": scenario_template,
            "agent": agent_name,
            "variant_id": self.scenario.get("metadata", {}).get("variant_id"),
            "model_override": model_override,
            "events_path": str(self.output_dir / f"{run_id}_events.jsonl"),
            "summary_path": str(summary_path),
        }
        manifest_path = summary_path.parent / "session.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(session_manifest, mf, indent=2)

        # Export to Azure AI Foundry format if configured
        foundry_paths = self._export_to_foundry(
            events=events,
            run_id=run_id,
            summary_path=summary_path,
        )
        if foundry_paths:
            session_manifest["foundry_data_path"] = str(foundry_paths.get("data"))
            if "config" in foundry_paths:
                session_manifest["foundry_config_path"] = str(foundry_paths.get("config"))
            # Update manifest with foundry paths
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(session_manifest, mf, indent=2)

        logger.info(f"Scenario complete! Summary: {summary_path}")

        return summary

    def _export_to_foundry(
        self,
        events: list,
        run_id: str,
        summary_path: Path,
    ) -> dict[str, Path] | None:
        """
        Export evaluation results to Azure AI Foundry format if configured.

        Args:
            events: List of TurnEvent objects
            run_id: Run identifier
            summary_path: Path to summary (for output directory)

        Returns:
            Dict of paths if export enabled, None otherwise
        """
        foundry_config = self.scenario.get("foundry_export")
        if not foundry_config:
            return None

        # Parse config
        try:
            export_config = FoundryExportConfig.model_validate(foundry_config)
        except Exception as e:
            logger.warning(f"Invalid foundry_export config: {e}")
            return None

        if not export_config.enabled:
            return None

        # Import exporter (lazy to avoid circular imports)
        from tests.evaluation.foundry_exporter import export_for_foundry

        output_dir = summary_path.parent
        foundry_paths = export_for_foundry(
            events=events,
            output_dir=output_dir,
            config=export_config,
            expectations=self.scenario,
        )

        logger.info(
            f"Foundry export complete | data={foundry_paths.get('data')} "
            f"config={foundry_paths.get('config')}"
        )

        return foundry_paths


class ComparisonRunner:
    """
    Runs A/B comparison scenarios.

    Handles scenarios with multiple variants (e.g., comparing GPT-4o vs o1).
    """

    def __init__(
        self,
        comparison_path: Path,
        output_dir: Path | None = None,
    ):
        """
        Initialize comparison runner.

        Args:
            comparison_path: Path to comparison YAML file
            output_dir: Output directory for results
        """
        self.comparison_path = comparison_path
        self.comparison = self._load_comparison(comparison_path)
        self.output_dir = output_dir or Path("runs")

    def _load_comparison(self, path: Path) -> dict[str, Any]:
        """Load and validate comparison YAML."""
        logger.info(f"Loading comparison from: {path}")

        with open(path, encoding="utf-8") as f:
            comparison = yaml.safe_load(f)

        # Validate
        if "comparison_name" not in comparison:
            raise ValueError("Comparison must have 'comparison_name' field")

        if "variants" not in comparison:
            raise ValueError("Comparison must have 'variants' field")

        if len(comparison["variants"]) < 2:
            raise ValueError("Comparison must have at least 2 variants")

        logger.info(f"Loaded comparison: {comparison['comparison_name']}")
        return comparison

    def _resolve_model_profiles(
        self,
        variant: dict[str, Any],
        profiles: dict[str, dict[str, Any]],
        agent_names: list[str],
    ) -> list[dict[str, Any]]:
        """
        Resolve model_profile to agent_overrides for DRY configuration.

        If variant specifies a model_profile, it applies to ALL agents in agent_names.
        Per-agent overrides in agent_overrides merge on top of the profile.

        Example:
            model_profiles:
              gpt4o_fast:
                deployment_id: gpt-4o
                temperature: 0.6

            variants:
              - variant_id: baseline
                model_profile: gpt4o_fast
                agent_overrides:
                  - agent: CardRecommendation
                    model_override:
                      temperature: 0.3  # Override just this field

        Args:
            variant: Variant dict with optional model_profile and agent_overrides
            profiles: Dict of profile_name -> ModelProfile config dict
            agent_names: List of agent names to apply profile to

        Returns:
            List of {agent: name, model_override: config} dicts
        """
        # If variant already has agent_overrides without model_profile, return as-is
        existing_overrides = variant.get("agent_overrides", [])
        profile_name = variant.get("model_profile")

        if not profile_name:
            return existing_overrides

        # Validate profile exists
        if profile_name not in profiles:
            logger.warning(
                "model_profile '%s' not found in model_profiles; using existing overrides",
                profile_name,
            )
            return existing_overrides

        # Parse profile into ModelProfile for validation
        try:
            profile = ModelProfile.model_validate(profiles[profile_name])
            base_config = profile.to_override_dict()
        except Exception as e:
            logger.warning("Invalid model_profile '%s': %s", profile_name, e)
            return existing_overrides

        # Build override map from existing agent_overrides (for merging)
        override_map: dict[str, dict[str, Any]] = {}
        for entry in existing_overrides:
            agent = entry.get("agent")
            if agent:
                override_map[agent] = entry.get("model_override", {})

        # Generate overrides for all agents
        resolved = []
        for agent_name in agent_names:
            # Start with profile config
            agent_config = dict(base_config)

            # Merge per-agent overrides if present
            if agent_name in override_map:
                agent_config.update(override_map[agent_name])

            resolved.append({"agent": agent_name, "model_override": agent_config})

        logger.info(
            "Resolved model_profile '%s' for %d agents (variant: %s)",
            profile_name,
            len(resolved),
            variant.get("variant_id", "unknown"),
        )

        return resolved

    async def run(self) -> dict[str, RunSummary]:
        """
        Run all variants and compare.

        Returns:
            Dict mapping variant_id -> RunSummary
        """
        comparison_name = self.comparison["comparison_name"]
        logger.info(f"Running comparison: {comparison_name}")

        # Create output directory for this comparison
        comparison_dir = self.output_dir / comparison_name
        comparison_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # Get model_profiles for DRY configuration (Phase 1 refactor)
        model_profiles = self.comparison.get("model_profiles", {})
        if model_profiles:
            logger.info(f"Found {len(model_profiles)} model_profiles: {list(model_profiles.keys())}")

        # Determine agent list for profile resolution
        # Priority: session_config.agents > scenario_template agents > discover_agents
        session_config_data = self.comparison.get("session_config")
        scenario_template = self.comparison.get("scenario_template")
        agent_names: list[str] = []

        if session_config_data:
            # Get agents from session_config
            all_agents = discover_agents()
            try:
                session_config = SessionAgentConfig.model_validate(session_config_data)
                agent_names = session_config.get_agent_list(all_agents)
            except Exception as e:
                logger.warning("Failed to parse session_config: %s", e)
        
        if not agent_names:
            # Fallback: discover all available agents
            all_agents = discover_agents()
            agent_names = list(all_agents.keys())

        logger.info(f"Agent list for profile resolution: {agent_names}")

        # Run each variant
        for variant in self.comparison["variants"]:
            variant_id = variant["variant_id"]
            logger.info(f"Running variant: {variant_id}")

            # Build scenario for this variant
            metadata = self.comparison.get("metadata", {}).copy()
            metadata["variant_id"] = variant_id

            # Phase 1 refactor: Resolve model_profile to agent_overrides
            if model_profiles and variant.get("model_profile"):
                agent_overrides = self._resolve_model_profiles(variant, model_profiles, agent_names)
            else:
                # Support both legacy single model_override and new agent_overrides format
                agent_overrides = variant.get("agent_overrides", [])
                legacy_override = variant.get("model_override")
                legacy_agent = variant.get("agent")

                # Convert legacy format to agent_overrides if needed
                if not agent_overrides and legacy_override and legacy_agent:
                    agent_overrides = [{"agent": legacy_agent, "model_override": legacy_override}]

            legacy_agent = variant.get("agent")

            # Get foundry export config from comparison or variant
            foundry_export = variant.get("foundry_export") or self.comparison.get("foundry_export")

            scenario = {
                "scenario_name": f"{comparison_name}_{variant_id}",
                "scenario_template": self.comparison.get("scenario_template"),
                "agent": legacy_agent,  # Start agent (optional)
                "agent_overrides": agent_overrides,
                "turns": self.comparison["turns"],
                "metadata": metadata,
                "foundry_export": foundry_export,
            }

            # Create temporary scenario file
            scenario_path = comparison_dir / f"{variant_id}_scenario.yaml"
            with open(scenario_path, "w", encoding="utf-8") as f:
                yaml.dump(scenario, f)

            # Run scenario
            runner = ScenarioRunner(
                scenario_path=scenario_path,
                output_dir=comparison_dir / variant_id,
            )

            summary = await runner.run()
            results[variant_id] = summary

            logger.info(f"Variant {variant_id} complete")

        # Compare results
        logger.info("Comparing variants...")
        self._compare_variants(results, comparison_dir)

        return results

    def _compare_variants(
        self,
        results: dict[str, RunSummary],
        output_dir: Path,
    ):
        """
        Compare variant results and save comparison report.

        Args:
            results: Dict of variant_id -> RunSummary
            output_dir: Directory to save comparison
        """
        comparison_metrics = self.comparison.get("comparison_metrics", [])

        # Build comparison report
        report = {
            "comparison_name": self.comparison["comparison_name"],
            "variants": {},
            "comparison": {},
        }

        # Extract metrics for each variant
        for variant_id, summary in results.items():
            # Get model breakdown from cost analysis for per-agent models
            model_breakdown = summary.cost_analysis.get("model_breakdown", {})
            models_used = list(model_breakdown.keys()) if model_breakdown else []
            primary_model = (
                summary.eval_model_config.model_name
                if summary.eval_model_config
                else models_used[0] if models_used else "unknown"
            )

            # Build per-turn details
            per_turn_details = []
            for turn_metric in summary.per_turn_metrics:
                per_turn_details.append({
                    "turn_id": turn_metric.turn_id,
                    "agent": turn_metric.agent_name,
                    "model": turn_metric.model_used,
                    "e2e_ms": turn_metric.e2e_ms,
                    "tools_expected": turn_metric.tools_expected,
                    "tools_called": turn_metric.tools_called,
                    "precision": turn_metric.tool_precision,
                    "recall": turn_metric.tool_recall,
                    "grounded": turn_metric.grounded_span_ratio,
                    "response_len": turn_metric.response_length,
                    "error": turn_metric.error,
                })

            report["variants"][variant_id] = {
                "model_config": (
                    summary.eval_model_config.model_dump()
                    if summary.eval_model_config
                    else {"model_name": "unknown"}
                ),
                "models_used": models_used,
                "primary_model": primary_model,
                "metrics": {
                    "tool_precision": summary.tool_metrics.get("precision", 0),
                    "tool_recall": summary.tool_metrics.get("recall", 0),
                    "tool_efficiency": summary.tool_metrics.get("efficiency", 0),
                    "latency_p95_ms": summary.latency_metrics.get("e2e_p95_ms", 0),
                    "latency_p50_ms": summary.latency_metrics.get("e2e_p50_ms", 0),
                    "grounded_span_ratio": summary.groundedness_metrics.get(
                        "avg_grounded_span_ratio", 0
                    ),
                    "cost_per_turn_usd": (
                        summary.cost_analysis.get("estimated_cost_usd", 0)
                        / summary.total_turns
                        if summary.total_turns > 0
                        else 0
                    ),
                },
                "per_turn": per_turn_details,
                "per_agent_costs": model_breakdown,
                "total_turns": summary.total_turns,
            }

        # Determine winners for each metric
        if comparison_metrics:
            for metric in comparison_metrics:
                values = {
                    vid: report["variants"][vid]["metrics"].get(metric, 0)
                    for vid in results.keys()
                }

                # Lower is better for latency and cost
                if "latency" in metric or "cost" in metric:
                    winner = min(values.keys(), key=lambda k: values[k])
                else:
                    winner = max(values.keys(), key=lambda k: values[k])

                report["comparison"][f"winner_{metric}"] = winner

        # Save comparison report
        comparison_path = output_dir / "comparison.json"
        with open(comparison_path, "w", encoding="utf-8") as f:
            import json
            json.dump(report, f, indent=2)

        logger.info(f"Comparison report saved: {comparison_path}")

        # Print summary
        print("\n" + "=" * 70)
        print(f"📊 COMPARISON: {self.comparison['comparison_name']}")
        print("=" * 70)

        for variant_id, data in report["variants"].items():
            models_used = data.get("models_used", [])
            primary = data.get("primary_model", "unknown")
            turns = data.get("total_turns", 0)

            print(f"\n▶ {variant_id}:")
            print(f"  Primary Model: {primary}")
            if len(models_used) > 1:
                print(f"  All models: {', '.join(models_used)}")

            # Per-turn breakdown with expected vs actual tools
            print(f"\n  Per-turn metrics:")
            for turn in data.get("per_turn", []):
                turn_id_short = turn["turn_id"].split(":")[-1] if ":" in turn["turn_id"] else turn["turn_id"]
                error_flag = " ❌" if turn.get("error") else ""
                
                # Show expected vs actual tools
                expected = turn.get("tools_expected", [])
                actual = turn.get("tools_called", [])
                
                # Calculate match status
                expected_set = set(expected)
                actual_set = set(actual)
                matched = expected_set & actual_set
                missed = expected_set - actual_set
                extra = actual_set - expected_set
                
                # Build tools display
                if expected:
                    match_icon = "✓" if matched == expected_set else "⚠"
                    expected_str = ", ".join(expected)
                    actual_str = ", ".join(actual) if actual else "(none)"
                    tools_display = f"expected=[{expected_str}] actual=[{actual_str}] {match_icon}"
                else:
                    actual_str = ", ".join(actual) if actual else "(none)"
                    tools_display = f"tools=[{actual_str}]"
                
                print(
                    f"    {turn_id_short}: {turn['agent']} | {turn['e2e_ms']:.0f}ms | {tools_display}{error_flag}"
                )

            # Aggregated metrics
            print(f"\n  Aggregated:")
            print(f"    Turns: {turns}")
            print(f"    Precision: {data['metrics']['tool_precision']:.2%}")
            print(f"    Recall: {data['metrics']['tool_recall']:.2%}")
            print(f"    Grounded: {data['metrics']['grounded_span_ratio']:.2%}")
            print(f"    Latency P50/P95: {data['metrics']['latency_p50_ms']:.0f}ms / {data['metrics']['latency_p95_ms']:.0f}ms")
            print(f"    Cost/turn: ${data['metrics']['cost_per_turn_usd']:.4f}")

        if report["comparison"]:
            print("\n🏆 Winners:")
            for metric, winner in report["comparison"].items():
                print(f"  {metric}: {winner}")

        # Print generated file location (just the comparison report)
        print(f"\n📁 Results: {comparison_path}")
        print("=" * 70 + "\n")


__all__ = [
    "ScenarioRunner",
    "ComparisonRunner",
]


if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    parser = argparse.ArgumentParser(
        description="Run evaluation scenarios or A/B comparisons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single scenario
  python -m tests.evaluation.scenario_runner scenario.yaml

  # Run an A/B comparison
  python -m tests.evaluation.scenario_runner comparison.yaml --comparison

  # Custom output directory
  python -m tests.evaluation.scenario_runner scenario.yaml -o runs/my_test
        """,
    )

    parser.add_argument(
        "scenario_path",
        type=Path,
        help="Path to scenario or comparison YAML file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("runs"),
        help="Output directory for results (default: runs/)",
    )
    parser.add_argument(
        "-c", "--comparison",
        action="store_true",
        help="Run as A/B comparison (auto-detected from YAML if has 'variants')",
    )

    args = parser.parse_args()

    if not args.scenario_path.exists():
        logger.error(f"Scenario file not found: {args.scenario_path}")
        sys.exit(1)

    # Auto-detect comparison vs single scenario
    with open(args.scenario_path, encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)

    is_comparison = args.comparison or "variants" in scenario_data

    async def main():
        if is_comparison:
            runner = ComparisonRunner(
                comparison_path=args.scenario_path,
                output_dir=args.output,
            )
            await runner.run()
        else:
            runner = ScenarioRunner(
                scenario_path=args.scenario_path,
                output_dir=args.output,
            )
            await runner.run()

    asyncio.run(main())
