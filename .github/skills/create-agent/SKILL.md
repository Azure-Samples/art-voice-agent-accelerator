---
name: create-agent
description: Create a new voice agent with YAML configuration and prompt template
---

# Create Agent Skill

Create a new agent in `apps/artagent/backend/registries/agentstore/`.

## Directory Structure
```
agentstore/
└── {agent_name}/
    ├── agent.yaml      # Agent configuration
    └── prompt.jinja    # System prompt template
```

## agent.yaml Template

```yaml
name: AgentName
description: Brief description of agent's purpose

handoff:
  trigger: handoff_agent_name  # Tool name other agents use to transfer here

greeting: |
  Hi{{ ' ' + caller_name if caller_name else '' }}, I'm {{ agent_name | default('your assistant') }}.

return_greeting: |
  Welcome back{{ ', ' + caller_name if caller_name else '' }}. How else can I help?

voice:
  name: en-US-AlloyTurboMultilingualNeural
  type: azure-standard
  rate: "-4%"

voicelive_model:
  deployment_id: gpt-realtime
  temperature: 0.7
  max_tokens: 2048

cascade_model:
  deployment_id: gpt-4o
  temperature: 0.8
  max_tokens: 2048

session:
  modalities: [TEXT, AUDIO]
  input_audio_format: PCM16
  output_audio_format: PCM16
  input_audio_transcription_settings:
    model: gpt-4o-transcribe
    language: en-US
  turn_detection:
    type: azure_semantic_vad
    threshold: 0.5
    silence_duration_ms: 720
  tool_choice: auto

tools:
  - tool_name_1
  - tool_name_2
  - handoff_concierge  # Return to main agent

prompts:
  path: prompt.jinja
```

## prompt.jinja Template

```jinja
You are {{ agent_name | default('an assistant') }} at {{ institution_name | default('our company') }}.

## Your Role
[Describe the agent's specific responsibilities]

## Guidelines
- Be concise and clear
- [Add specific behavioral guidelines]

## Available Tools
{% for tool in tools %}
- {{ tool }}
{% endfor %}

## Current Context
{% if caller_name %}Customer: {{ caller_name }}{% endif %}
{% if client_id %}Client ID: {{ client_id }}{% endif %}
```

## Steps

1. Create directory: `apps/artagent/backend/registries/agentstore/{agent_name}/`
2. Create `agent.yaml` with configuration
3. Create `prompt.jinja` with system prompt
4. Reference existing tools from `registries/toolstore/` or create new ones
5. Add handoff tool to other agents if they should be able to transfer here

## Key Classes

- `UnifiedAgent` in `registries/agentstore/base.py` - base dataclass
- `HandoffConfig`, `VoiceConfig`, `ModelConfig` - configuration dataclasses
- Agents are loaded automatically by the agent loader

## Tools Reference

Check existing tools in `registries/toolstore/`:
- `auth.py` - Authentication tools
- `banking/` - Banking operations
- `fraud.py` - Fraud detection
- `handoffs.py` - Agent transfer tools
