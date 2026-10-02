import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../config/constants.js';
import { callErrorMessage, canUseTelephonyProvider, parseProviderCatalog } from '../utils/communicationProviders.js';

export default function useCommunicationProviders(enabled) {
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [telephonyProvider, setTelephonyProvider] = useState('acs');
  const requestRef = useRef(null);

  const refresh = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError('');
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calls/providers`, {
        signal: controller.signal,
        cache: 'no-store',
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(response.status === 404
          ? 'Provider discovery is not supported by this backend. Update the backend and retry.'
          : callErrorMessage(body, `Provider configuration request failed (HTTP ${response.status}).`));
      }
      const next = parseProviderCatalog(body);
      if (requestRef.current === controller) setCatalog(next);
    } catch (err) {
      if (requestRef.current === controller) {
        setCatalog(null);
        setError(err.name === 'AbortError'
          ? 'Provider configuration request timed out. Retry to check configuration.'
          : err.message || 'Provider configuration could not be loaded.');
      }
    } finally {
      clearTimeout(timeout);
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (enabled) refresh();
    return () => {
      const request = requestRef.current;
      requestRef.current = null;
      request?.abort();
    };
  }, [enabled, refresh]);

  const selectProvider = useCallback((provider) => {
    if (!loading && !error && canUseTelephonyProvider(catalog, provider)) {
      setTelephonyProvider(provider);
    }
  }, [catalog, loading, error]);

  return {
    catalog, loading, error, telephonyProvider, selectProvider, refresh,
    canCall: !loading && !error && canUseTelephonyProvider(catalog, telephonyProvider),
  };
}
