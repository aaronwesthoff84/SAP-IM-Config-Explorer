import { expect, test } from '@playwright/test';
import path from 'node:path';

const baselineFixture = path.resolve('tests/fixtures/compare_baseline.xml');
const candidateFixture = path.resolve('tests/fixtures/compare_candidate.xml');
const invalidFixture = path.resolve('tests/fixtures/compare_invalid.xml');
const minimalFixture = path.resolve('tests/fixtures/minimal_plan.xml');

function collectBrowserErrors(page: any, errors: string[]) {
  page.on('pageerror', (error: Error) => errors.push(error.message));
  page.on('console', (message: any) => {
    if (message.type() === 'error' && !message.text().includes('400') && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test('compares two XML exports and reports added, removed, changed, and unchanged objects', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // Switch to Compare XML tab
  await page.locator('#compare-tab').click();
  await expect(page.locator('#compare-view')).toHaveClass(/active/);
  await expect(page.locator('#compare-status')).toBeVisible();

  // Set baseline and candidate files
  await page.locator('#compare-baseline-file').setInputFiles(baselineFixture);
  await page.locator('#compare-candidate-file').setInputFiles(candidateFixture);

  // Trigger comparison
  await page.locator('#compare-button').click();

  // Verify results container is shown
  await expect(page.locator('#compare-results-container')).toBeVisible();
  await expect(page.locator('#compare-status')).toContainText('Comparison complete');

  // Verify summary metrics
  const addedCount = await page.locator('#compare-count-added').textContent();
  const removedCount = await page.locator('#compare-count-removed').textContent();
  const changedCount = await page.locator('#compare-count-changed').textContent();
  const unchangedCount = await page.locator('#compare-count-unchanged').textContent();

  expect(Number(addedCount)).toBeGreaterThanOrEqual(3);
  expect(Number(removedCount)).toBeGreaterThanOrEqual(3);
  expect(Number(changedCount)).toBeGreaterThanOrEqual(3);
  expect(Number(unchangedCount)).toBeGreaterThanOrEqual(1);

  // Check changed objects in the item feed
  const itemsFeed = page.locator('#compare-items-list');
  await expect(itemsFeed).toContainText('Enterprise Plan');
  await expect(itemsFeed).toContainText('Credit Rule');
  await expect(itemsFeed).toContainText('Core Component');

  // Verify specific difference descriptions are rendered
  await expect(itemsFeed).toContainText('Bonus Component');
  await expect(itemsFeed).toContainText('BONUS_CALCULATION');

  // Test category filtering via summary cards
  // Click on "Changed" card
  await page.locator('.compare-card.card-changed').click();
  await expect(page.locator('#compare-category-filter')).toHaveValue('changed');
  await expect(itemsFeed.locator('.compare-badge.changed').first()).toBeVisible();
  await expect(itemsFeed.locator('.compare-badge.added')).toHaveCount(0);

  // Click on "Added" card
  await page.locator('.compare-card.card-added').click();
  await expect(page.locator('#compare-category-filter')).toHaveValue('added');
  await expect(itemsFeed.locator('.compare-badge.added').first()).toBeVisible();
  await expect(itemsFeed.locator('.compare-badge.changed')).toHaveCount(0);

  // Reset filters
  await page.locator('#compare-clear-filters').click();
  await expect(page.locator('#compare-category-filter')).toHaveValue('all');
  await expect(itemsFeed.locator('.compare-badge.changed').first()).toBeVisible();

  // Test object type filter
  await page.locator('#compare-type-filter').selectOption('Plan');
  const visibleCards = itemsFeed.locator('.compare-item-card');
  const count = await visibleCards.count();
  for (let i = 0; i < count; i++) {
    await expect(visibleCards.nth(i)).toContainText('Plan:');
  }

  // Test text search
  await page.locator('#compare-type-filter').selectOption('');
  await page.locator('#compare-search').fill('Credit Rule');
  await expect(itemsFeed).toContainText('Credit Rule');
  await expect(itemsFeed).not.toContainText('Decommissioned Plan');

  expect(errors).toEqual([]);
});

test('compares XML files regardless of upload filenames', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#compare-tab').click();

  // Upload identical content under different names or two different files
  await page.locator('#compare-baseline-file').setInputFiles({
    name: 'arbitrary_baseline_123.xml',
    mimeType: 'application/xml',
    buffer: Buffer.from((await import('node:fs')).readFileSync(baselineFixture)),
  });
  await page.locator('#compare-candidate-file').setInputFiles({
    name: 'completely_different_candidate_999.xml',
    mimeType: 'application/xml',
    buffer: Buffer.from((await import('node:fs')).readFileSync(candidateFixture)),
  });

  await page.locator('#compare-button').click();
  await expect(page.locator('#compare-results-container')).toBeVisible();
  await expect(page.locator('#compare-status')).toContainText('Comparison complete');

  // Verify Plans, Plan Components, Rules detected properly
  await expect(page.locator('#compare-items-list')).toContainText('Enterprise Plan');
  await expect(page.locator('#compare-items-list')).toContainText('Credit Rule');

  expect(errors).toEqual([]);
});

test('invalid or incomplete XML returns useful error without replacing prior results', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#compare-tab').click();

  // First run a valid comparison
  await page.locator('#compare-baseline-file').setInputFiles(baselineFixture);
  await page.locator('#compare-candidate-file').setInputFiles(candidateFixture);
  await page.locator('#compare-button').click();

  await expect(page.locator('#compare-results-container')).toBeVisible();
  const priorChangedText = await page.locator('#compare-items-list').textContent();
  expect(priorChangedText).toContain('Enterprise Plan');

  // Now select an invalid file as candidate
  await page.locator('#compare-candidate-file').setInputFiles(invalidFixture);
  await page.locator('#compare-button').click();

  // Error alert must be shown
  await expect(page.locator('#compare-error')).toBeVisible();
  await expect(page.locator('#compare-error')).toContainText(/XML|mismatched|unclosed|syntax/i);

  // Critical requirement: Prior valid comparison results MUST NOT be replaced or cleared
  await expect(page.locator('#compare-results-container')).toBeVisible();
  const preservedChangedText = await page.locator('#compare-items-list').textContent();
  expect(preservedChangedText).toContain('Enterprise Plan');

  expect(errors).toEqual([]);
});
