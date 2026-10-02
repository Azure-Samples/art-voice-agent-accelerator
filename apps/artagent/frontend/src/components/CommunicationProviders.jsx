import React, { memo, useCallback, useId } from 'react';
import { Alert, Box, Button, TextField, Typography } from '@mui/material';
import { SERVICE_PROVIDERS } from '../utils/communicationProviders.js';

const statusLabel = (option) => {
  if (!option) return 'Not checked';
  if (option.status === 'configured') return 'Configured';
  if (option.status === 'not_configured') return 'Not configured';
  return 'Unavailable';
};

const CommunicationProviders = memo(function CommunicationProviders({
  catalog, loading, error, telephonyProvider, onProviderChange, onRefresh, callBusy = false,
}) {
  const id = useId();
  const handleChange = useCallback((event) => {
    if (!callBusy && !loading && !error) onProviderChange(event.target.value);
  }, [callBusy, loading, error, onProviderChange]);
  const visibleStatuses = catalog?.telephony.options.filter(
    (option) => option.id === telephonyProvider || !option.available,
  ) ?? [];

  return (
    <Box component="section" aria-label="Communication services" sx={{ display: 'grid', gap: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography component="h3" variant="subtitle2" sx={{ flex: 1 }}>
          Communication services
        </Typography>
        <Button size="small" onClick={onRefresh} disabled={loading || callBusy}>
          {error ? 'Retry providers' : 'Refresh providers'}
        </Button>
      </Box>
      {loading && <Typography role="status" variant="caption">Checking server configuration…</Typography>}
      {error && <Alert severity="error">{error} Outbound calls are blocked until configuration can be checked.</Alert>}
      <TextField
        select
        id={`${id}-telephony`}
        label="Telephony provider"
        value={telephonyProvider}
        onChange={handleChange}
        disabled={callBusy || loading || Boolean(error) || !catalog}
        size="small"
        fullWidth
        slotProps={{ select: { native: true } }}
        helperText={callBusy ? 'Locked for the current call.' : 'Applies only to the next outbound call.'}
      >
        {SERVICE_PROVIDERS.telephony.map((provider) => {
          const option = catalog?.telephony.options.find((item) => item.id === provider.id);
          return (
            <option key={provider.id} value={provider.id} disabled={!option?.available}>
              {provider.label}{option?.available ? '' : ` — ${statusLabel(option)}`}
            </option>
          );
        })}
      </TextField>
      {!loading && !error && visibleStatuses.map((option) => (
        <Alert key={option.id} severity={option.available ? 'info' : 'warning'}>
          {option.label} — {statusLabel(option)}: {option.detail}
          {option.missing_settings.length > 0 && (
            <Box component="span" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
              Requirements not met: {option.missing_settings.join(', ')}
            </Box>
          )}
        </Alert>
      ))}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1.5 }}>
        {['email', 'sms'].map((service) => {
          const option = catalog?.[service].options.find((item) => item.id === 'acs');
          const label = service === 'email' ? 'Email provider' : 'SMS provider';
          return (
            <TextField
              key={service}
              select
              id={`${id}-${service}`}
              label={label}
              value="acs"
              onChange={() => {}}
              size="small"
              fullWidth
              disabled={loading || Boolean(error) || !catalog}
              slotProps={{ select: { native: true } }}
              helperText={`${statusLabel(option)} · server-configured${option?.detail ? `. ${option.detail}` : ''}`}
            >
              {SERVICE_PROVIDERS[service].map((provider) => (
                <option key={provider.id} value={provider.id} disabled={provider.id !== 'acs'}>
                  {provider.label}
                </option>
              ))}
            </TextField>
          );
        })}
      </Box>
      <Typography variant="caption" color="text.secondary">
        Email and SMS remain on ACS and are server-configured. External replacements are not implemented or wired.
        {' '}Teams Phone is telephony only, using ACS transport with Teams Phone extensibility (TPE).
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Configuration only—not live connectivity, licensing, or provisioning validation.
        {' '}This selection does not change inbound routing or deployment defaults. No Teams administration is performed here.
      </Typography>
    </Box>
  );
});

export default CommunicationProviders;
