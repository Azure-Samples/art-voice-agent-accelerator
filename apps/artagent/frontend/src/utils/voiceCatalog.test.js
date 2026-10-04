import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

let vite;
let catalog;

test.before(async () => {
  vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent',
  });
  catalog = await vite.ssrLoadModule('/src/utils/voiceCatalog.js');
});

test.after(async () => {
  await vite?.close();
});

const voices = [
  { name: 'en-US-AvaMultilingualNeural', language: 'en-US', display_name: 'Ava' },
  { name: 'en-US-JennyNeural', language: 'en-US', display_name: 'Jenny' },
  { name: 'en-US-Ava:DragonHDLatestNeural', language: 'en-US', display_name: 'Ava HD', is_hd: true },
  { name: 'en-US-Andrew:DragonHDOmniLatestNeural', language: 'en-US', display_name: 'Andrew Omni', is_hd: true },
  { name: 'en-US-Harper:MAI-Voice-2.1', language: 'en-US', display_name: 'Harper' },
  { name: 'fr-FR-DeniseNeural', language: 'fr-FR', display_name: 'Denise' },
  { name: 'fr-FR-VivienneMultilingualNeural', language: 'fr-FR', display_name: 'Vivienne' },
];
const names = (list) => list.map((voice) => voice.name);
const MAI_REGIONS = ['eastus', 'swedencentral', 'westus2'];

test('multilingual covers MAI, Dragon HD Omni and *Multilingual voices only', () => {
  assert.deepEqual(names(voices.filter(catalog.isMultilingualVoice)), [
    'en-US-AvaMultilingualNeural', 'en-US-Andrew:DragonHDOmniLatestNeural',
    'en-US-Harper:MAI-Voice-2.1', 'fr-FR-VivienneMultilingualNeural',
  ]);
});

test('voice families classify MAI, HD and standard voices', () => {
  assert.deepEqual(voices.map(catalog.voiceFamily), ['standard', 'standard', 'hd', 'hd', 'mai', 'standard', 'standard']);
});

test('locale labels read as language with region and fall back to the raw id', () => {
  assert.equal(catalog.localeLabel('en-US'), 'English (United States)');
  assert.equal(catalog.localeLabel('fr-FR'), 'French (France)');
  assert.equal(catalog.localeLabel(''), '');
  assert.equal(catalog.voiceLocale({ name: 'de-DE-KatjaNeural' }), 'de-DE');
});

test('language options pin Multilingual and All, then count each locale', () => {
  const options = catalog.buildLanguageOptions([...voices, { name: 'x', unlisted: true }]);
  assert.deepEqual(options.map(({ id, count }) => [id, count]), [
    ['multilingual', 4], ['all', 7], ['en-US', 5], ['fr-FR', 2],
  ]);
  assert.equal(options[2].label, 'English (United States)');
});

test('language and family narrow the list; search spans every language', () => {
  assert.deepEqual(names(catalog.filterVoices(voices, { language: 'fr-FR' })), [
    'fr-FR-DeniseNeural', 'fr-FR-VivienneMultilingualNeural',
  ]);
  assert.deepEqual(names(catalog.filterVoices(voices, { language: 'en-US', family: 'hd' })), [
    'en-US-Ava:DragonHDLatestNeural', 'en-US-Andrew:DragonHDOmniLatestNeural',
  ]);
  assert.deepEqual(names(catalog.filterVoices(voices, { language: 'en-US', query: 'french' })), [
    'fr-FR-DeniseNeural', 'fr-FR-VivienneMultilingualNeural',
  ]);
  assert.deepEqual(names(catalog.filterVoices(voices, { language: 'fr-FR', family: 'mai', query: 'harper' })), [
    'en-US-Harper:MAI-Voice-2.1',
  ]);
  const unlisted = { name: 'custom-voice', unlisted: true };
  assert.ok(catalog.filterVoices([unlisted], { language: 'fr-FR', family: 'hd' }).includes(unlisted));
});

test('family counts follow the selected language', () => {
  assert.deepEqual(catalog.familyCounts(voices, 'en-US'), { all: 5, mai: 1, hd: 2, standard: 2 });
  assert.deepEqual(catalog.familyCounts(voices, 'multilingual'), { all: 4, mai: 1, hd: 1, standard: 2 });
});

test('default language follows the selected voice, then the browser, then en-US', () => {
  assert.equal(catalog.defaultLanguage('fr-FR-DeniseNeural', voices, 'de-DE'), 'fr-FR');
  assert.equal(catalog.defaultLanguage('ja-JP-NanamiNeural', [], 'de-DE'), 'ja-JP');
  assert.equal(catalog.defaultLanguage('', [], 'de-DE'), 'de-DE');
  assert.equal(catalog.defaultLanguage('', [], 'en'), 'en-US');
});

test('merged options add unlisted MAI voices and preserve an unknown saved value', () => {
  const extras = [
    { name: 'en-US-Harper:MAI-Voice-2.1', language: 'en-US' },
    { name: 'en-US-Harper:MAI-Voice-2.1-Flash', language: 'en-US' },
  ];
  const merged = catalog.mergeVoiceOptions(voices, extras, 'my-custom-voice');
  assert.equal(merged.length, voices.length + 2);
  assert.deepEqual(names(merged.slice(0, 2)), ['en-US-Harper:MAI-Voice-2.1-Flash', 'en-US-Harper:MAI-Voice-2.1']);
  assert.ok(merged.find((voice) => voice.name === 'my-custom-voice').unlisted);
});

test('voice metadata keeps known response fields and drops the voices list', () => {
  const picked = catalog.pickVoiceMetadata({ voices: [1], region: 'eastus', mai_voice_regions: MAI_REGIONS, junk: 1 });
  assert.deepEqual(picked, { region: 'eastus', mai_voice_regions: MAI_REGIONS });
});

test('MAI region status is per orchestration mode', () => {
  const regions = { speechRegion: 'northcentralus', voiceLiveRegion: 'Sweden Central', supportedRegions: MAI_REGIONS };
  const cascade = catalog.maiRegionStatus({ ...regions, mode: 'cascade' });
  assert.equal(cascade.state, 'unsupported');
  assert.deepEqual(cascade.targets.map((t) => t.supported), [false]);
  assert.equal(catalog.maiRegionStatus({ ...regions, mode: 'voicelive' }).state, 'supported');
  const shared = catalog.maiRegionStatus(regions);
  assert.equal(shared.state, 'supported');
  assert.deepEqual(shared.targets.map((t) => [t.label, t.supported]), [
    ['Cascade Speech resource', false], ['VoiceLive resource', true],
  ]);
});

test('MAI region status trusts a speech catalog listing MAI and reports unknown without data', () => {
  assert.equal(catalog.maiRegionStatus({
    mode: 'cascade', speechRegion: 'northcentralus', supportedRegions: MAI_REGIONS, speechCatalogHasMai: true,
  }).state, 'supported');
  assert.equal(catalog.maiRegionStatus({ mode: 'cascade', speechRegion: 'eastus' }).state, 'unknown');
  assert.equal(catalog.maiRegionStatus({ supportedRegions: MAI_REGIONS }).state, 'unknown');
});
