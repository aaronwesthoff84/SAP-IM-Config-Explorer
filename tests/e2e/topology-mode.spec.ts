import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/extractor_families.xml');

test('switches topology without reselecting files and exports the selected graph', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto('/');
  const topology = page.getByRole('combobox', { name: 'Graph topology' });
  await expect(topology).toHaveValue('core');
  await page.locator('#np-xml-files').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();
  await expect(page.locator('#status')).toHaveText(
    'Core topology: 3 nodes, 2 links, no findings'
  );

  await topology.selectOption('full');
  await expect(page.locator('#status')).toHaveText(
    'Full topology: 17 nodes, 16 links, no findings'
  );
  await expect(page.locator('#validation-findings')).toContainText(
    'No validation findings.'
  );
  expect(await page.locator('#np-xml-files').evaluate((input: HTMLInputElement) =>
    [...(input.files ?? [])].map(file => file.name)
  )).toEqual(['extractor_families.xml']);

  const exportRequestPromise = page.waitForRequest('/api/export/graph-json');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const exportRequest = await exportRequestPromise;
  expect(exportRequest.postDataJSON().topologyMode).toBe('full');
  await expect(page.locator('#status')).toHaveText(
    'Exported Full topology graph JSON'
  );
  expect((await page.evaluate(() => (window as any).state.graph.topologyMode))).toBe('full');
  expect(browserErrors).toEqual([]);
});

test('keeps selection, graph status, and export aligned during overlapping regeneration', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto('/');
  const topology = page.getByRole('combobox', { name: 'Graph topology' });
  await page.locator('#np-xml-files').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();
  await expect(page.locator('#status')).toHaveText(
    'Core topology: 3 nodes, 2 links, no findings'
  );

  await page.route('**/api/graph', async route => {
    const body = route.request().postData() ?? '';
    if (/name="topology_mode"[\s\S]*?\r?\n\r?\nfull\r?\n/.test(body)) {
      await new Promise(resolve => setTimeout(resolve, 350));
    }
    await route.continue();
  });

  await topology.selectOption('full');
  await topology.selectOption('core');
  await expect(page.locator('#status')).toHaveText(
    'Core topology: 3 nodes, 2 links, no findings'
  );
  await page.waitForTimeout(500);
  await expect(topology).toHaveValue('core');
  expect(await page.evaluate(() => (window as any).state.graph.topologyMode)).toBe('core');
  await expect(page.locator('#status')).toHaveText(
    'Core topology: 3 nodes, 2 links, no findings'
  );

  await topology.selectOption('full');
  const exportRequestPromise = page.waitForRequest('/api/export/graph-json');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const exportRequest = await exportRequestPromise;
  expect(exportRequest.postDataJSON().topologyMode).toBe('full');
  await expect(page.locator('#status')).toHaveText(
    'Exported Full topology graph JSON'
  );
  expect(await page.evaluate(() => (window as any).state.graph.topologyMode)).toBe('full');
  expect(browserErrors).toEqual([]);
});
