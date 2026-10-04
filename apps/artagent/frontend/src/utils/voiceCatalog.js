/**
 * Voice picker navigation: language, family and MAI region support.
 *
 * Pure helpers shared by every voice picker (Quick Tune, Agent Builder and the
 * Scenario Builder agent editor) so filtering and MAI availability rules are
 * defined, and tested, once.
 */
import { regionKeyOf } from './foundryRegions.js';
import { isMaiVoice, maiVoiceRank } from './maiSpeech.js';

export const MULTILINGUAL = 'multilingual';
export const ALL_LANGUAGES = 'all';
export const ALL_FAMILIES = 'all';

// `/agent-builder/voices` fields the pickers use, minus the voices themselves.
const VOICE_METADATA_KEYS = [
  'source', 'region', 'resource_host', 'total', 'total_available', 'catalog_complete',
  'verified_against_region', 'cached', 'stale', 'retrieved_at', 'warnings',
  'runtime_transcription_models',
  'resource_name', 'endpoint_host', 'app_region', 'region_source', 'resource_fallback',
  'hd_from_catalog', 'mai_voice_regions', 'mai_voice_catalog',
];

export const pickVoiceMetadata = (data = {}) => Object.fromEntries(
  VOICE_METADATA_KEYS.filter((key) => key in data).map((key) => [key, data[key]]),
);

export const VOICE_FAMILIES = [
  { id: ALL_FAMILIES, label: 'All' },
  { id: 'mai', label: 'MAI' },
  { id: 'hd', label: 'HD' },
  { id: 'standard', label: 'Standard' },
];

const localeNames = typeof Intl.DisplayNames === 'function'
  ? new Intl.DisplayNames(['en'], { type: 'language', languageDisplay: 'standard' }) : null;

export function localeLabel(locale) {
  if (!locale || !localeNames) return locale || '';
  try {
    return localeNames.of(locale) || locale;
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return locale;
  }
}

export function voiceFamily(voice) {
  if (isMaiVoice(voice.name)) return 'mai';
  if (voice.is_hd || voice.category === 'hd' || /dragonhd/i.test(voice.name || '')) return 'hd';
  return 'standard';
}

// MAI-Voice-2.1 and Dragon HD Omni voices are documented as multilingual;
// other Azure voices advertise it in their name.
export function isMultilingualVoice(voice) {
  const name = voice.name || '';
  return isMaiVoice(name) || /multilingual|dragonhdomni/i.test(name);
}

export function voiceLocale(voice) {
  if (voice?.language) return voice.language;
  return /^([a-z]{2,3}-[A-Z][A-Za-z]{1,3})-/.exec(voice?.name || '')?.[1] || '';
}

function inLanguage(voice, language) {
  if (voice.unlisted || language === ALL_LANGUAGES) return true;
  if (language === MULTILINGUAL) return isMultilingualVoice(voice);
  return voiceLocale(voice) === language;
}

function searchTerms(query) {
  return String(query || '').toLowerCase().trim().split(/\s+/).filter(Boolean);
}

function matchesTerms(voice, terms) {
  const text = [
    voice.name, voice.display_name, voice.local_name, voice.language, localeLabel(voiceLocale(voice)),
    voice.gender, voice.category, ...(voice.styles || []),
  ].filter(Boolean).join(' ').toLowerCase();
  return terms.every((term) => text.includes(term));
}

/** Language + family narrow the list; a search query spans every language. */
export function filterVoices(voices, { language = ALL_LANGUAGES, family = ALL_FAMILIES, query = '' } = {}) {
  const terms = searchTerms(query);
  return voices.filter((voice) => (
    (family === ALL_FAMILIES || voice.unlisted || voiceFamily(voice) === family)
    && (terms.length ? matchesTerms(voice, terms) : inLanguage(voice, language))
  ));
}

/** Pinned Multilingual / All entries, then every locale with its voice count. */
export function buildLanguageOptions(voices) {
  const counts = new Map();
  let multilingual = 0;
  for (const voice of voices) {
    if (voice.unlisted) continue;
    const locale = voiceLocale(voice);
    if (locale) counts.set(locale, (counts.get(locale) || 0) + 1);
    if (isMultilingualVoice(voice)) multilingual += 1;
  }
  const locales = [...counts].map(([id, count]) => ({ id, label: localeLabel(id), count }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
  return [
    { id: MULTILINGUAL, label: 'Multilingual', count: multilingual, pinned: true },
    { id: ALL_LANGUAGES, label: 'All languages', count: [...counts.values()].reduce((a, b) => a + b, 0), pinned: true },
    ...locales,
  ];
}

export function familyCounts(voices, language) {
  const counts = Object.fromEntries(VOICE_FAMILIES.map(({ id }) => [id, 0]));
  for (const voice of voices) {
    if (voice.unlisted || !inLanguage(voice, language)) continue;
    counts[ALL_FAMILIES] += 1;
    counts[voiceFamily(voice)] += 1;
  }
  return counts;
}

/** The current voice's locale, else the browser locale, else en-US. */
export function defaultLanguage(value, voices = [], preferred = '') {
  const current = voices.find((voice) => voice.name === value) || { name: value };
  const locale = voiceLocale(current);
  if (locale) return locale;
  return /^[a-z]{2,3}-[A-Z]{2}$/.test(preferred) ? preferred : 'en-US';
}

/** Regional voices, then documented MAI voices the region didn't list, then a preserved value. */
export function mergeVoiceOptions(voices, extras, value) {
  const listed = new Set(voices.map((voice) => voice.name));
  const list = [...voices, ...extras.filter((voice) => !listed.has(voice.name))];
  if (value && !list.some((voice) => voice.name === value)) {
    list.unshift({ name: value, display_name: value, unlisted: true });
  }
  return list.sort((a, b) => (
    maiVoiceRank(a.name) - maiVoiceRank(b.name)
    || voiceLocale(a).localeCompare(voiceLocale(b))
    || (a.display_name || a.name).localeCompare(b.display_name || b.name)
    || a.name.localeCompare(b.name)
  ));
}

/**
 * Whether MAI voices will synthesize for the resource(s) that would speak them.
 *
 * Cascade synthesizes on the Speech resource; VoiceLive on the Voice Live
 * resource. Without a mode (a shared agent definition) MAI is usable when either
 * resource supports it. Each target's `supported` is true, false, or null when
 * its region is unknown. The overall `state` is 'supported', 'unsupported' or
 * 'unknown'.
 */
export function maiRegionStatus({
  mode, speechRegion = '', voiceLiveRegion = '', supportedRegions = [], speechCatalogHasMai = false,
} = {}) {
  const documented = new Set(supportedRegions.map(regionKeyOf));
  const check = (label, region, verified = false) => {
    const key = regionKeyOf(region);
    const supported = verified ? true : key && documented.size ? documented.has(key) : null;
    return { label, region, supported };
  };
  const speech = check('Cascade Speech resource', speechRegion, speechCatalogHasMai);
  const voiceLive = check('VoiceLive resource', voiceLiveRegion);
  let targets;
  if (mode === 'cascade') targets = [speech];
  else if (mode === 'voicelive') targets = [voiceLive];
  else targets = [speech, voiceLive].filter((target) => target.region || target.supported);
  let state = 'unsupported';
  if (targets.some((target) => target.supported)) state = 'supported';
  else if (!targets.length || targets.some((target) => target.supported == null)) state = 'unknown';
  return { state, targets };
}
