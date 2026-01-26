"""
Azure AI Foundry Schema Definitions
====================================

Schemas for exporting evaluation data to Azure AI Foundry's evaluation platform.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FoundryEvaluatorId(str, Enum):
    """
    Built-in Azure AI Foundry evaluator IDs.

    Reference: https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-approach-gen-ai
    """

    # Quality evaluators (require model deployment)
    RELEVANCE = "builtin.relevance"
    COHERENCE = "builtin.coherence"
    FLUENCY = "builtin.fluency"
    GROUNDEDNESS = "builtin.groundedness"
    SIMILARITY = "builtin.similarity"

    # Safety evaluators
    VIOLENCE = "builtin.violence"
    SEXUAL = "builtin.sexual"
    SELF_HARM = "builtin.self_harm"
    HATE_UNFAIRNESS = "builtin.hate_unfairness"

    # Traditional NLP metrics (no model required)
    F1_SCORE = "builtin.f1_score"
    BLEU_SCORE = "builtin.bleu_score"
    ROUGE_SCORE = "builtin.rouge_score"
    METEOR_SCORE = "builtin.meteor_score"
    GLEU_SCORE = "builtin.gleu_score"


class FoundryDataMapping(BaseModel):
    """
    Maps evaluation data fields to Foundry expected columns.

    Foundry expects specific field names; this maps from our TurnEvent fields.
    Uses ${data.field_name} syntax for dynamic mapping.
    """

    query: str = Field(
        default="${data.query}",
        description="Maps to user input/question field",
    )
    response: str = Field(
        default="${data.response}",
        description="Maps to agent response field",
    )
    context: Optional[str] = Field(
        default="${data.context}",
        description="Maps to context/evidence field (for groundedness)",
    )
    ground_truth: Optional[str] = Field(
        default="${data.ground_truth}",
        description="Maps to expected answer field (for similarity metrics)",
    )


class FoundryEvaluatorConfig(BaseModel):
    """
    Configuration for a single Foundry evaluator.

    Matches the EvaluatorConfiguration schema from azure-ai-projects SDK.
    """

    id: str = Field(
        ...,
        description="Evaluator ID (e.g., 'builtin.relevance' or custom evaluator path)",
    )
    init_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Initialization parameters (e.g., deployment_name for AI evaluators)",
    )
    data_mapping: FoundryDataMapping = Field(
        default_factory=FoundryDataMapping,
        description="Maps data fields to evaluator inputs",
    )


class FoundryDataRow(BaseModel):
    """
    Single row in Foundry-compatible JSONL dataset.

    This is the format expected by Azure AI Foundry's evaluation API.
    Each row represents one evaluation sample (typically one conversation turn).
    """

    # Core fields (always present)
    query: str = Field(..., description="User input/question")
    response: str = Field(..., description="Agent/model response")

    # Optional context fields
    context: Optional[str] = Field(
        None,
        description="Retrieved context or evidence (for RAG/groundedness evaluation)",
    )
    ground_truth: Optional[str] = Field(
        None,
        description="Expected/reference answer (for similarity metrics)",
    )

    # Metadata (preserved but not used by evaluators)
    turn_id: Optional[str] = Field(None, description="Turn identifier for tracing")
    session_id: Optional[str] = Field(None, description="Session identifier")
    agent_name: Optional[str] = Field(None, description="Agent that generated response")
    model_used: Optional[str] = Field(None, description="Model deployment used")
    scenario_name: Optional[str] = Field(None, description="Evaluation scenario name")

    # Additional metrics from our system (useful for correlation)
    e2e_ms: Optional[float] = Field(None, description="End-to-end latency")
    tools_called: Optional[List[str]] = Field(None, description="Tools invoked")
    tools_expected: Optional[List[str]] = Field(
        None, description="Expected tools from scenario YAML"
    )


class FoundryExportConfig(BaseModel):
    """
    Configuration for exporting evaluation results to Foundry format.

    Specified in evaluation YAML under 'foundry_export' key.
    """

    enabled: bool = Field(default=False, description="Enable Foundry export")
    evaluators: List[FoundryEvaluatorConfig] = Field(
        default_factory=list,
        description="Evaluators to configure for Foundry evaluation",
    )
    output_filename: str = Field(
        default="foundry_eval.jsonl",
        description="Output filename for Foundry JSONL",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include turn metadata in export (turn_id, agent, etc.)",
    )
    context_source: Literal["evidence", "conversation", "none"] = Field(
        default="evidence",
        description="Source for context field: 'evidence' (tool results), 'conversation' (history), or 'none'",
    )
    ground_truth_field: Optional[str] = Field(
        None,
        description="YAML field path for ground truth (e.g., 'expectations.expected_response')",
    )


__all__ = [
    "FoundryEvaluatorId",
    "FoundryDataMapping",
    "FoundryEvaluatorConfig",
    "FoundryDataRow",
    "FoundryExportConfig",
]
