import { test, expect } from '@playwright/test';
import { installQuickTuneMocks } from './helpers/quick-tune-mocks.js';

async function prepare(page, { configure = () => {}, maiVoices = true, supported = true } = {}) {
  const state = await installQuickTuneMocks(page);
  configure(state.agents.BankingConcierge);
  await page.route('**/api/v1/agent-builder/voices{,?*}', (route) => route.fulfill({
    json: {
      source: 'regional-service', region: maiVoices ? 'eastus' : 'northcentralus',
      catalog_complete: true, verified_against_region: true,
      runtime_transcription_models: supported ? {
        cascade: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech'],
        voicelive: ['mai-transcribe-2', 'mai-transcribe', 'azure-speech', 'whisper-1'],
      } : {},
      voices: [
        { name: 'en-US-AvaMultilingualNeural', display_name: 'Ava', language: 'en-US', category: 'standard' },
        ...(maiVoices ? [
          { name: 'en-US-Harper:MAI-Voice-2', display_name: 'Harper', language: 'en-US', category: 'mai' },
          { name: 'en-US-Ethan:MAI-Voice-2-Flash', display_name: 'Ethan', language: 'en-US', category: 'mai' },
        ] : []),
      ],
    },
  }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Quick Tune', exact: true }).press('Enter');
  const panel = page.getByRole('complementary', { name: 'Quick Tune workspace' });
  await expect(panel.getByRole('combobox', { name: /^Input transcription/ })).toBeVisible();
  return { panel, state };
}

async function chooseMai(page, panel, name = 'MAI Transcribe 2.0') {
  await panel.getByRole('combobox', { name: /^Input transcription/ }).click();
  const option = page.getByRole('option', { name, exact: true });
  await expect(option).toBeEnabled();
  await option.click();
}

test('MAI 2.0 is first and is the omitted Cascade default without changing native or output settings', async ({ page }) => {
  const { panel, state } = await prepare(page);
  for (const mode of ['VoiceLive', 'Custom Speech']) {
    await panel.getByRole('button', { name: mode, exact: true }).click();
    const voice = panel.getByRole('combobox', { name: 'Voice', exact: true });
    await voice.fill('');
    await voice.press('ArrowDown');
    const voices = page.getByRole('listbox');
    await expect(voices.getByRole('option').first()).toHaveAttribute('aria-label', /MAI-Voice-2-Flash/);
    await voice.press('Escape');
    const input = panel.getByRole('combobox', { name: /^Input transcription/ });
    await expect(input).toHaveText(mode === 'VoiceLive' ? 'Azure Speech' : 'MAI Transcribe 2.0');
    await input.click();
    await expect(page.getByRole('listbox').getByRole('option').first()).toHaveText('MAI Transcribe 2.0');
    await page.getByRole('listbox').press('Escape');
  }
  expect(state.calls).toEqual([]);
  expect(state.agents.BankingConcierge.voicelive_model.deployment_id).toBe('gpt-realtime');
  expect(state.agents.BankingConcierge.voice.name).toBe('en-US-AvaMultilingualNeural');
});

test('MAI input requires an explicit switch from native VoiceLive to a managed text pipeline', async ({ page }) => {
  const { panel, state } = await prepare(page);
  await chooseMai(page, panel);
  await expect(panel.getByText(/MAI Transcribe requires a text-based VoiceLive model/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  expect(state.calls).toEqual([]);
  await panel.getByRole('button', { name: 'Use managed gpt-4.1', exact: true }).click();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.voicelive_model.deployment_id).toBe('gpt-4.1');
  expect(saved.byom).toBeNull();
  expect(saved.session.input_audio_transcription_settings.model).toBe('mai-transcribe-2');
});

test('explicit BYOM chat retains the user deployment while enabling MAI input', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.byom = { mode: 'byom-azure-openai-chat-completion' };
    config.voicelive_model.deployment_id = 'customer-chat-deployment';
  } });
  await chooseMai(page, panel);
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.voicelive_model.deployment_id).toBe('customer-chat-deployment');
  expect(saved.byom.mode).toBe('byom-azure-openai-chat-completion');
  expect(saved.session.input_audio_transcription_settings.model).toBe('mai-transcribe-2');
});

test('incompatible Azure-only input options are removed only by explicit action', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.voicelive_model.deployment_id = 'gpt-4.1';
    config.session.input_audio_transcription_settings = {
      model: 'azure-speech', language: 'en', custom_speech: { en: 'custom-model' }, phrase_list: ['Contoso'],
    };
  } });
  await chooseMai(page, panel);
  await expect(panel.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  await panel.getByRole('button', { name: 'Remove Azure-only options', exact: true }).click();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  expect(state.calls.find((call) => call.type === 'save-agent').body.session.input_audio_transcription_settings)
    .toEqual({ model: 'mai-transcribe-2', language: 'en' });
});

test('Custom Speech MAI input preserves the separate LLM and VoiceLive configuration', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.speech.transcription_model = 'azure-speech';
    config.speech.use_semantic_segmentation = true;
    config.speech.enable_diarization = true;
  } });
  const original = structuredClone(state.agents.BankingConcierge);
  await panel.getByRole('button', { name: 'Custom Speech', exact: true }).click();
  await chooseMai(page, panel);
  await expect(panel.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  await panel.getByRole('button', { name: 'Use MAI live input settings', exact: true }).click();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.speech.transcription_model).toBe('mai-transcribe-2');
  expect(saved.speech.use_semantic_segmentation).toBe(true);
  expect(saved.speech.enable_diarization).toBe(false);
  expect(saved.cascade_model).toEqual(original.cascade_model);
  expect(saved.voicelive_model).toEqual(original.voicelive_model);
  expect(saved.session).toEqual(original.session);
  expect(saved.voice).toEqual(original.voice);
});

test('MAI voice uses Azure output without unnecessarily changing the LLM pipeline', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.voice.type = 'azure-custom';
    config.voice.endpoint_id = 'old-custom-endpoint';
  } });
  await panel.getByRole('combobox', { name: 'Voice', exact: true }).fill('Ethan');
  await page.getByRole('option', { name: /Ethan.*MAI-Voice-2-Flash/ }).click();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.voice.name).toBe('en-US-Ethan:MAI-Voice-2-Flash');
  expect(saved.voice.type).toBe('azure-standard');
  expect(saved.voice.endpoint_id).toBeNull();
  expect(saved.voicelive_model.deployment_id).toBe('gpt-realtime');
});

test('missing regional voices and older backends show MAI options as unavailable', async ({ page }) => {
  const { panel, state } = await prepare(page, { maiVoices: false, supported: false });
  await panel.getByRole('combobox', { name: 'Voice', exact: true }).fill('MAI');
  const choices = page.getByRole('listbox').getByRole('option');
  await expect(choices).toHaveCount(4);
  for (const choice of await choices.all()) await expect(choice).toHaveAttribute('aria-disabled', 'true');
  await panel.getByRole('combobox', { name: 'Voice', exact: true }).press('Escape');
  await panel.getByRole('combobox', { name: /^Input transcription/ }).click();
  const inputs = page.getByRole('option', { name: /MAI Transcribe.*backend update required/ });
  await expect(inputs).toHaveCount(2);
  for (const choice of await inputs.all()) await expect(choice).toHaveAttribute('aria-disabled', 'true');
  expect(state.calls).toEqual([]);
});

for (const profile of ['byom-azure-openai-chat-completion', 'byom-foundry-anthropic-messages']) {
  test(`${profile} defaults omitted input to explicit 2.0 without rewriting provider or deployment`, async ({ page }) => {
    const { panel, state } = await prepare(page, { configure: (config) => {
      config.byom = { mode: profile };
      config.voicelive_model.deployment_id = profile.includes('anthropic') ? 'claude-sonnet-4-6' : 'customer-chat-deployment';
      delete config.session.input_audio_transcription_settings.model;
    } });
    const original = structuredClone(state.agents.BankingConcierge);
    await expect(panel.getByText(/Effective input: MAI Transcribe 2.0/)).toBeVisible();
    await expect(panel.getByText(/service\/version availability is unconfirmed/)).toBeVisible();
    await panel.getByRole('slider', { name: 'Speaking rate', exact: true }).press('ArrowRight');
    await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
    const saved = state.calls.find((call) => call.type === 'save-agent').body;
    expect(saved.session).toEqual(original.session);
    expect(saved.byom).toEqual(original.byom);
    expect(saved.voicelive_model).toEqual(original.voicelive_model);
  });
}

test('omitted Cascade default is checked for diarization before any provider change', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.speech.enable_diarization = true;
  } });
  await panel.getByRole('button', { name: 'Custom Speech', exact: true }).click();
  await expect(panel.getByRole('combobox', { name: /^Input transcription/ })).toHaveText('MAI Transcribe 2.0');
  await panel.getByRole('slider', { name: 'Speaking rate', exact: true }).press('ArrowRight');
  await expect(panel.getByText(/does not support the Azure SDK diarization/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  await panel.getByRole('combobox', { name: /^Input transcription/ }).click();
  await page.getByRole('option', { name: 'Azure Speech', exact: true }).click();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.speech.transcription_model).toBe('azure-speech');
  expect(saved.speech.enable_diarization).toBe(true);
});

test('auto follows profile changes but an explicit generic alias stays generic', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.voicelive_model.deployment_id = 'gpt-4.1';
    config.session.input_audio_transcription_settings.model = 'auto';
  } });
  await expect(panel.getByRole('combobox', { name: /^Input transcription/ })).toHaveText('Auto (follow profile)');
  await expect(panel.getByText(/Effective input: Azure Speech/)).toBeVisible();
  await panel.getByRole('combobox', { name: /^Model source/ }).click();
  await page.getByRole('option', { name: 'My Foundry chat deployment', exact: true }).click();
  await expect(panel.getByText(/Effective input: MAI Transcribe 2.0/)).toBeVisible();
  await chooseMai(page, panel, 'MAI Transcribe (generic alias)');
  await panel.getByRole('combobox', { name: /^Model source/ }).click();
  await page.getByRole('option', { name: 'Managed VoiceLive', exact: true }).click();
  await expect(panel.getByRole('combobox', { name: /^Input transcription/ })).toHaveText('MAI Transcribe (generic alias)');
  await expect(panel.getByText(/generic service alias does not pin version 2.0/)).toBeVisible();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  expect(state.calls.find((call) => call.type === 'save-agent').body.session.input_audio_transcription_settings.model)
    .toBe('mai-transcribe');
});

test('clearing VoiceLive selection preserves language and Azure-only options', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.session.input_audio_transcription_settings = {
      model: 'azure-speech', language: 'fr', custom_speech: { fr: 'custom' }, phrase_list: ['Contoso'],
    };
  } });
  await panel.getByRole('combobox', { name: /^Input transcription/ }).click();
  await page.getByRole('option', { name: 'Use configured default', exact: true }).click();
  await expect(panel.getByText(/Effective input: VoiceLive service default/)).toBeVisible();
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  expect(state.calls.find((call) => call.type === 'save-agent').body.session.input_audio_transcription_settings)
    .toEqual({ model: '', language: 'fr', custom_speech: { fr: 'custom' }, phrase_list: ['Contoso'] });
});

test('explicit Azure BYOM input remains Azure after unrelated tuning', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.byom = { mode: 'byom-azure-openai-chat-completion' };
    config.voicelive_model.deployment_id = 'customer-chat-deployment';
  } });
  await expect(panel.getByText(/Effective input: Azure Speech/)).toBeVisible();
  await panel.getByRole('slider', { name: 'Speaking rate', exact: true }).press('ArrowRight');
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(panel.getByText(/Saved for the next connection/)).toBeVisible();
  expect(state.calls.find((call) => call.type === 'save-agent').body.session.input_audio_transcription_settings.model)
    .toBe('azure-speech');
});

async function openAdvanced(page, panel) {
  await panel.getByRole('button', { name: 'Advanced Builder', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('tab', { name: 'Model & Audio', exact: true }).click();
  return dialog;
}

test('Advanced Builder defaults Cascade to 2.0 and saves an explicit Azure override with diarization', async ({ page }) => {
  const { panel, state } = await prepare(page, { configure: (config) => {
    config.speech.enable_diarization = true;
  } });
  const original = structuredClone(state.agents.BankingConcierge);
  const dialog = await openAdvanced(page, panel);
  const input = dialog.getByRole('combobox', { name: 'Input transcription', exact: true });
  await expect(input).toHaveValue('mai-transcribe-2');
  await expect(dialog.getByText(/does not support the Azure SDK diarization/)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Save Agent', exact: true })).toBeDisabled();
  await input.selectOption('azure-speech');
  await dialog.getByRole('button', { name: 'Save Agent', exact: true }).click();
  await expect.poll(() => state.calls.filter((call) => call.type === 'save-agent').length).toBe(1);
  const saved = state.calls.find((call) => call.type === 'save-agent').body;
  expect(saved.name).toBe('BankingConcierge');
  expect(saved.speech.transcription_model).toBe('azure-speech');
  expect(saved.speech.enable_diarization).toBe(true);
  expect(saved.session).toEqual(original.session);
  expect(saved.voice).toEqual(original.voice);
});

for (const model of ['azure-speech', 'mai-transcribe', 'mai-transcribe-2']) {
  test(`Advanced Builder preserves existing explicit ${model} for BYOM when saving`, async ({ page }) => {
    const { panel, state } = await prepare(page, { configure: (config) => {
      config.byom = { mode: 'byom-azure-openai-chat-completion' };
      config.voicelive_model.deployment_id = 'customer-chat-deployment';
      config.session.input_audio_transcription_settings.model = model;
    } });
    const original = structuredClone(state.agents.BankingConcierge);
    const dialog = await openAdvanced(page, panel);
    await dialog.getByRole('button', { name: /VoiceLive.*Realtime managed audio/ }).click();
    await expect(dialog.getByRole('combobox', { name: 'Transcription Model', exact: true })).toHaveValue(model);
    await dialog.getByRole('button', { name: 'Save Agent', exact: true }).click();
    await expect.poll(() => state.calls.filter((call) => call.type === 'save-agent').length).toBe(1);
    const saved = state.calls.find((call) => call.type === 'save-agent').body;
    expect(saved.session).toEqual(original.session);
    expect(saved.voicelive_model).toEqual(original.voicelive_model);
    expect(saved.byom).toEqual(original.byom);
    expect(saved.voice).toEqual(original.voice);
  });
}

test('Advanced Builder reset uses auto so later BYOM changes follow the profile', async ({ page }) => {
  const { panel } = await prepare(page);
  await page.route('**/api/v1/agent-builder/defaults', (route) => route.fulfill({
    json: { defaults: { session: { input_audio_transcription_settings: { model: 'azure-speech', language: 'fr-FR' } } } },
  }));
  const dialog = await openAdvanced(page, panel);
  await dialog.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(dialog.getByText('Reset to defaults', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: /VoiceLive.*Realtime managed audio/ }).click();
  const input = dialog.getByRole('combobox', { name: 'Transcription Model', exact: true });
  await expect(input).toHaveValue('auto');
  await expect(dialog.getByText(/Effective input: Azure Speech/)).toBeVisible();
  const profile = dialog.getByRole('combobox', { name: 'BYOM Profile', exact: true });
  await profile.selectOption('byom-azure-openai-chat-completion');
  await expect(input).toHaveValue('auto');
  await expect(dialog.getByText(/Effective input: MAI Transcribe 2.0/)).toBeVisible();
  await input.selectOption('azure-speech');
  await profile.selectOption('byom-foundry-anthropic-messages');
  await expect(input).toHaveValue('azure-speech');
  await expect(dialog.getByText(/Effective input: Azure Speech/)).toBeVisible();
  await expect(dialog.getByRole('combobox', { name: 'Language', exact: true })).toHaveValue('fr-FR');
});

test('new Advanced Builder sessions start with profile-following auto input', async ({ page }) => {
  const { panel } = await prepare(page);
  await page.route('**/api/v1/agent-builder/templates?*', (route) => route.fulfill({ json: { templates: [] } }));
  const dialog = await openAdvanced(page, panel);
  await dialog.getByRole('button', { name: /VoiceLive.*Realtime managed audio/ }).click();
  await expect(dialog.getByRole('combobox', { name: 'Transcription Model', exact: true })).toHaveValue('auto');
  await expect(dialog.getByText(/Effective input: Azure Speech/)).toBeVisible();
  await dialog.getByRole('combobox', { name: 'BYOM Profile', exact: true }).selectOption('byom-foundry-anthropic-messages');
  await expect(dialog.getByText(/Effective input: MAI Transcribe 2.0/)).toBeVisible();
});
