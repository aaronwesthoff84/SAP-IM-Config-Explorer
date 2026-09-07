import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const graphFixture = path.resolve('tests/fixtures/portable_export_graph.json');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test.describe('Findings Workbench and Local Waivers', () => {
  test('filters findings by severity, code, snapshot, search, and resets', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');
    const importControl = page.getByLabel('Import Graph JSON');
    await importControl.setInputFiles(graphFixture);

    // Verify workbench is loaded
    await expect(page.locator('#findings-counter')).toContainText('Showing 2 of 2 findings (0 waived)');
    const findingsList = page.locator('#validation-findings .finding');
    await expect(findingsList).toHaveCount(2);

    // Filter by severity: error
    await page.selectOption('#findings-severity-filter', 'error');
    await expect(page.locator('#findings-counter')).toContainText('Showing 1 of 2 findings (0 waived)');
    await expect(findingsList).toHaveCount(1);
    await expect(findingsList.first()).toContainText('duplicate_object');

    // Filter by code: unused_object while severity is error -> 0 results
    await page.selectOption('#findings-code-filter', 'unused_object');
    await expect(page.locator('#findings-counter')).toContainText('Showing 0 of 2 findings (0 waived)');
    await expect(page.locator('#validation-findings')).toContainText('No findings match the current filters');

    // Click Reset
    await page.click('#findings-clear-filters');
    await expect(page.locator('#findings-counter')).toContainText('Showing 2 of 2 findings (0 waived)');
    await expect(findingsList).toHaveCount(2);

    // Filter by snapshot: production
    await page.selectOption('#findings-snapshot-filter', 'production');
    await expect(page.locator('#findings-counter')).toContainText('Showing 1 of 2 findings (0 waived)');
    await expect(findingsList.first()).toContainText('unused_object');

    // Search filter
    await page.fill('#findings-search', 'Pipe');
    await expect(page.locator('#findings-counter')).toContainText('Showing 0 of 2 findings (0 waived)'); // 'Pipe' is in configuration, not production
    await page.selectOption('#findings-snapshot-filter', '');
    await expect(page.locator('#findings-counter')).toContainText('Showing 1 of 2 findings (0 waived)');
    await expect(findingsList.first()).toContainText('duplicate_object');

    expect(errors).toEqual([]);
  });

  test('selecting a finding focuses related graph objects and displays source XML', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');
    const importControl = page.getByLabel('Import Graph JSON');
    await importControl.setInputFiles(graphFixture);

    const findingCard = page.locator('.finding[data-finding-id="finding-configuration"]');
    await expect(findingCard).toBeVisible();

    // Click on finding card header
    await findingCard.locator('.finding-header').click();
    await expect(findingCard).toHaveClass(/selected/);

    // Verify XML evidence and node summary update for affected node
    await expect(page.locator('#node-summary')).toContainText('Rule');
    await expect(page.locator('#raw-xml')).toContainText('EXCLUDED_RAW_XML');

    // Verify Cytoscape has highlighted/selected node
    const isNodeSelected = await page.evaluate(() => {
      const cy = (window as any).state.cy;
      return cy.nodes(':selected').length > 0;
    });
    expect(isNodeSelected).toBe(true);

    expect(errors).toEqual([]);
  });

  test('creates, edits, persists, and revokes a local waiver', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');
    const importControl = page.getByLabel('Import Graph JSON');
    await importControl.setInputFiles(graphFixture);

    const findingCard = page.locator('.finding[data-finding-id="finding-configuration"]');
    await expect(findingCard).toBeVisible();

    // Click Waive Finding
    await findingCard.locator('.waive-finding-btn').click();
    const form = findingCard.locator('.waiver-form');
    await expect(form).toBeVisible();

    // Attempt to save without required fields
    await form.locator('.save-waiver-btn').click();
    await expect(form.locator('.waiver-form-error')).toContainText('Reviewer and reason are required');

    // Fill valid waiver info
    await form.locator('.waiver-input-reviewer').fill('qa-reviewer@sap.com');
    await form.locator('.waiver-input-reason').fill('Legacy duplicate acknowledged during migration');
    await form.locator('.waiver-input-expiry').fill('2099-12-31');
    await form.locator('.save-waiver-btn').click();

    // Verify waived state
    await expect(findingCard).toHaveClass(/waived/);
    await expect(findingCard.locator('.badge-waived')).toContainText('[WAIVED]');
    await expect(findingCard.locator('.waiver-box')).toContainText('qa-reviewer@sap.com');
    await expect(findingCard.locator('.waiver-box')).toContainText('Legacy duplicate acknowledged');
    await expect(page.locator('#findings-counter')).toContainText('Showing 2 of 2 findings (1 waived)');

    // Test waiver filter: waived
    await page.selectOption('#findings-waiver-filter', 'waived');
    await expect(page.locator('#validation-findings .finding')).toHaveCount(1);
    await expect(page.locator('#validation-findings .finding').first()).toHaveAttribute('data-finding-id', 'finding-configuration');

    // Test waiver filter: unwaived
    await page.selectOption('#findings-waiver-filter', 'unwaived');
    await expect(page.locator('#validation-findings .finding')).toHaveCount(1);
    await expect(page.locator('#validation-findings .finding').first()).toHaveAttribute('data-finding-id', 'finding-production');

    // Reset waiver filter
    await page.selectOption('#findings-waiver-filter', 'all');

    // Edit waiver
    await findingCard.locator('.edit-waiver-btn').click();
    const editForm = findingCard.locator('.waiver-form');
    await expect(editForm.locator('.waiver-input-reviewer')).toHaveValue('qa-reviewer@sap.com');
    await editForm.locator('.waiver-input-reason').fill('Updated migration rationale');
    await editForm.locator('.save-waiver-btn').click();
    await expect(findingCard.locator('.waiver-box')).toContainText('Updated migration rationale');

    // Reload page and re-import to verify localStorage persistence
    await page.reload();
    const reimportControl = page.getByLabel('Import Graph JSON');
    await reimportControl.setInputFiles(graphFixture);

    const reloadedFindingCard = page.locator('.finding[data-finding-id="finding-configuration"]');
    await expect(reloadedFindingCard).toHaveClass(/waived/);
    await expect(reloadedFindingCard.locator('.badge-waived')).toContainText('[WAIVED]');
    await expect(reloadedFindingCard.locator('.waiver-box')).toContainText('Updated migration rationale');

    // Revoke waiver
    await reloadedFindingCard.locator('.revoke-waiver-btn').click();
    await expect(reloadedFindingCard).not.toHaveClass(/waived/);
    await expect(reloadedFindingCard.locator('.waive-finding-btn')).toBeVisible();
    await expect(page.locator('#findings-counter')).toContainText('Showing 2 of 2 findings (0 waived)');

    expect(errors).toEqual([]);
  });

  test('safely handles expired waivers and corrupted localStorage data', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    // Pre-populate an expired waiver and verify it marks finding as expired waiver
    await page.goto('/');
    await page.evaluate(() => {
      const expiredWaivers = {
        'finding-configuration': {
          findingId: 'finding-configuration',
          reviewer: 'historical-auditor',
          reason: 'Old temporary waiver',
          createdAt: '2020-01-01T00:00:00Z',
          expiresAt: '2021-01-01',
        },
      };
      localStorage.setItem('sap-im-config-explorer-waivers', JSON.stringify(expiredWaivers));
    });

    const importControl = page.getByLabel('Import Graph JSON');
    await importControl.setInputFiles(graphFixture);

    const findingCard = page.locator('.finding[data-finding-id="finding-configuration"]');
    await expect(findingCard).toHaveClass(/waiver-expired/);
    await expect(findingCard.locator('.badge-waiver-expired')).toContainText('[EXPIRED WAIVER]');
    await expect(findingCard.locator('.waiver-box')).toContainText('EXPIRED');

    // Corrupt localStorage to test fail-safe recovery
    await page.evaluate(() => {
      localStorage.setItem('sap-im-config-explorer-waivers', '{malformed_json_###');
    });
    await page.reload();
    const importControl2 = page.getByLabel('Import Graph JSON');
    await importControl2.setInputFiles(graphFixture);

    // Application should not crash, findings should load cleanly as unwaived
    await expect(page.locator('#findings-counter')).toContainText('Showing 2 of 2 findings (0 waived)');
    await expect(page.locator('#validation-findings .finding')).toHaveCount(2);

    expect(errors).toEqual([]);
  });
});
