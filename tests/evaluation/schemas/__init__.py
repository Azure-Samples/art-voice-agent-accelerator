"""
Evaluation Schemas Package
==========================

Modular schema definitions for the evaluation framework.

Modules:
    - foundry: Azure AI Foundry export schemas
    - events: Turn events, tool calls, handoffs
    - config: Model profiles, session configuration
    - expectations: Scenario expectations for validation
    - results: Scoring and summary models

All schemas are re-exported here for backward compatibility:
    from tests.evaluation.schemas import TurnEvent, ModelProfile, ...
"""

from .config import ModelProfile, SessionAgentConfig, SessionHandoffConfig
from .events import EvalModelConfig, EvidenceBlob, HandoffEvent, ToolCall, TurnEvent
from .expectations import ScenarioExpectations
from .foundry import (
    FoundryDataMapping,
    FoundryDataRow,
    FoundryEvaluatorConfig,
    FoundryEvaluatorId,
    FoundryExportConfig,
)
from .results import PerTurnSummary, RunSummary, TurnScore

__all__ = [
    # Foundry integration
    "FoundryEvaluatorId",
    "FoundryDataMapping",
    "FoundryEvaluatorConfig",
    "FoundryDataRow",
    "FoundryExportConfig",
    # Model profile (Phase 1 refactor)
    "ModelProfile",
    # Session-based scenario schemas
    "SessionHandoffConfig",
    "SessionAgentConfig",
    # Event schemas
    "ToolCall",
    "EvidenceBlob",
    "HandoffEvent",
    "EvalModelConfig",
    "TurnEvent",
    # Expectations
    "ScenarioExpectations",
    # Results
    "TurnScore",
    "PerTurnSummary",
    "RunSummary",
]
