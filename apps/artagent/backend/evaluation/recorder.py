"""
Event Recorder
==============

Records orchestration events to JSONL without modifying production code.

The EventRecorder is completely standalone and has no dependencies on
production orchestration code. It's designed to be injected via the
EvaluationOrchestratorWrapper.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.artagent.backend.evaluation.schemas import (
    EvalModelConfig,
    EvidenceBlob,
    HandoffEvent,
    ToolCall,
    TurnEvent,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class EventRecorder:
    """
    Records orchestration events to JSONL.

    Design principles:
    - Standalone: No production code dependencies
    - Non-blocking: Synchronous writes (async optional for Phase 2)
    - Stateful: Tracks current turn state in memory
    - Resilient: Handles missing data gracefully
    """

    def __init__(self, run_id: str, output_dir: Path):
        """
        Initialize event recorder.

        Args:
            run_id: Unique identifier for this evaluation run
            output_dir: Directory to write events.jsonl
        """
        self.run_id = run_id
        self.output_path = output_dir / f"{run_id}_events.jsonl"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory state for current turn
        self._current_turn: Dict[str, Any] = {}
        self._tool_calls: Dict[str, Dict[str, Any]] = {}
        self._evidence_blobs: List[EvidenceBlob] = []
        self._handoff: Optional[HandoffEvent] = None

        # Get commit SHA once at initialization
        self._commit_sha = self._get_git_commit_sha()

        logger.info(f"EventRecorder initialized | run_id={run_id} output={self.output_path}")

    def _get_git_commit_sha(self) -> Optional[str]:
        """Get current git commit SHA for versioning."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:12]  # Short SHA
        except Exception:
            pass
        return None

    def record_turn_start(
        self,
        turn_id: str,
        agent: str,
        user_text: str,
        timestamp: float,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Start recording a new turn.

        Args:
            turn_id: Unique turn identifier
            agent: Active agent name
            user_text: User input text
            timestamp: Start timestamp (seconds since epoch)
            context: Optional context dict for evidence extraction
        """
        self._current_turn = {
            "turn_id": turn_id,
            "agent": agent,
            "user_text": user_text,
            "start_ts": timestamp,
            "context": context or {},
        }
        self._tool_calls = {}
        self._evidence_blobs = []
        self._handoff = None

        logger.debug(f"Turn start | turn_id={turn_id} agent={agent}")

    def record_tool_start(self, tool_name: str, arguments: Any, timestamp: float):
        """
        Record tool call start.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments (dict or other)
            timestamp: Start timestamp
        """
        # Normalize arguments to dict
        if isinstance(arguments, dict):
            args_dict = arguments
        elif isinstance(arguments, str):
            try:
                args_dict = json.loads(arguments)
            except json.JSONDecodeError:
                args_dict = {"raw": arguments}
        else:
            args_dict = {"raw": str(arguments)}

        self._tool_calls[tool_name] = {
            "name": tool_name,
            "arguments": args_dict,
            "start_ts": timestamp,
            "status": "pending",
        }

        logger.debug(f"Tool start | tool={tool_name} args={list(args_dict.keys())}")

    def record_tool_end(
        self,
        tool_name: str,
        result: Any,
        end_ts: float,
        start_ts: Optional[float] = None,
    ):
        """
        Record tool call completion.

        Args:
            tool_name: Name of the tool
            result: Tool result (any type)
            end_ts: End timestamp
            start_ts: Start timestamp (if not already recorded)
        """
        if tool_name not in self._tool_calls:
            # Tool start wasn't recorded - create entry now
            self._tool_calls[tool_name] = {
                "name": tool_name,
                "arguments": {},
                "start_ts": start_ts or end_ts,
            }

        tool_call = self._tool_calls[tool_name]
        tool_call["end_ts"] = end_ts
        tool_call["duration_ms"] = (end_ts - tool_call["start_ts"]) * 1000
        tool_call["status"] = "success"

        # Create result summary and hash for deduplication
        result_str = str(result)
        result_excerpt = result_str[:200]
        tool_call["result_summary"] = result_excerpt
        tool_call["result_hash"] = hashlib.sha256(result_str.encode()).hexdigest()[:16]

        # Extract evidence for groundedness checking
        self._extract_evidence_from_tool(tool_name, result_str)

        logger.debug(
            f"Tool end | tool={tool_name} duration={tool_call['duration_ms']:.1f}ms "
            f"result_len={len(result_str)}"
        )

    def _extract_evidence_from_tool(self, tool_name: str, result_str: str):
        """Extract evidence blob from tool result for groundedness checking."""
        evidence = EvidenceBlob(
            source=f"tool:{tool_name}",
            content_hash=hashlib.sha256(result_str.encode()).hexdigest()[:16],
            content_excerpt=result_str[:200],
        )
        self._evidence_blobs.append(evidence)

    def record_handoff(
        self,
        source_agent: str,
        target_agent: str,
        timestamp: float,
        tool_name: Optional[str] = None,
        context: Optional[str] = None,
    ):
        """
        Record agent handoff.

        Args:
            source_agent: Agent initiating handoff
            target_agent: Agent receiving handoff
            timestamp: Handoff timestamp
            tool_name: Handoff tool used (if applicable)
            context: Handoff context/reason
        """
        self._handoff = HandoffEvent(
            source_agent=source_agent,
            target_agent=target_agent,
            tool_name=tool_name,
            handoff_type="discrete" if tool_name else "announced",
            context=context,
            timestamp=timestamp,
        )

        logger.info(f"Handoff recorded | {source_agent} → {target_agent}")

    def record_turn_end(
        self,
        turn_id: str,
        agent: str,
        response_text: str,
        e2e_ms: float,
        timestamp: float,
        model_config: Optional[EvalModelConfig] = None,
        response_tokens: Optional[int] = None,
        input_tokens: Optional[int] = None,
        reasoning_tokens: Optional[int] = None,
        error: Optional[str] = None,
        ttft_ms: Optional[float] = None,
    ):
        """
        Finalize turn and write to JSONL.

        Args:
            turn_id: Turn identifier
            agent: Active agent name
            response_text: Agent response text
            e2e_ms: End-to-end time (milliseconds)
            timestamp: End timestamp
            model_config: Model configuration used
            response_tokens: Response token count
            input_tokens: Input token count
            reasoning_tokens: Reasoning token count (o1/o3/o4)
            error: Error message (if turn failed)
            ttft_ms: Time to first token (milliseconds)
        """
        # Extract context evidence
        context = self._current_turn.get("context", {})
        for key, value in context.items():
            if isinstance(value, str) and value:
                evidence = EvidenceBlob(
                    source=f"context:{key}",
                    content_hash=hashlib.sha256(value.encode()).hexdigest()[:16],
                    content_excerpt=value[:200],
                )
                self._evidence_blobs.append(evidence)

        # Build TurnEvent
        event = TurnEvent(
            session_id=self.run_id,
            turn_id=turn_id,
            scenario_name=None,  # Set by ScenarioRunner if applicable
            user_end_ts=self._current_turn.get("start_ts", timestamp),
            agent_first_output_ts=timestamp - (ttft_ms / 1000 if ttft_ms else 0),
            agent_last_output_ts=timestamp,
            e2e_ms=e2e_ms,
            ttft_ms=ttft_ms,
            agent_name=agent,
            previous_agent=(
                self._handoff.source_agent if self._handoff else None
            ),
            user_text=self._current_turn.get("user_text", ""),
            response_text=response_text,
            response_tokens=response_tokens,
            input_tokens=input_tokens,
            reasoning_tokens=reasoning_tokens,
            tool_calls=[ToolCall(**tc) for tc in self._tool_calls.values()],
            evidence_blobs=self._evidence_blobs,
            handoff=self._handoff,
            eval_model_config=model_config or self._default_model_config(),
            commit_sha=self._commit_sha,
            error=error,
        )

        # Write to JSONL (append mode)
        with open(self.output_path, "a") as f:
            f.write(event.model_dump_json() + "\n")

        logger.info(
            f"Turn end | turn_id={turn_id} agent={agent} "
            f"e2e={e2e_ms:.1f}ms tools={len(self._tool_calls)} "
            f"response_len={len(response_text)}"
        )

        # Clear state for next turn
        self._current_turn = {}
        self._tool_calls = {}
        self._evidence_blobs = []
        self._handoff = None

    def _default_model_config(self) -> EvalModelConfig:
        """Return default model config when none provided."""
        return EvalModelConfig(
            model_name="unknown",
            endpoint_used="chat",
        )

    def get_events(self) -> List[TurnEvent]:
        """
        Load all events from JSONL file.

        Returns:
            List of TurnEvent objects
        """
        events = []
        if not self.output_path.exists():
            return events

        with open(self.output_path) as f:
            for line in f:
                if line.strip():
                    events.append(TurnEvent.model_validate_json(line))

        return events


__all__ = ["EventRecorder"]
