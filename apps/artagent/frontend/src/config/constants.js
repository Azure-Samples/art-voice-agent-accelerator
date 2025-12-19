/**
 * Application Configuration Constants
 * 
 * Central configuration for API endpoints and environment variables
 */

// Simple placeholder that gets replaced at container startup, with fallback for local dev
const backendPlaceholder = '__BACKEND_URL__';
const wsPlaceholder = '__WS_URL__';

const toWsUrl = (value) => {
  if (!value || typeof value !== 'string') {
    return 'ws://localhost';
  }
  if (/^wss?:\/\//i.test(value)) {
    return value;
  }
  if (/^https:\/\//i.test(value)) {
    return value.replace(/^https:\/\//i, 'wss://');
  }
  if (/^http:\/\//i.test(value)) {
    return value.replace(/^http:\/\//i, 'ws://');
  }
  return value;
};

export const API_BASE_URL = backendPlaceholder.startsWith('__')
  ? import.meta.env.VITE_BACKEND_BASE_URL || 'http://localhost:8000'
  : backendPlaceholder;

const wsBaseCandidate = wsPlaceholder.startsWith('__')
  ? import.meta.env.VITE_WS_BASE_URL || API_BASE_URL
  : wsPlaceholder;

export const WS_URL = toWsUrl(wsBaseCandidate);
export { toWsUrl };

// Application metadata
export const APP_CONFIG = {
  name: "Real-Time Voice App",
  subtitle: "AI-powered voice interaction platform",
  version: "1.0.0"
};
