# Testing Framework

:material-test-tube: Comprehensive unit and integration testing suite for ARTVoice Accelerator covering core components along the call automation path.

!!! tip "Related Documentation"
    For load testing and performance validation, see the [Load Testing Guide](load-testing.md).

---

## Overview

The testing framework provides validation for:

| Category | Description |
|----------|-------------|
| :material-flask-outline: **Unit Tests** | Core component testing for call automation path |
| :material-connection: **Integration Tests** | End-to-end event handling and lifecycle testing |
| :material-phone-dial: **DTMF Testing** | Dual-tone multi-frequency validation and failure scenarios |
| :material-format-paint: **Code Quality** | Automated formatting, linting, and type checking |

---

## Quick Start

### Run All Tests

```bash
# Run all unit tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest --cov=apps.artagent.backend --cov-report=term-missing tests/

# Using Makefile
make run_unit_tests
```

### Run Code Quality Checks

```bash
# All checks
make check_code_quality

# Auto-fix issues
make fix_code_quality
```

---

## Test Coverage

### Test Files Overview

```
tests/
├── test_acs_events_handlers.py              # ACS event processing
├── test_aoai_manager_invocation.py          # Azure OpenAI manager
├── test_artagent_wshelpers.py               # WebSocket helpers
├── test_call_transfer_service.py            # Call transfer functionality
├── test_cascade_llm_processing.py           # Cascade LLM orchestration
├── test_cascade_orchestrator_entry_points.py # Orchestrator entry points
├── test_communication_services.py           # Email/SMS services
├── test_cosmosdb_manager_ttl.py             # Cosmos DB TTL management
├── test_demo_env_phrase_bias.py             # Phrase bias configuration
├── test_dtmf_processor.py                   # DTMF tone processing
├── test_dtmf_validation_failure_cancellation.py  # DTMF error scenarios
├── test_dtmf_validation.py                  # DTMF validation flow
├── test_events_architecture_simple.py       # Event-driven architecture
├── test_generic_handoff_tool.py             # Agent handoff tools
├── test_handoff_service.py                  # Handoff service logic
├── test_memo_optimization.py                # Memory optimization
├── test_on_demand_pool.py                   # Resource pooling
├── test_phrase_list_manager.py              # Speech phrase lists
├── test_realtime.py                         # Realtime API integration
├── test_redis_manager.py                    # Redis session management
├── test_scenario_orchestration_contracts.py # Scenario contracts
├── test_session_agent_manager.py            # Session agent management
├── test_speech_phrase_list.py               # Speech phrase configuration
├── test_speech_queue.py                     # Audio queue management
├── test_v1_events_integration.py            # API v1 event integration
├── test_voice_handler_compat.py             # Voice handler compatibility
├── test_voice_handler_components.py         # Voice handler components
├── test_voicelive_memory.py                 # VoiceLive memory management
└── test_warmable_pool.py                    # Warmable resource pools
```

---

## Core Component Tests

### Event Handlers

Tests in `test_acs_events_handlers.py` validate ACS event processing and call lifecycle:

| Test | Description |
|------|-------------|
| `test_handle_call_initiated` | Outbound call setup |
| `test_handle_inbound_call_received` | Inbound call handling |
| `test_handle_dtmf_tone_received` | DTMF tone processing |
| `test_extract_caller_id_*` | Caller ID extraction variants |
| `test_call_transfer_*` | Transfer accepted/failed envelopes |
| `test_webhook_event_routing` | Cloud event dispatcher |
| `test_unknown_event_type_handling` | Unknown event handling |

### Cascade LLM Processing

Tests in `test_cascade_llm_processing.py` validate the cascade orchestration pipeline:

| Test | Description |
|------|-------------|
| `test_simple_text_response` | Basic text response generation |
| `test_streaming_with_tts_callback` | Streaming with TTS integration |
| `test_tool_call_detection_and_execution` | Tool call handling |
| `test_handoff_tool_returns_immediately` | Handoff tool behavior |
| `test_error_handling_returns_user_friendly_message` | Error handling |
| `test_max_iterations_prevents_infinite_loop` | Iteration safeguards |
| `test_sanitize_tts_text_removes_markdown` | TTS text processing |

### Voice Handler

Tests in `test_voice_handler_compat.py` validate the unified voice handler:

| Test Class | Coverage |
|------------|----------|
| `TestPcm16leRms` | Audio RMS calculation |
| `TestTransportType` | Transport type enumeration |
| `TestMediaHandlerConfig` | Configuration validation |
| `TestMediaHandlerFactory` | Factory pattern and pool acquisition |
| `TestMediaHandlerLifecycle` | Start/stop lifecycle |
| `TestBargeIn` | Interruption handling |
| `TestACSMessageHandling` | ACS message processing |
| `TestIdleTimeout` | Session timeout management |

### Session Agent Manager

Tests in `test_session_agent_manager.py` validate per-session agent configuration:

| Test Class | Coverage |
|------------|----------|
| `TestSessionAgentManagerCore` | Agent retrieval and activation |
| `TestSessionAgentManagerOverrides` | Prompt/voice/model overrides |
| `TestSessionAgentManagerHandoffs` | Handoff map management |
| `TestSessionAgentManagerExperiments` | A/B experiment support |
| `TestSessionAgentManagerPersistence` | Redis persistence |

### DTMF Processing

Tests in `test_dtmf_processor.py` provide comprehensive DTMF validation (58 tests):

- Tone normalization for digits 0-9, *, #
- Word-to-tone conversion (zero, one, star, pound)
- Case insensitivity and whitespace handling
- Invalid tone rejection

---

## Integration Tests

### Event Architecture

=== "Event Dispatching"

    Tests in `test_events_architecture_simple.py`:

    - Cloud event routing and handling
    - Event serialization and deserialization
    - Cross-component event flow validation

=== "V1 Events Integration"

    Tests in `test_v1_events_integration.py`:

    | Test | Description |
    |------|-------------|
    | `test_event_processor_registration` | Handler registration |
    | `test_default_handlers_registration` | Default handler setup |
    | `test_call_initiated_handler` | Call initiation events |
    | `test_webhook_events_router` | Webhook routing |
    | `test_acs_lifecycle_handler_event_emission` | Lifecycle events |
    | `test_processor_error_isolation` | Error handling isolation |
    | `test_active_call_tracking` | Call state tracking |

### VoiceLive Memory

Tests in `test_voicelive_memory.py` validate memory management:

| Test Class | Coverage |
|------------|----------|
| `TestLiveOrchestratorCleanup` | Orchestrator cleanup on disconnect |
| `TestOrchestratorRegistry` | Registry lifecycle and stale cleanup |
| `TestBackgroundTaskTracking` | Background task management |
| `TestGreetingTaskCleanup` | Greeting task cancellation |
| `TestMemoryLeakPrevention` | Unbounded growth prevention |
| `TestUserMessageHistoryBounds` | History size limits |
| `TestScenarioUpdate` | Dynamic scenario switching |
| `TestHotPathOptimization` | Non-blocking hot paths |

### Scenario Orchestration

Tests in `test_scenario_orchestration_contracts.py` validate scenario contracts (36 tests):

- Agent configuration validation
- Handoff map contracts
- Tool registration and execution
- Scenario loading and switching

---

## Running Tests

### Basic Execution

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific file
python -m pytest tests/test_cascade_llm_processing.py -v

# Run specific test
python -m pytest tests/test_acs_events_handlers.py::TestCallEventHandlers::test_handle_call_initiated -v

# Run tests matching pattern
python -m pytest tests/ -k "dtmf" -v
```

### Advanced Options

```bash
# Verbose with stdout capture disabled
python -m pytest tests/ -v -s

# Performance profiling (slowest 10 tests)
python -m pytest tests/ --durations=10

# Parallel execution (requires pytest-xdist)
python -m pytest tests/ -n auto

# Stop on first failure
python -m pytest tests/ -x

# Run with debugger on failure
python -m pytest tests/ --pdb
```

### Coverage Reporting

```bash
# Terminal report
python -m pytest --cov=apps.artagent.backend --cov-report=term-missing tests/

# HTML report
python -m pytest --cov=apps.artagent.backend --cov-report=html tests/
open htmlcov/index.html
```

---

## Code Quality Tools

### Automated Checks

```bash
# Run all checks
make check_code_quality
```

This runs:

| Tool | Purpose |
|------|---------|
| :material-format-paint: **ruff** | Python linter and code formatter |
| :material-code-braces: **black** | Code formatting |
| :material-sort: **isort** | Import sorting |
| :material-alert-circle: **flake8** | Style guide enforcement |
| :material-language-python: **mypy** | Static type checking |
| :material-shield-check: **bandit** | Security vulnerability scanning |
| :material-file-document: **interrogate** | Docstring coverage |
| :material-file-code: **check-yaml** | YAML validation |

### Auto-Fix

```bash
# Fix formatting issues
make fix_code_quality
```

This runs:

- `black .` — Format code
- `isort .` — Sort imports
- `ruff --fix .` — Auto-fix lint issues

### Pre-commit Hooks

```bash
# Install hooks
make set_up_precommit_and_prepush

# Run manually
pre-commit run --all-files
```

---

## Test Patterns

### Mocking External Services

```python
# WebSocket mocking
mock_websocket = MagicMock()
mock_websocket.send_text = AsyncMock()

# Azure service mocking
with patch('azure.communication.callautomation.CallAutomationClient'):
    # Test Azure integration
    pass

# Async operation testing
@pytest.mark.asyncio
async def test_async_operation():
    result = await async_function()
    assert result is not None
```

### Test Fixtures

```python
@pytest.fixture
def sample_call_event():
    """Provide sample call event data."""
    return CloudEvent(
        source="test",
        type=ACSEventTypes.CALL_CONNECTED,
        data={"callConnectionId": "test_123"}
    )

@pytest.fixture
def mock_memory_manager():
    """Provide mock memory manager."""
    manager = MagicMock()
    manager.get_context.return_value = None
    return manager
```

### Test Class Organization

```python
class TestComponentName:
    """Test class for ComponentName functionality."""

    @pytest.fixture
    def component_instance(self):
        """Fixture providing test instance."""
        return ComponentName()

    def test_component_basic_functionality(self, component_instance):
        """Test basic component operation."""
        pass

    def test_component_error_handling(self, component_instance):
        """Test component error scenarios."""
        pass
```

---

## Skipped Tests

!!! warning "Pending Refactoring"
    Some test modules are currently skipped pending refactoring:

    | Test File | Reason |
    |-----------|--------|
    | `test_acs_media_lifecycle.py` | Depends on removed `acs_media_lifecycle.py` (renamed to `media_handler.py`) |
    | `test_acs_media_lifecycle_memory.py` | Needs refactoring to use `MediaHandler` |
    | `test_acs_simple.py` | Depends on removed `acs_media_lifecycle.py` |

---

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Unit Tests
  run: make run_unit_tests

- name: Check Code Quality
  run: make check_code_quality

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

---

## Best Practices

### Test Development

1. :material-test-tube: **Isolation** — Each test should be independent and repeatable
2. :material-tag-text: **Clarity** — Test names should clearly describe what is being tested
3. :material-chart-bar: **Coverage** — Focus on critical paths and edge cases
4. :material-speedometer: **Performance** — Keep unit tests fast (< 1s per test)
5. :material-file-document: **Documentation** — Include docstrings explaining complex scenarios

### Debugging Failures

```bash
# Verbose output
python -m pytest tests/test_failing.py -v -s

# With debugger
python -m pytest tests/test_failing.py --pdb

# With logging
python -m pytest tests/test_failing.py --log-cli-level=DEBUG
```

---

## Resources

!!! abstract "References"
    - :material-book-open-variant: [pytest Documentation](https://docs.pytest.org/)
    - :material-code-braces: [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
    - :material-microsoft-azure: [Azure SDK Testing](https://github.com/Azure/azure-sdk-for-python/blob/main/doc/dev/tests.md)
