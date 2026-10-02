import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

let vite;
let speech;

test.before(async () => {
  vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent',
  });
  speech = await vite.ssrLoadModule('/src/utils/maiSpeech.js');
});

test.after(async () => {
  await vite?.close();
});

const profiles = ['byom-azure-openai-chat-completion', 'byom-foundry-anthropic-messages'];
const metadata = {
  runtime_transcription_models: {
    cascade: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech'],
    voicelive: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech'],
  },
};
const configFor = (profile, model) => ({
  byom: profile ? { mode: profile } : null,
  voicelive_model: { deployment_id: 'gpt-realtime' },
  session: { input_audio_transcription_settings: { model } },
});

test('explicit MAI 2.0 stays versioned; only legacy 1.5 normalizes to the generic alias', () => {
  assert.equal(speech.DEFAULT_TRANSCRIPTION_MODEL, 'mai-transcribe-2');
  assert.equal(speech.normalizeTranscriptionModel(' MAI-Transcribe-2 '), 'mai-transcribe-2');
  assert.equal(speech.normalizeTranscriptionModel('mai-transcribe'), 'mai-transcribe');
  assert.equal(speech.normalizeTranscriptionModel('MAI-Transcribe-1.5'), 'mai-transcribe');
  for (const model of ['mai-transcribe', 'mai-transcribe-2', 'mai-transcribe-1.5']) {
    assert.equal(speech.isMaiTranscriptionModel(model), true);
  }
  assert.equal(speech.isMaiTranscriptionModel('azure-speech'), false);
  assert.equal(speech.normalizeTranscriptionModel('Customer-Model'), 'Customer-Model');
});

test('omitted Cascade defaults to explicit 2.0; explicit Azure and generic remain unchanged', () => {
  for (const model of [undefined, null, '']) {
    assert.equal(speech.effectiveTranscriptionModel({ speech: { transcription_model: model } }, 'cascade'), 'mai-transcribe-2');
  }
  for (const model of ['azure-speech', 'mai-transcribe', 'mai-transcribe-2']) {
    const config = { speech: { transcription_model: model } };
    assert.equal(speech.effectiveTranscriptionModel(config, 'cascade'), model);
  }
});

test('only BYOM chat and Messages default omitted/null/empty/auto input to explicit 2.0', () => {
  for (const profile of profiles) {
    for (const model of [undefined, null, '', 'auto']) {
      const config = configFor(profile, model);
      assert.equal(speech.effectiveTranscriptionModel(config, 'voicelive'), 'mai-transcribe-2');
      assert.equal(speech.maiConfigurationError(config, 'voicelive', metadata), '');
    }
    for (const session of [undefined, null, {}, { input_audio_transcription_settings: null }]) {
      assert.equal(speech.effectiveTranscriptionModel({ byom: { mode: profile }, session }, 'voicelive'), 'mai-transcribe-2');
    }
  }
});

test('missing native and managed-chat inputs remain service defaults; explicit auto uses Azure', () => {
  for (const profile of [null, 'byom-azure-openai-realtime', 'unknown-profile']) {
    for (const model of [undefined, null, '']) {
      const config = configFor(profile, model);
      assert.equal(speech.effectiveTranscriptionModel(config, 'voicelive'), '');
      assert.equal(speech.maiConfigurationError(config, 'voicelive', metadata), '');
    }
    assert.equal(speech.effectiveTranscriptionModel(configFor(profile, 'auto'), 'voicelive'), 'azure-speech');
  }
  const managed = configFor(null);
  managed.voicelive_model.deployment_id = 'gpt-4.1';
  assert.equal(speech.effectiveTranscriptionModel(managed, 'voicelive'), '');
});

test('auto follows profile changes while explicit overrides never do', () => {
  const config = configFor(null, 'auto');
  const original = structuredClone(config);
  assert.equal(speech.effectiveTranscriptionModel(config, 'voicelive'), 'azure-speech');
  assert.deepEqual(config, original);
  for (const profile of profiles) {
    config.byom = { mode: profile };
    assert.equal(speech.effectiveTranscriptionModel(config, 'voicelive'), 'mai-transcribe-2');
  }
  for (const model of ['azure-speech', 'mai-transcribe', 'mai-transcribe-2', 'whisper-1']) {
    for (const profile of [null, ...profiles, 'byom-azure-openai-realtime']) {
      assert.equal(speech.effectiveTranscriptionModel(configFor(profile, model), 'voicelive'), model);
    }
  }
});

test('inferred Cascade MAI default validates diarization without requiring a selection change', () => {
  assert.match(
    speech.maiConfigurationError({ speech: { enable_diarization: true } }, 'cascade', metadata),
    /diarization/,
  );
  assert.equal(speech.maiConfigurationError({
    speech: { transcription_model: 'azure-speech', enable_diarization: true },
  }, 'cascade', metadata), '');
});

test('both MAI identifiers preserve native guards and inferred BYOM validates Azure-only options', () => {
  for (const model of ['mai-transcribe', 'mai-transcribe-2']) {
    assert.match(speech.maiConfigurationError(configFor(null, model), 'voicelive', metadata), /native realtime audio/);
  }
  for (const model of [undefined, 'auto', 'mai-transcribe', 'mai-transcribe-2']) {
    const config = configFor(profiles[0], model);
    config.session.input_audio_transcription_settings.custom_speech = { en: 'custom' };
    const original = structuredClone(config);
    assert.match(speech.maiConfigurationError(config, 'voicelive', metadata), /custom speech/);
    assert.deepEqual(config, original);
  }
});

test('generic-only runtime support does not advertise explicit 2.0 availability', () => {
  const legacy = { runtime_transcription_models: { cascade: ['mai-transcribe'] } };
  assert.match(speech.maiConfigurationError({}, 'cascade', legacy), /backend does not yet advertise/);
  assert.equal(speech.maiConfigurationError({
    speech: { transcription_model: 'mai-transcribe' },
  }, 'cascade', legacy), '');
  assert.match(speech.transcriptionHelp({}, 'cascade'), /service\/version availability is unconfirmed/);
  assert.match(speech.transcriptionHelp({ speech: { transcription_model: 'mai-transcribe' } }, 'cascade'), /does not pin version 2.0/);
});
