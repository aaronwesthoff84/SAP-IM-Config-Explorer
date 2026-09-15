import { expect, test } from '@playwright/test';
import path from 'node:path';

const candidateFixture = path.resolve('tests/fixtures/compare_candidate.xml');

function collectBrowserErrors(page: any, errors: string[]) {
  page.on('pageerror', (error: Error) => errors.push(error.message));
  page.on('console', (message: any) => {
    if (message.type() === 'error' && !message.text().includes('400') && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test('enables multi-tier clustering, compound node visualization, and metanode condensation', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // 1. Upload candidate configuration into graph
  await page.locator('#np-xml-files').setInputFiles(candidateFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...', { timeout: 15000 });
  await expect(page.locator('#graph canvas').first()).toBeVisible({ timeout: 15000 });

  // 2. Clustering toolbar elements should initially be present but filter/condense hidden
  const clusterModeSelect = page.locator('#cluster-mode-select');
  await expect(clusterModeSelect).toBeVisible();
  await expect(page.locator('#cluster-filter')).toBeHidden();
  await expect(page.locator('#condense-metanodes-btn')).toBeHidden();

  // 3. Switch to Louvain Modularity mode
  await clusterModeSelect.selectOption('louvain');
  await expect(page.locator('#clustering-metrics-banner')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#clustering-metrics-text')).toContainText('Louvain Modularity');
  await expect(page.locator('#clustering-metrics-text')).toContainText('Modularity (Q)');

  // 4. Verify cluster filter dropdown and condense button are now visible
  const clusterFilter = page.locator('#cluster-filter');
  await expect(clusterFilter).toBeVisible();
  const clusterOptionsCount = await clusterFilter.locator('option').count();
  expect(clusterOptionsCount).toBeGreaterThan(1);

  const condenseBtn = page.locator('#condense-metanodes-btn');
  await expect(condenseBtn).toBeVisible();
  await expect(condenseBtn).toHaveText('Condense Metanodes');

  // 5. Filter to a specific cluster
  await clusterFilter.selectOption({ index: 1 });
  await expect(page.locator('#filter-results')).toContainText('Showing');

  // 6. Reset filter to All Clusters
  await clusterFilter.selectOption({ index: 0 });

  // 7. Toggle metanode condensation
  await condenseBtn.click();
  await expect(condenseBtn).toHaveText('Expand Clusters', { timeout: 10000 });
  await expect(page.locator('#graph canvas').first()).toBeVisible();

  // 8. Switch to Plan-Type Hierarchy mode
  await clusterModeSelect.selectOption('plan_type');
  await expect(page.locator('#clustering-metrics-banner')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#clustering-metrics-text')).toContainText('Plan-Type Hierarchy');

  // 9. Reset to None
  await clusterModeSelect.selectOption('none');
  await expect(page.locator('#clustering-metrics-banner')).toBeHidden();
  await expect(page.locator('#cluster-filter')).toBeHidden();
  await expect(page.locator('#condense-metanodes-btn')).toBeHidden();

  expect(errors).toEqual([]);
});
