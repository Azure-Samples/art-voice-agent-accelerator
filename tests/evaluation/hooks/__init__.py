"""
Evaluation Hooks
================

Extensible hook system for custom turn analysis without modifying core runners.

Hook Types
----------
- on_turn_complete: Called after each turn completes
- on_tool_complete: Called after each tool execution
- pre_score: Called before metrics scoring

Usage
-----
```yaml
# In scenario YAML
hooks:
  on_turn_complete:
    - builtin.log_metrics
    - module: my_analyzers.sentiment
      function: analyze_response

  pre_score:
    - module: my_analyzers.domain
      function: compute_banking_accuracy
```

```python
# Custom hook implementation
from tests.evaluation.hooks import TurnHook

class SentimentAnalyzer(TurnHook):
    async def on_turn_complete(self, turn, context):
        sentiment = await self._analyze(turn.response_text)
        return {"sentiment_score": sentiment}
```
"""

from .base import TurnHook, ToolHook, PreScoreHook, HookResult
from .registry import HookRegistry
from .builtin import LogMetricsHook, ValidateExpectationsHook, CaptureReasoningHook

__all__ = [
    # Base classes
    "TurnHook",
    "ToolHook", 
    "PreScoreHook",
    "HookResult",
    # Registry
    "HookRegistry",
    # Built-in hooks
    "LogMetricsHook",
    "ValidateExpectationsHook",
    "CaptureReasoningHook",
]
