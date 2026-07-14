import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

test.describe('Dependency impact highlighting', () => {
  test('highlights upstream and downstream nodes when a node is selected', async ({ page }) => {
    await page.goto('/');

    // Upload file
    await page.locator('#xml-files').setInputFiles(fixture);

    // Generate Graph
    await page.locator('#graph-button').click();

    // Wait for graph to be rendered
    await page.waitForSelector('#graph canvas');

    // Select 'Core Component' and verify highlighting
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Core Component')[0];
      node.emit('tap', { target: node });
    });

    // Check if Enterprise Plan is NOT dimmed (it is a predecessor/parent)
    const isEnterprisePlanDimmed = await page.evaluate(() => {
        const cy = (window as any).state.cy;
        const node = cy.nodes().filter(n => n.data('label') === 'Enterprise Plan')[0];
        return node.hasClass('dimmed');
    });
    expect(isEnterprisePlanDimmed).toBe(false);

    // Check if Credit Rule is NOT dimmed (it is a successor/child)
    const isCreditRuleDimmed = await page.evaluate(() => {
        const cy = (window as any).state.cy;
        const node = cy.nodes().filter(n => n.data('label') === 'Credit Rule')[0];
        return node.hasClass('dimmed');
    });
    expect(isCreditRuleDimmed).toBe(false);
  });

  test('clears highlighting when clicking background', async ({ page }) => {
    await page.goto('/');
    await page.locator('#xml-files').setInputFiles(fixture);
    await page.locator('#graph-button').click();
    await page.waitForSelector('#graph canvas');

    // Select 'Core Component'
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Core Component')[0];
      node.emit('tap', { target: node });
    });

    // Clear by emitting tap on background
    await page.evaluate(() => {
        const cy = (window as any).state.cy;
        cy.emit('tap', { target: cy });
    });

    const areNodesDimmed = await page.evaluate(() => {
        const cy = (window as any).state.cy;
        return cy.elements('.dimmed').length > 0;
    });
    expect(areNodesDimmed).toBe(false);
  });
});
