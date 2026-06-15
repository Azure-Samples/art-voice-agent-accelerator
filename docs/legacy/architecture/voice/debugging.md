# Voice Debugging Guide

This guide helps you troubleshoot common voice issues. You'll learn:

- How to read voice logs
- Common problems and solutions
- Debugging tools and techniques
- Performance optimization

---

## Quick Diagnostics

### 1. Check if Voice Handler Started

Look for these log messages:

```
✅ Good: "[abc12345] Speech cascade handler started"
✅ Good: "[abc12345] Speech recognizer started"
❌ Bad:  "[abc12345] Failed to start recognizer: ..."
```

### 2. Check Audio Flow

```
✅ Good: "[abc12345] Partial speech: 'hello' (en-US)"
✅ Good: "[abc12345] Speech: 'check my balance' (en-US)"
❌ Bad:  No "Partial speech" logs = audio not reaching STT
```

### 3. Check Agent Response

```
✅ Good: "[abc12345] Enqueued speech event type=final"
✅ Good: "[abc12345] TTS response processed: Your balance is..."
❌ Bad:  "[abc12345] Orchestrator processing cancelled"
```

---

## Common Issues

### Issue: No Audio Recognition

**Symptoms:** No "Partial speech" or "Speech" logs

**Checklist:**

1. **Verify audio is being sent:**
   ```python
   # Add debug logging in handler
   logger.debug(f"Audio bytes received: {len(audio_bytes)}")
   ```

2. **Check Speech SDK initialization:**
   ```
   # Look for this log:
   "[abc12345] Pre-initialized push_stream"
   
   # If missing, recognizer may not be ready
   ```

3. **Verify audio format:**
   ```python
   # Expected: PCM 16-bit, 16kHz, mono
   # Check media streaming config in ACS
   ```

**Solution:**
```python
# Ensure push_stream is created before audio arrives
if hasattr(self.recognizer, "push_stream") and self.recognizer.push_stream is None:
    self.recognizer.create_push_stream()
```

---

### Issue: Barge-In Not Working

**Symptoms:** Can't interrupt the assistant while speaking

**Checklist:**

1. **Check barge-in suppression:**
   ```
   # During handoffs, barge-in is suppressed:
   "[abc12345] Barge-in suppressed"
   
   # After greeting plays:
   "[abc12345] Barge-in allowed"
   ```

2. **Check partial transcript threshold:**
   ```python
   # In speech_cascade/handler.py, partials < 3 chars are ignored
   if len(text.strip()) > 3:
       self.thread_bridge.schedule_barge_in(...)
   ```

3. **Verify TTS is cancelable:**
   ```
   # Look for:
   "[abc12345] Barge-in: cancelling TTS playback"
   ```

**Solution:**
```python
# Ensure barge-in is re-enabled after greetings
self.thread_bridge.allow_barge_in()
```

---

### Issue: Handoff Fails

**Symptoms:** "No target agent configured for handoff tool: X"

**Checklist:**

1. **Verify tool is registered:**
   ```bash
   python -c "
   from apps.artagent.backend.registries.toolstore.registry import get_all_tools
   print([t for t in get_all_tools() if 'handoff' in t['name']])
   "
   ```

2. **Check handoff map:**
   ```python
   # In orchestrator, handoff_map should include your tool:
   # {'handoff_fraud': 'FraudAgent', 'handoff_concierge': 'Concierge'}
   ```

3. **Verify target agent exists:**
   ```bash
   python -c "
   from apps.artagent.backend.registries.agentstore.loader import discover_agents
   print(list(discover_agents().keys()))
   "
   ```

**Solution:**
```yaml
# In agent YAML, ensure handoff trigger matches tool name:
handoff:
  trigger: handoff_fraud  # Must match tool name exactly
```

---

### Issue: Greeting Not Playing

**Symptoms:** Agent switches silently (when it shouldn't)

**Checklist:**

1. **Check handoff type in scenario:**
   ```yaml
   # Should be 'announced' for greeting:
   handoffs:
     - from_agent: Concierge
       to_agent: FraudAgent
       type: announced  # Not 'discrete'
   ```

2. **Check greeting template:**
   ```bash
   python -c "
   from apps.artagent.backend.registries.agentstore.loader import discover_agents
   agent = discover_agents()['FraudAgent']
   print('Greeting:', agent.config.greeting)
   "
   ```

3. **Look for greeting selection logs:**
   ```
   # Good:
   "Greeting resolved for FraudAgent: Hi, I'm a fraud specialist..."
   
   # Bad:
   "Discrete handoff - skipping greeting for FraudAgent"
   ```

**Solution:**
```yaml
# Ensure agent has a greeting defined:
greeting: |
  Hi, I'm the fraud specialist. How can I help?
```

---

### Issue: High Latency

**Symptoms:** Long delay between user speech and assistant response

**Debugging Steps:**

1. **Enable telemetry timing:**
   ```python
   # Turn spans track each phase:
   turn.record_stt_complete(...)   # STT done
   turn.record_llm_first_token()   # LLM started
   turn.record_tts_first_audio()   # TTS started
   ```

2. **Check queue depth:**
   ```
   # High queue size = bottleneck:
   "[abc12345] Enqueued speech event type=final qsize=5"
   
   # Should be 0-2 normally
   ```

3. **Profile each phase using telemetry:**
   - STT latency varies by utterance length and language
   - LLM latency varies by prompt size and model
   - TTS latency varies by text length (streaming reduces perceived latency)

   Use the turn metrics emitted to Application Insights to measure actual latencies in your environment.

**Solutions:**

| Phase | Optimization |
|-------|-------------|
| STT | Use semantic segmentation: `use_semantic_segmentation=True` |
| LLM | Use `gpt-4o-mini` for simple tasks |
| TTS | Ensure streaming TTS is enabled |

---

## VoiceLive-Specific Issues

VoiceLive uses the OpenAI Realtime API, so debugging differs from Cascade.

### Issue: VoiceLive Connection Fails

**Symptoms:** "Failed to connect to OpenAI Realtime API"

**Checklist:**

1. **Verify deployment exists:**
   ```bash
   # Must be a realtime-capable deployment
   az cognitiveservices account deployment show \
     --name your-openai-resource \
     --deployment-name gpt-4o-realtime
   ```

2. **Check endpoint configuration:**
   ```python
   # In settings, verify:
   AZURE_OPENAI_REALTIME_ENDPOINT  # Must be set
   AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME
   ```

3. **Look for WebSocket errors:**
   ```
   "[abc12345] Realtime WebSocket error: 401 Unauthorized"
   "[abc12345] Realtime WebSocket error: deployment not found"
   ```

**Solution:**
```yaml
# In agent YAML:
voicelive_model:
  deployment_id: gpt-4o-realtime  # Must match Azure deployment name
```

---

### Issue: VoiceLive VAD Not Detecting Speech End

**Symptoms:** Agent waits too long after user stops talking

**Context:** VoiceLive uses **server-side VAD** (Voice Activity Detection) — you can't control it like Cascade.

**What you CAN adjust:**

```python
# In voicelive handler, session config includes:
{
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,           # Sensitivity (0-1)
        "prefix_padding_ms": 300,   # Audio to keep before speech
        "silence_duration_ms": 500  # How long silence = end of turn
    }
}
```

**Log to look for:**
```
"[abc12345] input_audio_buffer.speech_started"   # User started talking
"[abc12345] input_audio_buffer.speech_stopped"   # User stopped
"[abc12345] conversation.item.input_audio_transcription.completed"  # STT done
```

---

### Issue: VoiceLive Tool Calls Not Working

**Symptoms:** Agent says "I'll check that" but tool never executes

**Checklist:**

1. **Verify tools are in session config:**
   ```
   # Look for this log during session setup:
   "[abc12345] Realtime session configured with tools: ['verify_identity', 'check_balance']"
   ```

2. **Check tool response format:**
   ```python
   # VoiceLive expects tool results via:
   # conversation.item.create with type="function_call_output"
   ```

3. **Look for tool call events:**
   ```
   "[abc12345] response.function_call_arguments.done \| tool=check_balance"
   "[abc12345] Tool result sent: {'balance': 1234.56}"
   ```

**Solution:**
```python
# Ensure tool execution sends result back:
await realtime_client.send({
    "type": "conversation.item.create",
    "item": {
        "type": "function_call_output",
        "call_id": tool_call_id,
        "output": json.dumps(result)
    }
})
await realtime_client.send({"type": "response.create"})
```

---

### Issue: VoiceLive Audio Quality Issues

**Symptoms:** Choppy audio, echoes, or distortion

**Checklist:**

1. **Check audio format conversion:**
   ```
   # ACS sends 16kHz PCM, Realtime expects 24kHz PCM
   # Handler should resample automatically
   ```

2. **Look for buffer underruns:**
   ```
   "[abc12345] Audio buffer underrun - late packet"
   ```

3. **Verify WebSocket throughput:**
   ```
   # Realtime streams audio bidirectionally
   # Network latency > 100ms causes issues
   ```

**Solution:**
- Use Azure regions close to OpenAI endpoints
- Ensure sufficient WebSocket buffer sizes
- Consider Cascade mode for unreliable networks

---

## Debugging Tools

### 1. Enable Debug Logging

```python
# In your .env or environment:
LOG_LEVEL=DEBUG

# Or per-module:
import logging
logging.getLogger("voice.shared.handoff_service").setLevel(logging.DEBUG)
```

### 2. Use the REST API Test Client

```bash
# Test agent directly (no voice):
curl -X POST http://localhost:8000/api/v1/agents/FraudAgent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I think my card was stolen"}'
```

### 3. Inspect Session State

```python
# During a call, dump memory manager state:
from pprint import pprint
pprint(memo_manager.get_all_corememory())
```

### 4. Use OpenTelemetry Traces

```bash
# Start Jaeger for trace visualization:
docker run -d -p 16686:16686 -p 6831:6831/udp jaegertracing/all-in-one

# View traces at http://localhost:16686
```

---

## Log Message Reference

### Speech Recognition (Cascade)

| Log | Meaning |
|-----|---------|
| `Partial speech: 'X'` | Interim transcription (may change) |
| `Speech: 'X'` | Final transcription (sent to LLM) |
| `Speech error: X` | STT failed |
| `Barge-in skipped (suppressed)` | User spoke during handoff/greeting |

### VoiceLive Events

| Log | Meaning |
|-----|---------|
| `session.created` | Realtime WebSocket connected |
| `input_audio_buffer.speech_started` | User started talking |
| `input_audio_buffer.speech_stopped` | Server VAD detected end |
| `conversation.item.input_audio_transcription.completed` | STT done |
| `response.audio.delta` | Audio chunk received from API |
| `response.function_call_arguments.done` | Tool call ready to execute |
| `response.done` | Turn completed |

### Handoff (Both Modes)

| Log | Meaning |
|-----|---------|
| `Handoff resolved \| A → B` | Successful handoff routing |
| `Generic handoff denied` | Generic handoff not allowed |
| `Target agent 'X' not found` | Agent not in registry |

### TTS (Cascade Only)

| Log | Meaning |
|-----|---------|
| `TTS response processed: X...` | Text sent to TTS |
| `Barge-in: cancelling TTS` | User interrupted |
| `Queue full, dropping PARTIAL` | System overloaded |

---

## Performance Checklist

Before going to production:

### Cascade Mode
- [ ] Use `gpt-4o` or `gpt-4o-mini` (not `gpt-4`)
- [ ] Enable streaming TTS
- [ ] Set appropriate `vad_silence_timeout_ms` (800ms default)
- [ ] Monitor queue depth (should stay < 3)
- [ ] Test with realistic audio (not just text input)
- [ ] Verify barge-in works end-to-end
- [ ] Check handoff greeting timing

### VoiceLive Mode
- [ ] Use `gpt-4o-realtime` deployment
- [ ] Verify WebSocket latency < 100ms to endpoint
- [ ] Test VAD sensitivity for your audio environment
- [ ] Validate tool execution round-trips
- [ ] Confirm audio format conversion works (16kHz ↔ 24kHz)
- [ ] Test interruption behavior (server-side VAD)

---

## Getting Help

1. **Check logs first** - 90% of issues appear in logs
2. **Reproduce minimally** - Isolate the failing component
3. **Check this guide** - Most issues are documented
4. **Ask in Teams/Slack** - Share connection_id and logs

---

## See Also

- [Voice Architecture Overview](README.md) - How voice works
- [Voice Configuration Guide](configuration.md) - Agent setup
- [Telemetry Guide](../../operations/telemetry.md) - Tracing setup
