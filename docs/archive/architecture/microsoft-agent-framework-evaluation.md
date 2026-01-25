# Microsoft Agent Framework Fit Check

Status: Draft  
Author: Codex  
Scope: ARTAgent stack (`apps/artagent/backend/src/agents`) and orchestrator (`apps/artagent/backend/src/orchestration/artagent`)

> Note: The workstation has restricted network access, so this write-up is based on recent Microsoft/Azure agent SDK patterns (`azure.ai.agents`, Azure AI Agent Service) plus code already present in this repo (see `agents/foundryagents`). Please cross-check against the latest official docs.

## Current System Snapshot
- **Agent shape**: YAML-driven `ARTAgent` (`artagent/base.py`) with prompt templates in `prompt_store/templates`, tools registered in `tool_store/tool_registry.py`, and per-agent config files in `artagent/agents/*.yaml`.
- **Invocation**: `orchestration/artagent/gpt_flow.py` streams AOAI responses, handles tool calls via `tool_store.tools_helper`, and emits TTS/events to websockets.
- **Routing**: `orchestration/artagent/orchestrator.py` routes each turn using `registry.py` (active_agent in `MemoManager`), runs auth first, then specialist handlers (fraud, agency, compliance, trading).
- **Handoffs**: Tool-based handoffs mapped in `voice_channels/handoffs/registry.py`; orchestrator switches agents when tools fire.
- **Parallel stack**: `agents/foundryagents/agent_builder.py` already knows how to turn ART-style YAML + tool registry into `azure.ai.agents` constructs (FunctionTool/ToolSet) for Azure AI Agent Service, but it is a one-off utility, not integrated into the runtime.

Pain points already noted in `docs/architecture/agent-configuration-proposal.md` (multiple files per agent, manual handoff map updates, scattered prompts).

## Microsoft Agent Framework (Azure AI Agents) - Relevant Bits
- **Artifacts**: Agents (name, instructions, tools), Threads (conversation state), Messages, Runs (invocations), Files/Vector stores. Tools are registered via `FunctionTool`/`ToolSet`; SDK is `azure.ai.agents`.
- **Execution model**: You create an agent once, then create threads and runs to get responses. Tool calls are surfaced in the run; you resolve them and resume the run.
- **Local vs hosted**: The SDK runs locally but calls the hosted Agent Service (backed by AOAI). There is no fully offline runtime; “local” means you can develop/debug from your machine while the control plane stays in Azure.
- **Telemetry/observability**: Built-in request IDs, run status, and event streaming; easier to trace than custom WebSocket envelopes, but you lose some control over low-level TTS/event pacing unless you layer it back in.

## Fit Analysis vs Current Stack
- **Config parity**: Your YAML already captures agent metadata, model, and tool list. It maps cleanly to `AgentsClient.create_agent(...)` (see `foundryagents/agent_builder.py`), but prompts/templates would be flattened into a single `instructions` string. The in-repo proposal to inline prompts into `agent.yaml` aligns well with the Agent Service shape.
- **Tooling**: Existing tool registries can be wrapped with the `json_safe_wrapper` pattern already in `foundryagents/agent_builder.py`. Handoff tools would need to trigger client-side orchestrator logic to switch target agents or threads.
- **State/memory**: Current system uses `MemoManager` + Redis and explicit `cm_set/cm_get`. Agent Service uses Threads as the state container. Migrating would require an adapter layer that mirrors `MemoManager` state into thread messages/metadata, or a dual-write phase.
- **Streaming/TTS**: `gpt_flow.py` is tightly coupled to WebSocket envelopes, ACS TTS chunking, and latency tooling. Agent Service run streaming would need a translation layer to keep ACS semantics; otherwise you lose the fine-grained control you currently have.
- **Handoffs/Orchestration**: Today’s routing is explicit (`active_agent` in cm + tool-based handoffs). Agent Service expects a single agent per run/thread; multi-agent workflows either happen inside one agent’s policy or through client-side orchestration (your current pattern). You would still keep a custom orchestrator to hop between agents.
- **Operational cost/lock-in**: Migrating core runtime to Agent Service ties you to Azure’s run/threads primitives and limits offline/local mockability. Benefits are managed persistence, telemetry, and a standard SDK, but you’d refactor a lot of glue that currently works.

## Effort/Value Call
- **Value**: Highest if you want managed persistence/threads, standardized tool contract, and easier integration with other Azure AI features (files/vector stores) with less custom infra.
- **Effort**: Medium-high for full migration. Major refactors: replace `MemoManager` state with threads, rebuild `gpt_flow` atop run streaming, wrap tools with Agent Service contracts, and rework handoff flow. The existing ARTAgent restructure (one-folder-per-agent) still delivers modularity with lower cost.
- **Risk**: Potential loss of ACS/latency-specific behaviors during migration; tighter Azure dependency; less control over token streaming cadence.

## Suggested Path (Incremental)
1) **Pilot**: Use `agents/foundryagents/agent_builder.py` to generate one Agent Service agent from an existing YAML (e.g., `artagent/agents/auth_agent.yaml`) and run a local notebook/service that proxies runs back through your WebSocket/TTS pipeline. Measure latency, tool-call fidelity, and handoff viability.
2) **Adapter layer**: Prototype a minimal adapter that maps `MemoManager` state ↔ Agent Service threads/messages while keeping current orchestrator semantics. This de-risks state migration.
3) **Decision gate**: If the pilot shows acceptable latency and manageable handoff logic, plan a phased migration starting with non-critical specialists. If not, continue with the in-repo modularization proposal (`docs/architecture/agent-configuration-proposal.md`) and keep the Agent Service as an optional integration path.

## Bottom Line
- The current ARTAgent stack already supports modular agents; the one-folder-per-agent proposal will simplify authoring without heavy refactors.
- Moving the core runtime onto Microsoft’s Agent Framework/Service is a bigger lift and mainly pays off if you want managed threads, built-in telemetry, and tighter Azure alignment. Recommended next step is a contained pilot rather than a wholesale rewrite.***
