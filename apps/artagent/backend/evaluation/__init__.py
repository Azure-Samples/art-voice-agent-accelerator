"""
Evaluation Package
==================

Model-to-model evaluation framework for voice agent orchestration.

⚠️ CRITICAL: This package should NEVER be imported in production code.
             Only use in:
             - tests/eval_scenarios/
             - Manual evaluation scripts
             - CI evaluation jobs

This module includes runtime checks to prevent accidental imports
in production environments.
"""

from __future__ import annotations

import os
import sys
import warnings

# =============================================================================
# IMPORT GUARDRAILS - Prevent production imports
# =============================================================================

# Check if we're in a production environment
_ENV = os.getenv("ENV", "").lower()
if _ENV in ["production", "prod", "staging"]:
    raise ImportError(
        "\n"
        "❌ CRITICAL: evaluation package should NEVER be imported in production!\n"
        "\n"
        "This package is for testing/CI only.\n"
        "Check your imports and remove any references to:\n"
        "    apps.artagent.backend.evaluation\n"
        "\n"
        f"Current ENV={_ENV}\n"
    )

# Warn if imported from production modules (developer safety net)
try:
    caller_frame = sys._getframe(1)
    caller_file = caller_frame.f_code.co_filename
    caller_name = caller_frame.f_code.co_name

    # List of production paths that should NOT import evaluation
    _PRODUCTION_PATHS = [
        "/voice/",
        "/api/",
        "/registries/agentstore/",
        "/registries/toolstore/",
        "/src/orchestration/",
    ]

    if any(prod_path in caller_file for prod_path in _PRODUCTION_PATHS):
        warnings.warn(
            f"\n"
            f"⚠️  WARNING: Evaluation package imported from production module!\n"
            f"\n"
            f"   File: {caller_file}\n"
            f"   Function: {caller_name}\n"
            f"\n"
            f"   This package should only be imported from:\n"
            f"   - tests/eval_scenarios/\n"
            f"   - Evaluation scripts (e.g., run_scenario.py)\n"
            f"   - CI evaluation jobs\n"
            f"\n"
            f"   Please refactor to keep evaluation code separate from production.\n",
            RuntimeWarning,
            stacklevel=2,
        )
except Exception:
    # Failed to get caller info - not critical, just skip warning
    pass

# =============================================================================
# PACKAGE EXPORTS
# =============================================================================

from apps.artagent.backend.evaluation.mocks import (
    MockMemoManager,
    MockOrchestratorContext,
    build_context,
)
from apps.artagent.backend.evaluation.recorder import EventRecorder
from apps.artagent.backend.evaluation.scenario_runner import (
    ComparisonRunner,
    ScenarioRunner,
)
from apps.artagent.backend.evaluation.schemas import (
    EvalModelConfig,
    EvidenceBlob,
    HandoffEvent,
    RunSummary,
    ScenarioExpectations,
    ToolCall,
    TurnEvent,
    TurnScore,
)
from apps.artagent.backend.evaluation.scorer import MetricsScorer
from apps.artagent.backend.evaluation.wrappers import EvaluationOrchestratorWrapper

__version__ = "0.2.0"  # Phase 3 complete

__all__ = [
    # Core components
    "EventRecorder",
    "EvaluationOrchestratorWrapper",
    "MetricsScorer",
    # Scenario runners
    "ScenarioRunner",
    "ComparisonRunner",
    # Mocks
    "MockMemoManager",
    "MockOrchestratorContext",
    "build_context",
    # Schemas
    "ToolCall",
    "EvidenceBlob",
    "HandoffEvent",
    "EvalModelConfig",
    "TurnEvent",
    "ScenarioExpectations",
    "TurnScore",
    "RunSummary",
]

# =============================================================================
# PACKAGE METADATA
# =============================================================================

_PACKAGE_INFO = {
    "name": "evaluation",
    "version": __version__,
    "description": "Model-to-model evaluation framework for voice agent orchestration",
    "safe_imports_from": [
        "tests/eval_scenarios/",
        "apps/artagent/backend/evaluation/",
    ],
    "forbidden_imports_from": [
        "apps/artagent/backend/voice/",
        "apps/artagent/backend/api/",
        "apps/artagent/backend/registries/",
    ],
}


def get_package_info() -> dict:
    """Get package metadata."""
    return _PACKAGE_INFO.copy()
