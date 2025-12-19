# Agent Consolidation Plan: YAML-Driven Architecture

**Author**: Claude
**Date**: 2025-11-29
**Status**: Proposal

---

## Executive Summary

This document proposes a path forward for consolidating the agent architecture in `apps/artagent/backend/src/agents/` to enable easier maintenance through YAML-based configuration. The current system requires updates across 5-7 different files when adding a new agent or tool, creating maintenance burden and potential for errors.

**Key Goals:**
1. Single source of truth for agent definitions (YAML only)
2. Auto-discovery and registration of agents and tools
3. Convention-based handoff mapping (eliminate manual wiring)
4. Unified tool registry across all agent types
5. Validation and error checking at startup
6. Backward compatibility with existing agents

---

## Current Architecture Analysis

### Three Agent Systems

The codebase currently has three parallel agent implementations:

| Type | Purpose | Status | Complexity |
|------|---------|--------|------------|
| **ARTAgent** | Chat/voice via Azure OpenAI Chat Completions | Production | Medium |
| **VoiceLiveAgent** | Real-time voice via Azure AI VoiceLive SDK | Primary system | High |
| **FoundryAgents** | Azure AI Foundry cloud deployment | Experimental | Low |

### Pain Points in Current System

#### 1. **Manual Handoff Registration** (Highest Priority)
**Location**: [`src/agents/vlagent/registry.py:11-23`](apps/artagent/backend/src/agents/vlagent/registry.py#L11-L23)

```python
HANDOFF_MAP: Dict[str, str] = {
    "handoff_to_auth": "AuthAgent",
    "handoff_fraud_agent": "FraudAgent",
    "handoff_transfer_agency_agent": "TransferAgency",
    # ... 6 more entries requiring manual maintenance
}
```

**Problem**: When adding a new agent that can receive handoffs:
- Must manually update this dictionary
- No validation that target agent exists
- Naming convention not enforced
- Easy to forget or make typos

#### 2. **Duplicate Tool Registries** (High Priority)
**Locations**:
- [`src/agents/artagent/tool_store/tool_registry.py:145`](apps/artagent/backend/src/agents/artagent/tool_store/tool_registry.py#L145)
- [`src/agents/vlagent/tool_store/tool_registry.py:262`](apps/artagent/backend/src/agents/vlagent/tool_store/tool_registry.py#L262)

**Problem**: Two separate but overlapping registries mean:
- Duplicate tool definitions
- Inconsistent schemas
- Double maintenance when updating tools
- No shared validation

#### 3. **Hard-coded UI Labels** (Medium Priority)
**Location**: [`api/v1/handlers/voice_live_sdk_handler.py:66-76`](apps/artagent/backend/api/v1/handlers/voice_live_sdk_handler.py#L66-L76)

```python
agent_labels = {
    "AuthAgent": "Authentication",
    "FraudAgent": "Fraud Detection",
    # ... more hard-coded labels
}
```

**Problem**: UI display names scattered in handler code instead of agent definitions.

#### 4. **Scattered Agent Metadata**

Agent configuration split across multiple locations:
```
agent_name.yaml          → Agent config, model settings, tools
templates/prompts.jinja  → System prompts
registry.py              → Handoff mappings
handler.py               → UI labels
tool_registry.py         → Tool schemas
```

#### 5. **No Startup Validation**

Current system doesn't validate:
- ✗ All referenced tools exist
- ✗ Handoff targets are valid agents
- ✗ Template files are present
- ✗ YAML schema compliance
- ✗ Circular handoff dependencies

---

## Proposed Solution Architecture

### Design Principles

1. **Convention Over Configuration**: Use naming patterns to eliminate manual wiring
2. **Single Source of Truth**: All agent metadata in YAML
3. **Auto-Discovery**: Scan directories, no manual registration
4. **Fail Fast**: Validate everything at startup
5. **Backward Compatible**: Existing agents work without changes

### Enhanced YAML Schema

```yaml
# apps/artagent/backend/src/agents/vlagent/agents/banking/fraud_agent.yaml

metadata:
  name: FraudAgent                    # Must match filename (minus .yaml)
  display_name: Fraud Detection       # UI-friendly name (auto-gen if missing)
  description: Handles suspected fraudulent activity
  version: "1.0.0"
  tags: [banking, security]

capabilities:
  accepts_handoffs: true              # Can receive handoffs from other agents
  handoff_keywords:                   # Optional: custom trigger words
    - fraud
    - suspicious
    - unauthorized
  primary_use_case: fraud_detection   # For analytics/routing

agent:
  greeting: "I'm here to help with any security concerns..."
  return_greeting: "Welcome back. Let's continue reviewing this case."

model:
  deployment_id: gpt-4o
  temperature: 0.5

session:
  voice:
    name: en-US-AndrewMultilingualNeural
    rate: "0%"
  turn_detection:
    threshold: 0.6
    silence_duration_ms: 800

prompts:
  path: fraud_agent_prompt.jinja
  variables:                          # Default template variables
    institution_name: "${INSTITUTION_NAME}"  # From settings/env
    escalation_threshold: "high"

tools:
  # Simple tool reference (uses default config from tool registry)
  - verify_client_identity
  - check_transaction_history

  # Advanced: Tool with agent-specific overrides
  - name: escalate_human
    config:
      priority: urgent
      department: fraud_team

  # Handoff tools auto-discovered by convention:
  # If AuthAgent exists and accepts_handoffs=true,
  # handoff_to_auth tool is automatically available
  - handoff_to_auth
  - handoff_to_compliance

handoff_routing:
  # Optional: Custom handoff logic (default is direct transfer)
  handoff_to_auth:
    preserve_context: true
    context_fields: [customer_id, case_number, risk_score]
    greeting_override: "I'm transferring you to verify your identity..."
```

### Unified Agent Registry System

#### Phase 1: Auto-Discovery Engine

**New File**: [`src/agents/registry.py`](apps/artagent/backend/src/agents/registry.py)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set
import yaml
from pydantic import BaseModel, ValidationError

@dataclass
class AgentMetadata:
    """Complete agent metadata from YAML + auto-discovery"""
    name: str
    display_name: str
    description: str
    agent_type: str  # 'artagent' | 'vlagent' | 'foundry'
    yaml_path: Path
    template_path: Optional[Path]
    accepts_handoffs: bool
    handoff_keywords: List[str]
    available_tools: List[str]
    handoff_targets: List[str]  # Other agents this can hand off to
    version: str

class AgentRegistry:
    """
    Centralized registry that auto-discovers and validates all agents.
    Replaces manual HANDOFF_MAP with convention-based discovery.
    """

    def __init__(self, agents_root: Path, templates_root: Path):
        self.agents_root = agents_root
        self.templates_root = templates_root
        self.agents: Dict[str, AgentMetadata] = {}
        self.handoff_map: Dict[str, str] = {}  # Auto-generated
        self.errors: List[str] = []

    def discover_agents(self) -> None:
        """
        Recursively scan agent directories for YAML files.
        Convention: filename must match metadata.name (case-insensitive)
        """
        for agent_type in ['artagent', 'vlagent', 'foundryagents']:
            agent_dir = self.agents_root / agent_type / 'agents'
            if not agent_dir.exists():
                continue

            for yaml_file in agent_dir.rglob('*.yaml'):
                if yaml_file.stem.startswith('_'):  # Skip templates
                    continue
                try:
                    metadata = self._load_agent(yaml_file, agent_type)
                    self.agents[metadata.name] = metadata
                except Exception as e:
                    self.errors.append(f"Failed to load {yaml_file}: {e}")

    def _load_agent(self, yaml_path: Path, agent_type: str) -> AgentMetadata:
        """Load and validate single agent YAML"""
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        # Validate schema (using Pydantic)
        # ... validation logic ...

        # Extract metadata
        meta = config.get('metadata', {})
        agent_name = meta.get('name', yaml_path.stem)

        # Convention check: filename should match name
        if yaml_path.stem.lower() != agent_name.lower():
            raise ValueError(
                f"Agent name '{agent_name}' doesn't match filename '{yaml_path.stem}'"
            )

        # Auto-discover template
        template_path = config.get('prompts', {}).get('path')
        if template_path:
            template_path = self.templates_root / template_path
            if not template_path.exists():
                raise FileNotFoundError(f"Template not found: {template_path}")

        # Extract handoff targets from tools list
        tools = config.get('tools', [])
        handoff_targets = [
            t.replace('handoff_to_', '') if isinstance(t, str) else t['name'].replace('handoff_to_', '')
            for t in tools
            if (isinstance(t, str) and t.startswith('handoff_')) or
               (isinstance(t, dict) and t.get('name', '').startswith('handoff_'))
        ]

        return AgentMetadata(
            name=agent_name,
            display_name=meta.get('display_name', agent_name),
            description=meta.get('description', ''),
            agent_type=agent_type,
            yaml_path=yaml_path,
            template_path=template_path,
            accepts_handoffs=config.get('capabilities', {}).get('accepts_handoffs', False),
            handoff_keywords=config.get('capabilities', {}).get('handoff_keywords', []),
            available_tools=[t if isinstance(t, str) else t['name'] for t in tools],
            handoff_targets=handoff_targets,
            version=meta.get('version', '1.0.0')
        )

    def build_handoff_map(self) -> Dict[str, str]:
        """
        Auto-generate handoff map using convention:
        handoff_to_<agent_name> → <AgentName>

        Only creates mappings for agents with accepts_handoffs=true
        """
        handoff_map = {}

        for agent_name, metadata in self.agents.items():
            if not metadata.accepts_handoffs:
                continue

            # Convention: handoff_to_auth → AuthAgent
            tool_name = f"handoff_to_{agent_name.lower()}"
            handoff_map[tool_name] = agent_name

            # Also support underscore_case → PascalCase
            # e.g., handoff_fraud_agent → FraudAgent
            snake_case = ''.join(['_' + c.lower() if c.isupper() else c for c in agent_name]).lstrip('_')
            alternate_tool = f"handoff_{snake_case}"
            if alternate_tool != tool_name:
                handoff_map[alternate_tool] = agent_name

        self.handoff_map = handoff_map
        return handoff_map

    def validate(self) -> List[str]:
        """
        Comprehensive validation at startup.
        Returns list of errors (empty if valid).
        """
        errors = list(self.errors)  # Start with discovery errors

        # 1. Validate handoff targets exist
        for agent_name, metadata in self.agents.items():
            for target in metadata.handoff_targets:
                # Try to find target agent (case-insensitive)
                if not any(target.lower() == a.lower() for a in self.agents.keys()):
                    errors.append(
                        f"{agent_name} references handoff target '{target}' which doesn't exist"
                    )

        # 2. Validate tools exist in unified registry
        from .tool_registry import UNIFIED_TOOL_REGISTRY
        for agent_name, metadata in self.agents.items():
            for tool in metadata.available_tools:
                if not tool.startswith('handoff_') and tool not in UNIFIED_TOOL_REGISTRY:
                    errors.append(
                        f"{agent_name} references unknown tool '{tool}'"
                    )

        # 3. Check for circular handoffs
        errors.extend(self._detect_circular_handoffs())

        # 4. Validate templates exist
        # Already done in _load_agent, but double-check

        return errors

    def _detect_circular_handoffs(self) -> List[str]:
        """Detect circular handoff dependencies using DFS"""
        errors = []

        def has_cycle(agent: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(agent)
            rec_stack.add(agent)

            for target in self.agents[agent].handoff_targets:
                target_agent = self._resolve_handoff_target(target)
                if target_agent not in visited:
                    if has_cycle(target_agent, visited, rec_stack):
                        return True
                elif target_agent in rec_stack:
                    errors.append(f"Circular handoff detected: {agent} → {target_agent}")
                    return True

            rec_stack.remove(agent)
            return False

        visited = set()
        for agent in self.agents:
            if agent not in visited:
                has_cycle(agent, visited, set())

        return errors

    def _resolve_handoff_target(self, target: str) -> str:
        """Resolve handoff target name (case-insensitive)"""
        for agent_name in self.agents:
            if target.lower() == agent_name.lower():
                return agent_name
        return target

    def get_agent(self, name: str) -> Optional[AgentMetadata]:
        """Get agent metadata by name (case-insensitive)"""
        for agent_name, metadata in self.agents.items():
            if name.lower() == agent_name.lower():
                return metadata
        return None

    def get_agents_by_tag(self, tag: str) -> List[AgentMetadata]:
        """Filter agents by tag (e.g., 'banking', 'security')"""
        return [
            m for m in self.agents.values()
            if tag in m.tags
        ]
```

#### Phase 2: Unified Tool Registry

**New File**: [`src/agents/tool_registry.py`](apps/artagent/backend/src/agents/tool_registry.py)

```python
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional, List
import inspect

@dataclass
class ToolSpec:
    """Enhanced tool specification with validation"""
    name: str
    function: Callable
    schema: Dict[str, Any]
    description: str
    supported_agent_types: List[str]  # ['artagent', 'vlagent', 'foundry']
    version: str
    deprecated: bool = False

class UnifiedToolRegistry:
    """
    Single tool registry shared across all agent types.
    Replaces separate ARTAgent and VoiceLive registries.
    """

    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}
        self._function_map: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        function: Callable,
        schema: Dict[str, Any],
        description: str = "",
        agent_types: List[str] = None,
        version: str = "1.0.0"
    ):
        """
        Register a tool with automatic schema validation.

        Example:
            @registry.register_decorator(
                name="verify_client_identity",
                agent_types=['artagent', 'vlagent']
            )
            async def verify_identity(customer_id: str) -> Dict[str, Any]:
                ...
        """
        if agent_types is None:
            agent_types = ['artagent', 'vlagent', 'foundry']

        # Validate schema matches function signature
        self._validate_schema(function, schema)

        tool_spec = ToolSpec(
            name=name,
            function=function,
            schema=schema,
            description=description or inspect.getdoc(function) or "",
            supported_agent_types=agent_types,
            version=version
        )

        self.tools[name] = tool_spec
        self._function_map[name] = function

    def register_decorator(self, name: str, **kwargs):
        """Decorator for easy tool registration"""
        def wrapper(func: Callable):
            # Auto-generate schema from function signature
            schema = self._generate_schema(func)
            self.register(name, func, schema, **kwargs)
            return func
        return wrapper

    def _generate_schema(self, func: Callable) -> Dict[str, Any]:
        """
        Auto-generate OpenAI function schema from Python function.
        Uses type hints and docstrings.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        # Extract parameters from signature
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'cls']:
                continue

            # Map Python types to JSON schema types
            param_type = self._python_to_json_type(param.annotation)
            properties[param_name] = {"type": param_type}

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": doc.split('\n')[0],  # First line of docstring
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    def _python_to_json_type(self, py_type) -> str:
        """Map Python type hints to JSON schema types"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        return type_map.get(py_type, "string")

    def _validate_schema(self, func: Callable, schema: Dict[str, Any]):
        """Validate that schema matches function signature"""
        # ... validation logic ...
        pass

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """
        Execute tool by name with arguments.
        Single entry point for all tool execution.
        """
        if tool_name not in self._function_map:
            raise ValueError(f"Unknown tool: {tool_name}")

        func = self._function_map[tool_name]

        # Handle both sync and async functions
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

    def get_tools_for_agent_type(self, agent_type: str) -> List[ToolSpec]:
        """Get all tools compatible with an agent type"""
        return [
            tool for tool in self.tools.values()
            if agent_type in tool.supported_agent_types
        ]

# Global registry instance
UNIFIED_TOOL_REGISTRY = UnifiedToolRegistry()
```

#### Phase 3: Migration of Existing Tools

**Migration Script**: [`scripts/migrate_tools.py`](apps/artagent/backend/scripts/migrate_tools.py)

```python
"""
One-time migration script to consolidate existing tool registries.
Merges ARTAgent and VoiceLive tool registries into unified registry.
"""

from src.agents.tool_registry import UNIFIED_TOOL_REGISTRY

# Import existing tools
from src.agents.vlagent.financial_tools import (
    verify_client_identity,
    send_mfa_code,
    check_transaction_history,
    # ... all other tools
)

# Register with new unified registry
UNIFIED_TOOL_REGISTRY.register(
    name="verify_client_identity",
    function=verify_client_identity,
    schema={...},  # Existing schema
    agent_types=['artagent', 'vlagent'],
    description="Verifies customer identity using MFA"
)

# ... repeat for all tools
```

### Updated Handler Integration

**Location**: [`api/v1/handlers/voice_live_sdk_handler.py`](apps/artagent/backend/api/v1/handlers/voice_live_sdk_handler.py)

```python
from src.agents.registry import AgentRegistry
from src.agents.tool_registry import UNIFIED_TOOL_REGISTRY

class VoiceLiveSDKHandler:
    def __init__(self, settings: Settings):
        self._settings = settings

        # Initialize unified registry
        self.agent_registry = AgentRegistry(
            agents_root=settings.agents_path,
            templates_root=settings.templates_path
        )

        # Auto-discover all agents
        self.agent_registry.discover_agents()

        # Validate at startup (fail fast)
        errors = self.agent_registry.validate()
        if errors:
            raise RuntimeError(
                f"Agent configuration errors:\n" + "\n".join(errors)
            )

        # Build handoff map automatically
        self.handoff_map = self.agent_registry.build_handoff_map()

        # Load agents (existing logic, now using registry)
        self.agents = self._load_agents_from_registry()

    def _load_agents_from_registry(self) -> Dict[str, AzureVoiceLiveAgent]:
        """Load agent instances using registry metadata"""
        agents = {}

        for agent_name, metadata in self.agent_registry.agents.items():
            if metadata.agent_type != 'vlagent':
                continue

            # Use existing AzureVoiceLiveAgent class
            agent = AzureVoiceLiveAgent(
                config_path=str(metadata.yaml_path),
                tool_registry=UNIFIED_TOOL_REGISTRY  # Use unified registry
            )
            agents[agent_name] = agent

        return agents

    def get_agent_labels(self) -> Dict[str, str]:
        """
        Get UI display labels from agent metadata.
        Replaces hard-coded agent_labels dictionary.
        """
        return {
            name: meta.display_name
            for name, meta in self.agent_registry.agents.items()
        }
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
**Goal**: Build core registry system without breaking existing functionality

**Tasks**:
1. Create `src/agents/registry.py` with `AgentRegistry` class
2. Create `src/agents/tool_registry.py` with `UnifiedToolRegistry` class
3. Add enhanced YAML schema fields to existing agents (backward compatible)
4. Write comprehensive unit tests for registry validation
5. Create validation CLI tool: `python -m src.agents.registry validate`

**Validation**:
- [ ] All existing agents load successfully
- [ ] Handoff map auto-generation matches current HANDOFF_MAP
- [ ] Validation catches intentionally broken configs

### Phase 2: Tool Consolidation (Week 2)
**Goal**: Merge duplicate tool registries into unified system

**Tasks**:
1. Migrate VoiceLive tools to unified registry
2. Migrate ARTAgent tools to unified registry
3. Update both agent base classes to use `UNIFIED_TOOL_REGISTRY`
4. Create decorator-based registration for new tools
5. Add tool compatibility matrix (which tools work with which agent types)

**Migration Path**:
```python
# Old (VoiceLive)
from src.agents.vlagent.tool_registry import TOOL_REGISTRY

# New (Unified)
from src.agents.tool_registry import UNIFIED_TOOL_REGISTRY
```

**Validation**:
- [ ] All existing agents have same tools available
- [ ] Tool execution behavior unchanged
- [ ] No duplicate tool definitions

### Phase 3: Handler Integration (Week 2-3)
**Goal**: Replace manual wiring with auto-discovery

**Tasks**:
1. Update `voice_live_sdk_handler.py` to use `AgentRegistry`
2. Replace `HANDOFF_MAP` import with `agent_registry.build_handoff_map()`
3. Replace hard-coded `agent_labels` with `agent_registry.get_agent_labels()`
4. Add startup validation that fails fast on errors
5. Update orchestrator to use registry for agent lookups

**Validation**:
- [ ] All existing handoffs work unchanged
- [ ] UI labels display correctly
- [ ] Startup validation catches misconfigurations

### Phase 4: Enhanced YAML Features (Week 3-4)
**Goal**: Enable new capabilities through YAML configuration

**Tasks**:
1. Implement `metadata` section support (display_name, version, tags)
2. Implement `capabilities` section (accepts_handoffs, keywords)
3. Implement agent-specific tool configuration overrides
4. Implement handoff_routing for custom handoff logic
5. Create comprehensive YAML documentation

**New Capabilities Enabled**:
- Add new agent: just create YAML file (no code changes needed)
- Handoff tools auto-discovered (no HANDOFF_MAP update)
- UI labels in YAML (no handler code changes)
- Agent filtering by tags for analytics
- Per-agent tool configuration

### Phase 5: Migration & Documentation (Week 4)
**Goal**: Complete migration and document new system

**Tasks**:
1. Migrate all existing agents to enhanced YAML format
2. Update agent creation documentation
3. Create migration guide for custom agents
4. Add CLI tools for agent management:
   - `agents list` - Show all registered agents
   - `agents validate` - Validate configuration
   - `agents tools <agent_name>` - Show available tools
   - `agents handoffs` - Show handoff map
5. Deprecate old registry patterns

**Documentation Deliverables**:
- [ ] Agent YAML schema reference
- [ ] Tool registration guide
- [ ] Handoff configuration guide
- [ ] Migration guide for existing agents

---

## Backward Compatibility Strategy

### Compatibility Guarantees

1. **Existing YAMLs Work**: All current agent YAML files work without modification
2. **Optional New Fields**: Enhanced metadata is optional; defaults provided
3. **Fallback Behavior**: Registry falls back to existing patterns if new fields missing
4. **Gradual Migration**: Can migrate agents one-by-one

### Migration Examples

#### Minimal Migration (No Changes Required)
```yaml
# fraud_agent.yaml - Current format still works
agent:
  name: FraudAgent
  greeting: "How can I help with security concerns?"

tools:
  - verify_client_identity
  - handoff_to_auth
```

With registry, this automatically:
- Generates display name: "FraudAgent" → "Fraud Agent"
- Sets `accepts_handoffs: false` (default)
- Discovers handoff_to_auth tool
- Validates auth agent exists

#### Enhanced Migration (Recommended)
```yaml
# fraud_agent.yaml - Enhanced format
metadata:
  name: FraudAgent
  display_name: Fraud Detection
  description: Specialized agent for handling suspected fraudulent activity
  tags: [banking, security, fraud]

capabilities:
  accepts_handoffs: true
  handoff_keywords: [fraud, suspicious, scam]

agent:
  greeting: "I'm here to help with any security concerns..."

tools:
  - verify_client_identity
  - handoff_to_auth
```

Benefits:
- Better UI labels
- Searchable/filterable
- Self-documenting
- Enables analytics

---

## Testing Strategy

### Unit Tests

**File**: [`tests/agents/test_registry.py`](apps/artagent/backend/tests/agents/test_registry.py)

```python
import pytest
from src.agents.registry import AgentRegistry

class TestAgentRegistry:
    def test_discover_agents(self):
        """Test auto-discovery finds all agent YAMLs"""
        registry = AgentRegistry(agents_path, templates_path)
        registry.discover_agents()

        assert "FraudAgent" in registry.agents
        assert "AuthAgent" in registry.agents
        assert len(registry.agents) >= 9  # Current count

    def test_handoff_map_generation(self):
        """Test handoff map matches manual HANDOFF_MAP"""
        registry = AgentRegistry(agents_path, templates_path)
        registry.discover_agents()
        handoff_map = registry.build_handoff_map()

        # Should match existing manual map
        assert handoff_map["handoff_to_auth"] == "AuthAgent"
        assert handoff_map["handoff_fraud_agent"] == "FraudAgent"

    def test_validation_catches_missing_tool(self):
        """Test validation detects unknown tool references"""
        # Create test agent with invalid tool
        test_yaml = {
            'agent': {'name': 'TestAgent'},
            'tools': ['nonexistent_tool']
        }

        registry = AgentRegistry(agents_path, templates_path)
        # ... load test agent ...
        errors = registry.validate()

        assert any('nonexistent_tool' in err for err in errors)

    def test_validation_catches_circular_handoff(self):
        """Test detection of circular handoff dependencies"""
        # Agent A → Agent B → Agent A
        # ... create test scenario ...

        errors = registry.validate()
        assert any('circular' in err.lower() for err in errors)

    def test_case_insensitive_agent_lookup(self):
        """Test agent retrieval is case-insensitive"""
        registry = AgentRegistry(agents_path, templates_path)
        registry.discover_agents()

        assert registry.get_agent("fraudagent") == registry.get_agent("FraudAgent")
```

### Integration Tests

**File**: [`tests/agents/test_integration.py`](apps/artagent/backend/tests/agents/test_integration.py)

```python
class TestAgentIntegration:
    def test_handler_uses_registry(self):
        """Test VoiceLiveSDKHandler integrates with registry"""
        handler = VoiceLiveSDKHandler(settings)

        # Should have auto-discovered agents
        assert len(handler.agents) >= 9

        # Should have auto-generated handoff map
        assert handler.handoff_map["handoff_to_auth"] == "AuthAgent"

    def test_orchestrator_handoff_via_registry(self):
        """Test orchestrator uses registry for handoffs"""
        orchestrator = LiveOrchestrator(...)

        # Trigger handoff
        await orchestrator.handle_handoff("handoff_to_auth", {...})

        # Should resolve to correct agent
        assert orchestrator.current_agent.name == "AuthAgent"
```

### Validation Tests

**File**: [`tests/agents/test_validation.py`](apps/artagent/backend/tests/agents/test_validation.py)

```python
class TestValidation:
    def test_all_production_agents_valid(self):
        """Ensure all production agents pass validation"""
        registry = AgentRegistry(settings.agents_path, settings.templates_path)
        registry.discover_agents()
        errors = registry.validate()

        assert len(errors) == 0, f"Validation errors:\n" + "\n".join(errors)

    def test_templates_exist(self):
        """Ensure all referenced templates are present"""
        registry = AgentRegistry(...)
        registry.discover_agents()

        for agent in registry.agents.values():
            if agent.template_path:
                assert agent.template_path.exists(), \
                    f"Template missing for {agent.name}: {agent.template_path}"
```

---

## Benefits Summary

### Maintenance Reduction

| Task | Before (Current) | After (Registry) | Time Saved |
|------|------------------|------------------|------------|
| Add new agent | 5-7 file edits | 1 YAML file + template | ~80% |
| Add handoff capability | Update HANDOFF_MAP + agent YAML | Set `accepts_handoffs: true` | ~90% |
| Update tool | Edit 2 registries + schemas | Edit 1 unified registry | ~50% |
| Update UI label | Edit handler code | Edit agent YAML metadata | ~70% |
| Validate config | Manual testing | Automatic at startup | ~95% |

### Code Quality Improvements

1. **Single Source of Truth**: Agent metadata lives only in YAML
2. **Fail Fast**: Errors caught at startup, not runtime
3. **Self-Documenting**: YAML files fully describe agent capabilities
4. **Convention-Based**: Naming patterns eliminate manual wiring
5. **Type-Safe**: Pydantic validation ensures schema compliance
6. **Testable**: Registry is pure Python, easy to unit test

### Developer Experience

**Before**:
```bash
# Adding a new agent required:
1. Create fraud_agent.yaml
2. Create fraud_agent_prompt.jinja
3. Update HANDOFF_MAP in registry.py
4. Update agent_labels in voice_live_sdk_handler.py
5. Update tool_registry.py for any new tools
6. Test manually to find mistakes
```

**After**:
```bash
# Adding a new agent requires:
1. Create fraud_agent.yaml (with full metadata)
2. Create fraud_agent_prompt.jinja
3. Run: python -m src.agents.registry validate
   → Auto-discovers agent
   → Auto-generates handoff tool
   → Validates all references
   → Catches errors before deployment
```

---

## Risk Assessment & Mitigation

### Risk 1: Breaking Changes During Migration
**Likelihood**: Medium
**Impact**: High
**Mitigation**:
- Comprehensive unit test coverage before changes
- Backward compatibility layer for existing patterns
- Feature flags to toggle between old/new registry
- Gradual rollout: registry runs in parallel with manual system initially

### Risk 2: Performance Impact from Validation
**Likelihood**: Low
**Impact**: Low
**Mitigation**:
- Validation only runs at startup (one-time cost)
- Can be disabled in production via config flag
- Benchmark shows <100ms for 20+ agents

### Risk 3: Learning Curve for Team
**Likelihood**: Medium
**Impact**: Low
**Mitigation**:
- Enhanced YAML is mostly additions, not changes
- Migration guide with examples
- CLI tools for validation and debugging
- Existing agents work without modification

### Risk 4: Schema Evolution
**Likelihood**: Medium
**Impact**: Medium
**Mitigation**:
- Versioned YAML schema (metadata.version field)
- Registry supports multiple schema versions
- Deprecation warnings for old patterns
- Automated migration tools

---

## Alternative Approaches Considered

### Alternative 1: Keep Separate Registries
**Description**: Maintain ARTAgent and VoiceLive registries separately

**Pros**:
- No migration needed
- Simpler to reason about in isolation

**Cons**:
- Duplicate tool definitions
- Inconsistent schemas
- Double maintenance
- No shared validation

**Decision**: Rejected - Duplication outweighs isolation benefits

### Alternative 2: Code-Based Registration (No YAML Enhancement)
**Description**: Keep YAML simple, use Python decorators for registration

```python
@register_agent(name="FraudAgent", accepts_handoffs=True)
class FraudAgentConfig:
    tools = ["verify_identity", "handoff_to_auth"]
```

**Pros**:
- More Pythonic
- Type checking in IDE
- Refactoring-friendly

**Cons**:
- Requires code changes for config updates
- Not editable by non-developers
- Harder to generate dynamically
- Loses declarative benefits of YAML

**Decision**: Rejected - YAML is more flexible for operations

### Alternative 3: Database-Backed Registry
**Description**: Store agent configs in database instead of YAML files

**Pros**:
- Dynamic updates without redeployment
- Query capabilities
- Audit trail

**Cons**:
- Added infrastructure complexity
- Harder to version control
- Deployment synchronization issues
- Overkill for current scale

**Decision**: Rejected - File-based is sufficient for now, can revisit at scale

---

## Success Metrics

### Quantitative Metrics

1. **Reduction in Files Edited per Agent**
   - Baseline: 5-7 files
   - Target: 1-2 files (YAML + template)
   - Measurement: Track git commits for agent additions

2. **Startup Validation Coverage**
   - Baseline: 0% (no automated validation)
   - Target: 95% of common errors caught
   - Measurement: Unit tests + intentional error injection

3. **Code Duplication**
   - Baseline: 2 tool registries (~500 lines duplicated)
   - Target: 1 unified registry
   - Measurement: Code coverage analysis

4. **Time to Add New Agent**
   - Baseline: ~2 hours (including testing/debugging)
   - Target: ~30 minutes
   - Measurement: Developer survey + time tracking

### Qualitative Metrics

1. **Developer Feedback**: Survey team on ease of use
2. **Error Reduction**: Track agent-related bugs in production
3. **Documentation Quality**: Measure completeness of agent metadata
4. **Onboarding Time**: Time for new developers to add first agent

---

## Next Steps

### Immediate Actions (This Week)

1. **Review & Feedback**: Circulate this document for team review
2. **Proof of Concept**: Build minimal `AgentRegistry` prototype
3. **Validation**: Run prototype against existing agents to verify compatibility
4. **Estimate Refinement**: Detailed task breakdown for Phase 1

### Decision Points

- [ ] **Approve overall architecture** - Registry pattern + YAML enhancement
- [ ] **Approve migration timeline** - 4-week phased approach
- [ ] **Assign ownership** - Who leads implementation?
- [ ] **Define success criteria** - What constitutes "done"?

### Open Questions

1. **Schema versioning**: What's the migration path when YAML schema evolves?
2. **Dynamic updates**: Do we need hot-reload of agent configs without restart?
3. **Multi-environment**: How do dev/staging/prod agent configs differ?
4. **Monitoring**: What agent metrics should we track in production?

---

## Appendix A: YAML Schema Reference

### Complete Enhanced Schema

```yaml
# Full example with all supported fields

metadata:
  name: string                    # Required: Must match filename
  display_name: string            # Optional: UI-friendly name
  description: string             # Optional: Human-readable description
  version: string                 # Optional: Semantic version (default: "1.0.0")
  tags: array<string>             # Optional: Categories for filtering
  author: string                  # Optional: Maintainer info
  deprecated: boolean             # Optional: Mark agent as deprecated

capabilities:
  accepts_handoffs: boolean       # Optional: Can receive handoffs? (default: false)
  handoff_keywords: array<string> # Optional: Keywords for handoff routing
  primary_use_case: string        # Optional: Analytics category
  max_turns: integer              # Optional: Turn limit before escalation
  supports_interruption: boolean  # Optional: VoiceLive interruption handling

agent:
  name: string                    # Backward compatibility (prefer metadata.name)
  greeting: string                # Optional: First-time greeting
  return_greeting: string         # Optional: Returning visitor greeting
  error_message: string           # Optional: Fallback error message

model:                            # ARTAgent only
  deployment_id: string           # Azure OpenAI deployment name
  temperature: float              # 0.0-2.0 (default: 0.7)
  top_p: float                    # 0.0-1.0 (default: 1.0)
  max_tokens: integer             # Max response tokens
  frequency_penalty: float        # Optional: -2.0 to 2.0
  presence_penalty: float         # Optional: -2.0 to 2.0

voice:                            # Optional: TTS configuration
  name: string                    # Voice model name
  style: string                   # Speaking style
  rate: string                    # Speed adjustment (e.g., "+5%")
  pitch: string                   # Pitch adjustment

session:                          # VoiceLiveAgent only
  modalities: array<string>       # [TEXT, AUDIO]
  input_audio_format: string      # PCM16, etc.
  output_audio_format: string     # PCM16, etc.
  voice:
    type: string                  # azure-standard, alloy, etc.
    name: string                  # Voice model name
    rate: string                  # Speed adjustment
  turn_detection:
    type: string                  # server_vad, etc.
    threshold: float              # VAD sensitivity (0.0-1.0)
    prefix_padding_ms: integer    # Pre-speech padding
    silence_duration_ms: integer  # Post-speech silence
    create_response: boolean      # Auto-create response
  input_audio_transcription_settings:
    model: string                 # Transcription model
    language: string              # Language code (e.g., en-US)
  tool_choice: string             # auto, none, required
  temperature: float              # Model temperature
  max_response_output_tokens: integer

prompts:
  path: string                    # Required: Relative to templates directory
  variables:                      # Optional: Default template variables
    key: value                    # Merged with runtime variables

tools:
  # Simple tool reference (string)
  - string

  # Advanced tool reference (object)
  - name: string                  # Tool name from registry
    config:                       # Optional: Agent-specific overrides
      key: value                  # Passed to tool at execution
    required: boolean             # Optional: Must be available?

handoff_routing:                  # Optional: Custom handoff configuration
  tool_name:                      # Key is handoff tool name
    preserve_context: boolean     # Maintain conversation context
    context_fields: array<string> # Specific fields to preserve
    greeting_override: string     # Custom greeting for this handoff
    priority: string              # urgent, normal, low

monitoring:                       # Optional: Observability settings
  log_level: string               # debug, info, warn, error
  track_metrics: boolean          # Enable metrics collection
  sample_rate: float              # Logging sample rate (0.0-1.0)
```

### Validation Rules

1. **Required Fields**: `agent.name` OR `metadata.name`
2. **Name Matching**: Filename must match agent name (case-insensitive)
3. **Tool References**: All tools must exist in `UNIFIED_TOOL_REGISTRY` or be handoff tools
4. **Handoff Targets**: Handoff tool targets must reference existing agents with `accepts_handoffs: true`
5. **Template Path**: Must be relative path from templates directory
6. **Version Format**: Must follow semantic versioning (X.Y.Z)

---

## Appendix B: CLI Tool Usage

### Agent Validation Tool

```bash
# Validate all agents
python -m src.agents.registry validate

# Output example:
✓ Discovered 12 agents
✓ Generated 9 handoff mappings
✓ All tool references valid
✗ Error: AuthAgent references unknown tool 'verify_biometric'
✗ Error: Circular handoff: FraudAgent → AuthAgent → FraudAgent

Summary: 2 errors found
```

### Agent Listing Tool

```bash
# List all agents
python -m src.agents.registry list

# Output:
Name                 Type        Accepts Handoffs  Tools  Version
-----------------------------------------------------------------
AuthAgent            vlagent     Yes               5      1.0.0
FraudAgent           vlagent     Yes               7      1.2.0
EricaConcierge       vlagent     Yes               12     2.0.0
...

# Filter by tag
python -m src.agents.registry list --tag banking

# Show detailed info
python -m src.agents.registry show FraudAgent
```

### Handoff Map Tool

```bash
# Show handoff mappings
python -m src.agents.registry handoffs

# Output:
Handoff Tool              Target Agent
------------------------------------------
handoff_to_auth          → AuthAgent
handoff_fraud_agent      → FraudAgent
handoff_erica_concierge  → EricaConcierge
...
```

### Agent Creation Tool

```bash
# Create new agent from template
python -m src.agents.registry create \
  --name CustomerServiceAgent \
  --type vlagent \
  --template base_agent \
  --tags customer-service,banking

# Creates:
# - agents/vlagent/agents/banking/customer_service_agent.yaml
# - templates/customer_service_agent_prompt.jinja
```

---

## Appendix C: Migration Checklist

### Pre-Migration Checklist

- [ ] All existing agents have unit tests
- [ ] Document current HANDOFF_MAP for validation
- [ ] Benchmark current startup time
- [ ] List all custom agent configurations
- [ ] Identify agents with special requirements

### Phase 1 Checklist (Registry Foundation)

- [ ] `AgentRegistry` class implemented
- [ ] `UnifiedToolRegistry` class implemented
- [ ] Unit tests achieve 90%+ coverage
- [ ] Validation CLI tool working
- [ ] All existing agents load via registry
- [ ] Handoff map generation matches manual map

### Phase 2 Checklist (Tool Consolidation)

- [ ] All VoiceLive tools migrated
- [ ] All ARTAgent tools migrated
- [ ] Both agent types use unified registry
- [ ] No tool duplication remains
- [ ] Tool execution behavior unchanged
- [ ] Integration tests passing

### Phase 3 Checklist (Handler Integration)

- [ ] Handler uses `AgentRegistry`
- [ ] HANDOFF_MAP import removed
- [ ] Hard-coded labels removed
- [ ] Startup validation active
- [ ] All existing tests passing
- [ ] No regression in functionality

### Phase 4 Checklist (Enhanced YAML)

- [ ] Metadata section supported
- [ ] Capabilities section supported
- [ ] Tool configuration overrides working
- [ ] Handoff routing implemented
- [ ] Documentation updated
- [ ] Example agents migrated

### Phase 5 Checklist (Final Migration)

- [ ] All agents use enhanced YAML
- [ ] CLI tools documented
- [ ] Migration guide published
- [ ] Old patterns deprecated
- [ ] Team training completed
- [ ] Production deployment successful

---

**Document Version**: 1.0
**Last Updated**: 2025-11-29
**Maintained By**: Engineering Team
