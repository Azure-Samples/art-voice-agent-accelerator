# Load Testing

Comprehensive WebSocket load testing framework for real-time voice agent using Locust with realistic conversation simulation and Azure Load Testing integration.

> **Note**: For unit tests, integration tests, and code quality validation, see [Testing Framework](testing.md).

## Overview

The load testing framework validates WebSocket performance under realistic conversation scenarios using:
- **Locust-based testing**: WebSocket simulation with real audio streaming
- **Audio generation**: Production TTS-generated conversation audio
- **Azure integration**: Seamless deployment to Azure Load Testing service
- **Realistic scenarios**: Multi-turn conversation patterns

## Audio Generation

### Production TTS Integration

The audio generator uses production [Azure Speech Services](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech) to create realistic conversation audio:

```python
# Audio generator configuration
synthesizer = SpeechSynthesizer(
    region=os.getenv("AZURE_SPEECH_REGION"),
    key=os.getenv("AZURE_SPEECH_KEY"),
    language="en-US",
    voice="en-US-JennyMultilingualNeural",
    playback="never",  # Disable for load testing
    enable_tracing=False  # Performance optimization
)
```

### Quick Start: Generate Audio Files

```bash
# Using Makefile (recommended)
make generate_audio

# Direct command with options
python tests/load/utils/audio_generator.py \
  --max-turns 5 \
  --scenarios insurance_inquiry quick_question
```

**Generated Structure:**
```
tests/load/audio_cache/
├── insurance_inquiry_turn_1_of_5_abc123.pcm
├── insurance_inquiry_turn_2_of_5_def456.pcm
├── insurance_inquiry_turn_3_of_5_ghi789.pcm
├── quick_question_turn_1_of_3_pqr678.pcm
├── quick_question_turn_2_of_3_stu901.pcm
└── manifest.jsonl  # Audio file metadata
```

### Conversation Scenarios

#### Insurance Inquiry (5 turns)
1. "Hello, my name is Alice Brown, my social is 1234, and my zip code is 60601"
2. "I'm calling about my auto insurance policy"
3. "I need to understand what's covered under my current plan"
4. "What happens if I get into an accident?"
5. "Thank you for all the information, that's very helpful"

#### Quick Question (3 turns)
1. "Hi there, I have a quick question"
2. "Can you help me check my account balance?"
3. "Thanks, that's all I needed to know"

### Audio Requirements

| Property | Value | Notes |
|----------|-------|-------|
| **Format** | 16-bit PCM | Compatible with WebSocket streaming |
| **Sample Rate** | 16 kHz | Optimized for voice recognition |
| **Channels** | Mono | Single channel for conversation |
| **Encoding** | Base64 | WebSocket transmission format |

## Locust Load Testing Framework

### Core Features

The [Locust framework](https://docs.locust.io/en/stable/) provides WebSocket load testing with:

- **Real-time audio streaming**: 20ms PCM chunks via WebSocket
- **TTFB measurement**: Time-to-first-byte response tracking
- **Barge-in testing**: Response interruption simulation
- **Connection management**: Automatic WebSocket reconnection
- **Configurable scenarios**: Multi-turn conversation patterns

### WebSocket Testing Implementation

The actual Locust implementation simulates realistic WebSocket voice conversation patterns:

```python
# From locustfile.py - actual implementation
WS_URL = os.getenv("WS_URL", "ws://127.0.0.1:8010/api/v1/media/stream")
PCM_DIR = os.getenv("PCM_DIR", "tests/load/audio_cache")
TURNS_PER_USER = int(os.getenv("TURNS_PER_USER", "3"))
CHUNKS_PER_TURN = int(os.getenv("CHUNKS_PER_TURN", "100"))  # ~2s @20ms
CHUNK_MS = int(os.getenv("CHUNK_MS", "20"))  # 20 ms chunks
FIRST_BYTE_TIMEOUT_SEC = float(os.getenv("FIRST_BYTE_TIMEOUT_SEC", "5.0"))
BARGE_QUIET_MS = int(os.getenv("BARGE_QUIET_MS", "400"))
```

### Audio Streaming Process

Based on the actual `locustfile.py` implementation:

1. **Connection Setup**: WebSocket connection with ACS correlation headers
2. **Audio Metadata**: Initial format specification (16kHz PCM mono)
3. **Chunk Streaming**: 20ms audio frames from PCM files at regular intervals
4. **Silence Frames**: End-of-speech detection with generated low-level noise
5. **Response Measurement**: TTFB and barge-in timing using `_measure_ttfb()`
6. **Turn Rotation**: Cycles through available PCM files for realistic conversation flow

### Configuration Options

```bash
# Environment variables for locustfile.py
export WS_URL="ws://localhost:8010/api/v1/media/stream"
export PCM_DIR="tests/load/audio_cache"
export TURNS_PER_USER=3
export CHUNKS_PER_TURN=100
export CHUNK_MS=20
export FIRST_BYTE_TIMEOUT_SEC=5.0
export BARGE_QUIET_MS=400
export WS_IGNORE_CLOSE_EXCEPTIONS=true
```

### Performance Metrics Tracked

#### Real-time Metrics
- **TTFB (Time-to-First-Byte)**: Server response latency after audio completion
- **Barge-in latency**: Response interruption timing measured with `_wait_for_end_of_response()`
- **WebSocket stability**: Connection durability under load with reconnection handling
- **Audio streaming**: Chunk transmission success rates with error handling
- **Turn completion**: End-to-end conversation success

#### Test Implementation Example

```python
class ACSUser(User):
    def _measure_ttfb(self, max_wait_sec: float) -> tuple[bool, float]:
        """Time-To-First-Byte after EOS: measure server response time"""
        start = time.time()
        deadline = start + max_wait_sec
        while time.time() < deadline:
            msg = self._recv_with_timeout(0.05)
            if msg:
                return True, (time.time() - start) * 1000.0
        return False, (time.time() - start) * 1000.0
```

## Running Load Tests

### Local Testing

```bash
# Basic local test
make run_load_test

# Custom configuration via Makefile
make run_load_test \
  URL=wss://your-backend.azurecontainerapps.io/api/v1/media/stream \
  CONVERSATIONS=50 \
  CONCURRENT=10

# Direct Locust command
locust -f tests/load/locustfile.py \
  --host=http://localhost:8010 \
  --users 20 \
  --spawn-rate 5 \
  --run-time 300s
```

### Makefile Integration

#### Available Commands

```bash
# Generate audio files for testing
make generate_audio

# Run local load test with defaults
make run_load_test

# Run with custom parameters
make run_load_test \
  URL=wss://prod-backend.azurecontainerapps.io/api/v1/media/stream \
  CONVERSATIONS=100 \
  CONCURRENT=20
```

#### Makefile Implementation

The actual implementation from the Makefile:

```makefile
# Audio generation target
generate_audio:
	python $(SCRIPTS_LOAD_DIR)/utils/audio_generator.py --max-turns 5

# Load testing target with configurable parameters
run_load_test:
	@echo "Running load test (override with make run_load_test URL=wss://host)"
	$(eval URL ?= wss://$(LOCAL_URL)/api/v1/media/stream)
	$(eval TURNS ?= 5)
	$(eval CONVERSATIONS ?= 20)
	$(eval CONCURRENT ?= 20)
	@locust -f $(SCRIPTS_LOAD_DIR)/locustfile.py \
		--headless \
		-u $(CONVERSATIONS) \
		-r $(CONCURRENT) \
		--run-time 10m \
		--host $(URL) \
		--stop-timeout 60 \
		--csv=locust_report \
		--only-summary
```

**Key Parameters:**
- `URL`: WebSocket endpoint to test (default: `wss://localhost:8010/api/v1/media/stream`)
- `CONVERSATIONS`: Number of concurrent users (default: 20)
- `CONCURRENT`: Spawn rate per second (default: 20)
- `TURNS`: Number of conversation turns (default: 5)

**Output Files:**
- `locust_report_stats.csv`: Detailed performance statistics
- `locust_report_failures.csv`: Error analysis
- `locust_report_exceptions.csv`: Exception tracking

## Azure Load Testing Integration

### Overview

[Azure Load Testing](https://learn.microsoft.com/en-us/azure/load-testing/overview-what-is-azure-load-testing) provides a fully managed load testing service that supports Locust-based testing for WebSocket applications.

### Setup Steps

#### 1. Create Azure Load Testing Resource

```bash
# Create load testing resource
az load create \
  --name "voice-agent-loadtest" \
  --resource-group "rg-voice-agent" \
  --location "eastus"
```

#### 2. Prepare Test Files

Upload the following files to Azure Load Testing:

**Required Files:**
- `tests/load/locustfile.py` (rename to `locustfile.py`)
- All PCM files from `tests/load/audio_cache/*.pcm`

**File Organization:**
```
Azure Load Testing Upload:
├── locustfile.py                    # Main test script
├── insurance_inquiry_turn_1_of_5_abc123.pcm
├── insurance_inquiry_turn_2_of_5_def456.pcm
├── quick_question_turn_1_of_3_pqr678.pcm
└── manifest.jsonl                   # Audio file metadata
```

#### 3. Configure Environment Variables

Set the following environment variables in Azure Load Testing:

```bash
# Target configuration
WS_URL=wss://your-backend.azurecontainerapps.io/api/v1/media/stream
PCM_DIR=./  # Azure places files in working directory

# Performance tuning
TURNS_PER_USER=3
CHUNKS_PER_TURN=100
CHUNK_MS=20
FIRST_BYTE_TIMEOUT_SEC=5.0
BARGE_QUIET_MS=400
WS_IGNORE_CLOSE_EXCEPTIONS=true

# Optional: Custom scenarios
RESPONSE_TOKENS=recognizer,greeting,response,transcript,result
END_TOKENS=final,end,completed,stopped,barge
```

#### 4. Configure Load Parameters

Following [Azure Load Testing best practices](https://learn.microsoft.com/en-us/azure/load-testing/quickstart-create-and-run-load-test):

| Parameter | Development | Staging | Production |
|-----------|-------------|---------|------------|
| **Virtual Users** | 5-10 | 50-100 | 200-500 |
| **Spawn Rate** | 1-2/sec | 5-10/sec | 20-50/sec |
| **Test Duration** | 5-10 min | 15-30 min | 30-60 min |
| **Engine Instances** | 1-2 | 3-5 | 5-10 |

#### 5. Add Server Monitoring

Integrate Azure resources for comprehensive monitoring:

```bash
# Add monitored resources using azd-env-name tag
az load test server-metric create \
  --test-id "voice-agent-test" \
  --load-test-resource "voice-agent-loadtest" \
  --resource-group "rg-voice-agent" \
  --metric-id "app-service-cpu" \
  --resource-id "/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Web/sites/{app-name}"
```

## Performance Targets

### Latency Benchmarks

| Metric | Target | Acceptable | Notes |
|--------|--------|------------|-------|
| **TTFB P95** | <2000ms | <3000ms | Time to first server response |
| **Barge-in P95** | <500ms | <1000ms | Response interruption latency |
| **Connection Success** | >98% | >95% | WebSocket establishment rate |
| **Turn Success** | >95% | >90% | Successful conversation completion |

### Capacity Targets

| Environment | Concurrent Users | Duration | Success Rate |
|-------------|------------------|----------|--------------|
| **Development** | 10 users | 5 minutes | >95% |
| **Staging** | 100 users | 30 minutes | >95% |
| **Production** | 500+ users | 60 minutes | >98% |

### Load Test Scenarios

#### Development Testing
```bash
make run_load_test \
  URL=ws://localhost:8010/api/v1/media/stream \
  CONVERSATIONS=5 \
  CONCURRENT=2
```

#### Staging Validation
```bash
make run_load_test \
  URL=wss://staging-backend.azurecontainerapps.io/api/v1/media/stream \
  CONVERSATIONS=50 \
  CONCURRENT=10
```

#### Production Scale Testing
```bash
make run_load_test \
  URL=wss://prod-backend.azurecontainerapps.io/api/v1/media/stream \
  CONVERSATIONS=200 \
  CONCURRENT=50
```

## Performance Analysis

### Result Interpretation

#### Locust Output Analysis
```bash
# View Locust results
cat locust_report_stats.csv | column -t -s,

# Analyze specific metrics
grep "speech_turns" locust_report_stats.csv

# Check error rates
cat locust_report_failures.csv
```

#### Azure Monitor Integration
```bash
# Monitor Azure resources during test
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Web/sites/{app}" \
  --metric "CpuPercentage,MemoryPercentage" \
  --start-time "2024-01-01T00:00:00Z" \
  --end-time "2024-01-01T01:00:00Z"
```

### Key Performance Indicators

#### Response Time Metrics
- **TTFB percentiles**: P50, P95, P99 response times
- **Barge-in timing**: Response interruption effectiveness
- **End-to-end latency**: Complete conversation turn timing

#### Throughput Metrics
- **Requests per second**: WebSocket message throughput
- **Concurrent connections**: Maximum sustainable WebSocket connections
- **Audio streaming rate**: PCM chunk transmission rates

#### Error Metrics
- **Connection failures**: WebSocket establishment errors
- **Timeout rates**: TTFB and response timeouts
- **Audio streaming errors**: PCM transmission failures

## Best Practices

### Local Development Testing

1. **Start small**: Begin with 5-10 concurrent users
2. **Validate setup**: Ensure audio files are generated correctly
3. **Monitor resources**: Watch local CPU/memory usage
4. **Check endpoints**: Verify WebSocket connection establishment

### Azure Load Testing Deployment

1. **File size optimization**: Compress PCM files if needed for upload
2. **Environment parity**: Match production WebSocket endpoints
3. **Monitoring integration**: Include all relevant Azure resources
4. **Gradual scaling**: Increase load incrementally
5. **Result analysis**: Review both client and server metrics

### Performance Optimization

#### WebSocket Configuration
- **Connection pooling**: Reuse WebSocket connections where possible
- **Message batching**: Optimize audio chunk transmission
- **Error handling**: Implement robust reconnection logic

#### Audio Processing
- **Chunk sizing**: Optimize PCM chunk size for performance
- **Silence detection**: Efficient end-of-speech handling
- **Memory management**: Proper audio buffer cleanup

## Troubleshooting

### Common Issues

#### Audio Generation Failures
```bash
# Check Azure Speech Service credentials
echo $AZURE_SPEECH_KEY
echo $AZURE_SPEECH_REGION

# Verify TTS functionality
python tests/load/utils/audio_generator.py --test-connection
```

#### WebSocket Connection Issues
```bash
# Test WebSocket endpoint
export WS_URL="ws://localhost:8010/api/v1/media/stream"
python -c "import websocket; ws = websocket.create_connection('$WS_URL'); print('Connected'); ws.close()"
```

#### Azure Load Testing Upload Issues
- Ensure file sizes are under Azure limits
- Verify all PCM files are in the correct format
- Check that locustfile.py is named correctly

### Debugging Load Test Issues

#### Locust Debug Mode
```bash
# Run with verbose logging
locust -f tests/load/locustfile.py --loglevel DEBUG

# Single user testing
locust -f tests/load/locustfile.py --users 1 --spawn-rate 1
```

#### Network Troubleshooting
```bash
# Test network connectivity
curl -I https://your-backend.azurecontainerapps.io/health

# Check DNS resolution
nslookup your-backend.azurecontainerapps.io

# Test WebSocket upgrade
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: test" \
  -H "Sec-WebSocket-Version: 13" \
  https://your-backend.azurecontainerapps.io/api/v1/media/stream
```

## Advanced Usage

### Custom Scenarios

To add new conversation scenarios:

1. **Update audio generator** with new conversation templates
2. **Regenerate audio files** using `make generate_audio`
3. **Update locustfile** to reference new audio files
4. **Test locally** before Azure deployment

### Integration with CI/CD

```yaml
# GitHub Actions example
- name: Generate Load Test Audio
  run: make generate_audio
  
- name: Run Load Test
  run: make run_load_test URL=${{ secrets.STAGING_WS_URL }}
  
- name: Upload Results
  uses: actions/upload-artifact@v3
  with:
    name: load-test-results
    path: locust_report_*.csv
```

### Continuous Performance Testing

#### Scheduled Testing
```bash
# Daily performance regression test
0 2 * * * cd /path/to/project && make run_load_test CONVERSATIONS=20 CONCURRENT=5

# Weekly capacity test
0 3 * * 0 cd /path/to/project && make run_load_test CONVERSATIONS=100 CONCURRENT=20
```

#### Performance Monitoring
- Set up alerts for performance degradation
- Track performance trends over time
- Compare results across different environments

---

This comprehensive load testing framework ensures reliable WebSocket performance testing with realistic audio streaming scenarios, supporting both local development and production-scale Azure Load Testing deployments.

> **📖 References**: [Azure Load Testing](https://learn.microsoft.com/en-us/azure/load-testing/overview-what-is-azure-load-testing) • [Locust Documentation](https://docs.locust.io/en/stable/) • [Azure Speech Services](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech)