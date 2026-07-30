import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/disconnected_plans.xml');

test.describe('Dependency impact highlighting', () => {
  test('highlights upstream and downstream nodes when a node is selected and dims unrelated ones', async ({ page }) => {
    await page.goto('/');

    // Upload file
    await page.locator('#np-xml-files').setInputFiles(fixture);

    // Generate Graph
    await page.locator('#graph-button').click();

    // Wait for graph to be rendered
    await page.waitForSelector('#graph canvas');

    // Wait for layout
    await page.waitForTimeout(2000);

    // Select 'Core Component' and verify highlighting
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Core Component')[0];
      node.emit('tap', { target: node });
    });

    // Enterprise Plan, Core Component, and Credit Rule should NOT be dimmed
    const related = ['Enterprise Plan', 'Core Component', 'Credit Rule'];
    for (const label of related) {
        const isDimmed = await page.evaluate((l) => {
            const node = (window as any).state.cy.nodes().filter(n => n.data('label') === l)[0];
            return node.hasClass('dimmed');
        }, label);
        expect(isDimmed).toBe(false);
    }

    // Other Plan and Other Component should be dimmed
    const unrelated = ['Other Plan', 'Other Component'];
    for (const label of unrelated) {
        const [isDimmed, specifiedOpacity] = await page.evaluate((l) => {
            const node = (window as any).state.cy.nodes().filter(n => n.data('label') === l)[0];
            return [node.hasClass('dimmed'), node.style('opacity')];
        }, label);
        expect(isDimmed).toBe(true);
        expect(parseFloat(specifiedOpacity)).toBeLessThan(0.15);
    }

    // Verify edges are also dimmed
    const areEdgesDimmed = await page.evaluate(() => {
        const cy = (window as any).state.cy;
        const dimmedEdges = cy.edges('.dimmed');
        return dimmedEdges.length > 0 && dimmedEdges.every(e => parseFloat(e.style('opacity')) < 0.15);
    });
    expect(areEdgesDimmed).toBe(true);
  });

  test('clears highlighting when clicking background', async ({ page }) => {
    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.locator('#graph-button').click();
    await page.waitForSelector('#graph canvas');
    await page.waitForTimeout(1000);

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
