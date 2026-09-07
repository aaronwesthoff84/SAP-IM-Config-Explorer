import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

test.describe('AI-Generated Documentation E2E Tests', () => {

  test('displays setup instructions when AI features are disabled', async ({ page }) => {
    await page.route('**/api/ai/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: false,
          provider: '',
          model: 'gpt-3.5-turbo',
          privacy_disclaimer: 'AI is disabled.'
        })
      });
    });

    await page.goto('/');

    await page.locator('#ai-doc-tab').click();

    await expect(page.locator('#ai-doc-setup-info')).toBeVisible();
    await expect(page.locator('#ai-doc-interactive')).toBeHidden();
    await expect(page.locator('#ai-doc-setup-info')).toContainText('AI Features Disabled');
    await expect(page.locator('#ai-doc-setup-info')).toContainText('Local-First');
  });

  test('displays interactive generator UI when AI features are enabled', async ({ page }) => {
    await page.route('**/api/ai/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: true,
          provider: 'stub',
          model: 'e2e-stub-model',
          privacy_disclaimer: 'Draft disclaimer.'
        })
      });
    });

    await page.goto('/');
    await page.locator('#ai-doc-tab').click();

    await expect(page.locator('#ai-doc-interactive')).toBeVisible();
    await expect(page.locator('#ai-doc-setup-info')).toBeHidden();
    await expect(page.locator('#ai-configured-endpoint-display')).toContainText('e2e-stub-model');
  });

  test('requires selecting a file before generating', async ({ page }) => {
    await page.route('**/api/ai/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true, provider: 'stub', model: 'e2e-stub-model' })
      });
    });

    await page.goto('/');
    await page.locator('#ai-doc-tab').click();

    await page.locator('#generate-ai-doc-button').click();
    await expect(page.locator('#ai-doc-status')).toContainText('Please select an XML file');
  });

  test('cancels generation if user rejects the confirmation dialog', async ({ page }) => {
    await page.route('**/api/ai/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true, provider: 'stub', model: 'e2e-stub-model' })
      });
    });

    await page.goto('/');

    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.locator('#ai-doc-tab').click();

    page.on('dialog', async (dialog) => {
      expect(dialog.message()).toContain('send configuration node metadata');
      await dialog.dismiss();
    });

    await page.locator('#generate-ai-doc-button').click();
    await expect(page.locator('#ai-doc-status')).toContainText('canceled by user');
  });

  test('successfully generates and renders AI documentation draft', async ({ page }) => {
    await page.route('**/api/ai/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true, provider: 'stub', model: 'e2e-stub-model' })
      });
    });

    await page.route('**/api/ai/generate-document', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          draft: '# Mocked Config Draft\n\n- Node 1: Alpha Plan\n- Node 2: Alpha Component',
          provider: 'stub',
          model: 'e2e-stub-model',
          timestamp: '2026-07-15T12:00:00Z',
          source_objects: ['plan:alpha-plan'],
          disclaimer: 'Mocked warning.'
        })
      });
    });

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.locator('#ai-doc-tab').click();

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#generate-ai-doc-button').click();

    await expect(page.locator('#ai-doc-status')).toContainText('generated successfully');
    await expect(page.locator('#ai-doc-output-container')).toBeVisible();
    await expect(page.locator('#ai-doc-meta-model')).toHaveText('e2e-stub-model');
    await expect(page.locator('#ai-doc-output-text')).toContainText('# Mocked Config Draft');
    await expect(page.locator('#ai-doc-output-text')).toContainText('Node 1: Alpha Plan');
  });

});
