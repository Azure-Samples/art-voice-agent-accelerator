---
name: repo-navigation
description: Locate where to edit common features (agents, tools, scenarios, frontend, backend, infra, tests, docs) in this repo.
---

# Repo Navigation Skill

Use the repository map to guide file discovery and edits.

## Primary Reference
- docs/guides/repository-structure.md

## Common Edit Locations
- Agents: apps/artagent/backend/registries/agentstore/
- Tools: apps/artagent/backend/registries/toolstore/
- Scenarios: apps/artagent/backend/registries/scenariostore/
- API endpoints: apps/artagent/backend/api/v1/endpoints/
- Backend entry point: apps/artagent/backend/main.py
- Backend configuration: apps/artagent/backend/config/
- Frontend app: apps/artagent/frontend/
- Infrastructure: infra/ and azure.yaml
- Shared config: config/
- Tests: tests/
- Docs: docs/
- Samples: samples/
- DevOps scripts: devops/

## Guidance
- Start with the closest README in the target area before editing.
- Use `rg` to find existing patterns before adding new ones.
