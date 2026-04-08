# Copilot Guide: Real-Time Voice Apps (Python 3.11, FastAPI, Azure)

## 📖 Required Reading Before Any Task

> **IMPORTANT:** Before making any changes, review these documents to understand the system and coding standards:

1. **[System Architecture](.github/instructions/system-architecture.instructions.md)** — Understand the system, data flows, and impact of changes
2. **[Coding Standards](.github/instructions/coding-standards.instructions.md)** — Quality guidelines and best practices

These documents ensure you understand **WHAT** the system is and **HOW** to write quality code for it.

---

## 🚨 The Leverage Pyramid — Why Order Matters

```
                    ┌─────────────────────┐
                    │     UNDERSTAND      │  ← Mistakes here = 1000s of bad lines
                    │  (Architecture)     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │       PLAN          │  ← Mistakes here = 100s of bad lines  
                    │  (Impact Analysis)  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │     IMPLEMENT       │  ← Mistakes here = 1 bad line
                    │  (Coding Standards) │
                    └─────────────────────┘
```

**A misunderstanding of the system architecture leads to thousands of bad lines of code.**
**A bad plan leads to hundreds of bad lines of code.**
**A bad line of code is just a bad line of code.**

Focus your attention on the TOP of the pyramid first.

---

## ✅ Workflow: Understand → Plan → Implement

### Step 1: UNDERSTAND (Highest Leverage)

Before writing ANY code:

1. Read **[system-architecture.instructions.md](.github/instructions/system-architecture.instructions.md)**
2. Identify which **layer** you're modifying (app, src, infra)
3. Understand the **data flow** for your change
4. Check the **Change Impact Matrix** — what else might break?

> **Ask yourself:** Do I understand WHY the system is structured this way?

### Step 2: PLAN (High Leverage)

Before implementing:

1. List the files you'll need to modify
2. Check if existing modules already solve your problem
3. Consider how your change affects **both orchestrators** (Cascade + VoiceLive)
4. Identify test cases for verification

> **Ask yourself:** If this plan is wrong, how many files will I need to undo?

### Step 3: IMPLEMENT (Execute)

Now write the code:

1. Follow **[coding-standards.instructions.md](.github/instructions/coding-standards.instructions.md)**
2. Use **skills/** for common tasks (create-agent, add-tool, add-endpoint)
3. Respect the design decisions (YAML agents, scenario handoffs, pooled clients)
4. Run tests and formatters before committing

---

## 🎯 Core Principles

- **Simplicity First:** Choose the simplest working solution. No over-engineering.
- **Reuse Before Create:** Check `src/`, `utils/`, `config/` before writing new code.
- **Async Everything:** All HTTP/WebSocket handlers must be `async`.
- **No Wrappers:** Do not create adapter/facade/manager classes around existing services.
- **No New Dependencies:** Do not add pip packages without explicit approval.

---

## 🎫 Issue Tracking with bd

**CRITICAL**: This project uses **bd** (beads) for ALL task tracking. Do NOT create markdown TODO lists.

### Essential Commands

```bash
# Find work
bd ready --json                    # Unblocked issues
bd stale --days 30 --json          # Forgotten issues

# Create and manage (ALWAYS include --description)
bd create "Title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd update <id> --status in_progress --json
bd close <id> --reason "Done" --json

# Search
bd list --status open --priority 1 --json
bd show <id> --json

# Sync (CRITICAL at end of session!)
bd sync  # Force immediate export/commit/push
```

### Git Workflow

- Always commit `.beads/issues.jsonl` with code changes
- Run `bd sync` at end of work sessions
- Install git hooks: `bd hooks install` (ensures DB ↔ JSONL consistency)

---

## 📚 Quick Reference

For detailed guidance, see the instruction files:

| Document | Purpose |
|----------|---------|
| [system-architecture.instructions.md](.github/instructions/system-architecture.instructions.md) | System overview, modules, data flows, impact matrix |
| [coding-standards.instructions.md](.github/instructions/coding-standards.instructions.md) | Code style, patterns, anti-patterns, testing |
| [api-endpoints.instructions.md](.github/instructions/api-endpoints.instructions.md) | API-specific conventions |

For task-specific guidance, see **skills/**:

| Skill | When to Use |
|-------|-------------|
| `create-agent` | Creating a new YAML-based agent |
| `add-tool` | Adding a tool to the registry |
| `add-endpoint` | Adding a FastAPI endpoint |
| `add-voice-handler` | Adding voice processing logic |

