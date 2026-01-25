# Unified Agent Configuration Proposal

> **Status**: Draft v3 - Unified + Handoff Strategy Aware  
> **Scope**: Flatten VLAgent + ARTAgent into single structure  
> **Goal**: Orchestrator-agnostic agents, handoff-strategy-aware design

---

## Executive Summary

This proposal flattens `vlagent/` and `artagent/` into a **single unified agent structure** under `apps/artagent/agents/`. Agents are orchestrator-agnostic but handoff-strategy-aware, compatible with both:

- **SpeechCascade** (gpt_flow) → State-based handoffs via MemoManager
- **VoiceLive** (LiveOrchestrator) → Tool-based handoffs via HANDOFF_MAP

The key insight: **agents don't care about orchestration type** (how audio flows), but **do care about handoff strategy** (how they transfer control).

---

## Problem Statement

Currently we have **two separate agent implementations** with duplicated concepts:

```text
Current State (Duplicated):
├── apps/artagent/backend/src/agents/artagent/
│   ├── agents/*.yaml              # ARTAgent YAML configs
│   ├── prompt_store/templates/    # Jinja prompts
│   ├── tool_store/                # Tools + registry
│   └── base.py                    # ARTAgent class
│
├── apps/artagent/backend/src/agents/vlagent/
│   ├── agents/*.yaml              # VoiceLive YAML configs
│   ├── templates/                 # Jinja prompts  
│   ├── tool_store/                # Tools + registry (duplicated!)
│   └── base.py                    # AzureVoiceLiveAgent class
│
└── apps/artagent/backend/voice_channels/handoffs/
    ├── strategies/                # HandoffStrategy interface
    │   ├── tool_based.py          # VoiceLive: LLM calls handoff tools
    │   └── state_based.py         # ARTAgent: MemoManager state changes
    └── registry.py                # HANDOFF_MAP (tool_name → agent_name)
```

**Problems:**
1. Duplicate tool registries with same tools defined twice
2. Different YAML schemas between VLAgent and ARTAgent
3. Prompts scattered across multiple directories
4. No clear path to add agents that work with both orchestrators

---

## Proposed Structure: Unified Agents

Flatten into a single, orchestrator-agnostic structure:

```text
apps/artagent/agents/                     # ← Single source of truth
├── __init__.py
├── loader.py                            # Universal agent loader
├── base.py                              # UnifiedAgent class
├── _defaults.yaml                       # Shared defaults
│
├── fraud_agent/
│   ├── agent.yaml                       # Unified config
│   └── prompt.jinja
│
├── auth_agent/
│   └── agent.yaml
│
├── erica_concierge/
│   ├── agent.yaml
│   └── prompt.jinja
│
└── (more agents...)

apps/artagent/backend/src/agents/shared/  # ← Shared infrastructure
├── tool_registry.py                     # Single tool registry
└── prompt_manager.py                    # Unified prompt loading

apps/artagent/backend/voice_channels/     # ← Orchestration layer
├── handoffs/
│   ├── strategies/
│   │   ├── tool_based.py                # VoiceLive handoffs
│   │   └── state_based.py               # SpeechCascade handoffs
│   └── registry.py                      # Auto-generated from agents
└── orchestrators/
    ├── speech_cascade_adapter.py        # Uses UnifiedAgent
    └── voicelive_adapter.py             # Uses UnifiedAgent
```

**Key Insight**: Agents define **what** they do. Orchestrators decide **how** to run them.

---

## Handoff Strategy: The Key Differentiator

Agents don't care about orchestration (SpeechCascade vs VoiceLive), but they **do** need to declare how handoffs work:

### Strategy 1: Tool-Based Handoffs (VoiceLive)

The LLM explicitly calls handoff tools. The orchestrator intercepts and switches agents.

```yaml
# fraud_agent/agent.yaml
handoff:
  strategy: tool_based
  trigger: handoff_fraud_agent    # Other agents call this to reach FraudAgent
  
tools:
  - handoff_auth_agent           # FraudAgent can transfer to AuthAgent
  - handoff_erica_concierge      # FraudAgent can transfer back to Erica
```

**Flow:**
```
User: "I need help with my identity"
LLM: calls handoff_auth_agent(reason="identity verification needed")
Orchestrator: intercepts → switches to AuthAgent
AuthAgent: "I'll help verify your identity..."
```

### Strategy 2: State-Based Handoffs (SpeechCascade)

Code logic updates MemoManager state. Handler observes and switches.

```yaml
# fraud_agent/agent.yaml
handoff:
  strategy: state_based
  trigger: handoff_fraud_agent
  state_key: pending_handoff      # MemoManager key to watch
```

**Flow:**
```
User: "I think my card was stolen"
route_turn(): detects fraud intent → sets cm["pending_handoff"] = {target: "FraudAgent"}
Handler: observes state change → switches to FraudAgent
FraudAgent: "I'll help secure your account..."
```

### Strategy 3: Hybrid (Both)

Agents can support **both** strategies for maximum flexibility:

```yaml
# fraud_agent/agent.yaml
handoff:
  strategy: auto                  # Works with either orchestrator
  trigger: handoff_fraud_agent
  state_key: pending_handoff      # For state-based
  
tools:
  - handoff_auth_agent           # For tool-based (only used in VoiceLive)
```

The orchestrator adapter chooses the appropriate strategy at runtime.

---

## Unified Agent Schema: `agent.yaml`

The unified schema supports both orchestration patterns with sensible defaults:

### Complete Schema

```yaml
# apps/artagent/agents/fraud_agent/agent.yaml

# ═══════════════════════════════════════════════════════════════════════════════
# IDENTITY (Required)
# ═══════════════════════════════════════════════════════════════════════════════
name: FraudAgent
description: |
  Post-auth fraud detection specialist handling credit card fraud,
  identity theft, and suspicious activity investigation.

# ═══════════════════════════════════════════════════════════════════════════════
# GREETINGS (Used by both orchestrators)
# ═══════════════════════════════════════════════════════════════════════════════
greeting: "You're speaking with the Fraud Prevention desk. What happened?"
return_greeting: "Welcome back to Fraud Prevention. What's changed?"

# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF CONFIGURATION (Strategy-aware)
# ═══════════════════════════════════════════════════════════════════════════════
handoff:
  # How this agent receives handoffs
  trigger: handoff_fraud_agent    # Tool name that routes TO this agent
  
  # Strategy preference (auto = works with both)
  strategy: auto                  # auto | tool_based | state_based
  
  # For state-based orchestrators (SpeechCascade)
  state_key: pending_handoff      # MemoManager key to observe

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL CONFIGURATION (Optional - inherits from _defaults.yaml)
# ═══════════════════════════════════════════════════════════════════════════════
model:
  deployment_id: gpt-4o           # Azure OpenAI deployment
  temperature: 0.6                # Lower for consistent fraud investigation
  top_p: 0.9
  max_tokens: 4096

# ═══════════════════════════════════════════════════════════════════════════════
# VOICE CONFIGURATION (Optional - for TTS)
# ═══════════════════════════════════════════════════════════════════════════════
voice:
  type: azure-standard
  name: en-US-OnyxTurboMultilingualNeural
  rate: "0%"

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION CONFIGURATION (VoiceLive-specific, ignored by SpeechCascade)
# ═══════════════════════════════════════════════════════════════════════════════
session:
  modalities: [TEXT, AUDIO]
  input_audio_format: PCM16
  output_audio_format: PCM16
  
  input_audio_transcription_settings:
    model: azure-speech
    language: en-US
  
  turn_detection:
    type: azure_semantic_vad
    threshold: 0.48
    prefix_padding_ms: 220
    silence_duration_ms: 650
  
  tool_choice: auto

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS (Referenced by name from shared registry)
# ═══════════════════════════════════════════════════════════════════════════════
tools:
  # Core capabilities
  - analyze_recent_transactions
  - check_suspicious_activity
  - block_card_emergency
  - create_fraud_case
  - ship_replacement_card
  
  # Handoff tools (for tool-based strategy)
  - handoff_auth_agent            # Can transfer to auth
  - handoff_erica_concierge       # Can transfer back to concierge
  
  # Escalation
  - transfer_call_to_call_center
  - escalate_emergency
  - escalate_human

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT (Inline or file reference)
# ═══════════════════════════════════════════════════════════════════════════════
prompt: prompt.jinja              # Or inline: prompt: |
                                  #   You are a fraud specialist...
```

### Minimal Agent (Uses Defaults)

```yaml
# apps/artagent/agents/simple_agent/agent.yaml
name: SimpleAgent
description: A minimal agent example

handoff:
  trigger: handoff_simple_agent

tools:
  - escalate_human

prompt: |
  You are a helpful assistant at {{ institution_name }}.
  {{ caller_context }}
```

---

## Orchestrator Adapters

The orchestrators consume `UnifiedAgent` and apply the appropriate handoff strategy:

### SpeechCascade Adapter (gpt_flow)

```python
# voice_channels/orchestrators/speech_cascade_adapter.py

from apps.artagent.backend.agents.loader import discover_agents, AgentConfig
from voice_channels.handoffs.strategies import StateBasedHandoff

class SpeechCascadeOrchestrator:
    """Adapter for gpt_flow-style orchestration with state-based handoffs."""
    
    def __init__(self, agents_dir: str = "apps/artagent/agents"):
        self.agents = discover_agents(agents_dir)
        self.handoff_strategy = StateBasedHandoff()
        self.active_agent: str = "EricaConcierge"
    
    def to_artagent(self, config: AgentConfig) -> "ARTAgent":
        """Convert unified config to ARTAgent instance."""
        return ARTAgent(
            name=config.name,
            model_id=config.model_id,
            temperature=config.temperature,
            tools=config.get_tools(),
            prompt_template=config.prompt_template,
            voice_name=config.voice_name,
        )
    
    async def check_handoff(self, cm: MemoManager) -> Optional[str]:
        """Check MemoManager for pending handoff (state-based)."""
        pending = cm.get_value_from_corememory("pending_handoff")
        if pending:
            target = pending.get("target_agent")
            cm.update_corememory("pending_handoff", None)  # Clear
            return target
        return None
```

### VoiceLive Adapter

```python
# voice_channels/orchestrators/voicelive_adapter.py

from apps.artagent.backend.agents.loader import discover_agents, build_handoff_map, AgentConfig
from voice_channels.handoffs.strategies import ToolBasedHandoff

class VoiceLiveOrchestrator:
    """Adapter for VoiceLive SDK with tool-based handoffs."""
    
    def __init__(self, agents_dir: str = "apps/artagent/agents"):
        self.agents = discover_agents(agents_dir)
        self.handoff_map = build_handoff_map(self.agents)
        self.handoff_strategy = ToolBasedHandoff(handoff_map=self.handoff_map)
        self.active_agent: str = "EricaConcierge"
    
    def to_voicelive_agent(self, config: AgentConfig) -> "AzureVoiceLiveAgent":
        """Convert unified config to VoiceLive agent instance."""
        return AzureVoiceLiveAgent(
            name=config.name,
            greeting=config.greeting,
            return_greeting=config.return_greeting,
            tools=config.get_tools(),  # From shared registry
            prompt_template=config.prompt_template,
            session_config=config.session,
            voice_config=config.voice,
        )
    
    async def handle_tool_call(self, tool_name: str, args: dict) -> dict:
        """Handle tool calls, detecting handoffs."""
        if self.handoff_strategy.is_handoff_tool(tool_name):
            target = self.handoff_strategy.get_target_agent(tool_name)
            await self._switch_to_agent(target, args)
            return {"success": True, "handoff": True, "target": target}
        
        # Execute regular tool
        return await self.agents[self.active_agent].execute_tool(tool_name, args)
```

---

## UnifiedAgent Class

The core agent class that works with any orchestrator:

```python
# apps/artagent/agents/base.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

@dataclass
class HandoffConfig:
    """Handoff configuration for an agent."""
    trigger: str = ""                    # Tool name that routes TO this agent
    strategy: str = "auto"               # auto | tool_based | state_based
    state_key: str = "pending_handoff"   # For state-based handoffs

@dataclass  
class UnifiedAgent:
    """
    Orchestrator-agnostic agent configuration.
    
    Works with both:
    - SpeechCascade (gpt_flow) → State-based handoffs
    - VoiceLive (LiveOrchestrator) → Tool-based handoffs
    
    The agent itself doesn't know which orchestrator will run it.
    The orchestrator adapter handles the translation.
    """
    
    # Identity
    name: str
    description: str = ""
    
    # Greetings
    greeting: str = ""
    return_greeting: str = ""
    
    # Handoff configuration
    handoff: HandoffConfig = field(default_factory=HandoffConfig)
    
    # Model settings
    model_id: str = "gpt-4o"
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 4096
    
    # Voice settings (TTS)
    voice_name: str = "en-US-ShimmerTurboMultilingualNeural"
    voice_type: str = "azure-standard"
    voice_rate: str = "+0%"
    
    # Session settings (VoiceLive-specific)
    session: Dict[str, Any] = field(default_factory=dict)
    
    # Prompt template (raw Jinja content)
    prompt_template: str = ""
    
    # Tool names (resolved from shared registry)
    tool_names: List[str] = field(default_factory=list)
    
    # Source location
    source_dir: Optional[Path] = None
    
    # ─────────────────────────────────────────────────────────────────
    # Tool Integration (via shared registry)
    # ─────────────────────────────────────────────────────────────────
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool schemas from shared registry."""
        from apps.artagent.backend.src.agents.shared.tool_registry import (
            get_tools_for_agent,
        )
        return get_tools_for_agent(self.tool_names)
    
    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name."""
        from apps.artagent.backend.src.agents.shared.tool_registry import execute_tool
        return await execute_tool(tool_name, args)
    
    # ─────────────────────────────────────────────────────────────────
    # Prompt Rendering
    # ─────────────────────────────────────────────────────────────────
    
    def render_prompt(self, context: Dict[str, Any]) -> str:
        """Render prompt template with runtime context."""
        from jinja2 import Template
        template = Template(self.prompt_template)
        return template.render(**context)
    
    # ─────────────────────────────────────────────────────────────────
    # Handoff Helpers
    # ─────────────────────────────────────────────────────────────────
    
    def get_handoff_tools(self) -> List[str]:
        """Get list of handoff tool names this agent can call."""
        return [t for t in self.tool_names if t.startswith("handoff_")]
    
    def can_handoff_to(self, agent_name: str) -> bool:
        """Check if this agent has a handoff tool for the target."""
        trigger = f"handoff_{agent_name.lower()}"
        return any(trigger in t.lower() for t in self.tool_names)
```

---

## Shared Tool Registry

Single source of truth for all tools:

```python
# apps/artagent/backend/src/agents/shared/tool_registry.py

from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

@dataclass
class ToolDefinition:
    """A registered tool with schema and executor."""
    name: str
    schema: Dict[str, Any]          # OpenAI function calling schema
    executor: Callable              # Async function to execute
    tags: Set[str] = field(default_factory=set)  # e.g., {"banking", "handoff"}
    is_handoff: bool = False        # True for handoff tools

# Global registry
_TOOL_REGISTRY: Dict[str, ToolDefinition] = {}

def register_tool(
    name: str,
    schema: Dict[str, Any],
    executor: Callable,
    tags: Optional[Set[str]] = None,
    is_handoff: bool = False,
) -> None:
    """Register a tool in the shared registry."""
    _TOOL_REGISTRY[name] = ToolDefinition(
        name=name,
        schema=schema,
        executor=executor,
        tags=tags or set(),
        is_handoff=is_handoff,
    )

def get_tools_for_agent(tool_names: List[str]) -> List[Dict[str, Any]]:
    """Get OpenAI-compatible tool schemas for an agent."""
    tools = []
    for name in tool_names:
        if name in _TOOL_REGISTRY:
            tools.append({
                "type": "function",
                "function": _TOOL_REGISTRY[name].schema,
            })
    return tools

async def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name."""
    if name not in _TOOL_REGISTRY:
        return {"success": False, "error": f"Unknown tool: {name}"}
    
    tool = _TOOL_REGISTRY[name]
    return await tool.executor(**args)

def is_handoff_tool(name: str) -> bool:
    """Check if a tool is a handoff tool."""
    return name in _TOOL_REGISTRY and _TOOL_REGISTRY[name].is_handoff

def get_handoff_tools() -> Dict[str, str]:
    """Get all registered handoff tools."""
    return {
        name: tool.schema.get("description", "")
        for name, tool in _TOOL_REGISTRY.items()
        if tool.is_handoff
    }
```

### Tool Registration (Banking Example)

```python
# apps/artagent/backend/src/agents/shared/tools/banking.py

from ..tool_registry import register_tool

async def analyze_recent_transactions(
    account_id: str,
    days: int = 30,
    **kwargs,
) -> Dict[str, Any]:
    """Analyze recent transactions for suspicious patterns."""
    # Implementation...
    return {"success": True, "transactions": [...], "risk_score": 0.2}

# Register at module load
register_tool(
    name="analyze_recent_transactions",
    schema={
        "name": "analyze_recent_transactions",
        "description": "Analyze recent transactions for suspicious patterns",
        "parameters": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "days": {"type": "integer", "default": 30},
            },
            "required": ["account_id"],
        },
    },
    executor=analyze_recent_transactions,
    tags={"banking", "fraud"},
)
```

### Handoff Tool Registration

```python
# apps/artagent/backend/src/agents/shared/tools/handoffs.py

from ..tool_registry import register_tool

async def handoff_fraud_agent(
    reason: str,
    caller_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Transfer to FraudAgent for fraud investigation."""
    return {
        "success": True,
        "handoff": True,
        "target_agent": "FraudAgent",
        "handoff_context": {
            "reason": reason,
            "caller_name": caller_name,
            **(context or {}),
        },
    }

register_tool(
    name="handoff_fraud_agent",
    schema={
        "name": "handoff_fraud_agent",
        "description": "Transfer to Fraud Prevention specialist",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why transferring"},
                "caller_name": {"type": "string"},
            },
            "required": ["reason"],
        },
    },
    executor=handoff_fraud_agent,
    tags={"handoff"},
    is_handoff=True,
)
```

---

## Handoff Map: Auto-Generated

No manual `HANDOFF_MAP` maintenance. Built automatically from agent configs:

```python
# apps/artagent/agents/loader.py

def build_handoff_map(agents: Dict[str, UnifiedAgent]) -> Dict[str, str]:
    """
    Build handoff map from agent declarations.
    
    Each agent's handoff.trigger becomes a key in the map.
    
    Example output:
    {
        "handoff_fraud_agent": "FraudAgent",
        "handoff_auth_agent": "AuthAgent",
        "handoff_erica_concierge": "EricaConcierge",
    }
    """
    return {
        agent.handoff.trigger: agent.name
        for agent in agents.values()
        if agent.handoff.trigger
    }

# voice_channels/handoffs/registry.py now just imports from loader
from apps.artagent.backend.agents.loader import discover_agents, build_handoff_map

_agents = discover_agents()
HANDOFF_MAP = build_handoff_map(_agents)
```

---

## Adding a New Agent

**One folder, one file:**

```bash
mkdir apps/artagent/agents/new_specialist
touch apps/artagent/agents/new_specialist/agent.yaml
```

```yaml
# apps/artagent/agents/new_specialist/agent.yaml

name: NewSpecialist
description: Handles specialized domain X

greeting: "Hi, I'm the X specialist. How can I help?"
return_greeting: "Welcome back! What else can I help with?"

handoff:
  trigger: handoff_new_specialist
  strategy: auto

tools:
  - search_knowledge_base
  - escalate_human
  - handoff_erica_concierge    # Can transfer back

prompt: |
  You are a specialist in domain X at {{ institution_name }}.
  
  ## Context
  {{ caller_context }}
  
  ## Guidelines
  - Be helpful and professional
  - If outside scope, transfer to Erica
```

**Done.** The loader auto-discovers it. HANDOFF_MAP auto-updates.

---

## Comparison: Before vs After

| Aspect | VLAgent (Before) | ARTAgent (Before) | Unified (After) |
|--------|------------------|-------------------|-----------------|
| **Config location** | `vlagent/agents/` | `artagent/agents/` | `agents/` |
| **Prompt location** | `vlagent/templates/` | `artagent/prompt_store/` | Same folder as config |
| **Tool registry** | `vlagent/tool_store/` | `artagent/tool_store/` | `shared/tool_registry.py` |
| **Handoff config** | Implicit in HANDOFF_MAP | Via tool routing | Explicit in `handoff:` |
| **Orchestrator coupling** | VoiceLive-specific | gpt_flow-specific | Orchestrator-agnostic |
| **Files to create agent** | 2-3 files | 3-4 files | 1 file |

---

## Migration Path

### Phase 1: Unified Structure (Week 1)
1. Create `apps/artagent/agents/` with `loader.py` and `base.py`
2. Create `apps/artagent/backend/src/agents/shared/tool_registry.py`
3. Migrate one agent (FraudAgent) as proof of concept
4. Test with both SpeechCascade and VoiceLive

### Phase 2: Consolidate Tools (Week 2)
1. Merge `vlagent/tool_store/` and `artagent/tool_store/` into `shared/`
2. Register all tools in the shared registry
3. Update agents to use tool names only

### Phase 3: Migrate All Agents (Week 3)
1. Convert remaining VLAgent YAMLs to unified schema
2. Convert remaining ARTAgent YAMLs to unified schema
3. Deprecate old agent directories

### Phase 4: Update Orchestrators (Week 4)
1. Create `SpeechCascadeOrchestrator` adapter
2. Refactor `LiveOrchestrator` to use unified agents
3. Verify both orchestrators work with any agent

---

## Directory Structure: Final State

```text
apps/artagent/
├── agents/                              # ← Unified agent configs
│   ├── __init__.py
│   ├── loader.py                        # Auto-discovery
│   ├── base.py                          # UnifiedAgent class
│   ├── _defaults.yaml                   # Shared defaults
│   │
│   ├── erica_concierge/
│   │   ├── agent.yaml
│   │   └── prompt.jinja
│   ├── fraud_agent/
│   │   ├── agent.yaml
│   │   └── prompt.jinja
│   ├── auth_agent/
│   │   └── agent.yaml
│   └── (more agents...)
│
├── backend/
│   └── src/
│       └── agents/
│           └── shared/                  # ← Shared infrastructure
│               ├── tool_registry.py     # Single tool registry
│               ├── prompt_manager.py    # Unified prompt loading
│               └── tools/               # Tool implementations
│                   ├── banking.py
│                   ├── fraud.py
│                   ├── auth.py
│                   └── handoffs.py
│
└── voice_channels/                      # ← Orchestration layer
    ├── handoffs/
    │   ├── strategies/
    │   │   ├── base.py
    │   │   ├── tool_based.py            # VoiceLive handoffs
    │   │   └── state_based.py           # SpeechCascade handoffs
    │   ├── context.py
    │   └── registry.py                  # Auto-generated from agents
    │
    └── orchestrators/
        ├── base.py
        ├── speech_cascade_adapter.py    # Uses UnifiedAgent
        └── voicelive_adapter.py         # Uses UnifiedAgent
```

---

## Open Questions

1. **Tool implementations location**: Keep in `backend/src/agents/shared/tools/` or move to `agents/tools/`?
2. **Validation**: Add JSON Schema for `agent.yaml` validation?
3. **Inheritance**: Support `extends: other_agent` for specialized variants?
4. **Hot reload**: Support agent config changes without restart?

---

## Summary

### Key Principles

1. **Agents are orchestrator-agnostic**: They define capabilities, not how they're run
2. **Agents are handoff-strategy-aware**: They declare how they transfer control
3. **Single source of truth**: One `agents/` directory, one `tool_registry.py`
4. **Auto-discovery**: No manual registration, no scattered configs

### Adding a New Agent

```text
1. mkdir agents/my_agent
2. Create agents/my_agent/agent.yaml
3. (Optional) Create agents/my_agent/prompt.jinja for complex prompts
4. Done ✓

agent.yaml contains:
- name, description
- greeting, return_greeting
- handoff (trigger, strategy)
- model/voice overrides (optional)
- session config (optional, for VoiceLive)
- tools list (by name)
- prompt (inline or filename)
```

### Handoff Strategy Decision Tree

```text
                    ┌──────────────────┐
                    │ Agent Configured │
                    │   with handoff:  │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    ┌─────────▼─────────┐         ┌─────────▼─────────┐
    │ strategy: auto    │         │ strategy: explicit│
    │ (recommended)     │         │                   │
    └─────────┬─────────┘         └─────────┬─────────┘
              │                             │
    ┌─────────▼─────────┐         ┌─────────┴─────────┐
    │ Orchestrator picks│         │                   │
    │ appropriate       │         │                   │
    │ strategy at       │         │                   │
    │ runtime           │         │                   │
    └───────────────────┘   ┌─────▼─────┐   ┌─────────▼─────────┐
                            │tool_based │   │   state_based     │
                            │(VoiceLive)│   │ (SpeechCascade)   │
                            └───────────┘   └───────────────────┘
```
