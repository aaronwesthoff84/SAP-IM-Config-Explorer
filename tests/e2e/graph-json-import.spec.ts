import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const graphFixture = path.resolve('tests/fixtures/portable_export_graph.json');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test('imports a local Graph JSON document into the complete workspace', async ({ page }) => {
  const errors: string[] = [];
  collectBrowserErrors(page, errors);

  await page.goto('/');
  const importControl = page.getByLabel('Import Graph JSON');
  await expect(importControl).toHaveAttribute('accept', '.json,application/json');
  await importControl.setInputFiles(graphFixture);

  await expect(page.locator('#status')).toContainText(
    'Imported portable_export_graph.json. Core topology:'
  );
  await expect(page.locator('#workspace-origin')).toHaveText(
    'Imported JSON: portable_export_graph.json'
  );
  await expect(page.locator('#workspace-origin')).toHaveAttribute('data-origin', 'imported');
  await expect(page.locator('#graph canvas').first()).toBeVisible();
  await expect(page.locator('#type-filter option')).toHaveCount(4);
  await expect(page.locator('#validation-findings')).toContainText('duplicate_object');
  await expect(page.locator('#migration-risk-container')).toBeVisible();

  const graphEvidence = await page.evaluate(() => {
    const state = (window as any).state;
    return {
      provenance: state.graph.provenance,
      nodeIds: state.graph.nodes.map((node: any) => node.id),
      linkIds: state.graph.links.map((link: any) => link.id),
      findingIds: state.graph.findings.map((finding: any) => finding.id),
    };
  });
  expect(graphEvidence.provenance).toEqual({
    origin: 'imported',
    fileName: 'portable_export_graph.json',
  });
  expect(graphEvidence.nodeIds).toHaveLength(6);
  expect(graphEvidence.linkIds).toHaveLength(4);
  expect(graphEvidence.findingIds).toHaveLength(2);

  await page.evaluate(() => {
    (window as any).state.cy.getElementById('plan-configuration').emit('tap');
  });
  await expect(page.locator('#node-summary')).toContainText('North | Plan');
  await expect(page.locator('#raw-xml')).toContainText('EXCLUDED_RAW_XML');
  expect(errors).toEqual([]);
});

