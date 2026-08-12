import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

test.describe('Visualization and Session Improvements', () => {
  test('toggles between 2D and 3D graph views', async ({ page }) => {
    await page.goto('/');

    // Load graph
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.locator('#graph-button').click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');

    // Check initial 2D view is visible, 3D hidden
    await expect(page.locator('#graph')).toBeVisible();
    await expect(page.locator('#graph-3d')).toBeHidden();

    // Toggle 3D view
    await page.locator('#toggle-3d').click();
    await expect(page.locator('#graph-3d')).toBeVisible();
    await expect(page.locator('#graph')).toBeHidden();

    // Toggle back to 2D view
    await page.locator('#toggle-2d').click();
    await expect(page.locator('#graph')).toBeVisible();
    await expect(page.locator('#graph-3d')).toBeHidden();
  });

  test('exports and imports a saved graph session', async ({ page }) => {
    await page.goto('/');

    // 1. Generate graph
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.locator('#graph-button').click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');

    // 2. Set search filter to trigger state change
    await page.locator('#search').fill('Standard Meas');

    // 3. Export session
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#export-session-button').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe('sap-im-config-graph-session.zip');

    const savedPath = path.resolve('test-results', 'sap-im-config-graph-session.zip');
    await download.saveAs(savedPath);

    // 4. Modify / Clear filters in current session to verify restore
    await page.locator('#search').fill('');
    await expect(page.locator('#search')).toHaveValue('');

    // 5. Import the session ZIP back
    await page.locator('#session-file').setInputFiles(savedPath);
    await expect(page.locator('#status')).toContainText('Session imported successfully');

    // 6. Verify restored filter values
    await expect(page.locator('#search')).toHaveValue('Standard Meas');
  });
});
