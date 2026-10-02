import { test, expect } from '@playwright/test';
import { AGENT_CONFIG, installQuickTuneMocks } from './helpers/quick-tune-mocks.js';

async function openTune(page) {
  await page.getByRole('button', { name: 'Open Quick Tune', exact: true }).click();
  const panel = page.getByRole('complementary', { name: 'Quick Tune workspace' });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('combobox', { name: 'Agent to tune' })).toHaveValue('BankingConcierge');
  await expect(panel.getByRole('button', { name: /^Behavior/ })).toBeVisible();
  return panel;
}

async function createDraft(page) {
  const panel = await openTune(page);
  await panel.getByRole('tab', { name: 'Create scenario', exact: true }).click();
  await panel.getByRole('textbox', { name: 'What should this scenario do?' }).fill('Help customers understand their balance with the available banking tools.');
  await panel.getByRole('button', { name: 'Generate draft', exact: true }).click();
  // Generate/Refine automatically opens the graphical review dialog. MUI
  // hides the rest of the page (including this Drawer) from the
  // accessibility tree while that modal is open, so close it first and only
  // then assert against the panel - both share the same draft state.
  await closeGraphReview(page);
  await expect(panel.getByText('Draft - not active', { exact: true })).toBeVisible();
  return panel;
}

async function closeGraphReview(page) {
  const dialog = page.getByRole('dialog', { name: /Review the generated scenario/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Close graphical editor' }).click();
  await expect(dialog).not.toBeVisible();
}

test.describe('Quick Tune authoring workspace', () => {
  test('uses one main-page entry point for editing and scenario creation', async ({ page }) => {
    await installQuickTuneMocks(page);
    await page.goto('/');
    const entry = page.getByRole('button', { name: 'Open Quick Tune', exact: true });
    await expect(entry).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Create scenario', exact: true })).toHaveCount(0);
    await page.locator('button[title="Select Industry Scenario"]').click();
    await expect(page.getByRole('button', { name: /Create custom scenario/ })).toHaveCount(0);
    const panel = await openTune(page);
    await expect(panel.getByRole('tab', { name: 'Tune agent', exact: true }))
      .toHaveAttribute('aria-selected', 'true');
    await panel.getByRole('tab', { name: 'Create scenario', exact: true }).click();
    await expect(panel.getByRole('textbox', { name: 'What should this scenario do?' })).toBeVisible();
    await entry.click();
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('tab', { name: 'Tune agent', exact: true }))
      .toHaveAttribute('aria-selected', 'true');
  });

  test('does not wait for deployment discovery before showing agent controls', async ({ page }) => {
    await installQuickTuneMocks(page);
    let releaseModels;
    const modelsGate = new Promise((resolve) => { releaseModels = resolve; });
    await page.route('**/api/v1/agent-builder/models{,?*}', async (route) => {
      await modelsGate;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"models":[]}' });
    });
    try {
      await page.goto('/');
      const panel = await openTune(page);
      await panel.getByRole('button', { name: /^Behavior/ }).click();
      await expect(panel.getByRole('textbox', { name: 'Instructions', exact: true }))
        .toHaveValue(AGENT_CONFIG.prompt);
    } finally {
      releaseModels();
    }
  });

  test('loads the named agent and preserves unedited settings when applying behavior', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/');
    const panel = await openTune(page);
    await panel.getByRole('button', { name: /^Behavior/ }).click();
    const instructions = panel.getByRole('textbox', { name: 'Instructions', exact: true });
    await expect(instructions).toHaveValue(AGENT_CONFIG.prompt);
    await instructions.fill(`${AGENT_CONFIG.prompt}\nKeep answers concise.`);
    await panel.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect(panel.getByRole('status')).toContainText('Saved for the next connection');
    const saved = state.calls.find((call) => call.type === 'save-agent');
    expect(saved.url).toContain('activate=false');
    expect(saved.body.name).toBe('BankingConcierge');
    expect(saved.body.prompt).toContain('Keep answers concise.');
    for (const key of ['cascade_model', 'voicelive_model', 'voice', 'speech', 'session', 'template_vars', 'tools']) {
      expect(saved.body[key]).toEqual(AGENT_CONFIG[key]);
    }
    expect(errors).toEqual([]);
  });

  test('keeps agent drafts across selection changes and closing the workspace', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    await page.goto('/');
    let panel = await openTune(page);
    await panel.getByRole('button', { name: /^Behavior/ }).click();
    await panel.getByRole('textbox', { name: 'Instructions', exact: true }).fill('Keep this unsaved instruction draft intact.');
    await panel.getByRole('combobox', { name: 'Agent to tune' }).fill('Fraud');
    await page.getByRole('option', { name: 'FraudAgent', exact: true }).click();
    await panel.getByRole('combobox', { name: 'Agent to tune' }).fill('Banking');
    await page.getByRole('option', { name: 'BankingConcierge', exact: true }).click();
    await panel.getByRole('button', { name: 'Close Quick Tune' }).click();
    panel = await openTune(page);
    await panel.getByRole('button', { name: /^Behavior/ }).click();
    await expect(panel.getByRole('textbox', { name: 'Instructions', exact: true }))
      .toHaveValue('Keep this unsaved instruction draft intact.');
    expect(state.calls.filter((call) => call.type === 'save-agent')).toHaveLength(0);
  });

  test('duplicates agents without overwriting existing names or switching the active agent', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await openTune(page);
    await panel.getByRole('button', { name: 'Duplicate agent', exact: true }).click();
    const name = panel.getByRole('textbox', { name: 'Agent name', exact: true });
    await expect(name).toHaveValue('BankingConciergeCopy');
    await name.fill('FraudAgent');
    await expect(panel.getByRole('button', { name: 'Save new agent', exact: true })).toBeDisabled();
    await name.fill('MyBankingAgent');
    await panel.getByRole('button', { name: 'Save new agent', exact: true }).click();
    await expect(panel.getByRole('status')).toContainText('Agent saved');
    expect(state.calls.find((call) => call.type === 'save-agent').url).toContain('create_only=true');
    expect(state.scenarios.scenariosResponse.active_start_agent).toBe('BankingConcierge');
    expect(state.agents.BankingConcierge.prompt).toBe(AGENT_CONFIG.prompt);
  });

  test('shows only relevant voice controls and never drops non-live edits from a patch', async ({ page }) => {
    await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await openTune(page);
    await panel.getByRole('button', { name: 'Custom Speech', exact: true }).click();
    await panel.getByRole('button', { name: 'Fine controls', exact: true }).click();
    await expect(panel.getByRole('checkbox', { name: 'Semantic turn detection' })).toBeVisible();
    await expect(panel.getByRole('combobox', { name: 'Input transcription' })).toBeVisible();
    const result = await page.evaluate(async (raw) => {
      const { editableAgent, liveSettingsPatch, affectsActiveMode } = await import('/src/utils/quickTune.js');
      const base = editableAgent(raw);
      const draft = structuredClone(base);
      draft.voice.rate = '+10%';
      const voiceOnly = liveSettingsPatch(base, draft);
      draft.voice.style = 'friendly';
      const withStyle = liveSettingsPatch(base, draft);
      draft.voice.style = base.voice.style;
      draft.session.input_audio_transcription_settings.model = 'whisper-1';
      const withTranscription = liveSettingsPatch(base, draft);
      const otherMode = structuredClone(base);
      otherMode.cascade_model.deployment_id = 'finance-mini';
      return { voiceOnly, withStyle, withTranscription, affectsVoiceLive: affectsActiveMode(base, otherMode, 'voicelive') };
    }, AGENT_CONFIG);
    expect(result.voiceOnly).toEqual({ mode: 'voicelive', voice: { rate: '+10%' } });
    expect(result.withStyle).toBeNull();
    expect(result.withTranscription).toBeNull();
    expect(result.affectsVoiceLive).toBe(false);
  });

  test('preserves handoff drafts across tabs and saves full scenario settings', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await openTune(page);
    await panel.getByRole('tab', { name: 'Edit scenario', exact: true }).click();
    const condition = panel.getByRole('textbox', { name: 'When should this handoff happen?' });
    await expect(condition).toHaveValue('The caller reports fraud.');
    await condition.fill('The caller reports a suspicious charge.');
    await panel.getByRole('tab', { name: 'Tune agent', exact: true }).click();
    await panel.getByRole('tab', { name: 'Edit scenario', exact: true }).click();
    await expect(condition).toHaveValue('The caller reports a suspicious charge.');
    await condition.fill('');
    await expect(panel.getByRole('button', { name: 'Save scenario', exact: true })).toBeDisabled();
    await expect(panel.getByText('Describe when handoff 1 should happen.')).toBeVisible();
    await condition.fill('The caller reports a suspicious charge.');
    await panel.getByRole('button', { name: 'Save scenario', exact: true }).click();
    await expect(panel.getByText('Scenario saved and selected. Start a conversation to try it.')).toBeVisible();
    const saved = state.scenarios.calls.find((call) => call.type === 'update');
    expect(saved.body.agent_defaults).toEqual({ voice_rate: '-5%' });
    expect(saved.body.tools).toEqual(['check_balance']);
    expect(saved.body.handoffs[0].context_vars).toEqual({ priority: 'urgent' });
  });

  test('retains the full builder as an explicit advanced path', async ({ page }) => {
    await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await openTune(page);
    await panel.getByRole('button', { name: 'Advanced Builder', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Identity', exact: true })).toBeVisible();
  });

  test('fits a small viewport and restores focus on close', async ({ page }, testInfo) => {
    await installQuickTuneMocks(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    const panel = await openTune(page);
    await expect(panel).toBeInViewport({ ratio: 0.99 });
    const bounds = await panel.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
    await page.screenshot({ path: testInfo.outputPath('quick-tune-mobile.png') });
    await panel.getByRole('button', { name: 'Close Quick Tune', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Open Quick Tune', exact: true })).toBeFocused();
  });

  test('does not resize or shift the conversation shell when Quick Tune opens or expands', async ({ page }, testInfo) => {
    await installQuickTuneMocks(page);
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.goto('/');
    const conversationBefore = await page.getByTestId('conversation-shell').boundingBox();
    const panel = await openTune(page);
    const conversationAfterOpen = await page.getByTestId('conversation-shell').boundingBox();
    expect(conversationAfterOpen).toEqual(conversationBefore);
    await panel.getByRole('button', { name: 'Expand workspace', exact: true }).click();
    await expect(panel).toBeInViewport({ ratio: 0.99 });
    // Quick Tune overlays the conversation shell (it is a fixed-position
    // panel) instead of resizing or shifting it - opening and expanding must
    // never change the conversation's geometry.
    const conversationAfterExpand = await page.getByTestId('conversation-shell').boundingBox();
    expect(conversationAfterExpand).toEqual(conversationBefore);
    await page.screenshot({ path: testInfo.outputPath('quick-tune-desktop.png') });
  });
});

test.describe('Tool-grounded scenario drafts', () => {
  test('generates without applying, lets users review, and applies only on explicit request', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/');
    const panel = await createDraft(page);
    expect(state.calls.map((call) => call.type)).toEqual(['generate']);
    expect(state.scenarios.scenariosResponse.active_scenario).toBe('Banking');
    await expect(panel.getByRole('button', { name: 'Apply scenario', exact: true })).toBeDisabled();
    await panel.getByRole('textbox', { name: 'company_name' }).fill('Northwind');
    await panel.getByRole('textbox', { name: 'Scenario purpose' }).fill('An edited, tool-grounded banking flow.');
    await panel.getByRole('button', { name: 'Apply scenario', exact: true }).click();
    await expect(panel.getByText('Scenario saved and selected. Start a conversation to try it.')).toBeVisible();
    const applied = state.calls.find((call) => call.type === 'apply-draft').body;
    expect(applied.scenario.global_template_vars.company_name).toBe('Northwind');
    expect(applied.scenario.description).toBe('An edited, tool-grounded banking flow.');
    expect(applied.agents.map((agent) => agent.name)).toEqual(['BalanceGuide']);
    expect(state.agents.BankingConcierge.prompt).toBe(AGENT_CONFIG.prompt);
    expect(state.scenarios.scenariosResponse.active_scenario).toBe('EverydayBanking');
    expect(errors).toEqual([]);
  });

  test('sends the edited draft when refining and keeps it after generation failure', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await createDraft(page);
    await panel.getByRole('textbox', { name: 'Scenario name', exact: true }).fill('EditedDraft');
    await panel.getByRole('textbox', { name: 'Describe a refinement' }).fill('Use a single agent instead.');
    state.generateError = 'The configured generation model is unavailable. Check your deployment.';
    await panel.getByRole('button', { name: 'Refine draft', exact: true }).click();
    await expect(panel.getByText(state.generateError)).toBeVisible();
    expect(state.calls.filter((call) => call.type === 'generate')[1].body.draft.scenario.name).toBe('EditedDraft');
    await expect(panel.getByRole('textbox', { name: 'Scenario name', exact: true })).toHaveValue('EditedDraft');
    expect(state.calls.filter((call) => call.type === 'apply-draft')).toHaveLength(0);
  });

  test('blocks unresolved capabilities and retains the draft after an apply failure', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    state.draft.missing_capabilities = ['No registered tool can issue a refund.'];
    await page.goto('/');
    const panel = await createDraft(page);
    await panel.getByRole('textbox', { name: 'company_name' }).fill('Northwind');
    await expect(panel.getByText('No registered tool can issue a refund.')).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Apply scenario', exact: true })).toBeDisabled();
    state.draft.missing_capabilities = [];
    await panel.getByRole('textbox', { name: 'Describe a refinement' }).fill('Remove refunds; only answer balance questions.');
    await panel.getByRole('button', { name: 'Refine draft', exact: true }).click();
    await closeGraphReview(page);
    await expect(panel.getByText('No registered tool can issue a refund.')).not.toBeVisible();
    await panel.getByRole('textbox', { name: 'company_name' }).fill('Northwind');
    state.applyError = 'Redis could not persist the scenario. Nothing was activated.';
    await panel.getByRole('button', { name: 'Apply scenario', exact: true }).click();
    await expect(panel.getByText(state.applyError)).toBeVisible();
    await expect(panel.getByText('Draft - not active', { exact: true })).toBeVisible();
    expect(state.scenarios.scenariosResponse.active_scenario).toBe('Banking');
    state.applyError = null;
    await panel.getByRole('button', { name: 'Apply scenario', exact: true }).click();
    await expect(panel.getByText('Scenario saved and selected. Start a conversation to try it.')).toBeVisible();
  });

  test('customizes a reused agent as a separate draft copy', async ({ page }) => {
    const state = await installQuickTuneMocks(page);
    await page.goto('/');
    const panel = await createDraft(page);
    await panel.getByRole('button', { name: 'Customize a copy', exact: true }).click();
    const composer = panel.getByTestId('quick-tune-create');
    await expect(composer.getByRole('textbox', { name: 'Agent name', exact: true })).toHaveValue('BankingConciergeCopy');
    await composer.getByRole('textbox', { name: 'Instructions', exact: true }).fill('A customized concierge using only approved tools.');
    await composer.getByRole('textbox', { name: 'company_name' }).fill('Northwind');
    await composer.getByRole('button', { name: 'Apply scenario', exact: true }).click();
    await expect(composer.getByText('Scenario saved and selected. Start a conversation to try it.')).toBeVisible();
    const body = state.calls.find((call) => call.type === 'apply-draft').body;
    expect(body.scenario.start_agent).toBe('BankingConciergeCopy');
    expect(body.scenario.handoffs[0].from_agent).toBe('BankingConciergeCopy');
    expect(body.agents.find((agent) => agent.name === 'BankingConciergeCopy').prompt)
      .toBe('A customized concierge using only approved tools.');
    expect(body.agents.find((agent) => agent.name === 'BankingConciergeCopy').handoff_trigger).toBe('');
    expect(body.agents.find((agent) => agent.name === 'BankingConciergeCopy').tools).toEqual(['check_balance']);
    expect(state.agents.BankingConcierge.prompt).toBe(AGENT_CONFIG.prompt);
  });
});
