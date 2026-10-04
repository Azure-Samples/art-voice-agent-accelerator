"""Complete, session-scoped scenario edits and discovery for Quick Tune."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from apps.artagent.backend.api.v1.endpoints import scenario_builder as api
from apps.artagent.backend.api.v1.schemas.scenario_builder import (
    DynamicScenarioConfig,
    ScenarioDraft,
    ScenarioGenerateRequest,
)
from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
from apps.artagent.backend.registries.scenariostore.loader import AgentOverride, ScenarioConfig
from apps.artagent.backend.registries.toolstore.registry import ToolDefinition
from apps.artagent.backend.src.orchestration import session_scenarios
from fastapi import HTTPException
from starlette.requests import Request


@pytest.fixture
def scenario():
    return ScenarioConfig(
        name="Banking",
        description="Original purpose",
        icon="B",
        agents=["Concierge"],
        start_agent="Concierge",
        tools=["check_balance"],
        global_template_vars={"company_name": "Northwind", "enabled": False, "limit": 0},
        agent_defaults=AgentOverride(voice_rate="-5%", template_vars={"policy": {"days": 14}}),
    )


@pytest.mark.asyncio
async def test_named_read_is_session_scoped_and_preserves_the_complete_config(
    monkeypatch, scenario
):
    lookup = Mock(return_value=scenario)
    monkeypatch.setattr(api, "get_session_scenario", lookup)
    result = await api.get_session_scenario_config(
        "session-a", Request({"type": "http"}), scenario_name="Banking"
    )
    lookup.assert_called_once_with("session-a", "Banking")
    assert result.config["tools"] == ["check_balance"]
    assert result.config["agent_defaults"]["template_vars"] == {"policy": {"days": 14}}
    assert result.config["global_template_vars"]["enabled"] is False
    assert result.config["global_template_vars"]["limit"] == 0


@pytest.mark.asyncio
async def test_missing_named_scenario_does_not_fall_back_to_the_active_one(monkeypatch):
    monkeypatch.setattr(api, "get_session_scenario", Mock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await api.get_session_scenario_config(
            "session-a", Request({"type": "http"}), scenario_name="NotHere"
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_listing_uses_session_edits_instead_of_reloading_builtin_defaults(
    monkeypatch, scenario
):
    updated = copy.deepcopy(scenario)
    updated.description = "Session-specific purpose"
    updated.global_template_vars["company_name"] = "Contoso"
    monkeypatch.setattr(api, "list_scenarios", lambda: ["banking_pack"])
    monkeypatch.setattr(api, "load_scenario", lambda _: scenario)
    monkeypatch.setattr(api, "list_session_scenarios_by_session", lambda _: {"banking": updated})
    monkeypatch.setattr(session_scenarios, "get_active_scenario_name", lambda _: "banking")
    result = await api.list_scenarios_for_session("session-a", Request({"type": "http"}))
    assert result["total"] == 1
    assert result["custom_scenarios"] == []
    entry = result["builtin_scenarios"][0]
    assert entry["id"] == "banking_pack"
    assert entry["is_session_override"] is True
    assert entry["description"] == "Session-specific purpose"
    assert entry["global_template_vars"]["company_name"] == "Contoso"
    assert entry["tools"] == ["check_balance"]
    assert entry["agent_defaults"]["voice_rate"] == "-5%"
    assert scenario.description == "Original purpose"
    assert scenario.global_template_vars["company_name"] == "Northwind"


@pytest.mark.asyncio
async def test_unedited_builtin_and_custom_listings_include_defaults_and_tools(
    monkeypatch, scenario
):
    custom = copy.deepcopy(scenario)
    custom.name = "CustomScenario"
    monkeypatch.setattr(api, "list_scenarios", lambda: ["banking"])
    monkeypatch.setattr(api, "load_scenario", lambda _: scenario)
    monkeypatch.setattr(
        api, "list_session_scenarios_by_session", lambda _: {"customscenario": custom}
    )
    monkeypatch.setattr(session_scenarios, "get_active_scenario_name", lambda _: "customscenario")
    result = await api.list_scenarios_for_session("session-a", Request({"type": "http"}))
    assert result["builtin_scenarios"][0]["is_session_override"] is False
    for entry in result["scenarios"]:
        assert entry["tools"] == ["check_balance"]
        assert entry["agent_defaults"]["template_vars"] == {"policy": {"days": 14}}
    assert result["custom_scenarios"][0]["is_active"] is True


@pytest.mark.asyncio
async def test_update_returns_every_persisted_editable_field(monkeypatch, scenario):
    original = api._scenario_response_config(scenario)
    config = DynamicScenarioConfig(**{**original, "description": "Updated in Quick Tune"})
    persist = AsyncMock()
    lookup = Mock(return_value=scenario)
    monkeypatch.setattr(api, "get_session_scenario", lookup)
    monkeypatch.setattr(api, "discover_agents", lambda: {"Concierge": object()})
    monkeypatch.setattr(api, "list_session_agents_by_session", lambda _: {})
    monkeypatch.setattr(api, "set_session_scenario_async", persist)
    result = await api.update_session_scenario("session-a", config, Request({"type": "http"}))
    lookup.assert_called_once_with("session-a", "Banking")
    persisted = persist.await_args.args[1]
    assert result.config == api._scenario_response_config(persisted)
    assert result.config["description"] == "Updated in Quick Tune"
    for field in ("tools", "agent_defaults", "global_template_vars"):
        assert result.config[field] == original[field]


@pytest.mark.asyncio
async def test_start_agent_activation_updates_session_scenario_and_adds_missing_agent(
    monkeypatch, scenario
):
    persist = AsyncMock()
    monkeypatch.setattr(api, "get_session_scenario", Mock(return_value=scenario))
    monkeypatch.setattr(api, "get_session_agent", Mock(return_value=None))
    monkeypatch.setattr(api, "discover_agents", lambda: {"FraudAgent": SimpleNamespace(name="FraudAgent")})
    monkeypatch.setattr(api, "set_session_scenario_async", persist)
    result = await api.set_session_start_agent(
        "session-a", " fraudagent ", Request({"type": "http"}), scenario_name="Banking"
    )
    persisted = persist.await_args.args[1]
    assert persisted.start_agent == "FraudAgent"
    assert persisted.agents == ["Concierge", "FraudAgent"]
    assert scenario.start_agent == "Concierge"
    assert result.config["start_agent"] == "FraudAgent"


@pytest.mark.asyncio
async def test_start_agent_activation_seeds_builtin_template_when_session_has_none(
    monkeypatch, scenario
):
    persist = AsyncMock()
    load = Mock(return_value=scenario)
    monkeypatch.setattr(api, "get_session_scenario", Mock(return_value=None))
    monkeypatch.setattr(api, "load_scenario", load)
    monkeypatch.setattr(api, "get_session_agent", Mock(return_value=SimpleNamespace(name="Concierge")))
    monkeypatch.setattr(api, "set_session_scenario_async", persist)
    await api.set_session_start_agent(
        "session-a", "Concierge", Request({"type": "http"}), scenario_name="Banking"
    )
    load.assert_called_once_with("banking")
    assert persist.await_args.args[1].agents == ["Concierge"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent", "scenario_found", "status"),
    [("Missing", True, 404), ("Concierge", False, 404), ("  ", True, 422)],
)
async def test_start_agent_activation_rejects_unknown_targets(
    monkeypatch, scenario, agent, scenario_found, status
):
    persist = AsyncMock()
    monkeypatch.setattr(api, "get_session_scenario", Mock(return_value=scenario if scenario_found else None))
    monkeypatch.setattr(api, "get_session_agent", Mock(return_value=None))
    monkeypatch.setattr(api, "discover_agents", lambda: {"Concierge": SimpleNamespace(name="Concierge")})
    monkeypatch.setattr(api, "set_session_scenario_async", persist)
    with pytest.raises(HTTPException) as error:
        await api.set_session_start_agent("session-a", agent, Request({"type": "http"}))
    assert error.value.status_code == status
    persist.assert_not_awaited()

def _generic_draft():
    return ScenarioDraft(
        summary="Use the configured generic handoff policy.",
        scenario={
            "name": "GenericFlow",
            "agents": ["Concierge", "Fraud"],
            "start_agent": "Concierge",
            "generic_handoff": {
                "enabled": True,
                "allowed_targets": [" fraud "],
                "require_client_id": True,
                "default_type": "discrete",
                "share_context": False,
            },
        },
    )


def _generic_catalog():
    return {
        "handoff_to_agent": ToolDefinition(
            name="handoff_to_agent",
            schema={"name": "handoff_to_agent"},
            executor=AsyncMock(),
            is_handoff=True,
        )
    }


@pytest.mark.asyncio
async def test_draft_apply_preserves_the_same_complete_generic_handoff_definition(monkeypatch):
    from apps.artagent.backend.api.v1.endpoints import scenario_drafts as drafts

    builtin = {name: UnifiedAgent(name=name) for name in ("Concierge", "Fraud")}
    snapshot = SimpleNamespace(agents={})
    published = AsyncMock()
    monkeypatch.setattr(drafts, "_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(drafts, "_builtin_agent_catalog", AsyncMock(return_value=builtin))
    monkeypatch.setattr(drafts, "_tool_catalog", lambda state: (_generic_catalog(), []))
    monkeypatch.setattr(drafts, "publish_draft", published)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    response = await drafts.apply_scenario_draft(_generic_draft(), request, "session")
    scenario = published.await_args.args[1]
    assert response.config == api._scenario_response_config(scenario)
    assert response.config["generic_handoff"] == {
        "enabled": True,
        "allowed_targets": ["Fraud"],
        "require_client_id": True,
        "default_type": "discrete",
        "share_context": False,
    }


@pytest.mark.parametrize("target", ["Outside", "", "fraud (session), Concierge"])
def test_draft_generic_handoff_cannot_escape_selected_agents(target):
    from apps.artagent.backend.api.v1.endpoints import scenario_drafts as drafts

    draft = _generic_draft()
    draft.scenario.generic_handoff.allowed_targets = [target]
    agents = {name.lower(): UnifiedAgent(name=name) for name in ("Concierge", "Fraud")}
    with pytest.raises(HTTPException, match="allowed_targets"):
        drafts.validate_draft(draft, agents, _generic_catalog())


@pytest.mark.parametrize(
    "settings,error",
    [
        ({"handoff": {"trigger": "unregistered"}}, "registered handoff tool"),
        ({"mcp_servers": ["not-selected"]}, "selected MCP capabilities"),
    ],
)
def test_draft_new_canonical_fields_are_validated_not_silently_accepted(settings, error):
    from apps.artagent.backend.api.v1.endpoints import scenario_drafts as drafts

    draft = ScenarioDraft(
        summary="Create an independent assistant.",
        scenario={"name": "SoloFlow", "agents": ["Solo"], "start_agent": "Solo"},
        agents=[{"name": "Solo", "prompt": "Help with the customer's question.", **settings}],
    )
    with pytest.raises(HTTPException, match=error):
        drafts.validate_draft(draft, {}, {})


@pytest.mark.asyncio
async def test_generated_draft_preserves_creation_defaults_through_shared_schema_roundtrip(
    monkeypatch,
):
    from apps.artagent.backend.api.v1.endpoints import scenario_drafts as drafts
    from apps.artagent.backend.api.v1.endpoints.agent_builder import build_session_agent

    monkeypatch.setattr(drafts, "_snapshot", AsyncMock(return_value=SimpleNamespace(agents={})))
    monkeypatch.setattr(drafts, "_builtin_agent_catalog", AsyncMock(return_value={}))
    monkeypatch.setattr(drafts, "_tool_catalog", lambda *args: ({}, []))
    monkeypatch.setattr(
        drafts,
        "_complete_draft",
        AsyncMock(
            return_value=json.dumps(
                {
                    "summary": "A new assistant with the standard model presets.",
                    "scenario": {"name": "NewFlow", "agents": ["New"], "start_agent": "New"},
                    "agents": [
                        {
                            "name": "New",
                            "prompt": "Help the customer with general questions.",
                            "session": {"turn_detection_threshold": 0.65},
                        }
                    ],
                }
            )
        ),
    )
    result = await drafts.generate_scenario_draft(
        ScenarioGenerateRequest(prompt="Create a helpful assistant."),
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        "session",
    )
    roundtrip = ScenarioDraft.model_validate(result.model_dump())
    agent = build_session_agent(roundtrip.agents[0], "session", created_at=1)
    assert agent.cascade_model.deployment_id == "gpt-4o"
    assert agent.voicelive_model.deployment_id == "gpt-realtime"
    assert agent.session["turn_detection"]["threshold"] == 0.65
