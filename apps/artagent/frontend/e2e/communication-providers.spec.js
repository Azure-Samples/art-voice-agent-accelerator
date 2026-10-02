import { expect, test } from '@playwright/test';
import { installProviderMocks, makeProviderCatalog } from './helpers/communication-provider-mocks.js';

const panel = (page) => page.getByRole('region', { name: 'Phone call', exact: true });
const telephony = (page) => panel(page).getByRole('combobox', { name: 'Telephony provider' });
const callButton = (page) => panel(page).getByRole('button', { name: 'Call Me' });

async function openPhone(page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Place call', exact: true }).click();
  await expect(panel(page)).toBeVisible();
  await panel(page).getByRole('textbox', { name: 'Phone number' }).fill('+15551234567');
}

test('defaults to ACS, disables unconfigured Teams and future email/SMS replacements', async ({ page }) => {
  const state = await installProviderMocks(page);
  await openPhone(page);
  await expect(telephony(page)).toHaveValue('acs');
  await expect(telephony(page).locator('option[value="teams"]')).toBeDisabled();
  for (const service of ['Email', 'SMS']) {
    const selector = panel(page).getByRole('combobox', { name: `${service} provider`, exact: true });
    await expect(selector).toHaveValue('acs');
    await expect(selector.locator('option[value="external"]')).toBeDisabled();
    await expect(selector).not.toContainText('Teams');
  }
  await expect(panel(page)).toContainText('Voice engine (independent of telephony)');
  await expect(panel(page)).toContainText('not live connectivity, licensing, or provisioning validation');
  await callButton(page).click();
  await expect.poll(() => state.calls.length).toBe(1);
  expect(state.calls[0].telephony_provider).toBe('acs');
  expect(state.calls[0].streaming_mode).toBeTruthy();
});

test('configured Teams uses the actual request body and stays locked until disconnect', async ({ page }) => {
  const state = await installProviderMocks(page, makeProviderCatalog({ teams: true }));
  await openPhone(page);
  await expect(telephony(page)).toHaveValue('acs');
  await telephony(page).selectOption('teams');
  await panel(page).getByRole('button', { name: /Custom Speech Cascade/ }).click();
  await expect(telephony(page)).toHaveValue('teams');
  let release;
  state.holdInitiation = new Promise((resolve) => { release = resolve; });
  // Two synchronous clicks exercise the ref guard, before React can rerender.
  await callButton(page).evaluate((button) => { button.click(); button.click(); });
  await expect.poll(() => state.calls.length).toBe(1);
  await expect(panel(page).getByRole('button', { name: 'Initiating…', exact: true })).toBeDisabled();
  await expect(telephony(page)).toBeDisabled();
  await expect(panel(page)).not.toContainText('Connected');
  expect(state.calls[0]).toMatchObject({
    target_number: '+15551234567', telephony_provider: 'teams', streaming_mode: 'media',
    context: { streaming_mode: 'media' },
  });
  expect(Object.keys(state.calls[0]).sort()).toEqual(['context', 'streaming_mode', 'target_number', 'telephony_provider']);
  release();
  await expect(panel(page)).toContainText('waiting for connection');
  await expect(telephony(page)).toBeDisabled();
  await expect(panel(page).getByRole('button', { name: /Custom Speech Cascade/ })).toBeDisabled();
  await expect(panel(page).getByRole('button', { name: 'Refresh providers' })).toBeDisabled();
  await expect.poll(() => Boolean(state.relay)).toBe(true);
  state.relay.send(JSON.stringify({ type: 'event', event_type: 'call_connected', call_connection_id: 'test-call-1' }));
  await expect(panel(page)).toContainText('Connected · Teams Phone');
  await expect(telephony(page)).toHaveValue('teams');
  await expect(telephony(page)).toBeDisabled();
  state.relay.send(JSON.stringify({ type: 'event', event_type: 'call_disconnected' }));
  await expect(telephony(page)).toBeEnabled();
  await expect(telephony(page)).toHaveValue('teams');
  await expect(callButton(page)).toBeEnabled();
});

test('Teams can be configured independently from standalone ACS without automatic selection', async ({ page }) => {
  const state = await installProviderMocks(page, makeProviderCatalog({ teams: true, acs: false }));
  await openPhone(page);
  await expect(telephony(page)).toHaveValue('acs');
  await expect(callButton(page)).toBeDisabled();
  await expect(panel(page)).toContainText('Requirements not met: ACS_SETTING');
  await telephony(page).selectOption('teams');
  await callButton(page).click();
  await expect.poll(() => state.calls.length).toBe(1);
  expect(state.calls[0].telephony_provider).toBe('teams');
});

for (const failure of ['network', 'invalid catalog', 'legacy backend']) {
  test(`${failure} blocks calling with explicit retry and never falls back from Teams`, async ({ page }) => {
    const state = await installProviderMocks(page, makeProviderCatalog({ teams: true }));
    await openPhone(page);
    await telephony(page).selectOption('teams');
    if (failure === 'network') state.discoveryFailure = true;
    if (failure === 'invalid catalog') state.discoveryBody = { telephony: { options: [] } };
    if (failure === 'legacy backend') {
      state.discoveryStatus = 404;
      state.discoveryBody = {};
    }
    await panel(page).getByRole('button', { name: 'Refresh providers' }).click();
    await expect(panel(page)).toContainText('Outbound calls are blocked');
    await expect(telephony(page)).toHaveValue('teams');
    await expect(telephony(page)).toBeDisabled();
    await expect(callButton(page)).toBeDisabled();
    expect(state.calls).toHaveLength(0);
    state.discoveryFailure = false;
    state.discoveryStatus = 200;
    state.discoveryBody = null;
    await panel(page).getByRole('button', { name: 'Retry providers' }).click();
    await expect(telephony(page)).toBeEnabled();
    await expect(telephony(page)).toHaveValue('teams');
    await expect(callButton(page)).toBeEnabled();
    state.catalog = makeProviderCatalog({ teams: false });
    await panel(page).getByRole('button', { name: 'Refresh providers' }).click();
    await expect(panel(page)).toContainText('Teams Phone (via ACS/TPE) needs server configuration.');
    await expect(telephony(page)).toHaveValue('teams');
    await expect(callButton(page)).toBeDisabled();
  });
}

test('server errors are visible, preserve Teams, and permit an explicit retry', async ({ page }) => {
  const state = await installProviderMocks(page, makeProviderCatalog({ teams: true }));
  state.initiateStatus = 409;
  state.initiateBody = { detail: { code: 'provider_not_configured', message: 'Teams resource account is not configured on the server.' } };
  await openPhone(page);
  await telephony(page).selectOption('teams');
  await callButton(page).click();
  await expect(panel(page)).toContainText('Teams resource account is not configured on the server.');
  await expect(telephony(page)).toHaveValue('teams');
  await expect(telephony(page)).toBeEnabled();
  await expect(callButton(page)).toBeEnabled();
  expect(state.calls).toHaveLength(1);
  await expect(panel(page)).not.toContainText('[object Object]');
});

test('pending Teams calls hang up via the shared terminate endpoint and preserve the selection', async ({ page }) => {
  const state = await installProviderMocks(page, makeProviderCatalog({ teams: true }));
  await openPhone(page);
  await telephony(page).selectOption('teams');
  await callButton(page).click();
  await expect(panel(page)).toContainText('waiting for connection');
  await panel(page).getByRole('button', { name: 'Hang Up', exact: false }).click();
  await expect.poll(() => state.terminations.length).toBe(1);
  expect(state.terminations[0].call_id).toBe('test-call-1');
  await page.getByRole('button', { name: 'Place call', exact: true }).click();
  await expect(telephony(page)).toHaveValue('teams');
  await expect(callButton(page)).toBeEnabled();
});

test('a narrow viewport keeps the service panel on screen and scrollable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installProviderMocks(page);
  await openPhone(page);
  const bounds = await panel(page).boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(bounds.height).toBeLessThanOrEqual(684);
  await expect(telephony(page)).toHaveValue('acs');
});

test('failed hangup does not unlock provider selection or lose the ongoing call', async ({ page }) => {
  const state = await installProviderMocks(page, makeProviderCatalog({ teams: true }));
  state.terminateStatus = 503;
  await openPhone(page);
  await telephony(page).selectOption('teams');
  await callButton(page).click();
  await expect(panel(page)).toContainText('waiting for connection');
  await panel(page).getByRole('button', { name: 'Hang Up', exact: false }).click();
  await expect(panel(page)).toContainText('Unable to terminate this call. Retry hangup.');
  await expect(telephony(page)).toHaveValue('teams');
  await expect(telephony(page)).toBeDisabled();
  state.terminateStatus = 200;
  await panel(page).getByRole('button', { name: 'Hang Up', exact: false }).click();
  await expect(panel(page)).not.toBeVisible();
  expect(state.terminations).toHaveLength(2);
});

test('a new page load always starts on ACS rather than persisting Teams', async ({ page }) => {
  await installProviderMocks(page, makeProviderCatalog({ teams: true }));
  await openPhone(page);
  await telephony(page).selectOption('teams');
  await openPhone(page);
  await expect(telephony(page)).toHaveValue('acs');
});

test('unsupported Teams SDK requirements are visible without enabling or selecting Teams', async ({ page }) => {
  const catalog = makeProviderCatalog({ teams: true });
  Object.assign(catalog.telephony.options[1], {
    available: false,
    status: 'unavailable',
    detail: 'Teams is enabled and the resource account is configured, but the installed SDK is unsupported.',
    missing_settings: ['Call Automation SDK with explicit teams_app_source support'],
  });
  catalog.email.options[0].detail = 'Email settings exist; demo-only tools remain demos and delivery is not validated.';
  catalog.sms.options[0].detail = 'SMS settings are missing; demo-only tools remain demos.';
  const state = await installProviderMocks(page, catalog);
  await openPhone(page);
  await expect(telephony(page)).toHaveValue('acs');
  await expect(telephony(page).locator('option[value="teams"]')).toBeDisabled();
  await expect(panel(page)).toContainText('Teams Phone (via ACS/TPE) — Unavailable');
  await expect(panel(page)).toContainText('Requirements not met: Call Automation SDK with explicit teams_app_source support');
  await expect(panel(page)).toContainText('Email settings exist; demo-only tools remain demos and delivery is not validated.');
  await expect(panel(page)).toContainText('SMS settings are missing; demo-only tools remain demos.');
  await callButton(page).click();
  await expect.poll(() => state.calls.length).toBe(1);
  expect(state.calls[0].telephony_provider).toBe('acs');
});
