import { MANAGED_VOICELIVE_MODELS, classifyModelArch } from './foundryModels.js';

export const MAI_TRANSCRIPTION_MODEL = 'mai-transcribe';
export const DEFAULT_TRANSCRIPTION_MODEL = 'mai-transcribe-2';
const CHAT_PROFILES = new Set(['byom-azure-openai-chat-completion', 'byom-foundry-anthropic-messages']);

export const MAI_VOICE_DOCS_URL = 'https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices#availability-and-regions';

// Fallback for backends that don't send `mai_voice_catalog`.
export const MAI_VOICE_PRESETS = [
  ['en-US-Harper:MAI-Voice-2.1-Flash', 'Harper', 'Female'],
  ['en-US-Ethan:MAI-Voice-2.1-Flash', 'Ethan', 'Male'],
  ['en-US-Harper:MAI-Voice-2.1', 'Harper', 'Female'],
  ['en-US-Ethan:MAI-Voice-2.1', 'Ethan', 'Male'],
].map(([name, display_name, gender]) => ({
  name, display_name, gender, language: 'en-US', category: 'mai', status: 'Preview',
  region_verified: false,
}));

export function normalizeTranscriptionModel(model) {
  const value = String(model || '').trim().toLowerCase();
  if (value === 'mai-transcribe-1.5') return MAI_TRANSCRIPTION_MODEL;
  if ([MAI_TRANSCRIPTION_MODEL, DEFAULT_TRANSCRIPTION_MODEL].includes(value)) {
    return value;
  }
  return model || '';
}

export function isMaiTranscriptionModel(model) {
  return [MAI_TRANSCRIPTION_MODEL, DEFAULT_TRANSCRIPTION_MODEL].includes(normalizeTranscriptionModel(model));
}

export function effectiveTranscriptionModel(config, mode) {
  const model = normalizeTranscriptionModel(mode === 'voicelive'
    ? config.session?.input_audio_transcription_settings?.model : config.speech?.transcription_model);
  if (mode !== 'voicelive') return model || DEFAULT_TRANSCRIPTION_MODEL;
  if ((!model || model === 'auto') && CHAT_PROFILES.has(config.byom?.mode)) {
    return DEFAULT_TRANSCRIPTION_MODEL;
  }
  return model === 'auto' ? 'azure-speech' : model;
}

export function transcriptionModelLabel(model) {
  if (model === DEFAULT_TRANSCRIPTION_MODEL) return 'MAI Transcribe 2.0';
  if (model === MAI_TRANSCRIPTION_MODEL) return 'MAI Transcribe (generic alias)';
  if (model === 'azure-speech') return 'Azure Speech';
  if (model === 'auto') return 'Auto (follow profile)';
  return model || 'VoiceLive service default';
}

export function transcriptionHelp(config, mode) {
  const model = effectiveTranscriptionModel(config, mode);
  const effective = `Effective input: ${transcriptionModelLabel(model)}.`;
  const availability = model === DEFAULT_TRANSCRIPTION_MODEL
    ? ' Explicit mai-transcribe-2; service/version availability is unconfirmed.'
    : model === MAI_TRANSCRIPTION_MODEL ? ' The generic service alias does not pin version 2.0.' : '';
  const pipeline = mode === 'voicelive'
    ? ' Auto follows the BYOM profile; native realtime audio is unchanged.'
    : ' Your Custom Speech LLM and TTS remain unchanged.';
  return effective + availability + pipeline;
}

export function isMaiVoice(name) {
  return String(name || '').toLowerCase().includes(':mai-voice');
}

// Newest MAI model first, Flash ahead of the full model within a version
// (2.1-Flash, 2.1, 2-Flash, 2), then unrecognized MAI names, then other voices.
export function maiVoiceRank(name) {
  if (!isMaiVoice(name)) return 1;
  const match = /:mai-voice-(\d+(?:\.\d+)?)(-flash)?$/i.exec(String(name));
  if (!match) return 0;
  return -Math.round(Number(match[1]) * 100) * 2 + (match[2] ? 0 : 1);
}

export function voiceDisplayLabel(voice) {
  const label = voice.display_name || voice.name;
  if (!isMaiVoice(voice.name) || /mai/i.test(label)) return label;
  return `${label} (${voice.name.split(':').at(-1)})`;
}

export function voiceLivePipeline(config) {
  const profile = config.byom?.mode;
  if (CHAT_PROFILES.has(profile)) return 'byom-chat';
  if (profile === 'byom-azure-openai-realtime') return 'native';
  if (profile) return 'unknown';
  const model = config.voicelive_model?.deployment_id || config.model?.deployment_id;
  const managed = MANAGED_VOICELIVE_MODELS.find((item) => item.id === model);
  return managed ? classifyModelArch(model) === 'native' ? 'native' : 'managed-chat' : 'unknown';
}

export function maiConfigurationError(config, mode, voiceMetadata) {
  if (!config) return '';
  const model = effectiveTranscriptionModel(config, mode);
  if (!isMaiTranscriptionModel(model)) return '';
  if (voiceMetadata !== undefined
    && !voiceMetadata?.runtime_transcription_models?.[mode]?.includes(model)) {
    return 'The connected backend does not yet advertise MAI input support for this mode. Update the API and refresh the catalog before applying.';
  }
  if (mode === 'voicelive') {
    if (!['managed-chat', 'byom-chat'].includes(voiceLivePipeline(config))) {
      return 'MAI Transcribe requires a text-based VoiceLive model or a BYOM chat/Messages profile, not native realtime audio.';
    }
    const settings = config.session?.input_audio_transcription_settings || {};
    if (settings.custom_speech != null || settings.phrase_list != null) {
      return 'MAI Transcribe cannot use Azure-only custom speech models or phrase lists. Remove those options or use Azure Speech.';
    }
  } else if (config.speech?.enable_diarization) {
    return 'MAI live input does not support the Azure SDK diarization option. Disable diarization to use this input provider.';
  }
  return '';
}

export function useManagedMaiPipeline(config) {
  return {
    ...config,
    byom: null,
    voicelive_model: {
      ...config.voicelive_model, deployment_id: 'gpt-4.1', name: 'gpt-4.1', model_family: null,
    },
  };
}
