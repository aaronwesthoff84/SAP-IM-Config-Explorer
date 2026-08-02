import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');
const genericAttributeFixture = path.resolve('tests/fixtures/generic_attribute_actions.xml');
const namespaceFixture = path.resolve('tests/fixtures/compatibility/namespace_profile.xml');

function collectBrowserErrors(page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test('loads the local-first application without browser errors', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await expect(page).toHaveTitle('SAP IM Config Explorer');
  await expect(page.getByRole('heading', { name: 'SAP IM Config Explorer' })).toBeVisible();
  await expect(page.locator('#status')).toHaveText('Ready');
  expect(errors).toEqual([]);
});

test('uploads XML and generates graph and HTML output', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(fixture);

  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...');
  await expect.poll(async () => page.locator('#type-filter option').count()).toBeGreaterThan(1);
  await expect(page.locator('#graph canvas').first()).toBeVisible();

  await page.locator('#html-button').click();
  await expect(page.locator('#status')).toContainText('Generated');
  await expect(page.locator('#html-output-view')).toHaveClass(/active/);
  await expect(page.locator('#html-output-download')).toBeVisible();
  await expect(page.locator('#html-output-preview')).toHaveAttribute('srcdoc', /SAP|Plan|html/i);

  expect(errors).toEqual([]);
});

test('loads a namespace-qualified profile without widening the graph allowlist', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(namespaceFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).toHaveText('Core topology: 3 nodes, 2 links, no findings');
  await expect(page.locator('#graph canvas').first()).toBeVisible();

  const graphEvidence = await page.evaluate(() => ({
    schemaVersion: (window as any).state.graph.schemaVersion,
    sourceProfiles: (window as any).state.graph.snapshots[0].sourceProfiles,
    nodeTypes: (window as any).state.graph.nodes.map((node: any) => node.type).sort(),
    nodeLabels: (window as any).state.graph.nodes.map((node: any) => node.label).sort(),
  }));

  expect(graphEvidence).toEqual({
    schemaVersion: '1.2',
    sourceProfiles: [{
      sourceFile: 'namespace_profile.xml',
      encoding: 'utf-8',
      namespaceUri: 'urn:sap:incentive-management:configuration:16.0',
      exportVersion: '16.0',
    }],
    nodeTypes: ['Plan', 'PlanComponent', 'Rule'],
    nodeLabels: ['Compatibility Component', 'Compatibility Plan', 'Compatibility Rule'],
  });
  expect(graphEvidence.nodeLabels).not.toContain('Must remain unknown');
  expect(errors).toEqual([]);
});

test('numbers generic attributes in the HTML preview by source position', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(genericAttributeFixture);
  await page.locator('#html-button').click();
  await expect(page.locator('#status')).toContainText('Generated');

  const preview = page.frameLocator('#html-output-preview');
  const genericLabels = preview.locator('td.FunctionParameterLineNumber', {
    hasText: /^Generic Attribute \d+$/,
  });
  await expect(genericLabels).toHaveText([
    'Generic Attribute 1',
    'Generic Attribute 2',
    'Generic Attribute 3',
    'Generic Attribute 5',
    'Generic Attribute 1',
  ]);
  await expect(preview.getByText('VetSuite Select', { exact: true })).toBeVisible();
  await expect(preview.getByText('Second Action Attribute', { exact: true })).toBeVisible();
  await expect(preview.locator('body')).not.toContainText('NULL');

  expect(errors).toEqual([]);
});

test('persists theme choice', async ({ page }) => {
  await page.goto('/');
  const toggle = page.locator('#theme-toggle');
  const initial = await toggle.getAttribute('aria-pressed');
  await toggle.click();
  await expect(toggle).not.toHaveAttribute('aria-pressed', initial ?? 'false');
  const changed = await toggle.getAttribute('aria-pressed');
  await page.reload();
  await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', changed ?? 'true');
});
