"""
Scenarios API
=============

Endpoints for managing and selecting agent scenarios.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.artagent.backend.registries.scenariostore import (
    list_scenarios,
    load_scenario,
)

router = APIRouter()


class ScenarioInfo(BaseModel):
    """Scenario information."""

    name: str
    description: str
    agents: list[str]
    start_agent: str | None


class ScenarioListResponse(BaseModel):
    """List of available scenarios."""

    scenarios: list[ScenarioInfo]


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["Scenarios"])
async def get_scenarios():
    """
    List all available scenarios.

    Returns:
        List of scenario configurations with basic info
    """
    scenario_names = list_scenarios()
    scenarios = []

    for name in scenario_names:
        scenario = load_scenario(name)
        if scenario:
            scenarios.append(
                ScenarioInfo(
                    name=scenario.name,
                    description=scenario.description,
                    agents=scenario.agents if scenario.agents else ["all"],
                    start_agent=scenario.start_agent,
                )
            )

    return ScenarioListResponse(scenarios=scenarios)


@router.get("/scenarios/{scenario_name}", response_model=ScenarioInfo, tags=["Scenarios"])
async def get_scenario(scenario_name: str):
    """
    Get details for a specific scenario.

    Args:
        scenario_name: Name of the scenario

    Returns:
        Scenario configuration details

    Raises:
        HTTPException: If scenario not found
    """
    scenario = load_scenario(scenario_name)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_name}' not found")

    return ScenarioInfo(
        name=scenario.name,
        description=scenario.description,
        agents=scenario.agents if scenario.agents else ["all"],
        start_agent=scenario.start_agent,
    )
