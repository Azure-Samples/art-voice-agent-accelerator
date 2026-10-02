import { installApiMocks, makeScenario } from './scenario-mocks.js';

export const AGENT_CONFIG = {
  name: 'BankingConcierge',
  description: 'Everyday banking help',
  prompt: 'Help {{customer_name}} with everyday banking. Use only your assigned tools. '
    + 'Confirm the request before taking an action. '.repeat(18),
  greeting: 'How can I help with your banking?',
  return_greeting: 'Welcome back.',
  handoff_trigger: 'handoff_concierge',
  tools: ['check_balance', 'handoff_to_agent'],
  cascade_model: {
    deployment_id: 'finance-deployment', name: 'finance-deployment', model_family: 'gpt-4',
    temperature: 0.37, max_tokens: 2300,
    top_p: 0.82, api_version: 'v1', endpoint_preference: 'responses',
  },
  voicelive_model: { deployment_id: 'gpt-realtime', temperature: 0.65, max_tokens: 4096 },
  byom: null,
  voice: {
    name: 'en-US-AvaMultilingualNeural', type: 'azure-standard', style: 'chat',
    rate: '-4%', pitch: '+8%',
  },
  speech: { vad_silence_timeout_ms: 800, use_semantic_segmentation: false, candidate_languages: ['en-US', 'es-ES'] },
  session: {
    modalities: ['TEXT', 'AUDIO'], input_audio_format: 'PCM16', output_audio_format: 'PCM16',
    turn_detection_type: 'azure_semantic_vad', turn_detection_threshold: 0.42,
    silence_duration_ms: 750, prefix_padding_ms: 280, tool_choice: 'auto',
    input_audio_transcription_settings: { model: 'azure-speech', language: 'en-US' },
  },
  template_vars: { customer_name: 'Test Customer', preferences: { language: 'en-US' } },
};

export const TOOL_CATALOG = [
  { name: 'check_balance', description: 'Read the account balance', tags: ['banking'], is_handoff: false, source: 'local' },
  { name: 'get_transactions', description: 'Read recent card transactions', tags: ['banking'], is_handoff: false, source: 'local' },
  { name: 'handoff_to_agent', description: 'Transfer to an agent by name', tags: [], is_handoff: true, source: 'local' },
];

export function scenarioDraft() {
  return {
    summary: 'Reuse the banking concierge and add a specialist to explain account balances.',
    scenario: {
      name: 'EverydayBanking', description: 'Answer balance questions and escalate to a specialist.',
      icon: 'B', agents: ['BankingConcierge', 'BalanceGuide'], start_agent: 'BankingConcierge',
      handoff_type: 'announced',
      handoffs: [{
        from_agent: 'BankingConcierge', to_agent: 'BalanceGuide', tool: 'handoff_to_agent',
        type: 'announced', share_context: true, handoff_condition: 'The customer asks about a balance.',
        context_vars: {},
      }],
      global_template_vars: { company_name: '' }, tools: [],
    },
    agents: [{
      ...structuredClone(AGENT_CONFIG), name: 'BalanceGuide', description: 'Explains balances',
      prompt: 'You explain account balances for {{company_name}} using check_balance.',
      handoff_trigger: '', tools: ['check_balance'],
    }],
    warnings: [], missing_capabilities: [], required_inputs: ['company_name'],
  };
}

export async function installQuickTuneMocks(page) {
  const scenarios = await installApiMocks(page);
  const state = {
    scenarios, calls: [], generateError: null, applyError: null, agentSaveError: null,
    scenarioConfigs: {}, scenarioSaveError: null, scenarioLoadError: null,
    draft: scenarioDraft(),
    missingOverrides: new Set(['BankingConcierge']),
    agents: {
      BankingConcierge: structuredClone(AGENT_CONFIG),
      FraudAgent: { ...structuredClone(AGENT_CONFIG), name: 'FraudAgent', description: 'Investigates fraud', prompt: 'Investigate fraud, not everyday balances.' },
    },
  };
  const respond = (route, body, status = 200) => route.fulfill({
    status, contentType: 'application/json', body: JSON.stringify(body),
  });
  const saveScenario = (config) => {
    const key = config.name.toLowerCase();
    state.scenarioConfigs[key] = structuredClone(config);
    const old = scenarios.scenariosResponse;
    const builtin = old.builtin_scenarios.some((item) => item.name.toLowerCase() === key);
    const saved = { ...makeScenario(config), ...config, is_active: true, is_custom: !builtin };
    const builtins = old.builtin_scenarios.map((item) => item.name.toLowerCase() === key
      ? { ...item, ...saved, is_session_override: true } : { ...item, is_active: false });
    const customs = old.custom_scenarios.filter((item) => item.name.toLowerCase() !== key)
      .map((item) => ({ ...item, is_active: false }));
    if (!builtin) customs.push(saved);
    scenarios.scenariosResponse = {
      ...old, builtin_scenarios: builtins, custom_scenarios: customs, scenarios: [...builtins, ...customs],
      active_scenario: saved.name, active_start_agent: saved.start_agent, active_scenario_icon: saved.icon,
    };
    return saved;
  };
  const inventory = () => ({
    agents: Object.values(state.agents).map((config) => ({
      name: config.name, description: config.description, tools: config.tools,
      model: config.cascade_model?.deployment_id, voice: config.voice?.name,
    })),
    start_agent: scenarios.scenariosResponse.active_start_agent,
  });
  await page.route('**/api/v1/agents{,?*}', (route) => respond(route, inventory()));
  await page.route('**/api/v1/agent-builder/templates?*', (route) => respond(route, {
    templates: Object.values(state.agents).map((config) => ({
      ...config, id: config.name.toLowerCase(), prompt_full: config.prompt,
    })),
  }));
  await page.route('**/api/v1/agent-builder/templates/*', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').pop();
    const config = Object.values(state.agents).find((agent) => agent.name.toLowerCase() === id);
    return respond(route, config ? { config, template: { ...config, id } }
      : { detail: 'Not found' }, config ? 200 : 404);
  });
  await page.route('**/api/v1/agent-builder/tools', (route) => respond(route, { tools: TOOL_CATALOG }));
  await page.route('**/api/v1/agent-builder/voices{,?*}', (route) => respond(route, {
    runtime_transcription_models: {
      cascade: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech'],
      voicelive: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech', 'whisper-1'],
    },
    voices: [
      { name: 'en-US-AvaMultilingualNeural', display_name: 'Ava' },
      { name: 'en-US-JennyNeural', display_name: 'Jenny' },
    ],
  }));
  await page.route('**/api/v1/agent-builder/models{,?*}', (route) => respond(route, {
    models: [
      { deployment_id: 'finance-deployment', category: 'chat', modes: ['cascade', 'voicelive'] },
      { deployment_id: 'finance-mini', category: 'chat', modes: ['cascade', 'voicelive'] },
    ],
  }));
  await page.route('**/api/v1/agent-builder/session/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const name = url.searchParams.get('agent_name');
    if (request.method() === 'GET') {
      if (name && state.missingOverrides.has(name)) return respond(route, { detail: 'No override' }, 404);
      // The default endpoint deliberately returns a DIFFERENT agent. Quick Tune
      // must ask for the named selection instead of editing the last-created one.
      const config = state.agents[name || 'FraudAgent'];
      return respond(route, config ? { config: { ...config, prompt_full: config.prompt } }
        : { detail: 'No override' }, config ? 200 : 404);
    }
    const body = request.postDataJSON();
    state.calls.push({ type: url.pathname.endsWith('live-settings') ? 'live' : 'save-agent', body, url: request.url() });
    if (state.agentSaveError) return respond(route, { detail: state.agentSaveError }, 503);
    if (request.method() === 'PUT') {
      state.agents[body.name] = body;
      state.missingOverrides.delete(body.name);
      return respond(route, { config: body, status: 'updated', agent_name: body.name });
    }
    return respond(route, { applied: true, live: true });
  });
  await page.route('**/api/v1/scenario-builder/generate?*', (route) => {
    state.calls.push({ type: 'generate', body: route.request().postDataJSON() });
    return state.generateError ? respond(route, { detail: state.generateError }, 503)
      : respond(route, state.draft);
  });
  await page.route('**/api/v1/scenario-builder/apply-draft?*', (route) => {
    const body = route.request().postDataJSON();
    state.calls.push({ type: 'apply-draft', body });
    if (state.applyError) return respond(route, { detail: state.applyError }, 503);
    for (const config of body.agents) state.agents[config.name] = config;
    const saved = saveScenario(body.scenario);
    return respond(route, { status: 'created', config: saved });
  });
  await page.route('**/api/v1/scenario-builder/templates/*', (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop());
    const template = scenarios.scenariosResponse.builtin_scenarios.find((item) => (
      item.id || item.name.toLowerCase()
    ) === id);
    if (!template) return respond(route, { detail: 'Template not found' }, 404);
    return respond(route, {
      config: template.name === 'Banking' ? {
        ...template,
        agent_defaults: { voice_rate: '-5%' }, tools: ['check_balance'],
        handoffs: [{
          from_agent: 'BankingConcierge', to_agent: 'FraudAgent', tool: 'handoff_to_agent',
          type: 'announced', share_context: true, handoff_condition: 'The caller reports fraud.',
          context_vars: { priority: 'urgent' },
        }],
      } : { ...template, agent_defaults: null, tools: [] },
    });
  });
  await page.route('**/api/v1/scenario-builder/session/*?scenario_name=*', (route) => {
    const name = new URL(route.request().url()).searchParams.get('scenario_name');
    if (state.scenarioLoadError) return respond(route, { detail: state.scenarioLoadError }, 503);
    const config = state.scenarioConfigs[name.toLowerCase()];
    return respond(route, config ? { config } : { detail: 'No saved scenario' }, config ? 200 : 404);
  });
  await page.route('**/api/v1/scenario-builder/session/*', async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback();
    const body = route.request().postDataJSON();
    scenarios.calls.push({ type: 'update', method: 'PUT', url: route.request().url(), body });
    if (state.scenarioSaveError) return respond(route, { detail: state.scenarioSaveError }, 503);
    return respond(route, { status: 'updated', config: saveScenario(body) });
  });
  return state;
}
