/**
 * Shared fixtures and API mock helpers for scenario E2E tests.
 *
 * These build consistent mock responses that mirror the real backend
 * shape from /api/v1/scenario-builder/session/{sid}/scenarios.
 */

// ---------------------------------------------------------------------------
// Mock data factories
// ---------------------------------------------------------------------------

/** Create a scenario entry matching the backend response shape. */
export function makeScenario({
  name,
  icon = '🎭',
  start_agent = 'Agent1',
  agents = ['Agent1'],
  is_active = false,
  is_custom = false,
  description = '',
  handoffs = [],
  handoff_type = 'announced',
  global_template_vars = {},
}) {
  return {
    name,
    description: description || `${name} scenario`,
    icon,
    agents,
    start_agent,
    handoffs,
    handoff_type,
    global_template_vars,
    is_active,
    is_custom,
  };
}

/** Industry template helpers */
export const BANKING = (active = false) =>
  makeScenario({
    name: 'Banking',
    icon: '🏦',
    start_agent: 'BankingConcierge',
    agents: ['BankingConcierge', 'FraudAgent'],
    is_active: active,
    is_custom: false,
  });

export const INSURANCE = (active = false) =>
  makeScenario({
    name: 'Insurance',
    icon: '🛡️',
    start_agent: 'InsuranceConcierge',
    agents: ['InsuranceConcierge', 'ClaimsAgent'],
    is_active: active,
    is_custom: false,
  });

export const HEALTHCARE = (active = false) =>
  makeScenario({
    name: 'Healthcare',
    icon: '🏥',
    start_agent: 'HealthConcierge',
    agents: ['HealthConcierge'],
    is_active: active,
    is_custom: false,
  });

/** Build a full scenarios-list response matching the backend shape. */
export function buildScenariosResponse({
  builtins = [BANKING(true), INSURANCE(), HEALTHCARE()],
  customs = [],
  activeScenario = null,
} = {}) {
  // Derive active from the arrays if not explicitly set
  const allScenarios = [...builtins, ...customs];
  const active = activeScenario
    || allScenarios.find(s => s.is_active)?.name
    || builtins[0]?.name
    || null;
  const activeEntry = allScenarios.find(s => s.name === active);

  return {
    status: 'success',
    session_id: 'test-session',
    total: allScenarios.length,
    active_scenario: active,
    active_start_agent: activeEntry?.start_agent || null,
    active_scenario_icon: activeEntry?.icon || null,
    scenarios: allScenarios,
    builtin_scenarios: builtins,
    custom_scenarios: customs,
  };
}

// ---------------------------------------------------------------------------
// Route-level API mocking
// ---------------------------------------------------------------------------

/**
 * Install API route mocks on a Playwright page.
 *
 * Returns a controller object that lets tests:
 *   - Change what the scenarios endpoint returns (to simulate server updates)
 *   - Inspect which API calls were made and their arguments
 *   - Simulate failures
 */
export async function installApiMocks(page, initialResponse = null) {
  const state = {
    scenariosResponse: initialResponse || buildScenariosResponse(),
    calls: [],           // { method, url, body? }[]
    failNextPost: false,
    // When > 0, the next N GET /scenarios requests will be delayed by this
    // many ms AND will return a snapshot of scenariosResponse captured
    // BEFORE the delay.  This simulates the real-world race where the
    // backend hasn't propagated a write yet when the GET arrives.
    staleGetDelayMs: 0,
    staleGetCount: 0,     // how many GETs to make stale (0 = none)
  };

  // -----------------------------------------------------------------------
  // IMPORTANT: Playwright routes registered LATER take HIGHER priority.
  // Register the catch-all FIRST (lowest priority) so specific routes
  // registered afterwards always win.
  // -----------------------------------------------------------------------

  // Catch-all for unmatched API calls to prevent network errors (LOWEST priority)
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    });
  });

  // Mock: GET /api/v1/sessions/* (session details — needed for initialization)
  await page.route('**/api/v1/sessions/*', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session: { id: 'test-session', created_at: new Date().toISOString() },
        memory: {},
      }),
    });
  });

  // Mock: GET /api/v1/agents (agent inventory — needed for initialization)
  await page.route('**/api/v1/agents', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agents: [
          { name: 'BankingConcierge', description: 'Banking assistant' },
          { name: 'FraudAgent', description: 'Fraud detection' },
          { name: 'InsuranceConcierge', description: 'Insurance assistant' },
          { name: 'HealthConcierge', description: 'Health assistant' },
        ],
      }),
    });
  });

  // Mock: GET /api/v1/scenario-builder/available-agents (for scenario builder)
  await page.route('**/api/v1/scenario-builder/available-agents*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agents: [
          { name: 'BankingConcierge', description: 'Banking assistant', tools: [], handoffs: [] },
          { name: 'FraudAgent', description: 'Fraud detection', tools: [], handoffs: [] },
          { name: 'InsuranceConcierge', description: 'Insurance assistant', tools: [], handoffs: [] },
          { name: 'HealthConcierge', description: 'Health assistant', tools: [], handoffs: [] },
        ],
      }),
    });
  });

  // Mock: GET /api/v1/scenario-builder/session/*/scenarios-list (builder's own list)
  await page.route('**/api/v1/scenario-builder/session/*/scenarios-list*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ scenarios: state.scenariosResponse.scenarios }),
    });
  });

  // Mock: PUT /api/v1/scenario-builder/session/*  (update scenario)
  await page.route('**/api/v1/scenario-builder/session/*', async (route, request) => {
    if (request.method() !== 'PUT') {
      await route.fallback();
      return;
    }
    const body = request.postDataJSON();
    state.calls.push({ method: 'PUT', url: request.url(), type: 'update', body });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'updated', config: body }),
    });
  });

  // Mock: POST /api/v1/scenario-builder/create*
  await page.route('**/api/v1/scenario-builder/create*', async (route) => {
    const body = route.request().postDataJSON();
    state.calls.push({ method: 'POST', url: route.request().url(), type: 'create', body });

    if (state.failNextPost) {
      state.failNextPost = false;
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
      return;
    }

    const newScenario = makeScenario({
      name: body?.name || 'Custom Scenario',
      icon: body?.icon || '🎭',
      start_agent: body?.start_agent || 'Agent1',
      agents: body?.agents || ['Agent1'],
      is_active: true,
      is_custom: true,
      description: body?.description || '',
      handoffs: body?.handoffs || [],
    });

    // Add to mock state
    state.scenariosResponse.builtin_scenarios = state.scenariosResponse.builtin_scenarios.map(s => ({ ...s, is_active: false }));
    state.scenariosResponse.custom_scenarios = [
      ...state.scenariosResponse.custom_scenarios.map(s => ({ ...s, is_active: false })),
      newScenario,
    ];
    state.scenariosResponse.scenarios = [...state.scenariosResponse.builtin_scenarios, ...state.scenariosResponse.custom_scenarios];
    state.scenariosResponse.active_scenario = newScenario.name;
    state.scenariosResponse.active_start_agent = newScenario.start_agent;
    state.scenariosResponse.active_scenario_icon = newScenario.icon;

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'created', config: newScenario }),
    });
  });

  // Mock: POST /api/v1/scenario-builder/session/*/active*
  await page.route('**/api/v1/scenario-builder/session/*/active*', async (route) => {
    const url = route.request().url();
    state.calls.push({ method: 'POST', url, type: 'set-active' });

    if (state.failNextPost) {
      state.failNextPost = false;
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
      return;
    }

    const scenarioName = new URL(url).searchParams.get('scenario_name') || '';
    const allScenarios = [...state.scenariosResponse.builtin_scenarios, ...state.scenariosResponse.custom_scenarios];
    const matched = allScenarios.find(s => s.name.toLowerCase() === scenarioName.toLowerCase());

    if (matched) {
      state.scenariosResponse.builtin_scenarios = state.scenariosResponse.builtin_scenarios.map(s => ({
        ...s, is_active: s.name.toLowerCase() === scenarioName.toLowerCase(),
      }));
      state.scenariosResponse.custom_scenarios = state.scenariosResponse.custom_scenarios.map(s => ({
        ...s, is_active: s.name.toLowerCase() === scenarioName.toLowerCase(),
      }));
      state.scenariosResponse.scenarios = [...state.scenariosResponse.builtin_scenarios, ...state.scenariosResponse.custom_scenarios];
      state.scenariosResponse.active_scenario = matched.name;
      state.scenariosResponse.active_start_agent = matched.start_agent;
      state.scenariosResponse.active_scenario_icon = matched.icon;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: matched ? 'active' : 'not_found',
        session_id: 'test-session',
        scenario: matched ? {
          name: matched.name,
          start_agent: matched.start_agent,
          agents: matched.agents,
        } : null,
      }),
    });
  });

  // Mock: POST /api/v1/scenario-builder/session/*/apply-template*
  await page.route('**/api/v1/scenario-builder/session/*/apply-template*', async (route) => {
    const url = route.request().url();
    state.calls.push({ method: 'POST', url, type: 'apply-template' });

    if (state.failNextPost) {
      state.failNextPost = false;
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
      return;
    }

    // Extract template_id from query string
    const templateId = new URL(url).searchParams.get('template_id');
    const templateName = templateId?.replace(/_/g, ' ') || 'unknown';
    
    // Update the mock state so subsequent GET returns the new active scenario
    const allScenarios = [...state.scenariosResponse.builtin_scenarios, ...state.scenariosResponse.custom_scenarios];
    const matched = allScenarios.find(s => s.name.toLowerCase().replace(/\s+/g, '_') === templateId);

    if (matched) {
      // Update is_active flags
      state.scenariosResponse.builtin_scenarios = state.scenariosResponse.builtin_scenarios.map(s => ({
        ...s, is_active: s.name === matched.name,
      }));
      state.scenariosResponse.custom_scenarios = state.scenariosResponse.custom_scenarios.map(s => ({
        ...s, is_active: false,
      }));
      state.scenariosResponse.scenarios = [...state.scenariosResponse.builtin_scenarios, ...state.scenariosResponse.custom_scenarios];
      state.scenariosResponse.active_scenario = matched.name;
      state.scenariosResponse.active_start_agent = matched.start_agent;
      state.scenariosResponse.active_scenario_icon = matched.icon;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'applied',
        session_id: 'test-session',
        template_id: templateId,
        scenario: {
          name: matched?.name || templateName,
          description: matched?.description || '',
          icon: matched?.icon || '🎭',
          start_agent: matched?.start_agent || 'Agent1',
          agents: matched?.agents || ['Agent1'],
          handoff_count: 0,
        },
      }),
    });
  });

  // Mock: GET /api/v1/scenario-builder/session/*/scenarios (HIGHEST priority — registered last)
  await page.route('**/api/v1/scenario-builder/session/*/scenarios', async (route) => {
    state.calls.push({ method: 'GET', url: route.request().url() });

    // Support simulating stale/delayed GET responses.  When staleGetCount > 0,
    // we snapshot the response BEFORE waiting, so the reply reflects the old
    // state even if a POST updates it during the delay window.
    if (state.staleGetCount > 0 && state.staleGetDelayMs > 0) {
      const staleSnapshot = JSON.stringify(state.scenariosResponse);
      state.staleGetCount -= 1;
      await new Promise(r => setTimeout(r, state.staleGetDelayMs));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: staleSnapshot,
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state.scenariosResponse),
    });
  });

  return state;
}
