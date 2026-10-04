import { API_BASE_URL } from '../config/constants.js';
import { DEFAULT_TRANSCRIPTION_MODEL, MAI_TRANSCRIPTION_MODEL } from './maiSpeech.js';

export const agentKey = (name) => String(name || '').trim().toLowerCase();

// Only for displaying tool assignments. Draft metadata never enters a save payload.
export function mergeAgentAssignments(...catalogs) {
  const agents = new Map();
  catalogs.flat().forEach((agent) => {
    const key = agentKey(agent.name);
    agents.set(key, { ...agents.get(key), ...agent });
  });
  return [...agents.values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
}

export const CASCADE_MODEL_PRESETS = [
  'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-4',
  'gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'o3-mini', 'o3', 'o1',
].map((id) => ({ id, label: id }));

export const BYOM_OPTIONS = [
  { value: '', label: 'Managed VoiceLive' },
  { value: 'byom-azure-openai-realtime', label: 'My Azure OpenAI Realtime deployment' },
  { value: 'byom-azure-openai-chat-completion', label: 'My Foundry chat deployment' },
  { value: 'byom-foundry-anthropic-messages', label: 'Foundry Anthropic (preview)' },
];

export const TRANSCRIPTION_MODELS = [
  DEFAULT_TRANSCRIPTION_MODEL, MAI_TRANSCRIPTION_MODEL, 'azure-speech',
  'gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'whisper-1', 'auto',
];

export function parsePercent(value) {
  if (typeof value === 'number') return value;
  const match = String(value || '').match(/[+-]?\d+(\.\d+)?/);
  return match ? Number(match[0]) : 0;
}

export const toPercent = (value) => `${value >= 0 ? '+' : ''}${Math.round(value)}%`;
export const sameConfig = (left, right) => JSON.stringify(left) === JSON.stringify(right);

export async function quickTuneRequest(path, {
  signal, timeoutMs = 20000, allowNotFound = false, ...options
} = {}) {
  const timeout = AbortSignal.timeout(timeoutMs);
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/${path}`, {
      ...options,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch (cause) {
    if (cause?.name !== 'TypeError') throw cause;
    // Gateway/WAF rejections omit CORS headers, so the browser only reports a network failure.
    throw new Error('The request did not reach the server. It may have been blocked by a firewall or proxy, or the network is unavailable.', { cause });
  }
  if (allowNotFound && response.status === 404) return null;
  if (!response.headers.get('content-type')?.includes('json')) {
    throw new Error(`The server returned an unexpected response (HTTP ${response.status}).`);
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc?.join('.') || 'Configuration'}: ${item.msg}`).join('; ')
      : data.detail;
    const error = new Error(typeof detail === 'string' ? detail : `Request failed (HTTP ${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}

// Resolve the API's read shapes to its write schema without using truncated
// prompt previews or replacing unedited settings with UI defaults.
export function editableAgent(raw) {
  const session = structuredClone(raw.session || {});
  if (session.turn_detection) {
    const detection = session.turn_detection;
    session.turn_detection_type = detection.type ?? session.turn_detection_type;
    session.turn_detection_threshold = detection.threshold ?? session.turn_detection_threshold;
    session.silence_duration_ms = detection.silence_duration_ms ?? session.silence_duration_ms;
    session.prefix_padding_ms = detection.prefix_padding_ms ?? session.prefix_padding_ms;
    delete session.turn_detection;
  }
  return {
    name: raw.name,
    description: raw.description || '',
    greeting: raw.greeting || '',
    return_greeting: raw.return_greeting || '',
    handoff_trigger: raw.handoff_trigger || '',
    prompt: raw.prompt_full ?? raw.prompt ?? '',
    tools: [...(raw.tools || [])],
    cascade_model: structuredClone(raw.cascade_model || raw.model || {}),
    voicelive_model: structuredClone(raw.voicelive_model || raw.model || {}),
    byom: structuredClone(raw.byom || null),
    voice: structuredClone(raw.voice || {}),
    speech: structuredClone(raw.speech || {}),
    session,
    template_vars: structuredClone(raw.template_vars || {}),
  };
}

export async function loadEditableAgent(name, sessionId, templates, signal) {
  let data = await quickTuneRequest(
    `agent-builder/session/${encodeURIComponent(sessionId)}?agent_name=${encodeURIComponent(name)}`,
    { signal, allowNotFound: true },
  );
  if (!data) {
    const template = templates.find((agent) => agentKey(agent.name) === agentKey(name));
    if (!template?.id) throw new Error(`No configuration found for "${name}". Refresh the agent catalog.`);
    data = await quickTuneRequest(`agent-builder/templates/${encodeURIComponent(template.id)}`, { signal });
  }
  const raw = data.config;
  if (!raw || agentKey(raw.name) !== agentKey(name)
    || typeof (raw.prompt_full ?? raw.prompt) !== 'string') {
    throw new Error('The server did not return the selected agent\'s full configuration. Nothing was changed.');
  }
  return editableAgent(raw);
}

export function liveSettingsPatch(base, draft) {
  if (!base || !draft || sameConfig(base, draft)) return null;
  const before = structuredClone(base);
  const after = structuredClone(draft);
  const patch = { mode: 'voicelive' };
  const voice = {};
  for (const key of ['name', 'rate']) {
    if (before.voice[key] !== after.voice[key]) voice[key] = after.voice[key];
    delete before.voice[key];
    delete after.voice[key];
  }
  const detection = {};
  for (const [key, apiKey] of [
    ['turn_detection_type', 'type'],
    ['turn_detection_threshold', 'threshold'],
    ['silence_duration_ms', 'silence_duration_ms'],
    ['prefix_padding_ms', 'prefix_padding_ms'],
  ]) {
    if (before.session[key] !== after.session[key]) detection[apiKey] = after.session[key];
    delete before.session[key];
    delete after.session[key];
  }
  if (!sameConfig(before, after)) return null;
  if (Object.keys(voice).length) patch.voice = voice;
  if (Object.keys(detection).length) {
    patch.turn_detection = {
      type: draft.session.turn_detection_type || 'azure_semantic_vad', ...detection,
    };
  }
  return patch;
}

export function affectsActiveMode(base, draft, mode) {
  if (!base) return false;
  const before = structuredClone(base);
  const after = structuredClone(draft);
  for (const key of mode === 'voicelive' ? ['cascade_model', 'speech'] : ['voicelive_model', 'byom', 'session']) {
    delete before[key];
    delete after[key];
  }
  return !sameConfig(before, after);
}

export function copyAgentName(name, names) {
  const used = new Set(names.map(agentKey));
  const stem = `${String(name || 'Agent').replace(/\s+/g, '').slice(0, 48)}Copy`;
  let candidate = stem;
  let suffix = 2;
  while (used.has(agentKey(candidate))) candidate = `${stem}${suffix++}`;
  return candidate;
}

export function copyAgentConfig(config, names, tools) {
  const routingTools = new Set(tools.filter((tool) => tool.is_handoff).map((tool) => tool.name));
  return {
    ...structuredClone(config),
    name: copyAgentName(config.name, names),
    handoff_trigger: '',
    // A copy keeps capabilities; the new scenario supplies its own routing.
    tools: (config.tools || []).filter((name) => !routingTools.has(name)),
  };
}

export function replaceScenarioAgent(scenario, previousName, nextName) {
  const replace = (name) => agentKey(name) === agentKey(previousName) ? nextName : name;
  return {
    ...scenario,
    agents: scenario.agents.map(replace),
    start_agent: replace(scenario.start_agent),
    handoffs: scenario.handoffs.map((route) => ({
      ...route,
      from_agent: replace(route.from_agent),
      to_agent: replace(route.to_agent),
    })),
  };
}

export function scenarioFlowError(scenario, tools) {
  if (!scenario) return '';
  if (!scenario.name?.trim() || scenario.name.length > 64) {
    return 'Give the scenario a name of 1 to 64 characters.';
  }
  const names = (scenario.agents || []).map(agentKey);
  if (!names.length || names.some((name) => !name) || new Set(names).size !== names.length) {
    return 'Select at least one agent, with no duplicate names.';
  }
  if (!names.includes(agentKey(scenario.start_agent))) return 'Choose a starting agent from this scenario.';
  const routingTools = new Set(tools.filter((tool) => tool.is_handoff).map((tool) => tool.name));
  for (const [index, route] of (scenario.handoffs || []).entries()) {
    const source = agentKey(route.from_agent);
    const target = agentKey(route.to_agent);
    if (!names.includes(source) || !names.includes(target) || source === target) {
      return `Handoff ${index + 1} must connect two different agents in this scenario.`;
    }
    if (!route.handoff_condition?.trim()) return `Describe when handoff ${index + 1} should happen.`;
    if (!routingTools.has(route.tool)) return `Choose a registered tool for handoff ${index + 1}.`;
  }
  return '';
}
