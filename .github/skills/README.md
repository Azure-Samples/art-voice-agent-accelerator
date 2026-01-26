# Skills Directory

Task-oriented skills for AI assistants working with this codebase.

## Philosophy

**Code is documentation.** Skills provide focused task guidance; the codebase itself is the reference. Agents should explore existing patterns via:

- `registries/toolstore/registry.py` - Tool registration patterns
- `registries/agentstore/base.py` - Agent schema and helpers
- `registries/agentstore/*/agent.yaml` - Agent configuration examples

## Available Skills

| Skill | Description |
| ----- | ----------- |
| `add-component` | Add React component with Material UI |
| `add-endpoint` | Add FastAPI endpoint |
| `add-evaluation` | Create evaluation scenario |
| `add-message-handler` | Handle new WebSocket message type |
| `add-tool` | Add tool to agent registry |
| `add-voice-handler` | Add voice module feature |
| `create-agent` | Create complete agent with tools |

## Skill Conventions

Each skill lives in `.github/skills/{skill-name}/SKILL.md` with frontmatter:

```yaml
---
name: skill-name
description: Brief task description
---
```

**Supported attributes:** `name`, `description`, `compatibility`, `license`, `metadata`

## Naming

- `add-*` for creating new items (add-endpoint, add-tool)
- `create-*` for complex multi-file creation (create-agent)
- Verb-noun pattern, lowercase, hyphenated
