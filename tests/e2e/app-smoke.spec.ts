import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

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
  await page.locator('#xml-files').setInputFiles(fixture);

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
