---
name: Weekly Voice Live roadmap
description: Compare public Voice Live documentation with the accelerator and maintain a prioritized, deduplicated integration backlog.
on:
  schedule:
    - cron: "17 9 * * 1"
  workflow_dispatch:
    inputs:
      dry_run:
        description: Preview issue proposals and comments without publishing them
        type: boolean
        default: true
        required: true
permissions:
  contents: read
  issues: read
  pull-requests: read
engine:
  id: copilot
  agent: voicelive-roadmap
imports:
  - .github/agents/voicelive-roadmap.agent.md
strict: true
timeout-minutes: 30
concurrency:
  group: voicelive-roadmap-${{ github.repository }}
  cancel-in-progress: false
  job-discriminator: ${{ github.run_id }}
network:
  allowed:
    - defaults
    - github
    - learn.microsoft.com
    - aka.ms
tools:
  github:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    toolsets: [repos, issues, pull_requests]
    # Read outsider/bot issues too: hiding them defeats semantic deduplication.
    # All content remains untrusted and no code-writing outputs are available.
    min-integrity: none
    allowed-repos:
      - aiappsgbbfactory/art-voice-agent-accelerator
      - microsoftdocs/azure-ai-docs
      - azure/azure-sdk-for-python
      - azure-samples/*
  web-fetch:
  bash: ["date -u", "git rev-parse HEAD", "git ls-files", "git grep:*"]
  edit: false
safe-outputs:
  github-token: ${{ secrets.GITHUB_TOKEN }}
  staged: ${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}
  # Operational failures belong in Actions, not the feature backlog.
  report-failure-as-issue: false
  report-failed-jobs: false
  missing-tool:
    create-issue: false
  missing-data:
    create-issue: false
  report-incomplete:
    create-issue: false
  noop:
    report-as-issue: false
  allowed-domains: [learn.microsoft.com]
  allowed-github-references: [repo]
  mentions: false
  create-issue:
    title-prefix: "[VoiceLive] "
    labels: [enhancement]
    max: 5
    expires: false
    deduplicate-by-title: true
  add-comment:
    target: "*"
    max: 10
  messages:
    append-only-comments: true
---

# Weekly Voice Live integration review

Follow the imported `voicelive-roadmap` agent's research, evidence, prioritization,
deduplication, and append-only update contract.

Repository: ${{ github.repository }}
Examined commit: obtain the actual checkout SHA with `git rev-parse HEAD`.
Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}

Analyze the checked-out revision, not a remembered deployment or an upstream
repository selected implicitly by GitHub CLI. Scheduled runs examine the default
branch; manual runs examine the selected ref and must identify that revision.
All issue operations must target this workflow's repository, never upstream.

Start with the public Python integration guide, then follow its relevant official
Voice Live documentation and SDK links. Evaluate features and preview/GA changes
against the current native Voice Live agent implementation, shared agent schema,
authoring experience, configuration, and both orchestrators' runtime contracts.

Do not limit discovery to the last seven days: previously deferred candidates and
baseline gaps still deserve assessment. Existing issues and their comments are
the durable change history. A fresh timestamp without new evidence is a no-op.
Finish source retrieval and existing-issue discovery before requesting writes.

Propose at most five new issues and ten update comments, highest priority first.
Use only `create_issue` and `add_comment` safe outputs for publication. Do not use
`add_comment` on pull requests; PRs are read-only evidence. Do not rewrite, close,
reopen, relabel, assign, or implement existing issues. Do not create a weekly
summary issue. Record the summary in the run output; use `noop` for a complete
scan with no actionable delta and `missing_data` for incomplete/blocked research.

Manual runs default to staged previews. Still request the same structured safe
outputs in dry-run mode: the publisher, not prompt obedience, prevents writes.
