import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const boundaryFixture = path.resolve('tests/fixtures/temporal_boundary.xml');
const overlapFixture = path.resolve('tests/fixtures/temporal_overlap.xml');
const gapFixture = path.resolve('tests/fixtures/temporal_gap.xml');
const missingDateFixture = path.resolve('tests/fixtures/temporal_missing_date.xml');
const baselineFixture = path.resolve('tests/fixtures/compare_baseline.xml');
const candidateFixture = path.resolve('tests/fixtures/compare_candidate.xml');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test.describe('Effective-date as-of view and temporal validation', () => {
  test('computes temporal status correctly in browser context', async ({ page }) => {
    await page.goto('/');

    const statuses = await page.evaluate(() => {
      const fn = (window as any).computeTemporalStatus;
      const dated = { metadata: { effectiveStartDate: '2026-01-01', effectiveEndDate: '2026-12-31' } };
      const openStart = { metadata: { effectiveStartDate: '2026-06-01' } };
      const openEnd = { metadata: { effectiveEndDate: '2026-06-01' } };
      const undated = { metadata: {} };
      const invalid = { metadata: { effectiveStartDate: 'not-a-date' } };
      const inverted = { metadata: { effectiveStartDate: '2026-12-31', effectiveEndDate: '2026-01-01' } };

      return {
        active: fn(dated, '2026-06-15').status,
        future: fn(dated, '2025-12-31').status,
        expired: fn(dated, '2027-01-01').status,
        undated: fn(undated, '2026-06-15').status,
        invalid: fn(invalid, '2026-06-15').status,
        inverted: fn(inverted, '2026-06-15').status,
        openStartActive: fn(openStart, '2026-07-01').status,
        openStartFuture: fn(openStart, '2026-05-01').status,
        openEndActive: fn(openEnd, '2026-05-01').status,
        openEndExpired: fn(openEnd, '2026-07-01').status,
      };
    });

    expect(statuses.active).toBe('active');
    expect(statuses.future).toBe('future');
    expect(statuses.expired).toBe('expired');
    expect(statuses.undated).toBe('undated');
    expect(statuses.invalid).toBe('unknown');
    expect(statuses.inverted).toBe('unknown');
    expect(statuses.openStartActive).toBe('active');
    expect(statuses.openStartFuture).toBe('future');
    expect(statuses.openEndActive).toBe('active');
    expect(statuses.openEndExpired).toBe('expired');
  });

  test('displays temporal status badge and explanation in node details and filters by date', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');

    // Upload boundary fixture to generate graph
    const fileInput = page.locator('#np-xml-files');
    await fileInput.setInputFiles(boundaryFixture);
    await page.click('#graph-button');

    // Wait for graph status to be populated
    await expect(page.locator('#status')).toContainText('topology:');

    // Filter control for effective date should be visible
    const dateControl = page.locator('#effective-date-filter-control');
    await expect(dateControl).toBeVisible();

    // Click on a node in cytoscape by querying node details
    await page.evaluate(() => {
      const state = (window as any).state;
      const node = state.graph.nodes.find(
        (n: any) => n.label === 'Boundary Component' && n.metadata?.effectiveEndDate === '2026-06-30'
      );
      if (node && (window as any).showNodeDetails) {
        (window as any).showNodeDetails(node);
      }
    });

    // Check node summary displays temporal badge and range
    const summary = page.locator('#node-summary');
    await expect(summary).toContainText('Temporal status');
    await expect(summary.locator('.temporal-badge')).toBeVisible();
    await expect(summary).toContainText('Effective range');

    // Set effective date to 2026-06-15 (within range 2026-01-01 to 2026-06-30)
    await page.fill('#effective-date-filter', '2026-06-15');

    // Badge should be Active
    await expect(summary.locator('.temporal-badge')).toHaveClass(/active/);
    await expect(summary.locator('.temporal-badge')).toHaveText('Active');
    await expect(summary.locator('.temporal-explanation')).toContainText('Active on 2026-06-15');

    // Set effective date to 2026-08-15 (past 2026-06-30) -> Expired
    await page.fill('#effective-date-filter', '2026-08-15');
    await expect(summary.locator('.temporal-badge')).toHaveClass(/expired/);
    await expect(summary.locator('.temporal-badge')).toHaveText('Expired');
    await expect(summary.locator('.temporal-explanation')).toContainText('Expired on 2026-06-30');

    // Reset filters
    await page.click('#clear-filters');
    await expect(page.locator('#effective-date-filter')).toHaveValue('');

    expect(errors).toEqual([]);
  });

  test('detects temporal overlap, gap, and invalid date findings in findings workbench', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');

    // Upload overlap fixture
    await page.locator('#np-xml-files').setInputFiles(overlapFixture);
    await page.click('#graph-button');
    await expect(page.locator('#status')).toContainText('topology:');

    // Check findings workbench contains temporal_overlap
    const findingsEl = page.locator('#validation-findings');
    await expect(findingsEl).toContainText('temporal_overlap');

    // Upload gap fixture
    await page.locator('#np-xml-files').setInputFiles(gapFixture);
    await page.click('#graph-button');
    await expect(page.locator('#status')).toContainText('topology:');
    await expect(findingsEl).toContainText('temporal_gap');

    // Upload missing / invalid date fixture
    await page.locator('#np-xml-files').setInputFiles(missingDateFixture);
    await page.click('#graph-button');
    await expect(page.locator('#status')).toContainText('topology:');
    await expect(findingsEl).toContainText('invalid_effective_date');

    expect(errors).toEqual([]);
  });

  test('comparison view records as-of date, shows as-of banner and temporal badges', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');

    // Switch to compare view
    await page.locator('#compare-tab').click();
    await expect(page.locator('#compare-view')).toHaveClass(/active/);

    // Set baseline and candidate files
    await page.locator('#compare-baseline-file').setInputFiles(baselineFixture);
    await page.locator('#compare-candidate-file').setInputFiles(candidateFixture);

    // Run comparison first to show results container
    await page.locator('#compare-button').click();
    await expect(page.locator('#compare-results-container')).toBeVisible();
    await expect(page.locator('#compare-status')).toContainText('Comparison complete');

    // Now fill as-of date filter in the results toolbar
    await page.locator('#compare-as-of-date').fill('2026-06-01');

    // Verify as-of banner is displayed in items list
    const itemsList = page.locator('#compare-items-list');
    await expect(itemsList.locator('.compare-as-of-banner')).toBeVisible();
    await expect(itemsList.locator('.compare-as-of-banner')).toContainText('As-of Date: 2026-06-01');

    // Verify cards display temporal badges
    const cards = itemsList.locator('.compare-item-card');
    const firstCardBadge = cards.first().locator('.temporal-badge');
    await expect(firstCardBadge).toBeVisible();

    // Reset filters and verify as-of date input is cleared
    await page.locator('#compare-clear-filters').click();
    await expect(page.locator('#compare-as-of-date')).toHaveValue('');

    expect(errors).toEqual([]);
  });
});
