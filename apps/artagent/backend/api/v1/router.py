"""
API V1 Router
=============

Main router for API v1 endpoints.

Note: Tags are defined at the endpoint level (in each endpoint file) to avoid
duplication in OpenAPI docs. See apps/artagent/backend/api/swagger_docs.py for
tag definitions and descriptions.
"""

from fastapi import APIRouter

from .endpoints import agent_builder, browser, calls, health, media, metrics, scenario_builder, scenarios

# Create v1 router
v1_router = APIRouter(prefix="/api/v1")

# Include endpoint routers - tags are defined at endpoint level to avoid duplication
v1_router.include_router(health.router)
v1_router.include_router(calls.router, prefix="/calls")
v1_router.include_router(media.router, prefix="/media")
v1_router.include_router(browser.router, prefix="/browser")
v1_router.include_router(metrics.router, prefix="/metrics")
v1_router.include_router(agent_builder.router, prefix="/agent-builder")
v1_router.include_router(scenario_builder.router, prefix="/scenario-builder")
v1_router.include_router(scenarios.router)
