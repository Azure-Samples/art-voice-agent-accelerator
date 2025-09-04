# **Load Testing Framework**

**Comprehensive multi-turn conversation load testing** for ARTVoice Accelerator with detailed per-turn statistics and realistic conversation simulation.

## **Key Features**

- **Per-Turn Statistics**: P50-P99.9 percentiles for every conversation turn
- **Concurrency Analysis**: Peak concurrent connections and latency impact
- **Conversation Recording**: 20% sampling for detailed conversation analysis  
- **Multiple Scenarios**: Insurance inquiry (5 turns) and quick questions (3 turns)
- **Comprehensive Metrics**: Speech recognition, agent processing, and end-to-end latency

## **Quick Start**

### **1. Generate Audio Files**
```bash
python tests/load/audio_generator.py \
  --max-turns 5 \
  --scenarios insurance_inquiry quick_question
```

### **2. Run Load Test**
```bash
# Basic load test
locust -f tests/load/locustfile.py --host=http://localhost:8010

# Advanced configuration
locust -f tests/load/locustfile.py \
  --host=https://your-backend.azurecontainerapps.io \
  --users 50 \
  --spawn-rate 5 \
  --run-time 300s
```

## **Metrics Tracked**

- **Speech Recognition Latency**: Audio end to first agent response
- **Agent Processing Latency**: First to last agent response  
- **End-to-End Latency**: Total turn completion time
- **Turn Success Rate**: Percentage of successful turns by position

**Generated Files Structure:**
```
tests/load/audio_cache/
├── insurance_inquiry_turn_1_of_5_abc123.pcm
├── insurance_inquiry_turn_2_of_5_def456.pcm
├── insurance_inquiry_turn_3_of_5_ghi789.pcm
├── insurance_inquiry_turn_4_of_5_jkl012.pcm
├── insurance_inquiry_turn_5_of_5_mno345.pcm
├── quick_question_turn_1_of_3_pqr678.pcm
├── quick_question_turn_2_of_3_stu901.pcm
└── quick_question_turn_3_of_3_vwx234.pcm
```

### 2. Run Detailed Statistics Load Tests

#### **Fixed Turn Count with Detailed Analysis**
```bash
# Run detailed 5-turn analysis (20 conversations, 5 concurrent)
python tests/load/detailed_statistics_analyzer.py \
  --turns 5 \
  --conversations 20 \
  --concurrent 5 \
  --url ws://localhost:8010/api/v1/media/stream
```

#### **Compare Different Turn Counts**
```bash
# Test 3-turn conversations
python tests/load/detailed_statistics_analyzer.py --turns 3 --conversations 15

# Test 5-turn conversations  
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 20

# Test 7-turn conversations (extended insurance_inquiry)
python tests/load/detailed_statistics_analyzer.py --turns 7 --conversations 10
```

#### **Quick Validation Test**
```bash
# Fast test to validate setup
python tests/load/test_multi_turn.py
```

## 📊 Understanding Detailed Statistics

### **Comprehensive Per-Turn Analysis**
```
⏱️  OVERALL LATENCY STATISTICS

📈 Speech Recognition Latency Ms
  Count:      95
  Mean:     850.2ms
  P50:      820.1ms
  P95:     1150.3ms
  P99:     1380.7ms
  P99.9:   1520.4ms
  Min:      650.0ms
  Max:     1600.2ms
  StdDev:   180.5ms

🔄 PER-TURN POSITION ANALYSIS
Turn   Count    Success%  Recognition P95  Processing P95   E2E P95
-----------------------------------------------------------------------
1      20       100.0%    1050.2ms         1850.4ms         2100.1ms
2      20       95.0%     1120.8ms         1920.3ms         2250.7ms
3      19       95.0%     1180.5ms         2050.1ms         2400.2ms
4      18       90.0%     1250.3ms         2180.8ms         2580.5ms
5      17       85.0%     1320.7ms         2350.2ms         2750.3ms
```

### **Template Performance Comparison**
```
📋 TEMPLATE COMPARISON ANALYSIS

📝 Insurance Inquiry
  Conversations: 12
  Successful Turns: 57/60
  Avg Duration: 45.8s
  End-to-End: Mean=2150.3ms, P95=2580.1ms, P99=2850.7ms

📝 Quick Question  
  Conversations: 8
  Successful Turns: 23/24
  Avg Duration: 18.2s
  End-to-End: Mean=1850.2ms, P95=2100.5ms, P99=2350.1ms
```

### **Key Metrics Explained**

#### **Per-Turn Metrics**
- **Speech Recognition Latency**: Critical for responsiveness - target <1000ms
- **Agent Processing Latency**: LLM + TTS pipeline time - target <2000ms  
- **End-to-End Latency**: Total user experience - target <3000ms
- **Turn Success Rate**: Should stay >90% across all turn positions

## ☁️ Azure Load Testing (Locust)

Use Azure Load Testing to run this Locust-based websocket load test at scale.

### Prerequisites
- Target backend reachable from Azure Load Testing engines (public or VNet-integrated).
- WebSocket endpoint URL (use `wss://` for non-local targets).
- Generated PCM audio files (see step 1 below).

### Steps
1) Generate audio files
```bash
python tests/load/audio_generator.py --max-turns 5 --scenarios insurance_inquiry quick_question
# Files appear under tests/load/audio_cache/*.pcm
```

2) Create an Azure Load Test (type: Locust)
- In Azure Portal: Azure Load Testing → Tests → Create → Test type: Locust.
- Test script: upload `tests/load/locustfile.py` (ensure it is named `locustfile.py`).

3) Upload PCM files
- In “Additional files”, upload all `.pcm` files from `tests/load/audio_cache`.
- Azure places additional files in the working directory alongside the test script.
- Set `PCM_DIR` to `./` so the Locust task finds the uploaded audio.

4) Configure environment variables
- `WS_URL`: target websocket, for example `wss://<host>/api/v1/media/stream`.
- `PCM_DIR`: set to `./` (Azure keeps uploaded PCM files in the same dir).
- Optional tuning:
  - `TURNS_PER_USER` (default 3), `CHUNKS_PER_TURN` (default 100), `CHUNK_MS` (default 20)
  - `FIRST_BYTE_TIMEOUT_SEC`, `BARGE_QUIET_MS`, `TURN_TIMEOUT_SEC`
  - `WS_IGNORE_CLOSE_EXCEPTIONS=true` to treat normal WS close codes (1000/1001/1006) as non-errors

5) Configure load and engines
- Users (spawned) and spawn rate: based on desired concurrency.
- Test duration and number of engine instances as needed.

6) Add server-side metrics (recommended)
- In the test configuration, add monitored Azure resources (App Service, AKS, etc.).
- Use the `azd-env-name` tag to locate resources for your environment and add them.

7) Run and analyze
- Start the test and review client metrics (TTFB, barge-in) and server metrics together.
- Note: graceful WebSocket closes are common under load; with the default config, these are not counted as failures.

## 🖥️ Run Locally (Locust)

Run the same Locust test on your machine for quick, iterative validation.

### Install dependencies
```bash
pip install -r requirements.txt
```

### 1) Generate audio files
```bash
python tests/load/audio_generator.py --max-turns 5 --scenarios insurance_inquiry quick_question
```

### 2) Set environment variables
- `WS_URL` (local example): `ws://127.0.0.1:8010/api/v1/media/stream`
- `WS_URL` (remote/TLS): `wss://<host>/api/v1/media/stream`
- `PCM_DIR`: `tests/load/audio_cache`
- Optional: `WS_IGNORE_CLOSE_EXCEPTIONS=true` (default enabled)

Example:
```bash
export WS_URL=ws://127.0.0.1:8010/api/v1/media/stream
export PCM_DIR=tests/load/audio_cache
```

### 3) Run with web UI
```bash
locust -f tests/load/locustfile.py
# Open http://localhost:8089 and configure Users/Spawn rate/Run time
```

### 4) Run headless (CI-friendly)
```bash
locust -f tests/load/locustfile.py \
  --headless -u 10 -r 2 --run-time 5m \
  --stop-timeout 30
```

Notes
- The Locust task streams PCM frames to `WS_URL` and rotates across all files in `PCM_DIR`.
- For `wss://` endpoints, TLS verification is enabled with system CAs (via certifi) and the `Origin` header is set automatically.
- Normal WebSocket closes (1000/1001/1006) are treated as non-errors by default; set `WS_IGNORE_CLOSE_EXCEPTIONS=false` to enforce strict behavior.

#### **Performance Degradation Patterns**
- **Turn Position Impact**: Later turns often have higher latency
- **Template Complexity**: Longer conversations show accumulating delays
- **Concurrent Load Effect**: Higher concurrency increases P95/P99 latencies

## 🎭 Conversation Scenarios (Simplified)

### **Scenario 1: `insurance_inquiry` (5 turns)**
1. "Hello, my name is Alice Brown, my social is 1234, and my zip code is 60601"
2. "I'm calling about my auto insurance policy"  
3. "I need to understand what's covered under my current plan"
4. "What happens if I get into an accident?"
5. "Thank you for all the information, that's very helpful"

### **Scenario 2: `quick_question` (3 turns)**
1. "Hi there, I have a quick question"
2. "Can you help me check my account balance?"
3. "Thanks, that's all I needed to know"

## 🏗️ FAANG-Level Test Strategy

### **Development Testing**
```bash
# Quick validation (3 turns, 5 conversations)
python tests/load/detailed_statistics_analyzer.py --turns 3 --conversations 5 --concurrent 2
```

### **Performance Testing**
```bash
# Realistic load (5 turns, 20 conversations)  
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 20 --concurrent 5
```

### **Stress Testing**
```bash
# Heavy load (5 turns, 50 conversations, 10 concurrent)
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 50 --concurrent 10
```

### **Latency Profiling**
```bash
# Fixed turn count for consistent latency analysis
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 30 --concurrent 3
```

## 📈 Performance Targets (FAANG Standards)

### **Latency Targets by Turn Position**
| Turn | Recognition P95 | Processing P95 | E2E P95 | Success Rate |
|------|----------------|----------------|---------|--------------|
| 1    | <1000ms        | <1800ms        | <2500ms | >98%         |
| 2    | <1100ms        | <1900ms        | <2600ms | >95%         |
| 3    | <1200ms        | <2000ms        | <2700ms | >92%         |
| 4    | <1300ms        | <2100ms        | <2800ms | >90%         |
| 5    | <1400ms        | <2200ms        | <2900ms | >88%         |

### **Conversation-Level Targets**
- **3-turn conversations**: <20s total duration, >95% success rate
- **5-turn conversations**: <50s total duration, >90% success rate
- **Concurrent capacity**: 10+ concurrent 5-turn conversations
- **Error rate**: <5% overall turn failure rate

## 🔧 Configuration Examples

### **Consistent Turn Analysis**
```python
config = LoadTestConfig(
    max_conversation_turns=5,
    min_conversation_turns=5,
    turn_variation_strategy="fixed",  # Same turns every time
    conversation_templates=["insurance_inquiry", "quick_question"]
)
```

### **Production Validation**
```python
config = LoadTestConfig(
    max_concurrent_conversations=10,
    total_conversations=50,
    max_conversation_turns=5,
    turn_variation_strategy="fixed"
)
```

## 💾 Output Files

### **Detailed Analysis JSON**
```
tests/load/results/detailed_stats_5turns_20250829_143022.json
```

Contains:
- Complete per-turn statistics with all percentiles
- Turn position analysis (performance by turn number)
- Template comparison metrics
- Failure analysis with error categorization
- Conversation-level statistics

### **Load Test Results JSON**  
```
tests/load/results/conversation_load_test_20250829_143022.json
```

Contains:
- Raw conversation metrics
- Configuration used
- Individual conversation details
- Error logs and timestamps

## 🚀 Quick Start Commands

```bash
# 1. Generate audio files (run once)
python tests/load/audio_generator.py --max-turns 5

# 2. Validate setup  
python tests/load/test_multi_turn.py

# 3. Run detailed analysis (5 turns, 20 conversations)
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 20

# 4. Compare different turn counts
python tests/load/detailed_statistics_analyzer.py --turns 3 --conversations 15
python tests/load/detailed_statistics_analyzer.py --turns 5 --conversations 20
```

This framework now provides **production-grade detailed statistics** with **FAANG-level analysis depth** for your multi-turn conversation load testing! 🎯
