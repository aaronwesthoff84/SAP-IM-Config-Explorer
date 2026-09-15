import { expect, test } from '@playwright/test';
import path from 'node:path';

const pipelineFixture = path.resolve('tests/fixtures/pipeline_known_order.xml');

function collectBrowserErrors(page: any, errors: string[]) {
  page.on('pageerror', (error: Error) => errors.push(error.message));
  page.on('console', (message: any) => {
    if (message.type() === 'error' && !message.text().includes('400') && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test('runs interactive rule simulator with event propagation and graph animation', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // 1. Upload pipeline XML file into graph
  await page.locator('#np-xml-files').setInputFiles(pipelineFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...', { timeout: 15000 });
  await expect(page.locator('#graph canvas').first()).toBeVisible({ timeout: 15000 });

  // 2. Switch to Rule Simulator tab
  await page.locator('#simulator-tab').click();
  await expect(page.locator('#simulator-view')).toHaveClass(/active/);
  await expect(page.locator('#simulator-form')).toBeVisible();

  // 3. Test preset selection: select "Over-Quota Accelerator"
  const presetSelect = page.locator('#simulator-preset-select');
  await presetSelect.selectOption('overquota');
  await expect(page.locator('#sim-amount')).toHaveValue('150000');
  await expect(page.locator('#sim-participant')).toHaveValue('TOP_PERFORMER');

  // 4. Run Simulation
  await page.locator('#sim-run-button').click();

  // 5. Verify summary banner is populated with calculation metrics
  await expect(page.locator('#simulator-summary-banner')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#sim-metric-credited')).toContainText('$150,000');
  await expect(page.locator('#sim-metric-attainment')).toContainText('150.0%');
  await expect(page.locator('#sim-metric-incentive')).toContainText('$21,875');
  await expect(page.locator('#sim-metric-deposit')).toContainText('$21,875');

  // 6. Verify calculation pipeline step cards
  const stepCards = page.locator('.sim-step-card');
  await expect(stepCards).toHaveCount(6);

  // Step 1 should be active by default
  await expect(stepCards.first()).toHaveClass(/active/);
  await expect(stepCards.first()).toContainText('Step 1: Crediting');

  // 7. Verify player controls and step forward
  const nextBtn = page.locator('#sim-btn-next');
  await expect(nextBtn).toBeEnabled();
  await nextBtn.click();

  // Step 2 should now be active
  await expect(stepCards.nth(1)).toHaveClass(/active/);
  await expect(stepCards.nth(1)).toContainText('Step 2: Primary Measurement');

  // 8. Test clicking a step card directly (Step 4: Standard Commission)
  await stepCards.nth(3).click();
  await expect(stepCards.nth(3)).toHaveClass(/active/);

  // 9. Test Play / Pause toggle
  const playBtn = page.locator('#sim-btn-play');
  await expect(playBtn).toHaveText('▶ Play');
  await playBtn.click();
  await expect(playBtn).toHaveText('⏸ Pause');
  await playBtn.click();
  await expect(playBtn).toHaveText('▶ Play');

  // 10. Test Reset button
  const resetBtn = page.locator('#sim-btn-reset');
  await resetBtn.click();
  await expect(stepCards.first()).toHaveClass(/active/);

  expect(errors).toHaveLength(0);
});
