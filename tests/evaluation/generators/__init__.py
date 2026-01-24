"""
Turn Generators Module (Phase 4)
================================

Provides template variable resolution and turn generators for dynamic
scenario content.

Features:
    - Template Variables: Inject dynamic values into turn user_input
    - Turn Generators: Generate turns programmatically at runtime
    - Sequence Imports: Reuse turn sequences across scenarios

Example YAML
------------
```yaml
# Template variables - inject values into user_input
turns:
  - turn_id: turn_1
    user_input: "Check balance for account {{account_id}}"
    inject:
      account_id:
        source: fixture
        key: test_account_1

  - turn_id: turn_2
    user_input: "Transfer ${{amount}} to {{recipient}}"
    inject:
      amount:
        source: previous_turn
        extract: "balance * 0.1"
      recipient:
        source: context
        key: test_recipient

# Turn generators - create turns programmatically
  - turn_id: dynamic_1
    generator:
      module: my_generators.banking
      function: generate_fraud_scenarios
      params:
        count: 3
        include_edge_cases: true
```

Usage
-----
```python
from tests.evaluation.generators import TurnExpander, TurnGenerator

# Expand template variables
expander = TurnExpander()
expanded_turns = expander.expand_turns(scenario["turns"], context)

# Register custom generators
@turn_generator("banking.fraud_scenarios")  
def generate_fraud_scenarios(params: dict, context: dict) -> list[dict]:
    return [{"turn_id": f"fraud_{i}", "user_input": f"..."} for i in range(count)]
```
"""

from .base import GeneratedTurn, GeneratorConfig, TurnGenerator, turn_generator
from .expander import TurnExpander
from .registry import GeneratorRegistry, get_global_registry

# Import built-in generators to register them
from . import builtin  # noqa: F401

__all__ = [
    "GeneratedTurn",
    "GeneratorConfig",
    "TurnGenerator",
    "turn_generator",
    "TurnExpander",
    "GeneratorRegistry",
    "get_global_registry",
]
