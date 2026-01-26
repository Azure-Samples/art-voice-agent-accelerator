# Agent Evaluation Overview

Evaluate voice agent orchestration quality using YAML-based scenarios, automated testing, and CI/CD integration.

## Overview

The evaluation framework measures agent performance across multiple dimensions without modifying production code:

| Category | Metrics |
|----------|---------|
| **Tool Accuracy** | Precision, recall, efficiency |
| **Groundedness** | Response accuracy vs evidence |
| **Latency** | E2E P50/P95/P99, TTFT |
| **Verbosity** | Token usage, budget compliance |
| **Cost** | Per-model breakdown, USD estimates |
| **Handoffs** | Correct agent routing |

!!! tip "Framework Documentation"
    For detailed YAML format, CLI reference, and implementation details, see the **[Evaluation Framework Guide](evaluation.md)**.

---

## Quick Start

### Run a Scenario

```bash
# Single scenario
python -m tests.evaluation.cli run \
  --input tests/evaluation/scenarios/smoke/basic_identity_verification.yaml

# A/B model comparison (auto-detected)
python -m tests.evaluation.cli run \
  --input tests/evaluation/scenarios/ab_tests/fraud_detection_comparison.yaml
```

### Run via pytest

```bash
# All evaluation tests
pytest tests/evaluation/test_scenarios.py -v -m evaluation

# Specific scenario
pytest tests/evaluation/test_scenarios.py -k "banking_multi_agent" -v

# With Azure AI Foundry submission
pytest tests/evaluation/test_scenarios.py --submit-to-foundry -v
```

---

## Available Scenarios

| Scenario | Type | Description |
|----------|------|-------------|
| `basic_identity_verification` | Smoke | Quick validation (~2 turns) |
| `banking_multi_agent` | Session | Multi-agent banking flow |
| `all_agents_discovery` | Session | Discover and test all agents |
| `fraud_detection_comparison` | A/B | GPT-4o vs GPT-5.1 comparison |

Scenarios are located in `tests/evaluation/scenarios/`:

```
scenarios/
├── smoke/                    # Quick validation tests
├── session_based/            # Multi-turn, multi-agent flows
└── ab_tests/                 # Model comparisons
```

---

## GitHub Actions Integration

The repository includes a **Scenario Evaluation** workflow (`.github/workflows/evaluate-scenarios.yml`) for automated evaluation runs.

### Workflow Features

| Feature | Description |
|---------|-------------|
| **Manual Trigger** | Run on-demand with configurable options |
| **Scheduled Runs** | Weekly smoke tests (Monday 6am UTC) |
| **Scenario Selection** | Run smoke, session_based, ab_tests, or individual scenarios |
| **Model Override** | Test with different models (gpt-4o, gpt-4o-mini, o1-preview, o3-mini) |
| **Foundry Export** | Optional upload to Azure AI Foundry |
| **Cost Estimation** | Shows estimated cost before running |

### Running Evaluations in CI

#### Manual Trigger

1. Go to **Actions** → **🎯 Scenario Evaluation**
2. Click **Run workflow**
3. Configure options:
   - **Environment**: `dev`, `staging`, or `prod`
   - **Scenario selection**: `smoke`, `session_based`, `ab_tests`, `all`, or individual scenario name
   - **Model variant**: Override model for all scenarios (optional)
   - **Output to Foundry**: Enable Azure AI Foundry export

#### Workflow Dispatch Options

```yaml
# Example: Run fraud detection comparison on staging
workflow_dispatch:
  inputs:
    environment: staging
    scenario_selection: fraud_detection_comparison
    model_variant: gpt-4o
    output_to_foundry: true
```

### Adopting for Your Fork

To use the evaluation workflow in your own repository:

#### 1. Configure Environment Secrets

Set these secrets in your GitHub repository (Settings → Secrets and variables → Actions):

| Secret | Description |
|--------|-------------|
| `AZURE_CLIENT_ID` | Service principal or managed identity client ID |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_CLIENT_SECRET` | Service principal secret (if not using OIDC) |

#### 2. Configure Environment Variables

Set these variables per environment (`dev`, `staging`, `prod`):

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_SPEECH_REGION` | Azure Speech region |
| `AZURE_APPCONFIG_ENDPOINT` | App Configuration endpoint |
| `AZURE_AI_FOUNDRY_PROJECT_ENDPOINT` | (Optional) Foundry project endpoint |

#### 3. Create Environments

In GitHub repository settings, create environments matching the workflow options:

- `dev` - Development environment
- `staging` - Staging environment  
- `prod` - Production environment

#### 4. Enable OIDC Authentication (Recommended)

For passwordless authentication, configure [OIDC with Azure](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure):

```bash
# Create federated credential for GitHub Actions
az ad app federated-credential create \
  --id <app-id> \
  --parameters '{
    "name": "github-actions-eval",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<owner>/<repo>:environment:<env>",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

### Workflow Output

The workflow produces:

1. **Job Summary** - Markdown table with pass/fail status, metrics
2. **Artifacts** - Full JSON results (retained 30 days)
   - `evaluation-results-{run_number}` - All scenario summaries
   - `foundry-export-{run_number}` - Foundry JSONL files (if enabled)

Example summary output:

```
## 🎯 Scenario Evaluation Results

| Metric | Value |
|--------|-------|
| Total Scenarios | 4 |
| ✅ Passed | 4 |
| ❌ Failed | 0 |
| Selection | session_based |
| Estimated Cost | $1.50 |

### Single Scenarios

| Scenario | Precision | Recall | P95 Latency | Cost |
|----------|-----------|--------|-------------|------|
| banking_multi_agent | 100.0% | 100.0% | 3500ms | $0.0045 |
```

---

## Metrics at a Glance

=== "Tool Metrics"

    | Metric | Formula | Target |
    |--------|---------|--------|
    | **Precision** | correct / called | ≥ 80% |
    | **Recall** | called / expected | ≥ 80% |
    | **Efficiency** | 1 - (redundant / total) | ≥ 90% |

=== "Performance Metrics"

    | Metric | Description | Target |
    |--------|-------------|--------|
    | **E2E P95** | 95th percentile latency | ≤ 10s |
    | **TTFT** | Time to first token | ≤ 2s |
    | **Cost/Turn** | Estimated USD per turn | Varies |

=== "Quality Metrics"

    | Metric | Description | Target |
    |--------|-------------|--------|
    | **Groundedness** | Response backed by evidence | ≥ 50% |
    | **Handoff Accuracy** | Correct agent routing | 100% |

---

## Next Steps

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **Framework Details**

    ---

    YAML format, CLI reference, pytest options, Foundry integration

    [:octicons-arrow-right-24: Evaluation Framework](evaluation.md)

-   :material-github:{ .lg .middle } **Create Custom Scenarios**

    ---

    Define your own evaluation scenarios in YAML

    [:octicons-arrow-right-24: Scenario Examples](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/tests/evaluation/scenarios)

-   :material-play-circle:{ .lg .middle } **Run Locally**

    ---

    Execute evaluations on your development machine

    [:octicons-arrow-right-24: Quick Start](#quick-start)

-   :material-cloud-sync:{ .lg .middle } **Azure AI Foundry**

    ---

    Cloud-based evaluation with AI-powered metrics

    [:octicons-arrow-right-24: Foundry Integration](evaluation.md#azure-ai-foundry-integration)

</div>

---

## Related Documentation

- [Evaluation Framework Guide](evaluation.md) - Complete reference
- [Testing Overview](index.md) - All testing options
- [Load Testing](../operations/load-testing.md) - Performance testing
