---
name: test-and-document
description: Require relevant tests and documentation updates for any code or config change, and report what was run.
---

# Test and Document Skill

Apply these rules to every change.

## Rules
- Select and run the most relevant tests for the change.
- Update documentation or CHANGELOG.md when behavior or usage changes.
- Report tests run in the response; if tests are skipped, state why and what should be run.

## Test Selection
- Backend logic: run targeted pytest under tests/ or the most relevant file set.
- Evaluation scenarios: run pytest tests/evaluation/test_scenarios.py -v.
- Load testing: follow docs/testing/index.md and docs/operations/load-testing.md.
- Frontend changes: check apps/artagent/frontend/README.md or package.json for test commands.

## Documentation Targets
- docs/ for user-facing behavior changes.
- CHANGELOG.md if your workflow requires release notes.
- README.md if setup or usage changes.

## Output Checklist
- Tests run: list commands.
- Documentation updated: list files.
