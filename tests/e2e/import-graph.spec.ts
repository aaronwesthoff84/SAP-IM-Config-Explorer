import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

const xmlFixture = path.resolve('tests/fixtures/minimal_plan.xml');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test('exports a graph and successfully imports it back with visual indicator', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // 1. Generate graph from XML
  await page.locator('#np-xml-files').setInputFiles(xmlFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).toContainText('Core topology:');

  // 2. Export to JSON
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export-button').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('sap-im-config-graph.json');

  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();

  const graphJsonContent = fs.readFileSync(downloadPath!, 'utf8');
  const graphJson = JSON.parse(graphJsonContent);
  expect(graphJson.schemaVersion).toBe('1.2');

  // Copy downloaded file to a path ending in .json so the upload name validator accepts it
  const tempJsonPath = path.resolve('tests/fixtures/temp_e2e_import.json');
  fs.copyFileSync(downloadPath!, tempJsonPath);

  try {
    // 3. Reload page to clear current in-memory state
    await page.reload();
    await expect(page.locator('#status')).toHaveText('Ready');
    await expect(page.locator('#graph canvas').first()).not.toBeVisible();

    // 4. Import the JSON back
    await page.locator('#import-graph-json').setInputFiles(tempJsonPath);

    // 5. Verify the imported status, the visual distinguishing class, and the canvas visibility
    await expect(page.locator('#status')).toContainText('[Imported] Core topology:');
    await expect(page.locator('#status')).toHaveClass(/imported/);
    await expect(page.locator('#graph canvas').first()).toBeVisible();

    // 6. Verify that interactively clicking elements still displays details
    const detailsPanel = page.locator('#node-summary');
    await expect(detailsPanel).toContainText('Select a graph item');

    // Let's trigger a tap/click on a node inside cytoscape
    const nodeLabel = await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().first();
      node.select();
      node.emit('tap', { target: node });
      return node.data('label');
    });

    await expect(detailsPanel).toContainText(nodeLabel);
  } finally {
    if (fs.existsSync(tempJsonPath)) {
      fs.unlinkSync(tempJsonPath);
    }
  }

  // 7. Verify no browser errors occurred
  expect(errors).toEqual([]);
});

test('shows elegant error message when importing malformed JSON', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');

  // Create temporary malformed JSON file
  const malformedPath = path.resolve('tests/fixtures/malformed_imported_graph.json');
  fs.writeFileSync(malformedPath, '{"invalid_json": ', 'utf8');

  try {
    await page.locator('#import-graph-json').setInputFiles(malformedPath);
    await expect(page.locator('#status')).toContainText('Malformed or dangerous payload');
  } finally {
    fs.unlinkSync(malformedPath);
  }
});
