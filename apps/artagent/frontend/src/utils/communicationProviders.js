export const SERVICE_PROVIDERS = {
  telephony: [
    { id: 'acs', label: 'ACS (standalone)' },
    { id: 'teams', label: 'Teams Phone (via ACS/TPE)' },
  ],
  email: [
    { id: 'acs', label: 'ACS Email' },
    { id: 'external', label: 'External email provider (not implemented)' },
  ],
  sms: [
    { id: 'acs', label: 'ACS SMS' },
    { id: 'external', label: 'External SMS provider (not implemented)' },
  ],
};

export function parseProviderCatalog(payload) {
  const catalog = {};
  for (const [service, expected] of Object.entries(SERVICE_PROVIDERS)) {
    const section = payload?.[service];
    if (section?.default !== 'acs' || !Array.isArray(section.options)) {
      throw new Error('Invalid provider configuration response. Refresh or update the backend.');
    }
    catalog[service] = {
      default: 'acs',
      options: expected.map(({ id, label }) => {
        const matches = section.options.filter((option) => option?.id === id);
        const option = matches[0];
        if (
          matches.length !== 1
          || typeof option.available !== 'boolean'
          || !['configured', 'not_configured', 'unavailable'].includes(option.status)
          || option.available !== (option.status === 'configured')
          || typeof option.detail !== 'string'
          || !Array.isArray(option.missing_settings)
          || !option.missing_settings.every((setting) => typeof setting === 'string')
          || (id === 'external' && option.available)
        ) {
          throw new Error('Invalid provider configuration response. Refresh or update the backend.');
        }
        // Retain only the public, non-secret configuration contract.
        return {
          id, label, available: option.available, status: option.status,
          detail: option.detail, missing_settings: option.missing_settings,
        };
      }),
    };
  }
  return catalog;
}

export function canUseTelephonyProvider(catalog, provider) {
  return catalog?.telephony?.options.some((option) => (
    option.id === provider && option.available === true && option.status === 'configured'
  )) ?? false;
}

export function callErrorMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((entry) => entry?.msg).filter((msg) => typeof msg === 'string');
    if (messages.length) return messages.join('; ');
  }
  if (typeof detail?.message === 'string') return detail.message;
  if (typeof body?.message === 'string') return body.message;
  return fallback;
}
