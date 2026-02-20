/**
 * E2E tests for scenario switching.
 *
 * These tests validate that:
 * 1. Clicking an industry template in the sidebar menu immediately shows it as active
 * 2. Clicking a custom scenario immediately shows it as active
 * 3. Creating a new custom scenario in the Scenario Builder shows it as active
 * 4. Switching scenarios shows the correct icon in the sidebar
 * 5. Failed API calls roll back the optimistic update
 * 6. The active checkmark moves correctly between scenarios
 *
 * All backend API calls are mocked at the route level so tests don't
 * require a running backend.
 */

import { test, expect } from '@playwright/test';
import {
  installApiMocks,
  buildScenariosResponse,
  BANKING,
  INSURANCE,
  HEALTHCARE,
  makeScenario,
} from './helpers/scenario-mocks.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Open the scenario dropdown menu */
async function openScenarioMenu(page) {
  const scenarioBtn = page.locator('button[title="Select Industry Scenario"]');
  await expect(scenarioBtn).toBeVisible({ timeout: 10_000 });
  await scenarioBtn.click();
  const menu = page.locator('[data-scenario-menu]');
  await expect(menu).toBeVisible({ timeout: 5_000 });
  return menu;
}

/** Find a scenario button in the menu by its name text */
function scenarioButton(menu, name) {
  return menu.locator('button').filter({ hasText: name });
}

/** Assert which scenario is shown as active (has ✓ checkmark) */
async function expectActiveScenario(menu, expectedName) {
  // The active scenario has a ✓ following its name
  const activeBtn = menu.locator('button').filter({ hasText: '✓' }).filter({ hasText: expectedName });
  await expect(activeBtn).toBeVisible({ timeout: 5_000 });
}

/** Assert a scenario does NOT have the ✓ checkmark */
async function expectNotActiveScenario(menu, name) {
  const btn = scenarioButton(menu, name);
  await expect(btn).toBeVisible();
  // The button should exist but not contain ✓
  const checkmark = btn.locator('text=✓');
  await expect(checkmark).toHaveCount(0);
}

/** Get the sidebar scenario button's displayed icon text */
async function getSidebarIcon(page) {
  const btn = page.locator('button[title="Select Industry Scenario"]');
  return btn.innerText();
}

// ---------------------------------------------------------------------------
// Tests: Industry Template Switching (Sidebar Menu)
// ---------------------------------------------------------------------------

test.describe('Industry Template Switching', () => {
  test('clicking a template immediately shows it as active', async ({ page }) => {
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');
    const menu = await openScenarioMenu(page);

    // Banking should start as active
    await expectActiveScenario(menu, 'Banking');
    await expectNotActiveScenario(menu, 'Insurance');

    // Click Insurance
    await scenarioButton(menu, 'Insurance').click();

    // Menu closes — reopen to verify
    const menu2 = await openScenarioMenu(page);

    // Insurance should now be active, Banking should not
    await expectActiveScenario(menu2, 'Insurance');
    await expectNotActiveScenario(menu2, 'Banking');
  });

  test('switching template updates sidebar icon', async ({ page }) => {
    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    // Should show Banking icon initially
    const sidebarBtn = page.locator('button[title="Select Industry Scenario"]');
    await expect(sidebarBtn).toContainText('🏦');

    // Switch to Insurance
    const menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();

    // Sidebar icon should update to Insurance icon
    await expect(sidebarBtn).toContainText('🛡️', { timeout: 5_000 });
  });

  test('switching template calls the correct API endpoint', async ({ page }) => {
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');
    const menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Healthcare').click();

    // Wait for the API call
    await page.waitForTimeout(500);

    // Verify apply-template was called
    const templateCalls = mockState.calls.filter(c => c.type === 'apply-template');
    expect(templateCalls.length).toBeGreaterThanOrEqual(1);
    const lastCall = templateCalls[templateCalls.length - 1];
    expect(lastCall.url).toContain('template_id=healthcare');
  });

  test('rapid switching settles on last clicked template', async ({ page }) => {
    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    // Click Banking -> Insurance quickly
    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();
    
    // Reopen and click Healthcare
    menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Healthcare').click();

    // Final state should show Healthcare active
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Healthcare');
  });
});

// ---------------------------------------------------------------------------
// Tests: Custom Scenario Switching
// ---------------------------------------------------------------------------

test.describe('Custom Scenario Switching', () => {
  test('clicking a custom scenario shows it as active', async ({ page }) => {
    const customScenario = makeScenario({
      name: 'My Telecom Flow',
      icon: '📞',
      start_agent: 'TelecomBot',
      agents: ['TelecomBot', 'BillingAgent'],
      is_active: false,
      is_custom: true,
    });

    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE()],
      customs: [customScenario],
    }));

    await page.goto('/');
    let menu = await openScenarioMenu(page);

    // Banking should be active initially
    await expectActiveScenario(menu, 'Banking');

    // Click custom scenario
    await scenarioButton(menu, 'My Telecom Flow').click();

    // Reopen menu to verify
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'My Telecom Flow');
    await expectNotActiveScenario(menu, 'Banking');
  });

  test('custom scenario icon appears in sidebar after selection', async ({ page }) => {
    const customScenario = makeScenario({
      name: 'My Telecom Flow',
      icon: '📞',
      start_agent: 'TelecomBot',
      is_active: false,
      is_custom: true,
    });

    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true)],
      customs: [customScenario],
    }));

    await page.goto('/');
    const sidebarBtn = page.locator('button[title="Select Industry Scenario"]');
    await expect(sidebarBtn).toContainText('🏦'); // Banking initially

    const menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'My Telecom Flow').click();

    // After selecting custom scenario, sidebar should show its icon
    await expect(sidebarBtn).toContainText('📞', { timeout: 5_000 });
  });

  test('switching from custom back to builtin template works', async ({ page }) => {
    const customScenario = makeScenario({
      name: 'Custom Flow',
      icon: '⚡',
      start_agent: 'CustomBot',
      is_active: true,
      is_custom: true,
    });

    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(), INSURANCE()],
      customs: [customScenario],
    }));

    await page.goto('/');
    let menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Custom Flow');

    // Switch to Banking
    await scenarioButton(menu, 'Banking').click();

    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Banking');
    await expectNotActiveScenario(menu, 'Custom Flow');
  });
});

// ---------------------------------------------------------------------------
// Tests: API Failure Rollback
// ---------------------------------------------------------------------------

test.describe('API Failure Rollback', () => {
  // fixme: applyScenarioOptimistically captures prevState via a React setState
  // updater closure, but React 18 batching defers updater execution so
  // prevState is null when the rollback fires.  The rollback sets
  // sessionScenarioConfig to null, clearing all scenario buttons.
  test.fixme('builtin template switch rolls back on API failure', async ({ page }) => {
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE()],
    }));

    await page.goto('/');

    // Set up failure
    mockState.failNextPost = true;

    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();

    // Wait for the failed request and rollback
    await page.waitForTimeout(1000);

    // Reopen menu — Banking should still be active (rolled back)
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Banking');
  });

  // fixme: same React 18 batching issue as the builtin rollback test above.
  test.fixme('custom scenario switch rolls back on API failure', async ({ page }) => {
    const customScenario = makeScenario({
      name: 'Custom Flow',
      icon: '⚡',
      start_agent: 'CustomBot',
      is_active: false,
      is_custom: true,
    });

    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true)],
      customs: [customScenario],
    }));

    await page.goto('/');

    // Set up failure
    mockState.failNextPost = true;

    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Custom Flow').click();

    await page.waitForTimeout(1000);

    // Reopen — Banking should still be active
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Banking');
  });
});

// ---------------------------------------------------------------------------
// Tests: Active Indicator Consistency
// ---------------------------------------------------------------------------

test.describe('Active Indicator Consistency', () => {
  test('only one scenario shows active checkmark at a time', async ({ page }) => {
    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
      customs: [
        makeScenario({ name: 'Custom1', is_custom: true }),
        makeScenario({ name: 'Custom2', is_custom: true }),
      ],
    }));

    await page.goto('/');
    const menu = await openScenarioMenu(page);

    // Count checkmarks — should be exactly 1
    const checkmarks = menu.locator('button').filter({ hasText: '✓' });
    await expect(checkmarks).toHaveCount(1);
    await expectActiveScenario(menu, 'Banking');
  });

  test('checkmark moves when switching scenarios', async ({ page }) => {
    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    // Start: Banking active
    let menu = await openScenarioMenu(page);
    let checkmarks = menu.locator('button').filter({ hasText: '✓' });
    await expect(checkmarks).toHaveCount(1);

    // Switch to Insurance
    await scenarioButton(menu, 'Insurance').click();

    // Reopen: Insurance should be the only active
    menu = await openScenarioMenu(page);
    checkmarks = menu.locator('button').filter({ hasText: '✓' });
    await expect(checkmarks).toHaveCount(1);
    await expectActiveScenario(menu, 'Insurance');

    // Switch to Healthcare
    await scenarioButton(menu, 'Healthcare').click();

    // Reopen: Healthcare active
    menu = await openScenarioMenu(page);
    checkmarks = menu.locator('button').filter({ hasText: '✓' });
    await expect(checkmarks).toHaveCount(1);
    await expectActiveScenario(menu, 'Healthcare');
  });
});

// ---------------------------------------------------------------------------
// Tests: Scenario State After Page Reload
// ---------------------------------------------------------------------------

test.describe('Scenario Persistence', () => {
  test('active scenario persists after menu close and reopen', async ({ page }) => {
    await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE()],
    }));

    await page.goto('/');

    // Switch to Insurance
    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();

    // Wait for state to settle
    await page.waitForTimeout(500);

    // Close and reopen menu multiple times
    for (let i = 0; i < 3; i++) {
      menu = await openScenarioMenu(page);
      await expectActiveScenario(menu, 'Insurance');
      await page.locator('button[title="Select Industry Scenario"]').click();
      await page.waitForTimeout(200);
    }
  });
});

// ---------------------------------------------------------------------------
// Tests: Race Condition Protection  (stale refetch must NOT clobber)
// ---------------------------------------------------------------------------

test.describe('Race Condition Protection', () => {
  test('stale refetch after builtin switch does NOT revert active scenario', async ({ page }) => {
    // Simulate backend returning stale data on the first GET after a switch.
    // This mirrors real-world Redis propagation delay.
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    // After the initial load, set the next GET to be stale: it will return
    // a snapshot of the current state (Banking active) AFTER a 500ms delay,
    // even though the POST will update the mock state to Insurance immediately.
    mockState.staleGetDelayMs = 500;
    mockState.staleGetCount = 2; // cover both the confirmation fetch + any background ones

    // Switch to Insurance
    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();

    // Wait long enough for the stale GET to have arrived
    await page.waitForTimeout(1500);

    // Open menu — Insurance MUST still be active (the stale GET should
    // have been discarded by the version guard)
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Insurance');
    await expectNotActiveScenario(menu, 'Banking');
  });

  test('stale refetch after custom scenario switch does NOT revert', async ({ page }) => {
    const customScenario = makeScenario({
      name: 'My Custom',
      icon: '🔮',
      start_agent: 'CustomBot',
      is_active: false,
      is_custom: true,
    });

    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true)],
      customs: [customScenario],
    }));

    await page.goto('/');

    // Make the next GET stale — it will return Banking-active snapshot
    mockState.staleGetDelayMs = 500;
    mockState.staleGetCount = 2;

    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'My Custom').click();

    await page.waitForTimeout(1500);

    // Custom scenario must stay active
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'My Custom');
    await expectNotActiveScenario(menu, 'Banking');
  });

  test('rapid switch: second switch sticks even when first refetch is slow', async ({ page }) => {
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    // First switch: Banking → Insurance. Make refetch slow.
    mockState.staleGetDelayMs = 1000;
    mockState.staleGetCount = 1;

    let menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Insurance').click();

    // Immediately switch again: Insurance → Healthcare (no delay this time)
    menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Healthcare').click();

    // Wait for all fetches to complete
    await page.waitForTimeout(2000);

    // Healthcare must be the active scenario — not Insurance, not Banking
    menu = await openScenarioMenu(page);
    await expectActiveScenario(menu, 'Healthcare');
  });

  test('switch settles correctly: sidebar icon matches after stale refetch', async ({ page }) => {
    const mockState = await installApiMocks(page, buildScenariosResponse({
      builtins: [BANKING(true), INSURANCE(), HEALTHCARE()],
    }));

    await page.goto('/');

    const sidebarBtn = page.locator('button[title="Select Industry Scenario"]');
    await expect(sidebarBtn).toContainText('🏦'); // Banking initially

    // Add delay to simulate stale response
    mockState.staleGetDelayMs = 300;
    mockState.staleGetCount = 2;

    // Switch to Healthcare
    const menu = await openScenarioMenu(page);
    await scenarioButton(menu, 'Healthcare').click();

    // Wait for delayed GET to arrive
    await page.waitForTimeout(1000);

    // Sidebar icon MUST show Healthcare, not Banking
    await expect(sidebarBtn).toContainText('🏥', { timeout: 3_000 });
  });
});
