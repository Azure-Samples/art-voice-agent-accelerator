# ARTAgent System

## Quick Start

### Create an Agent

1. **YAML Config** (`agent.yaml`):
```yaml
agent:
  name: "MyAgent"
  description: "Handles specific domain tasks"
model:
  deployment_id: "gpt-4o"
  temperature: 0.7
prompts:
  path: "my_agent_prompt.jinja"
tools:
  - tool_name_one
  - tool_name_two
voice:
  name: "en-US-AriaNeural"
  style: "chat"
```

2. **Initialize Agent**:
```python
agent = ARTAgent(config_path="path/to/agent.yaml")
result = await agent.respond(cm, user_input, ws, is_acs=False)
```

## ARTAgent Class

**Constructor**: Loads YAML config, validates required fields, sets up tools and prompts.

**Key Properties**:
- `name`, `description` - Agent metadata
- `model_id`, `temperature`, `top_p`, `max_tokens` - Model config
- `voice_name`, `voice_style`, `voice_rate` - TTS config
- `tools` - Available tool functions
- `prompt_path` - Jinja template path

**Main Method**: `respond(cm, user_prompt, ws, **kwargs)` - Processes user input and returns GPT response.

## Config Structure

```yaml
agent:          # Required: name, optional: creator, organization, description
model:          # Required: deployment_id, optional: temperature, top_p, max_tokens
prompts:        # Optional: path (defaults to voice_agent_authentication.jinja)
tools:          # Optional: list of tool names or dict configs
voice:          # Optional: name, style, rate for TTS
```

## File Organization

- `base.py` - ARTAgent class
- `agent_store/` - Agent YAML configs
- `prompt_store/` - Jinja prompt templates  
- `tool_store/` - Tool function registry