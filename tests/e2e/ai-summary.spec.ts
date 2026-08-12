import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/disconnected_plans.xml');

test.describe('AI Summary generation', () => {
  test('generates and displays summaries for selected objects using stub provider', async ({ page }) => {
    await page.goto('/');

    // AI Summary container should be hidden initially
    const container = page.locator('#ai-summary-container');
    await expect(container).not.toBeVisible();

    // Upload file
    await page.locator('#np-xml-files').setInputFiles(fixture);

    // Generate Graph
    await page.locator('#graph-button').click();

    // Wait for graph to be rendered
    await page.waitForSelector('#graph canvas');
    await page.waitForTimeout(1000);

    // Select 'Core Component' node
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Core Component')[0];
      node.emit('tap', { target: node });
    });

    // AI Summary container should now be visible
    await expect(container).toBeVisible();

    // Verify AI Summary status is ready
    const status = page.locator('#ai-summary-status');
    await expect(status).toContainText('Ready to generate summary via local stub provider');

    // Click Generate Summary button
    const generateButton = page.locator('#generate-summary-button');
    await generateButton.click();

    // Verify loading state and then successful completion
    await expect(status).toContainText('Summary generated successfully');

    // Verify summary label and content
    const label = page.locator('#ai-summary-label');
    const content = page.locator('#ai-summary-content');
    await expect(label).toBeVisible();
    await expect(label).toContainText('AI-Generated Summary (Stub Provider)');
    await expect(content).toBeVisible();
    await expect(content).toContainText("Summary for PlanComponent 'Core Component'");
    await expect(content).toContainText("disconnected_plans.xml");

    // Take screenshot for verification
    await page.screenshot({ path: '/home/jules/verification/screenshots/verification.png' });

    // Click background to deselect node
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      cy.emit('tap', { target: cy });
    });

    // AI Summary container should be hidden again
    await expect(container).not.toBeVisible();
  });
});
