---
name: add-message-handler
description: Add a handler for a new WebSocket message type
---

# Add Message Handler Skill

Add handlers for new WebSocket message types in the frontend.

## Message Envelope Structure

```typescript
interface MessageEnvelope {
  type: string;           // Message type identifier
  sender: string;         // "Assistant" | "User" | "System"
  payload: object;        // Actual message content
  ts: string;             // ISO 8601 timestamp
  session_id: string;     // Session identifier
  topic?: string;         // Optional routing topic
}
```

## Steps

### 1. Define Message Type

Add to message handler switch in `hooks/useWebSocket.js` or `App.jsx`:

```jsx
const handleMessage = useCallback((event) => {
  const envelope = JSON.parse(event.data);

  switch (envelope.type) {
    // ... existing cases ...

    case 'my_new_type':
      handleMyNewType(envelope.payload);
      break;

    default:
      console.log('Unknown message type:', envelope.type);
  }
}, []);
```

### 2. Create Handler Function

```jsx
const handleMyNewType = useCallback((payload) => {
  // Extract data from payload
  const { field1, field2 } = payload;

  // Update state
  setMyState(prev => ({
    ...prev,
    field1,
    field2,
  }));

  // Optional: trigger side effects
  if (field1) {
    onFieldUpdate?.(field1);
  }
}, [onFieldUpdate]);
```

### 3. Add State if Needed

```jsx
const [myState, setMyState] = useState({
  field1: null,
  field2: null,
});
```

## Common Message Types

| Type | Payload | Handler Action |
|------|---------|----------------|
| `assistant_streaming` | `{ content, streaming }` | Append to message buffer |
| `assistant` | `{ content }` | Finalize message |
| `event` | `{ event_type, event_data }` | Route to event handler |
| `tool_start` | `{ tool_name, tool_call_id }` | Show tool indicator |
| `tool_end` | `{ tool_name, result, error }` | Hide indicator, log result |
| `audio_data` | `{ data, sample_rate }` | Send to AudioWorklet |

## Example: Tool Progress Handler

```jsx
// State
const [activeTools, setActiveTools] = useState(new Map());

// Handler
const handleToolProgress = useCallback((envelope) => {
  const { tool_name, tool_call_id, pct } = envelope.payload;

  setActiveTools(prev => {
    const next = new Map(prev);
    if (envelope.type === 'tool_start') {
      next.set(tool_call_id, { name: tool_name, progress: 0 });
    } else if (envelope.type === 'tool_progress') {
      const tool = next.get(tool_call_id);
      if (tool) next.set(tool_call_id, { ...tool, progress: pct });
    } else if (envelope.type === 'tool_end') {
      next.delete(tool_call_id);
    }
    return next;
  });
}, []);

// In switch
case 'tool_start':
case 'tool_progress':
case 'tool_end':
  handleToolProgress(envelope);
  break;
```

## Example: Event Handler with Routing

```jsx
const handleEventMessage = useCallback((payload) => {
  const { event_type, event_data } = payload;

  switch (event_type) {
    case 'agent_change':
      setActiveAgent(event_data.active_agent_label);
      break;
    case 'session_updated':
      setSession(prev => ({ ...prev, ...event_data }));
      break;
    case 'call_connected':
      setCallStatus('connected');
      break;
    default:
      console.log('Unhandled event:', event_type);
  }
}, []);
```

## Sending Messages

```jsx
// Text message envelope
const sendTextMessage = (text) => {
  socket.send(JSON.stringify({
    type: 'user_message',
    sender: 'User',
    payload: { text },
    ts: new Date().toISOString(),
    session_id: sessionId,
  }));
};

// Binary audio data (no envelope)
const sendAudioData = (pcmSamples) => {
  socket.send(pcmSamples.buffer);
};
```
