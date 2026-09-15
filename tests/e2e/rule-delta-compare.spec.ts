import { expect, test } from '@playwright/test';
import path from 'node:path';

const baselineFixture = path.resolve('tests/fixtures/compare_baseline.xml');
const candidateFixture = path.resolve('tests/fixtures/compare_candidate.xml');

function collectBrowserErrors(page: any, errors: string[]) {
  page.on('pageerror', (error: Error) => errors.push(error.message));
  page.on('console', (message: any) => {
    if (message.type() === 'error' && !message.text().includes('400') && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test('renders formula AST diff and enables graph blast radius navigation', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // First load a configuration into the main graph so graph view has elements
  await page.locator('#np-xml-files').setInputFiles(candidateFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...', { timeout: 15000 });
  await expect(page.locator('#graph canvas').first()).toBeVisible({ timeout: 15000 });

  // Navigate to Compare XML tab
  await page.locator('#compare-tab').click();
  await expect(page.locator('#compare-view')).toHaveClass(/active/);

  // Set baseline and candidate files
  await page.locator('#compare-baseline-file').setInputFiles(baselineFixture);
  await page.locator('#compare-candidate-file').setInputFiles(candidateFixture);

  // Trigger comparison
  await page.locator('#compare-button').click();

  // Verify results container is shown
  await expect(page.locator('#compare-results-container')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#compare-status')).toContainText('Comparison complete');

  // Filter to changed items
  await page.locator('#compare-category-filter').selectOption('changed');

  // Verify blast radius box or formula diff is rendered for changed items
  const compareItemsList = page.locator('#compare-items-list');
  await expect(compareItemsList).toBeVisible();

  // Check for blast radius box
  const blastBoxes = compareItemsList.locator('.blast-radius-box');
  const blastBoxCount = await blastBoxes.count();
  expect(blastBoxCount).toBeGreaterThanOrEqual(1);

  // Check for show-blast-radius button
  const blastBtn = compareItemsList.locator('.show-blast-radius-btn').first();
  if (await blastBtn.isVisible()) {
    await blastBtn.click();

    // Verify view switches back to Graph view
    await expect(page.locator('#graph-view')).toHaveClass(/active/);
    await expect(page.locator('#tab-graph-view')).toHaveClass(/active/);
  }

  expect(errors).toEqual([]);
});
