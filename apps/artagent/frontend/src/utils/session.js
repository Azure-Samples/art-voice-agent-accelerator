import logger from './logger.js';

export const SESSION_STORAGE_KEY = 'voice_agent_session_id';

const pickSessionIdFromUrl = () => {
  if (typeof window === 'undefined') return null;
  try {
    const params = new URLSearchParams(window.location.search || '');
    return (
      params.get('session_id') ||
      params.get('sessionId') ||
      params.get('sid')
    );
  } catch {
    return null;
  }
};

export const setSessionId = (sessionId) => {
  if (!sessionId) return null;
  sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  logger.info('Session ID set explicitly:', sessionId);
  return sessionId;
};

export const getOrCreateSessionId = () => {
  let sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);

  // Allow users to bring their own session id (e.g., restoring a short-term conversation)
  if (!sessionId) {
    const fromUrl = pickSessionIdFromUrl();
    if (fromUrl) {
      sessionId = setSessionId(fromUrl);
    }
  }

  if (!sessionId) {
    const tabId = Math.random().toString(36).substr(2, 6);
    sessionId = `session_${Date.now()}_${tabId}`;
    setSessionId(sessionId);
  }

  return sessionId;
};

export const createNewSessionId = () => {
  const tabId = Math.random().toString(36).substr(2, 6);
  const sessionId = `session_${Date.now()}_${tabId}`;
  return setSessionId(sessionId);
};

export const createMetricsState = () => ({
  sessionStart: null,
  sessionStartIso: null,
  sessionId: null,
  firstTokenTs: null,
  ttftMs: null,
  turnCounter: 0,
  turns: [],
  bargeInEvents: [],
  pendingBargeIn: null,
  lastAudioFrameTs: null,
  currentTurnId: null,
  awaitingAudioTurnId: null,
});

export const toMs = (value) => (typeof value === 'number' ? Math.round(value) : undefined);

export const buildSessionProfile = (raw, fallbackSessionId, previous) => {
  if (!raw && !previous) {
    return null;
  }
  const container = raw ?? {};
  const data = container.data ?? {};
  const demoMeta =
    container.demo_metadata ??
    container.demoMetadata ??
    data.demo_metadata ??
    data.demoMetadata ??
    {};
  const sessionValue =
    container.session_id ??
    container.sessionId ??
    data.session_id ??
    data.sessionId ??
    demoMeta.session_id ??
    previous?.sessionId ??
    fallbackSessionId;
  const profileValue =
    container.profile ??
    data.profile ??
    demoMeta.profile ??
    previous?.profile ??
    null;
  const rawTransactions = container.transactions ?? data.transactions;
  const metaTransactions = demoMeta.transactions;
  const transactionsValue =
    Array.isArray(rawTransactions) && rawTransactions.length
      ? rawTransactions
      : Array.isArray(metaTransactions) && metaTransactions.length
      ? metaTransactions
      : previous?.transactions ?? [];
  const interactionPlanValue =
    container.interaction_plan ??
    container.interactionPlan ??
    data.interaction_plan ??
    data.interactionPlan ??
    demoMeta.interaction_plan ??
    previous?.interactionPlan ??
    null;
  const entryIdValue =
    container.entry_id ??
    container.entryId ??
    data.entry_id ??
    data.entryId ??
    demoMeta.entry_id ??
    previous?.entryId ??
    null;
  const expiresAtValue =
    container.expires_at ??
    container.expiresAt ??
    data.expires_at ??
    data.expiresAt ??
    demoMeta.expires_at ??
    previous?.expiresAt ??
    null;
  const safetyNoticeValue =
    container.safety_notice ??
    container.safetyNotice ??
    data.safety_notice ??
    data.safetyNotice ??
    demoMeta.safety_notice ??
    previous?.safetyNotice ??
    null;

  // Scenario-based data (banking vs insurance)
  const scenarioValue =
    container.scenario ??
    data.scenario ??
    demoMeta.scenario ??
    previous?.scenario ??
    'banking';
  
  // Insurance-specific data
  const rawPolicies = container.policies ?? data.policies;
  const metaPolicies = demoMeta.policies;
  const policiesValue =
    Array.isArray(rawPolicies) && rawPolicies.length
      ? rawPolicies
      : Array.isArray(metaPolicies) && metaPolicies.length
      ? metaPolicies
      : previous?.policies ?? [];
  
  const rawClaims = container.claims ?? data.claims;
  const metaClaims = demoMeta.claims;
  const claimsValue =
    Array.isArray(rawClaims) && rawClaims.length
      ? rawClaims
      : Array.isArray(metaClaims) && metaClaims.length
      ? metaClaims
      : previous?.claims ?? [];

  return {
    sessionId: sessionValue,
    profile: profileValue,
    transactions: transactionsValue,
    interactionPlan: interactionPlanValue,
    entryId: entryIdValue,
    expiresAt: expiresAtValue,
    safetyNotice: safetyNoticeValue,
    // Scenario-based fields
    scenario: scenarioValue,
    policies: policiesValue,
    claims: claimsValue,
  };
};
