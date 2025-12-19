# Testing Framework (WIP)

Comprehensive unit and integration testing suite for ARTVoice Accelerator covering core components along the call automation path.

> **Note**: For load testing and performance validation, see [Load Testing Guide](load-testing.md).

## Overview

The testing framework provides validation for:

- **Unit Tests**: Core component testing for call automation path
- **Integration Tests**: End-to-end event handling and lifecycle testing
- **DTMF Testing**: Dual-tone multi-frequency validation and failure scenarios
- **Code Quality**: Automated formatting, linting, and type checking

## Unit Tests

### Test Coverage Overview

The unit test suite validates critical components along the call automation path:

```
tests/
├── test_acs_media_lifecycle.py         # Audio processing pipeline
├── test_acs_events_handlers.py         # Event processing & WebSocket integration  
├── test_redis_manager.py               # Session state management
├── test_dtmf_validation.py             # DTMF tone processing
├── test_dtmf_validation_failure_cancellation.py  # DTMF error scenarios
├── test_events_architecture_simple.py  # Event-driven architecture
├── test_speech_queue.py                # Audio queue management
└── test_v1_events_integration.py       # API v1 event integration
```

### Core Components Coverage

#### ACS Media Lifecycle (`test_acs_media_lifecycle.py`)

Tests the real-time audio processing pipeline components:

**ThreadBridge Testing:**
- Queue management and speech result handling
- Backpressure handling when queues are full
- Cross-thread communication patterns

**SpeechSDKThread Testing:**
- Speech recognition lifecycle and audio streaming
- Push stream initialization and management
- Recognizer state management and error handling

**MainEventLoop Testing:**
- WebSocket message handling and audio metadata processing
- Barge-in functionality and playback cancellation
- Audio chunk processing and base64 decoding

**RouteTurnThread Testing:**
- Turn processing and conversation flow management
- Cancellation logic and queue cleanup
- Response task management

```python
# Example test coverage
def test_thread_bridge_queue_speech_result_put_nowait():
    # Tests immediate queue operations
    
def test_main_event_loop_handle_barge_in_cancels_playback():
    # Tests response interruption handling
    
def test_route_turn_thread_cancel_current_processing_clears_queue():
    # Tests conversation state cleanup
```

#### Event Handlers (`test_acs_events_handlers.py`)

Validates event processing and WebSocket integration:

**Call Event Processing:**
- Inbound and outbound call lifecycle management
- Call connection state transitions
- Participant management and call metadata

**DTMF Event Handling:**
- Tone sequence processing and validation
- DTMF recognition and routing
- Sequence building and context updates

**WebSocket Broadcasting:**
- Client notification system
- Message serialization and delivery
- Multi-client event distribution

**Event Routing:**
- Cloud event dispatcher functionality
- Unknown event type handling
- Event context management

```python
# Key test scenarios
def test_handle_call_initiated():
    # Tests outbound call setup
    
def test_handle_call_connected_with_broadcast():
    # Tests WebSocket client notifications
    
def test_handle_dtmf_tone_received():
    # Tests tone processing and sequence building
```

#### Redis Session Management (`test_redis_manager.py`)

Tests Azure Redis cluster management and session persistence:

**Cluster Detection:**
- Automatic cluster mode switching on MovedError
- Fallback behavior when cluster support unavailable
- Connection pool management

**Address Remapping:**
- IP to domain name mapping for Azure Redis
- Cluster node address resolution
- Connection string handling

**Session Operations:**
- Session data storage and retrieval
- Conversation history persistence
- Memory context management

```python
def test_get_session_data_switches_to_cluster():
    # Tests automatic cluster detection
    
def test_remap_cluster_address_to_domain():
    # Tests Azure Redis address mapping
```

#### DTMF Validation (`test_dtmf_validation.py`)

Validates dual-tone multi-frequency processing:

**Validation Flow:**
- AWS Connect DTMF validation setup
- Validation gate state management
- Tone collection and processing

**Context Management:**
- Session state persistence during validation
- Validation context setup and teardown
- Error state handling

**Timeout Handling:**
- Validation completion monitoring
- Timeout detection and handling
- Async validation workflows

```python
def test_setup_aws_connect_validation_flow_sets_context():
    # Tests validation workflow initialization
    
def test_wait_for_dtmf_validation_completion_success():
    # Tests successful validation completion
```

### Running Unit Tests

#### Basic Test Execution

```bash
# Run all unit tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_acs_media_lifecycle.py -v

# Run with coverage reporting
python -m pytest --cov=apps.artagent.backend --cov-report=term-missing tests/

# Run specific test method
python -m pytest tests/test_acs_events_handlers.py::TestCallEventHandlers::test_handle_call_connected_with_broadcast -v
```

#### Advanced Test Options

```bash
# Run tests with detailed output
python -m pytest tests/ -v -s

# Run tests matching pattern
python -m pytest tests/ -k "dtmf" -v

# Run tests with performance profiling
python -m pytest tests/ --durations=10

# Run tests in parallel (if pytest-xdist installed)
python -m pytest tests/ -n auto
```

## Integration Testing

### Event Architecture Testing

**Event Dispatching** (`test_events_architecture_simple.py`):
- Cloud event routing and handling
- Event serialization and deserialization
- Cross-component event flow validation

**Memory Management**:
- Session context persistence across events
- Memory cleanup and lifecycle management
- Context sharing between components

**Error Handling**:
- Exception management and recovery
- Graceful degradation scenarios
- Error propagation patterns

### V1 Events Integration (`test_v1_events_integration.py`)

**WebSocket Events**:
- Real-time event streaming validation
- Event ordering and sequencing
- Connection lifecycle management

**Event Serialization**:
- JSON event format validation
- Event schema compliance
- Backward compatibility testing

**Client Broadcasting**:
- Multi-client event distribution
- Client subscription management
- Event filtering and routing

## Code Quality

### Automated Code Quality Checks

The project uses comprehensive code quality tools:

```bash
# Run all code quality checks
make check_code_quality

# Auto-fix formatting issues  
make fix_code_quality

# Individual tool execution
make run_unit_tests                 # Execute unit tests with coverage
```

#### Code Quality Tools

**Formatting and Style:**
- **ruff**: Python linter and code formatter
- **black**: Code formatting
- **isort**: Import sorting and organization
- **flake8**: Style guide enforcement

**Type Checking:**
- **mypy**: Static type checking
- **Type annotations**: Function and class type hints

**Security:**
- **bandit**: Security vulnerability scanning
- **Dependency scanning**: Package vulnerability checks

**Documentation:**
- **interrogate**: Docstring coverage checking
- **YAML validation**: Configuration file validation

### Pre-commit Hooks

```bash
# Install pre-commit hooks
make set_up_precommit_and_prepush

# Manual pre-commit execution
pre-commit run --all-files
```

## Test Structure and Patterns

### Test Organization

**File Naming Convention:**
- `test_<component>.py`: Unit tests for specific components
- `test_<feature>_integration.py`: Integration tests for features
- `test_<scenario>_failure_<condition>.py`: Failure scenario tests

**Test Class Structure:**
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

### Mocking and Test Doubles

**Common Patterns:**
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

### Test Data Management

**Fixtures for Test Data:**
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

## Development Workflow

### Testing During Development

1. **Write tests first**: Follow TDD principles where applicable
2. **Run tests frequently**: Use `pytest --watch` for continuous testing
3. **Check coverage**: Maintain >80% test coverage on critical paths
4. **Review test output**: Analyze test failures and performance

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  run: make run_unit_tests

- name: Check Code Quality  
  run: make check_code_quality

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

### Test Environment Setup

```bash
# Create test environment
make create_conda_env

# Activate environment
make activate_conda_env

# Install test dependencies (using uv - recommended)
uv sync --extra dev

# Or with pip:
# pip install -e .[dev]
```

## Best Practices

### Test Development Guidelines

1. **Isolation**: Each test should be independent and repeatable
2. **Clarity**: Test names should clearly describe what is being tested
3. **Coverage**: Focus on critical paths and edge cases
4. **Performance**: Keep unit tests fast (<1s per test)
5. **Documentation**: Include docstrings explaining complex test scenarios

### Debugging Test Failures

```bash
# Run with verbose output
python -m pytest tests/test_failing.py -v -s

# Run with debugger
python -m pytest tests/test_failing.py --pdb

# Run with logging
python -m pytest tests/test_failing.py --log-cli-level=DEBUG
```

### Mock Strategy

- **Unit tests**: Mock external dependencies (Azure services, databases)
- **Integration tests**: Use test doubles for expensive operations
- **End-to-end tests**: Minimize mocking, use test environments

## Test Results and Coverage

### Current Test Coverage

The test suite provides comprehensive coverage of:
- **ACS Media Pipeline**: 85% coverage of audio processing components
- **Event Handling**: 90% coverage of webhook and cloud event processing
- **Redis Management**: 95% coverage of session state management
- **DTMF Processing**: 80% coverage of tone validation logic

### Coverage Reporting

```bash
# Generate HTML coverage report
python -m pytest --cov=apps.artagent.backend --cov-report=html tests/

# View coverage report
open htmlcov/index.html
```

### Performance Testing

For performance and load testing capabilities, including WebSocket stress testing and Azure Load Testing integration, see the dedicated [Load Testing Guide](load-testing.md).

---

This testing framework ensures the reliability and maintainability of the ARTVoice Accelerator platform through comprehensive unit and integration testing coverage.

> **📖 References**: [pytest Documentation](https://docs.pytest.org/) • [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/) • [Azure SDK Testing](https://github.com/Azure/azure-sdk-for-python/blob/main/doc/dev/tests.md)