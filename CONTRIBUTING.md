# Contributing to ARTVoice Accelerator

This project welcomes contributions and suggestions. Most contributions require you to
agree to a Contributor License Agreement (CLA) declaring that you have the right to,
and actually do, grant us the rights to use your contribution. For details, visit
https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need
to provide a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the
instructions provided by the bot. You will only need to do this once across all repositories using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

---

## Development Workflow

### 1. Start with an Issue
Create an issue for bugs, feature requests, or enhancements before starting work.

### 2. Clone and Setup
```bash
git clone https://github.com/pablosalvador10/gbb-ai-audio-agent.git
cd gbb-ai-audio-agent
```

### 3. Environment Setup
The project uses Python 3.11 and Conda for environment management.

```bash
# Create and activate environment
conda env create -f environment.yaml
conda activate audioagent

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-codequality.txt
```

For local development, also see `docs/quickstart-local-development.md`.

### 4. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
# or for bug fixes:
git checkout -b bugfix/issue-description
```

**Branching Strategy:**
- `feature/*` → Development branches
- `staging` → Testing and validation
- `main` → Production-ready code

### 5. Development Process
- Write tests for new functionality
- Update documentation and docstrings
- Follow the FastAPI and Python 3.11 patterns established in the codebase
- Ensure compatibility with Azure services (ACS, Speech, OpenAI)

### 6. Quality Checks
```bash
# Run all quality checks
make run_code_quality_checks

# Run tests
make run_tests

# Start local development
make start_backend  # FastAPI backend
make start_frontend # React frontend
```

### 7. Submit Your Changes
```bash
git add .
git commit -m "feat: brief description of change"
git push origin your-branch-name
```

Create a pull request targeting the appropriate branch with:
- Clear description of changes
- Link to related issue (e.g., "Closes #123")
- Test results and validation steps

---

## Development Environment Setup

### VSCode Configuration
1. Install Python and Jupyter extensions
2. Select the `audioagent` conda environment as your Python interpreter
3. Configure settings for FastAPI development

### Pre-commit Hooks
```bash
make set_up_precommit_and_prepush
```

This sets up automated code quality checks that run before commits.

---

## Project Architecture

### Core Components
- **FastAPI Backend** → Real-time voice processing with WebSocket support
- **Azure Communication Services** → Telephony integration
- **Azure Speech Services** → STT/TTS processing
- **Azure OpenAI** → LLM inference
- **React Frontend** → Administrative interface

### Testing Strategy
- **Unit Tests** → `tests/test_*.py`
- **Integration Tests** → End-to-end workflow testing
- **Load Tests** → Voice pipeline performance validation

### Key Directories
- `src/` → Core application modules (ACS, Speech, AI, etc.)
- `apps/rtagent/` → Main application code
- `infra/` → Infrastructure as Code (Bicep/Terraform)
- `docs/` → Documentation and guides

---

## Project Governance

### Maintainers
| Role | Contributor |
|------|-------------|
| **Lead Developer** | [Pablo Salvador Lopez](https://github.com/pablosalvador10) |
| **Infrastructure Lead** | [Jin Lee](https://github.com/marcjimz) |

### Pull Request Process
1. All PRs require maintainer review
2. CI checks must pass (tests, linting, security scans)
3. Documentation updates required for new features
4. Breaking changes require version bump discussion

### Release Process
- **Major** → Breaking API changes
- **Minor** → New features, backward compatible
- **Patch** → Bug fixes and improvements

Releases are managed through GitHub releases with automated deployment via Azure DevOps.

---

## Getting Help

| Resource | Purpose |
|----------|---------|
| **GitHub Issues** | Bug reports and feature requests |
| **GitHub Discussions** | Questions and community support |
| **Documentation** | `docs/` folder for technical guides |

---

**Thank you for contributing to ARTVoice Accelerator!** Your contributions help advance real-time voice AI capabilities.
