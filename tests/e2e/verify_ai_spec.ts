import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixturePath = path.resolve('tests/fixtures/minimal_plan.xml');

test('capture screenshots of AI summary and AI docs', async ({ page }) => {
  await page.goto('/');
  await expect(page).to_have_title("SAP IM Config Explorer");

  // Upload XML file to generate graph
  console.log("Uploading XML...");
  await page.locator('#np-xml-files').setInputFiles(fixturePath);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...', { timeout: 15000 });

  // Select first node in cytoscape (Rule)
  console.log("Selecting node...");
  await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const node = cy.nodes().first();
    node.select();
    node.emit('tap', { target: node });
  });

  // Click Generate AI Summary
  console.log("Generating AI Summary...");
  await expect(page.locator('#generate-ai-summary-button')).toBeVisible();
  await page.locator('#generate-ai-summary-button').click();

  // Wait for AI Summary to render
  await expect(page.locator('#ai-summary-content h3')).toBeVisible({ timeout: 15000 });

  // Save screenshot of AI Summary in Details pane
  console.log("Saving AI Summary screenshot...");
  await page.screenshot({ path: '/home/jules/verification/ai_summary.png', fullPage: true });

  // Go to AI Docs tab
  console.log("Going to AI Docs tab...");
  await page.locator('#ai-docs-tab').click();
  await expect(page.locator('#generate-ai-docs-button')).toBeVisible();
  await expect(page.locator('#generate-ai-docs-button')).toBeEnabled();

  // Click Generate Documentation
  console.log("Generating AI Documentation...");
  await page.locator('#generate-ai-docs-button').click();
  await expect(page.locator('#ai-docs-text h1')).toBeVisible({ timeout: 15000 });

  // Save screenshot of AI Docs
  console.log("Saving AI Docs screenshot...");
  await page.screenshot({ path: '/home/jules/verification/ai_docs.png', fullPage: true });
  console.log("Screenshots saved!");
});
