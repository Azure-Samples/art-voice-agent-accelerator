/**
 * Foundry model & voice discovery helpers.
 *
 * Centralizes the "what can the CONNECTED Azure AI Foundry / Azure OpenAI
 * resource actually serve in its region" queries so both the standalone
 * AgentBuilder dialog and the embedded AgentBuilderContent (scenario builder)
 * show the same live deployment list instead of a hardcoded preset list.
 *
 *   • GET /api/v1/agent-builder/models  → real model deployments (incl. regional
 *     realtime/voice models). Each entry is tagged by the backend with `category`,
 *     `arch` ('native' | 'cascaded') and `modes` (['cascade'], ['voicelive'], or
 *     both) so we can route it to the correct dropdown.
 *   • GET /api/v1/agent-builder/voices  → TTS neural voices, already validated
 *     against the region by the backend (`verified_against_region`).
 *
 * Design contract: these helpers NEVER throw. On any failure (no creds, network,
 * empty list) they return null so callers can fall back to their static presets.
 */
import { API_BASE_URL } from '../config/constants.js';

/**
 * Classify a model by its VoiceLive audio architecture. Mirrors the backend
 * tagging; used only as a fallback when a model entry lacks an explicit `arch`.
 *   • 'native'   → realtime speech-to-speech (audio in/out).
 *   • 'cascaded' → Azure STT → text LLM → Azure TTS.
 */
export const classifyModelArch = (deploymentId) => {
  const name = (deploymentId || '').toLowerCase();
  if (!name) return 'native';
  return name.includes('realtime') ? 'native' : 'cascaded';
};

/**
 * Managed Voice Live models — the VoiceLive-hosted models used when BYOM is OFF.
 * These are NOT your resource deployments; they're billed by Voice Live pricing
 * tier. (BYOM is what lets you use your own deployments instead.)
 * https://learn.microsoft.com/azure/ai-services/speech-service/voice-live
 */
export const MANAGED_VOICELIVE_MODELS = [
  { id: 'gpt-realtime', tier: 'pro' },
  { id: 'gpt-4o', tier: 'pro' },
  { id: 'gpt-4.1', tier: 'pro' },
  { id: 'gpt-5', tier: 'pro' },
  { id: 'gpt-5-chat', tier: 'pro' },
  { id: 'gpt-realtime-mini', tier: 'basic' },
  { id: 'gpt-4o-mini', tier: 'basic' },
  { id: 'gpt-4.1-mini', tier: 'basic' },
  { id: 'gpt-5-mini', tier: 'basic' },
  { id: 'gpt-5-nano', tier: 'lite' },
  { id: 'phi4-mm-realtime', tier: 'lite' },
  { id: 'phi4-mini', tier: 'lite' },
];

// {id, label} options for the managed VoiceLive model dropdown (label shows tier).
export const MANAGED_VOICELIVE_OPTIONS = MANAGED_VOICELIVE_MODELS.map((m) => ({
  id: m.id,
  label: `${m.id} · ${m.tier}`,
  tier: m.tier,
}));

/**
 * Fetch the live model deployments from the connected Foundry/Azure OpenAI
 * resource. Returns { models, source, byCategory } or null on failure/empty.
 */
export async function fetchFoundryModels() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/models`);
    if (!res.ok) return null;
    const data = await res.json();
    const models = Array.isArray(data.models) ? data.models : [];
    if (models.length === 0) return null;
    return {
      models,
      source: data.source || 'azure_openai',
      byCategory: data.by_category || {},
    };
  } catch {
    return null;
  }
}

/**
 * From the raw /models list, derive ordered option lists for each builder mode.
 * Each option is normalized to { id, label, category, arch, deployed: true }.
 * Realtime (native-audio) models are surfaced first in the VoiceLive list.
 */
export function deriveModelOptions(models = []) {
  const cascade = [];
  const voicelive = [];
  const seenCascade = new Set();
  const seenVoicelive = new Set();

  // Realtime models first for the VoiceLive dropdown; otherwise preserve order.
  const ordered = [...models].sort((a, b) => {
    const ar = a.category === 'realtime' ? 0 : 1;
    const br = b.category === 'realtime' ? 0 : 1;
    return ar - br;
  });

  for (const m of ordered) {
    const id = (m.deployment_id || '').trim();
    if (!id) continue;
    const category = m.category || 'chat';
    if (category === 'embedding' || category === 'transcription') continue;
    const arch = m.arch || classifyModelArch(id);
    const modes =
      Array.isArray(m.modes) && m.modes.length
        ? m.modes
        : category === 'realtime'
          ? ['voicelive']
          : ['cascade', 'voicelive'];
    const key = id.toLowerCase();
    if (modes.includes('cascade') && !seenCascade.has(key)) {
      seenCascade.add(key);
      cascade.push({ id, label: id, category, arch, deployed: true });
    }
    if (modes.includes('voicelive') && !seenVoicelive.has(key)) {
      seenVoicelive.add(key);
      voicelive.push({ id, label: id, category, arch, deployed: true });
    }
  }

  return { cascade, voicelive };
}

/**
 * Fetch the region-validated TTS voice list plus verification metadata.
 * Returns { voices, verifiedAgainstRegion, source, defaultVoice } or null.
 */
export async function fetchRegionVoices() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/voices`);
    if (!res.ok) return null;
    const data = await res.json();
    return {
      voices: data.voices || [],
      verifiedAgainstRegion: Boolean(data.verified_against_region),
      source: data.source || 'static-catalog',
      defaultVoice: data.default_voice || null,
    };
  } catch {
    return null;
  }
}
