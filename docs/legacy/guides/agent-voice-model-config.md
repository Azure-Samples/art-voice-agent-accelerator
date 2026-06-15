# Agent Voice & Model Configuration Guide

## 📋 Overview

You can configure **TTS voice** and **LLM model** for each agent in two places:
1. **Agent YAML** (`registries/agentstore/{agent_name}/agent.yaml`) - Agent defaults
2. **Scenario YAML** (`registries/scenariostore/{scenario}/scenario.yaml`) - Per-scenario overrides

---

## 🎙️ Voice Configuration (TTS)

### In Agent YAML

```yaml
# registries/agentstore/concierge/agent.yaml

voice:
  name: en-US-AvaMultilingualNeural  # Azure TTS voice name
  type: azure-standard                # Voice provider type
  rate: "-4%"                         # Speech rate (slower/faster)
  style: cheerful                     # Voice style (optional)
  pitch: "+5%"                        # Pitch adjustment (optional)
```

### Available Azure TTS Voices

**Popular Banking/Insurance Voices**:
```yaml
# Professional & Friendly
voice:
  name: en-US-AvaMultilingualNeural      # Young, professional female
  
voice:
  name: en-US-AndrewMultilingualNeural   # Professional male
  
voice:
  name: en-US-EmmaMultilingualNeural     # Clear, trustworthy female
  
voice:
  name: en-US-BrianMultilingualNeural    # Authoritative male

# More options
voice:
  name: en-US-JennyNeural                # Warm, conversational
  
voice:
  name: en-US-GuyNeural                  # Mature, confident
  
voice:
  name: en-US-AriaNeural                 # Energetic, clear
  
voice:
  name: en-US-DavisNeural                # Deep, professional
```

**Find more**: [Azure TTS Voice Gallery](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)

### Voice Styles (Optional)

Some voices support styles:
```yaml
voice:
  name: en-US-AvaMultilingualNeural
  style: cheerful     # Options: cheerful, empathetic, calm, angry, sad, excited
```

### Speech Rate & Pitch

```yaml
voice:
  name: en-US-AvaMultilingualNeural
  rate: "-10%"   # Slower (range: -50% to +100%)
  pitch: "+5%"   # Higher pitch (range: -50% to +50%)
```

---

## 🤖 Model Configuration (LLM)

### Configuration Options: Same vs Different Models

You have **TWO options** for configuring models:

#### Option 1: Same Model for Both Modes (Simpler)

Use **`model:`** only - both VoiceLive and Cascade will use this configuration:

```yaml
# registries/agentstore/concierge/agent.yaml

# ✅ SIMPLE: One model for both modes
model:
  deployment_id: gpt-4o                   # Used by BOTH modes
  temperature: 0.7                        # Creativity (0.0-1.0)
  top_p: 0.9                             # Nucleus sampling (0.0-1.0)
  max_tokens: 150                        # Max response length
```

#### Option 2: Different Models Per Mode (Advanced)

Use **`model:`** for VoiceLive AND **`llm:`** for Cascade:

```yaml
# registries/agentstore/concierge/agent.yaml

# ✅ ADVANCED: Different model per mode
model:
  deployment_id: gpt-realtime  # VoiceLive mode uses this
  temperature: 0.7
  max_tokens: 150

llm:
  deployment_id: gpt-4o-mini              # Cascade mode uses this
  temperature: 0.8                        # Can be different!
  max_tokens: 200                         # Can be different!
```

**When to use different models**:
- 💰 Save costs: VoiceLive with `gpt-4o` + Cascade with `gpt-4o-mini`
- 🧪 A/B testing: Compare model performance across modes
- ⚙️ Different tuning: Different temperature/tokens per mode
- 🎯 Specialized: Realtime model for VoiceLive, optimized model for Cascade

### Configuration Priority

```
If ONLY "model:" is defined:
  → Both VoiceLive and Cascade use "model:"

If BOTH "model:" and "llm:" are defined:
  → VoiceLive uses "model:"
  → Cascade uses "llm:"

If ONLY "llm:" is defined:
  → VoiceLive falls back to defaults
  → Cascade uses "llm:"
```

### Mode-Specific Behavior

**VoiceLive Mode** (`ACS_STREAMING_MODE=voice_live`):
- Reads from `model:` section
- Uses Azure OpenAI Realtime API
- Best with: `gpt-realtime` or `gpt-4o`
- Handles STT, TTS, and turn detection automatically

**Cascade Mode** (`ACS_STREAMING_MODE=media`):
- Reads from `llm:` section (if exists), otherwise `model:`
- Uses standard Azure OpenAI Chat Completions API
- Works with: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
- Separate Speech SDK handles STT/TTS

### Examples

**Example 1: Cost Optimization**
```yaml
# Use expensive model only in VoiceLive, cheaper in Cascade
model:
  deployment_id: gpt-realtime  # VoiceLive (premium)
  temperature: 0.7

llm:
  deployment_id: gpt-4o-mini              # Cascade (cheaper)
  temperature: 0.8
```

**Example 2: Testing Strategy**
```yaml
# Test different models in each mode
model:
  deployment_id: gpt-4o                   # VoiceLive
  temperature: 0.6

llm:
  deployment_id: gpt-4-turbo              # Cascade
  temperature: 0.7
```

**Example 3: Different Tuning**
```yaml
# Same model, different parameters
model:
  deployment_id: gpt-4o
  temperature: 0.5                        # VoiceLive: more conservative
  max_tokens: 100                         # Shorter responses

llm:
  deployment_id: gpt-4o
  temperature: 0.8                        # Cascade: more creative
  max_tokens: 200                         # Longer responses
```

**Example 4: Simple Setup**
```yaml
# One model, both modes (recommended for most use cases)
model:
  deployment_id: gpt-4o
  temperature: 0.7
  max_tokens: 150
```

### STT Configuration (Speech-to-Text)

```yaml
# In agent YAML
session:
  input_audio_transcription_settings:
    model: gpt-4o-transcribe     # Whisper model for STT
    language: en-US              # Primary language
```

**Available STT Models**:
- `gpt-4o-transcribe` - Best accuracy (recommended)
- `whisper-1` - Good accuracy, faster

---

## 🎯 Scenario Overrides

### Override Voice Per Scenario

```yaml
# registries/scenariostore/banking/scenario.yaml

agent_overrides:
  concierge:
    voice:
      name: en-US-EmmaMultilingualNeural  # Different voice for banking
      rate: "-5%"                         # Slightly slower for clarity
      style: professional
    
  investment_advisor:
    voice:
      name: en-US-BrianMultilingualNeural # Male voice for advisor
      rate: "0%"                          # Normal speed
      pitch: "-5%"                        # Slightly deeper
```

### Override Model Per Scenario

```yaml
# registries/scenariostore/insurance/scenario.yaml

agent_overrides:
  fraud_agent:
    model:
      deployment_id: gpt-4o              # More powerful model for fraud
      temperature: 0.5                   # Lower temp for consistency
      max_tokens: 200
    
  auth_agent:
    model:
      deployment_id: gpt-4o-mini         # Faster model for auth
      temperature: 0.3                   # Very consistent
```

---

## 🏗️ Complete Example: Banking Concierge

### Full Agent Configuration (Works with BOTH modes)

```yaml
# registries/agentstore/concierge/agent.yaml

name: Concierge
description: Primary banking assistant

greeting: |
  {% if caller_name %}Hi {{ caller_name }}, I'm {{ agent_name }}, your banking assistant. How can I help you today?
  {% else %}Hi, I'm your banking assistant. How can I help you today?
  {% endif %}

return_greeting: |
  {% if caller_name %}Welcome back, {{ caller_name }}. Is there anything else I can assist you with?
  {% else %}Is there anything else I can assist you with?
  {% endif %}

# ─────────────────────────────────────────────────────────────────────────────
# Handoff Configuration
# ─────────────────────────────────────────────────────────────────────────────
handoff:
  trigger: handoff_concierge
  is_entry_point: true                   # This is the starting agent

# ─────────────────────────────────────────────────────────────────────────────
# Voice Configuration (Used by BOTH VoiceLive and Cascade)
# ─────────────────────────────────────────────────────────────────────────────
voice:
  name: en-US-AvaMultilingualNeural      # Azure TTS voice
  type: azure-standard                   # Voice type
  rate: "-4%"                            # Slightly slower for clarity
  # pitch: "+0%"                         # Optional: adjust pitch
  # style: cheerful                      # Optional: voice style

# ─────────────────────────────────────────────────────────────────────────────
# Model Configuration (Used by BOTH modes)
# ─────────────────────────────────────────────────────────────────────────────
model:
  deployment_id: gpt-realtime # Works in VoiceLive & Cascade
  temperature: 0.7                       # Balanced creativity
  top_p: 0.9                            # Nucleus sampling
  max_tokens: 150                       # Response length limit
  # frequency_penalty: 0.0               # Optional: reduce repetition
  # presence_penalty: 0.0                # Optional: encourage diversity

# ─────────────────────────────────────────────────────────────────────────────
# Session Configuration (VoiceLive Mode ONLY)
# ─────────────────────────────────────────────────────────────────────────────
# Only used when ACS_STREAMING_MODE=voice_live
# Ignored in cascade mode
session:
  modalities: [TEXT, AUDIO]
  input_audio_format: PCM16
  output_audio_format: PCM16

  # STT settings (VoiceLive mode)
  input_audio_transcription_settings:
    model: gpt-4o-transcribe             # Whisper model
    language: en-US                      # Primary language

  # Turn detection (when user finishes speaking)
  turn_detection:
    type: azure_semantic_vad             # VAD type
    threshold: 0.5                       # Sensitivity (0.0-1.0)
    prefix_padding_ms: 240               # Audio buffer before speech
    silence_duration_ms: 720             # Silence before responding

  # Tool behavior
  tool_choice: auto                      # Let model decide when to use tools
  # parallel_tool_calls: true            # Allow multiple tools at once

# ─────────────────────────────────────────────────────────────────────────────
# Speech Configuration (Cascade Mode ONLY)
# ─────────────────────────────────────────────────────────────────────────────
# Only used when ACS_STREAMING_MODE=media
# Ignored in voice_live mode
speech:
  # Speech-to-Text (Azure Speech SDK)
  recognition:
    language: en-US
    # phrase_list:                       # Custom vocabulary
    #   - "Contoso Bank"
    #   - "certificate of deposit"
    
  # Text-to-Speech (Azure Speech SDK)
  synthesis:
    voice_name: en-US-AvaMultilingualNeural  # Inherits from voice.name
    
  # Voice Activity Detection
  vad:
    threshold: 0.02                      # RMS threshold
    silence_duration_ms: 700             # Silence to end turn
    prefix_padding_ms: 200               # Audio buffer

# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────
tools:
  - verify_client_identity
  - get_account_summary
  - get_recent_transactions
  - handoff_investment_advisor
  - handoff_card_recommendation
  - escalate_human

# ─────────────────────────────────────────────────────────────────────────────
# Prompt Template
# ─────────────────────────────────────────────────────────────────────────────
prompt_template_path: concierge/prompt.md
```

### Key Points

1. **`voice:`** - Used by both modes for TTS
2. **`model:`** - Used by both modes for LLM reasoning
3. **`session:`** - Only for VoiceLive mode (STT, turn detection)
4. **`speech:`** - Only for Cascade mode (Speech SDK settings)

When you switch `ACS_STREAMING_MODE` environment variable, the agent automatically uses the correct configuration sections!

---

## 🎨 Scenario-Specific Customization

```yaml
# registries/scenariostore/banking/scenario.yaml

name: banking
start_agent: concierge

agents:
  - concierge
  - investment_advisor

agent_overrides:
  # Use warmer, friendlier voice for private banking
  concierge:
    voice:
      name: en-US-EmmaMultilingualNeural
      rate: "-5%"
      style: friendly
    model:
      temperature: 0.8                    # More creative responses
    greeting: "Welcome to Private Banking! I'm Emma, your personal concierge."
  
  # Use professional male voice for investment advisor
  investment_advisor:
    voice:
      name: en-US-BrianMultilingualNeural
      rate: "0%"
      style: professional
    model:
      deployment_id: gpt-4o               # Use best model for investment advice
      temperature: 0.6                    # Balance creativity and consistency
    greeting: "I'm your investment advisor. Let's discuss your portfolio."
```

---

## 🔧 Testing Different Voices

### Quick Voice Test

1. Edit agent YAML:
```yaml
voice:
  name: en-US-AndrewMultilingualNeural  # Try different voice
```

2. Restart backend:
```bash
make restart_backend
```

3. Test call - voice should change immediately!

### A/B Testing Multiple Voices

```yaml
# registries/scenariostore/banking/scenario.yaml

agent_overrides:
  concierge:
    voice:
      name: en-US-AvaMultilingualNeural   # Voice A
      
# registries/scenariostore/insurance/scenario.yaml

agent_overrides:
  concierge:
    voice:
      name: en-US-EmmaMultilingualNeural  # Voice B
```

Switch scenarios in UI to compare voices!

---

## 📊 Voice Configuration Hierarchy

**Priority (highest to lowest)**:
1. **Scenario override** - `registries/scenariostore/{scenario}/scenario.yaml` → `agent_overrides.{agent}.voice`
2. **Agent default** - `registries/agentstore/{agent}/agent.yaml` → `voice`
3. **Global default** - `registries/agentstore/_defaults.yaml` → `voice`
4. **System fallback** - `en-US-AvaMultilingualNeural`

Example:
```
Banking scenario override:      en-US-EmmaMultilingualNeural  ← WINS
Agent YAML default:             en-US-AvaMultilingualNeural
Global default:                 en-US-JennyNeural
```

---

## 🎯 Common Configuration Patterns

### Pattern 1: Professional Banking Voice
```yaml
voice:
  name: en-US-EmmaMultilingualNeural
  rate: "-5%"      # Slightly slower for clarity
  style: professional
model:
  deployment_id: gpt-4o
  temperature: 0.6  # Balanced responses
```

### Pattern 2: Friendly Insurance Agent
```yaml
voice:
  name: en-US-AvaMultilingualNeural
  rate: "0%"
  style: cheerful
model:
  deployment_id: gpt-4o-mini
  temperature: 0.8   # More conversational
```

### Pattern 3: Authoritative Fraud Agent
```yaml
voice:
  name: en-US-BrianMultilingualNeural
  rate: "-3%"
  pitch: "-5%"       # Deeper voice
  style: serious
model:
  deployment_id: gpt-4o
  temperature: 0.4   # Very consistent, fact-based
```

### Pattern 4: Fast Customer Service
```yaml
voice:
  name: en-US-JennyNeural
  rate: "+5%"        # Faster for efficiency
model:
  deployment_id: gpt-4o-mini  # Fast model
  temperature: 0.7
  max_tokens: 100    # Shorter responses
```

---

## 🚀 Best Practices

### Voice Selection
✅ **Do**:
- Test voices with real users
- Match voice to agent persona (friendly concierge vs serious fraud agent)
- Adjust rate based on complexity (slower for financial details)
- Use multilingual voices for international scenarios

❌ **Don't**:
- Use fast speech rates for complex information
- Change voices too frequently (confuses users)
- Use extreme pitch adjustments (sounds unnatural)

### Model Selection
✅ **Do**:
- Use `gpt-4o` for complex reasoning (fraud detection, financial advice)
- Use `gpt-4o-mini` for simple tasks (auth, routing)
- Lower temperature for factual responses (0.3-0.5)
- Higher temperature for creative responses (0.7-0.9)

❌ **Don't**:
- Use `gpt-4o` everywhere (expensive)
- Set temperature > 0.9 (too random)
- Set max_tokens too low (truncated responses)

---

## 📝 Quick Reference

**Voice Changes**:
```yaml
# Agent YAML or Scenario override
voice:
  name: en-US-AvaMultilingualNeural    # Required
  rate: "-5%"                          # Optional: -50% to +100%
  pitch: "0%"                          # Optional: -50% to +50%
  style: cheerful                      # Optional: voice-dependent
```

**Model Changes**:
```yaml
# Option 1: Same model for both modes
model:
  deployment_id: gpt-4o                   # Used by both modes
  temperature: 0.7                        # Optional: 0.0-1.0
  max_tokens: 150                         # Optional: response length

# Option 2: Different models per mode
model:
  deployment_id: gpt-realtime  # VoiceLive uses this
  temperature: 0.7
  
llm:
  deployment_id: gpt-4o-mini              # Cascade uses this
  temperature: 0.8
  max_tokens: 200
```

**STT Changes (VoiceLive mode only)**:
```yaml
# Agent YAML only
session:
  input_audio_transcription_settings:
    model: gpt-4o-transcribe  # Or whisper-1
    language: en-US           # Or es-ES, fr-FR, etc.
```

**Speech SDK Changes (Cascade mode only)**:
```yaml
# Agent YAML only
speech:
  recognition:
    language: en-US
    phrase_list:              # Custom vocabulary
      - "Contoso Bank"
      - "401k"
  synthesis:
    voice_name: en-US-AvaMultilingualNeural
  vad:
    threshold: 0.02
    silence_duration_ms: 700
```

---

## 🔗 Related Documentation

- [Agent Framework](../architecture/agents/README.md) — Agent configuration and YAML schemas
- [Orchestration Overview](../architecture/orchestration/README.md) — VoiceLive vs Cascade modes
- [Azure TTS Voice List](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)
- [OpenAI Model Documentation](https://platform.openai.com/docs/models)
