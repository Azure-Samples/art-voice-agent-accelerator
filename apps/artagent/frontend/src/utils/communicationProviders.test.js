import assert from 'node:assert/strict';
import test from 'node:test';
import { makeProviderCatalog } from '../../e2e/helpers/communication-provider-mocks.js';
import { callErrorMessage, canUseTelephonyProvider, parseProviderCatalog } from './communicationProviders.js';

test('ACS is the catalog default and Teams requires explicit configuration', () => {
  const catalog = parseProviderCatalog(makeProviderCatalog());
  assert.equal(catalog.telephony.default, 'acs');
  assert.equal(canUseTelephonyProvider(catalog, 'acs'), true);
  assert.equal(canUseTelephonyProvider(catalog, 'teams'), false);
  assert.equal(canUseTelephonyProvider(null, 'acs'), false);
  assert.equal(canUseTelephonyProvider(catalog, 'external'), false);
});

test('Teams is independent from standalone ACS and email/SMS stay ACS', () => {
  const catalog = parseProviderCatalog(makeProviderCatalog({ teams: true, acs: false }));
  assert.equal(canUseTelephonyProvider(catalog, 'teams'), true);
  assert.equal(canUseTelephonyProvider(catalog, 'acs'), false);
  for (const service of ['email', 'sms']) {
    assert.equal(catalog[service].default, 'acs');
    assert.equal(catalog[service].options[1].available, false);
    assert.doesNotMatch(catalog[service].options.map((option) => option.label).join(' '), /Teams/);
  }
});

test('malformed or inconsistent discovery cannot authorize calls', () => {
  const mutations = [
    () => null,
    () => ({}),
    (catalog) => ({ data: catalog }),
    (catalog) => { catalog.telephony.default = 'teams'; return catalog; },
    (catalog) => { catalog.telephony.options.pop(); return catalog; },
    (catalog) => { catalog.telephony.options.push(catalog.telephony.options[0]); return catalog; },
    (catalog) => { catalog.telephony.options[1].available = 'true'; return catalog; },
    (catalog) => { catalog.telephony.options[1].available = true; return catalog; },
    (catalog) => { catalog.telephony.options[1].status = 'ready'; return catalog; },
    (catalog) => { catalog.telephony.options[1].missing_settings = {}; return catalog; },
    (catalog) => { catalog.email.options[1].available = true; catalog.email.options[1].status = 'configured'; return catalog; },
  ];
  for (const mutate of mutations) {
    assert.throws(() => parseProviderCatalog(mutate(makeProviderCatalog())), /Invalid provider/);
  }
});

test('only public fields are retained and arbitrary labels cannot misrepresent email/SMS', () => {
  const body = makeProviderCatalog();
  body.telephony.options[0].credentials = 'must-not-retain';
  body.email.options[0].label = 'Teams Email';
  const catalog = parseProviderCatalog(body);
  assert.equal(catalog.telephony.options[0].credentials, undefined);
  assert.equal(catalog.email.options[0].label, 'ACS Email');
});

test('HTTP errors expose actionable messages, not object dumps or HTML', () => {
  assert.equal(callErrorMessage({ detail: 'Teams is not configured.' }, 'Failed'), 'Teams is not configured.');
  assert.equal(callErrorMessage({ detail: [{ msg: 'Invalid phone number' }] }, 'Failed'), 'Invalid phone number');
  assert.equal(callErrorMessage({ detail: { code: 'not_configured', message: 'Configure Teams on the server' } }, 'Failed'), 'Configure Teams on the server');
  assert.equal(callErrorMessage({ detail: { secret: 'hidden' } }, 'Failed'), 'Failed');
  assert.equal(callErrorMessage(null, 'HTTP 502'), 'HTTP 502');
});
