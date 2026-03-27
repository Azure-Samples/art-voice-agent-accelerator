# ART Agent Accelerator with Foundry Agent and MCP Servers

## Overall Approach

The Foundry Agent v2 release brings compelling features for distributed, scalable agent deployments. Persistent Agents in Foundry wrap instructions and references to tools and knowledge bases.

This iteration will support existing agents and tools running in the current model, which are referred to as Local Agents, and new agents and tools running in Foundry Agent v2 and an MCP model, which are referred to here as Remote Agents.

MCP Services are the standardized wrapper for distributed tools. This approach introduces a new folder hierarchy, `apps/artagent/mcp` that will be for all MCP services. Under this will be folders for `common`, `insurance`, and `banking` to represent the major hierarchies and 3 distinct MCP servers. Each MCP server will run multiple tools. Each can be deployed into a new app service or, when enabled, 3 containers in a kubernetes cluster that can scale independently.

One refactor necessitated by the new roles and responsibilities of objects is that an orchestrator needs to be a little more purely route-and-transform where some agent management has crept in. Those agent-specific actions will be pushed down into the respective class hierarchy.

This shows a couple of agents and a couple of tools, but represents a pattern that is used to mirror all local agent functions as remote agents deployed in Foundry, and all local tools as tools in MCP servers.

## Changes and Additions

### Current Codebase Refactoring

#### apps/artagent/backend/registries/agentstore/base.py: class UnifiedAgent 

- Becomes an abstract base class with partial implementation
- Common functions and data that will be used for both local and remote agents are kept
- Functions and data specific to Local Agent are pushed into a new `class LocalAgent(UnifiedAgent)`
- Functions and data specific to Remote Agent are developed in a new `class RemoteAgent(UnifiedAgent)`

#### apps/artagent/voice/speech_cascasde/orchestrator.py and voicelive/orchestrator.py

- Some logic in orchestration.py is going to change based on Local versus Remote agent.
- Parallel logic already exists for VoiceLive versus Cascade. Adding in remote + local agent models may get messy. Some control loops or similiar-but-different functions may need to exist for interuptable (VoiceLive) versus complete transcript (Cascade), but would be encapsulated closer to the agent.
- To make orchestrator.py less complex with the new scenarios, push agent-specific tasks into UnifiedAgent hierarchy. This makes the code in orchestrator more specific to orchestration only and encapsulates agent-specific code in the right branch of that family tree.

### Infrastructure and new Deployments

#### Foundry Agents v2

##### Claims Specialist Agent

Refactor agent from `apps/artagent/backend/registries/agentstore/claims_specialist` to a persistent agent in Microsoft Agent Framework in `apps/artagent/foundry/agentstore/claims_specialist`

Tools will be mapped at design time (not runtime as exists now) via the MCP Registry.

#### Azure API Center as MCP Registry

An inventory in APIC will be used for an MPC registry. Thre will be 3 MCP Servers, one for common items, one for banking, and one for insurance.

## Questions and Assumptions

### How do we handle memory for agent context?

### Is there a Foundry Agent deployment besdies SDK available yet? 

Research or confirmation needed. Copilot says no. If not, it just necessitates writing a simple python class for deployments that might be invoked by azd.
