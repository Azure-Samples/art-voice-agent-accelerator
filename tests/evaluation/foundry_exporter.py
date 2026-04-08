"""
Foundry Exporter
================

Exports evaluation events to Azure AI Foundry-compatible JSONL format.

This module converts our internal TurnEvent format to Foundry's expected
dataset format for cloud-based evaluation using built-in evaluators like
relevance, coherence, violence detection, etc.

Usage
-----
```python
from tests.evaluation.foundry_exporter import FoundryExporter

exporter = FoundryExporter(export_config)
exporter.export_events(events, output_path)

# Or convert single event
foundry_row = exporter.event_to_foundry_row(turn_event)
```

Azure AI Foundry Integration
----------------------------
The exported JSONL can be:
1. Uploaded directly via `project_client.datasets.upload_file()`
2. Used with local evaluators from `azure-ai-evaluation` package
3. Imported into Foundry evaluation runs via the UI

Reference: https://learn.microsoft.com/azure/ai-foundry/how-to/evaluate-sdk
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests.evaluation.schemas import (
    FoundryDataRow,
    FoundryExportConfig,
    TurnEvent,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class FoundryExporter:
    """
    Exports evaluation events to Azure AI Foundry-compatible format.

    Handles:
    - Converting TurnEvent to FoundryDataRow
    - Building context from tool results/evidence
    - Generating JSONL output for Foundry dataset upload
    - Generating evaluator configuration for Foundry runs
    """

    def __init__(self, config: Optional[FoundryExportConfig] = None):
        """
        Initialize exporter with configuration.

        Args:
            config: Export configuration (defaults to basic export if None)
        """
        self.config = config or FoundryExportConfig(enabled=True)

    def event_to_foundry_row(
        self,
        event: TurnEvent,
        expectations: Optional[Dict[str, Any]] = None,
    ) -> FoundryDataRow:
        """
        Convert a TurnEvent to Foundry-compatible data row.

        Args:
            event: The turn event to convert
            expectations: Optional expectations dict for ground_truth extraction

        Returns:
            FoundryDataRow ready for JSONL export
        """
        # Build context based on config
        context = self._build_context(event)

        # Extract ground truth if configured
        ground_truth = self._extract_ground_truth(event, expectations)

        # Build tools list
        tools_called = [tc.name for tc in event.tool_calls] if event.tool_calls else None

        # Extract expected tools from scenario expectations
        tools_expected = self._extract_tools_expected(event, expectations)

        return FoundryDataRow(
            query=event.user_text,
            response=event.response_text,
            context=context,
            ground_truth=ground_truth,
            turn_id=event.turn_id if self.config.include_metadata else None,
            session_id=event.session_id if self.config.include_metadata else None,
            agent_name=event.agent_name if self.config.include_metadata else None,
            model_used=(
                event.eval_model_config.model_name
                if event.eval_model_config and self.config.include_metadata
                else None
            ),
            scenario_name=event.scenario_name if self.config.include_metadata else None,
            e2e_ms=event.e2e_ms if self.config.include_metadata else None,
            tools_called=tools_called if self.config.include_metadata else None,
            tools_expected=tools_expected if self.config.include_metadata else None,
        )

    def _build_context(self, event: TurnEvent) -> Optional[str]:
        """
        Build context string based on configuration.

        Args:
            event: Turn event with evidence blobs

        Returns:
            Combined context string or None
        """
        if self.config.context_source == "none":
            return None

        if self.config.context_source == "evidence":
            # Combine evidence from tool results
            if not event.evidence_blobs:
                return None

            context_parts = []
            for blob in event.evidence_blobs:
                # Include source and excerpt
                context_parts.append(f"[{blob.source}]: {blob.content_excerpt}")

            return "\n\n".join(context_parts) if context_parts else None

        if self.config.context_source == "conversation":
            # Use tool call results as context
            if not event.tool_calls:
                return None

            context_parts = []
            for tc in event.tool_calls:
                if tc.result_summary:
                    context_parts.append(f"[{tc.name}]: {tc.result_summary}")

            return "\n\n".join(context_parts) if context_parts else None

        return None

    def _extract_ground_truth(
        self,
        event: TurnEvent,
        expectations: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Extract ground truth from expectations if configured.

        Args:
            event: Turn event (for turn_id matching)
            expectations: Scenario expectations dict

        Returns:
            Ground truth string or None
        """
        if not self.config.ground_truth_field or not expectations:
            return None

        # Navigate to the specified field path
        # e.g., "turns.turn_1.expectations.expected_response"
        field_path = self.config.ground_truth_field.split(".")

        value = expectations
        for key in field_path:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list):
                # Try to find matching turn by turn_id
                for item in value:
                    if isinstance(item, dict) and item.get("turn_id") == event.turn_id:
                        value = item
                        break
                else:
                    value = None
            else:
                value = None

            if value is None:
                break

        return str(value) if value else None

    def _extract_tools_expected(
        self,
        event: TurnEvent,
        expectations: Optional[Dict[str, Any]],
    ) -> Optional[List[str]]:
        """
        Extract expected tools for this turn from scenario expectations.

        Args:
            event: Turn event (for turn_id matching)
            expectations: Scenario expectations dict with 'turns' list

        Returns:
            List of expected tool names or None
        """
        if not expectations:
            return None

        turns = expectations.get("turns", [])
        if not turns:
            return None

        # Extract turn key (e.g., "turn_1" from "gpt4o_vs_o3_banking_o3_mini_chat:turn_1")
        turn_key = event.turn_id.split(":")[-1] if ":" in event.turn_id else event.turn_id

        for turn_spec in turns:
            if turn_spec.get("turn_id") == turn_key:
                exp = turn_spec.get("expectations", {})
                tools = exp.get("tools_called", [])
                return tools if tools else None

        return None

    def export_events(
        self,
        events: List[TurnEvent],
        output_path: Path,
        expectations: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Export events to Foundry-compatible JSONL file.

        Args:
            events: List of turn events to export
            output_path: Directory or file path for output
            expectations: Optional scenario expectations for ground_truth

        Returns:
            Path to the generated JSONL file
        """
        # Determine output file path
        if output_path.suffix == ".jsonl":
            jsonl_path = output_path
        else:
            jsonl_path = output_path / self.config.output_filename

        jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert and write events
        rows_written = 0
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for event in events:
                row = self.event_to_foundry_row(event, expectations)
                f.write(row.model_dump_json(exclude_none=True) + "\n")
                rows_written += 1

        logger.info(
            f"Foundry export complete | rows={rows_written} path={jsonl_path}"
        )

        return jsonl_path

    def generate_evaluator_config_json(self) -> Dict[str, Any]:
        """
        Generate evaluator configuration for Foundry SDK.

        Returns a dict that can be used with:
        ```python
        from azure.ai.projects.models import EvaluatorConfiguration
        evaluators = {config["id"]: EvaluatorConfiguration(**config) for config in configs}
        ```

        Returns:
            List of evaluator configuration dicts
        """
        configs = []

        for evaluator in self.config.evaluators:
            config = {
                "id": evaluator.id,
                "init_params": evaluator.init_params,
                "data_mapping": {
                    "query": evaluator.data_mapping.query,
                    "response": evaluator.data_mapping.response,
                },
            }

            # Add optional mappings if specified
            if evaluator.data_mapping.context:
                config["data_mapping"]["context"] = evaluator.data_mapping.context
            if evaluator.data_mapping.ground_truth:
                config["data_mapping"]["ground_truth"] = evaluator.data_mapping.ground_truth

            configs.append(config)

        return {"evaluators": configs}

    def save_evaluator_config(self, output_path: Path) -> Path:
        """
        Save evaluator configuration to JSON file.

        This file can be used to configure Foundry evaluation runs.

        Args:
            output_path: Directory to save config

        Returns:
            Path to saved config file
        """
        config_path = output_path / "foundry_evaluators.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = self.generate_evaluator_config_json()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Foundry evaluator config saved | path={config_path}")
        return config_path


def export_for_foundry(
    events: List[TurnEvent],
    output_dir: Path,
    config: Optional[FoundryExportConfig] = None,
    expectations: Optional[Dict[str, Any]] = None,
) -> Dict[str, Path]:
    """
    Convenience function to export events and config for Foundry.

    Args:
        events: Turn events to export
        output_dir: Output directory
        config: Export configuration
        expectations: Optional scenario expectations

    Returns:
        Dict with paths: {"data": jsonl_path, "config": config_path}
    """
    exporter = FoundryExporter(config)

    paths = {}

    # Export data
    paths["data"] = exporter.export_events(events, output_dir, expectations)

    # Export evaluator config if evaluators are defined
    if config and config.evaluators:
        paths["config"] = exporter.save_evaluator_config(output_dir)

    return paths


def create_default_export_config(
    evaluator_ids: Optional[List[str]] = None,
    deployment_name: Optional[str] = None,
) -> FoundryExportConfig:
    """
    Create a default Foundry export configuration.

    Args:
        evaluator_ids: List of evaluator IDs to include (defaults to relevance + coherence)
        deployment_name: Model deployment for AI-based evaluators

    Returns:
        FoundryExportConfig with specified evaluators
    """
    from tests.evaluation.schemas import (
        FoundryDataMapping,
        FoundryEvaluatorConfig,
        FoundryEvaluatorId,
    )

    # Default evaluators
    if evaluator_ids is None:
        evaluator_ids = [
            FoundryEvaluatorId.RELEVANCE.value,
            FoundryEvaluatorId.COHERENCE.value,
        ]

    evaluators = []
    for eval_id in evaluator_ids:
        init_params = {}

        # AI-based evaluators need deployment_name
        ai_evaluators = [
            FoundryEvaluatorId.RELEVANCE.value,
            FoundryEvaluatorId.COHERENCE.value,
            FoundryEvaluatorId.FLUENCY.value,
            FoundryEvaluatorId.GROUNDEDNESS.value,
            FoundryEvaluatorId.SIMILARITY.value,
        ]

        if eval_id in ai_evaluators and deployment_name:
            init_params["deployment_name"] = deployment_name

        evaluators.append(
            FoundryEvaluatorConfig(
                id=eval_id,
                init_params=init_params,
                data_mapping=FoundryDataMapping(),
            )
        )

    return FoundryExportConfig(
        enabled=True,
        evaluators=evaluators,
        include_metadata=True,
        context_source="evidence",
    )


async def submit_to_foundry(
    data_path: Path,
    evaluators_config_path: Optional[Path] = None,
    project_endpoint: Optional[str] = None,
    dataset_name: Optional[str] = None,
    evaluation_name: Optional[str] = None,
    model_deployment_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit evaluation data to Azure AI Foundry for cloud-based evaluation.

    Uses azure-ai-evaluation's evaluate() function with azure_ai_project parameter
    to run evaluators locally and log results to AI Foundry portal.

    Args:
        data_path: Path to foundry_eval.jsonl file
        evaluators_config_path: Path to foundry_evaluators.json (optional)
        project_endpoint: Azure AI Foundry project endpoint URL
            Format: https://<resource>.services.ai.azure.com/api/projects/<project>
            If not provided, uses AZURE_AI_FOUNDRY_PROJECT_ENDPOINT from config
        dataset_name: Name for the uploaded dataset (unused, kept for API compat)
        evaluation_name: Name for the evaluation run (defaults to auto-generated)
        model_deployment_name: Model deployment for AI-based evaluators (e.g., "gpt-4o")

    Returns:
        Dict with evaluation results:
        {
            "evaluation_name": str,
            "status": str,
            "metrics": dict,
            "rows_evaluated": int,
            "output_path": str,
            "studio_url": str,
        }

    Raises:
        ImportError: If azure-ai-evaluation is not installed
        ValueError: If project endpoint is not configured
        Exception: If evaluation fails

    Example:
        result = await submit_to_foundry(
            data_path=Path("runs/my_scenario/foundry_eval.jsonl"),
        )
        print(f"View in Foundry: {result['studio_url']}")
    """
    import os
    import time
    from datetime import datetime

    # Get project endpoint from args or config settings
    try:
        from apps.artagent.backend.config import AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
        endpoint = project_endpoint or AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
    except ImportError:
        endpoint = project_endpoint or os.environ.get("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", "")

    if not endpoint:
        raise ValueError(
            "AI Foundry project endpoint required. "
            "Set AZURE_AI_FOUNDRY_PROJECT_ENDPOINT in App Config or .env.local, "
            "or pass project_endpoint parameter. "
            "Format: https://<resource>.services.ai.azure.com/api/projects/<project>"
        )

    try:
        from azure.ai.evaluation import (
            CoherenceEvaluator,
            F1ScoreEvaluator,
            FluencyEvaluator,
            GroundednessEvaluator,
            RelevanceEvaluator,
            ViolenceEvaluator,
            SexualEvaluator,
            SelfHarmEvaluator,
            HateUnfairnessEvaluator,
            evaluate,
        )
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        raise ImportError(
            "azure-ai-evaluation package required for cloud submission. "
            "Install with: pip install azure-ai-evaluation"
        ) from e

    # Generate names with timestamps
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S_UTC")

    if not evaluation_name:
        evaluation_name = f"eval_{data_path.parent.name}_{int(time.time())}"

    logger.info(f"Running Foundry evaluation | endpoint={endpoint} data={data_path}")

    # Build evaluators dict
    deployment = model_deployment_name or "gpt-4o"

    # Extract the base Azure OpenAI endpoint from the project endpoint
    # Project endpoint: https://<resource>.services.ai.azure.com/api/projects/<project>
    # Azure OpenAI endpoint: https://<resource>.openai.azure.com/
    base_endpoint = endpoint.rsplit("/api/projects", 1)[0]

    # Model config for AI-based evaluators - needs Azure OpenAI endpoint
    # Try to get from environment first
    azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", base_endpoint)

    model_config = {
        "azure_endpoint": azure_openai_endpoint,
        "azure_deployment": deployment,
        "api_version": "2024-06-01",
    }

    # Add API key if available
    api_key = os.environ.get("AZURE_OPENAI_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
    if api_key:
        model_config["api_key"] = api_key

    # Credential for safety evaluators
    credential = DefaultAzureCredential()

    evaluators = {}
    evaluator_config = {}

    if evaluators_config_path and evaluators_config_path.exists():
        with open(evaluators_config_path, encoding="utf-8") as f:
            config_data = json.load(f)

        for eval_cfg in config_data.get("evaluators", []):
            eval_id = eval_cfg["id"]
            # Use the correct keyword mapping for Foundry portal display
            eval_name = eval_id.split(".")[-1] if "." in eval_id else eval_id

            # Map evaluator IDs to classes with correct keyword names
            # Quality evaluators (use model_config)
            if "coherence" in eval_id.lower():
                evaluators["coherence"] = CoherenceEvaluator(model_config=model_config)
            elif "relevance" in eval_id.lower():
                evaluators["relevance"] = RelevanceEvaluator(model_config=model_config)
            elif "fluency" in eval_id.lower():
                evaluators["fluency"] = FluencyEvaluator(model_config=model_config)
            elif "groundedness" in eval_id.lower():
                evaluators["groundedness"] = GroundednessEvaluator(model_config=model_config)
            elif "f1" in eval_id.lower():
                evaluators["f1_score"] = F1ScoreEvaluator()
            # Safety evaluators (use credential + azure_ai_project)
            elif "violence" in eval_id.lower():
                evaluators["violence"] = ViolenceEvaluator(
                    credential=credential,
                    azure_ai_project=endpoint,
                )
            elif "sexual" in eval_id.lower():
                evaluators["sexual"] = SexualEvaluator(
                    credential=credential,
                    azure_ai_project=endpoint,
                )
            elif "self_harm" in eval_id.lower() or "selfharm" in eval_id.lower():
                evaluators["self_harm"] = SelfHarmEvaluator(
                    credential=credential,
                    azure_ai_project=endpoint,
                )
            elif "hate" in eval_id.lower() or "unfairness" in eval_id.lower():
                evaluators["hate_unfairness"] = HateUnfairnessEvaluator(
                    credential=credential,
                    azure_ai_project=endpoint,
                )
            else:
                logger.warning(f"Unknown evaluator ID: {eval_id}, skipping")
                continue

            # Set up column mappings based on evaluator type
            eval_name = eval_id.split(".")[-1] if "." in eval_id else eval_id
            evaluator_config[eval_name] = {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                }
            }
    else:
        # Check what fields are available in the data to determine which evaluators to use
        has_ground_truth = False
        try:
            with open(data_path, encoding="utf-8") as f:
                first_line = f.readline()
                if first_line:
                    first_record = json.loads(first_line)
                    has_ground_truth = bool(first_record.get("ground_truth"))
        except (json.JSONDecodeError, IOError):
            pass

        # Default evaluators with correct keyword names for portal display
        evaluators["coherence"] = CoherenceEvaluator(model_config=model_config)
        evaluator_config["coherence"] = {
            "column_mapping": {
                "query": "${data.query}",
                "response": "${data.response}",
            }
        }

        # Only add F1 evaluator if ground_truth is available in the data
        if has_ground_truth:
            evaluators["f1_score"] = F1ScoreEvaluator()
            evaluator_config["f1_score"] = {
                "column_mapping": {
                    "response": "${data.response}",
                    "ground_truth": "${data.ground_truth}",
                }
            }
        else:
            logger.info("Skipping F1ScoreEvaluator (no ground_truth in data)")

    logger.info(f"Running evaluation with {len(evaluators)} evaluators: {list(evaluators.keys())}")

    # Output path for local results
    output_path = data_path.parent / "foundry_results"

    # Run evaluation with Foundry logging
    # The azure_ai_project parameter accepts the endpoint string directly
    logger.debug(f"Calling evaluate() with azure_ai_project={endpoint}")
    result = evaluate(
        data=str(data_path),
        evaluators=evaluators,
        evaluator_config=evaluator_config,
        evaluation_name=evaluation_name,
        azure_ai_project=endpoint,
        output_path=str(output_path),
    )

    logger.debug(f"evaluate() returned type={type(result)}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}")

    # Extract metrics from result
    # The evaluate() API returns a dict with 'metrics', 'rows', 'traces', and 'studio_url'
    metrics = dict(result.get("metrics", {})) if isinstance(result, dict) else {}
    rows = result.get("rows", []) if isinstance(result, dict) else []
    studio_url = result.get("studio_url") if isinstance(result, dict) else None

    response = {
        "evaluation_name": evaluation_name,
        "status": "completed",
        "metrics": metrics,
        "rows_evaluated": len(rows),
        "output_path": str(output_path),
        "foundry_endpoint": endpoint,
        "studio_url": studio_url,
    }

    logger.info(
        f"Foundry evaluation complete | name={evaluation_name} rows={len(rows)} metrics={metrics}"
    )
    if studio_url:
        logger.info(f"View results in AI Foundry portal: {studio_url}")
    else:
        logger.warning(
            "No studio_url returned. Prerequisites for logging to Foundry: "
            "1) Create and connect storage account to Foundry project at resource level "
            "2) Ensure storage account has 'Storage Blob Data Owner' role for your account and project. "
            "See: https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk#prerequisite-set-up-steps-for-microsoft-foundry-projects"
        )

    return response


def submit_to_foundry_sync(
    data_path: Path,
    evaluators_config_path: Optional[Path] = None,
    project_endpoint: Optional[str] = None,
    dataset_name: Optional[str] = None,
    evaluation_name: Optional[str] = None,
    model_deployment_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronous wrapper for submit_to_foundry.

    See submit_to_foundry for full documentation.
    """
    import asyncio
    return asyncio.run(submit_to_foundry(
        data_path=data_path,
        evaluators_config_path=evaluators_config_path,
        project_endpoint=project_endpoint,
        dataset_name=dataset_name,
        evaluation_name=evaluation_name,
        model_deployment_name=model_deployment_name,
    ))


__all__ = [
    "FoundryExporter",
    "export_for_foundry",
    "create_default_export_config",
    "submit_to_foundry",
    "submit_to_foundry_sync",
]
