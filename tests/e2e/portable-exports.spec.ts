import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test('downloads the complete current graph as CSV, Markdown, and GraphML', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(fixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).toContainText('Core topology:');

  for (const [button, filename, label] of [
    ['#export-csv-button', 'sap-im-config-graph-csv.zip', 'CSV'],
    ['#export-markdown-button', 'sap-im-config-graph.md', 'Markdown'],
    ['#export-graphml-button', 'sap-im-config-graph.graphml', 'GraphML'],
  ]) {
    const downloadPromise = page.waitForEvent('download');
    await page.locator(button).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(filename);
    await expect(page.locator('#status')).toContainText(`graph ${label}`);
  }

  expect(errors).toEqual([]);
});

test('reports backend details and caught network failures without unhandled errors', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(fixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).toContainText('Core topology:');

  await page.route('**/api/export/graph-csv', route => route.fulfill({
    status: 422,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'Portable contract rejected test payload.' }),
  }));
  await page.locator('#export-csv-button').click();
  await expect(page.locator('#status')).toHaveText(
    'CSV export failed: Portable contract rejected test payload.'
  );
  await page.unroute('**/api/export/graph-csv');

  await page.route('**/api/export/graph-csv', route => route.abort('connectionfailed'));
  await page.locator('#export-csv-button').click();
  await expect(page.locator('#status')).toContainText('CSV export failed:');
  await expect(page.locator('#status')).not.toHaveText('CSV export failed:');
  expect(pageErrors).toEqual([]);
});
