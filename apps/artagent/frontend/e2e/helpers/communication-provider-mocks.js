import { installApiMocks } from './scenario-mocks.js';

export function makeProviderCatalog({ teams = false, acs = true } = {}) {
  const option = (id, label, available) => ({
    id, label, available,
    status: available ? 'configured' : id === 'external' ? 'unavailable' : 'not_configured',
    detail: available ? `${label} is configured.` : id === 'external'
      ? 'Not implemented. ACS remains in use.' : `${label} needs server configuration.`,
    missing_settings: available || id === 'external' ? [] : [`${id.toUpperCase()}_SETTING`],
  });
  return {
    telephony: {
      default: 'acs',
      options: [option('acs', 'ACS (standalone)', acs), option('teams', 'Teams Phone (via ACS/TPE)', teams)],
    },
    email: {
      default: 'acs',
      options: [option('acs', 'ACS Email', true), option('external', 'External email provider', false)],
    },
    sms: {
      default: 'acs',
      options: [option('acs', 'ACS SMS', false), option('external', 'External SMS provider', false)],
    },
  };
}

export async function installProviderMocks(page, catalog = makeProviderCatalog()) {
  await installApiMocks(page);
  const state = {
    catalog, discoveryStatus: 200, discoveryBody: null, discoveryFailure: false,
    initiateStatus: 200, initiateBody: null, calls: [], terminations: [], relay: null,
    terminateStatus: 200,
    holdInitiation: null,
  };
  const respond = (route, body, status = 200) => route.fulfill({
    status, contentType: 'application/json', body: JSON.stringify(body),
  });
  await page.route('**/api/v1/calls/providers', (route) => state.discoveryFailure
    ? route.abort('failed')
    : respond(route, state.discoveryBody ?? state.catalog, state.discoveryStatus));
  await page.route('**/api/v1/calls/initiate', async (route) => {
    const body = route.request().postDataJSON();
    state.calls.push(body);
    if (state.holdInitiation) await state.holdInitiation;
    return respond(route, state.initiateBody ?? {
      call_id: `test-call-${state.calls.length}`, telephony_provider: body.telephony_provider,
    }, state.initiateStatus);
  });
  await page.route('**/api/v1/calls/terminate', (route) => {
    state.terminations.push(route.request().postDataJSON());
    return respond(route, state.terminateStatus === 200
      ? { status: 'terminated' } : { detail: 'Unable to terminate this call. Retry hangup.' }, state.terminateStatus);
  });
  await page.routeWebSocket('**/api/v1/browser/dashboard/relay?*', (socket) => {
    state.relay = socket;
  });
  return state;
}
