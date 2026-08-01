import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const nonProductionFixture = path.resolve('tests/fixtures/risk_high.xml');
const productionFixture = path.resolve('tests/fixtures/risk_low.xml');

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

async function loadComparisonGraph(page: Page) {
  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(nonProductionFixture);
  await page.locator('#p-xml-files').setInputFiles(productionFixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...');
  await expect(page.locator('#graph canvas').first()).toBeVisible();
}

for (const viewport of viewports) {
  test(`keeps graph labels separate without Cytoscape warnings on ${viewport.name}`, async ({ page }) => {
    const browserProblems: string[] = [];
    page.on('pageerror', error => browserProblems.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error' || message.type() === 'warning') {
        browserProblems.push(message.text());
      }
    });

    await page.setViewportSize(viewport);
    await loadComparisonGraph(page);

    const collisions = await page.evaluate(async () => {
      const cy = (window as any).state.cy;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const labels = cy.nodes().map(node => ({
        id: node.id(),
        label: node.data('label'),
        box: node.renderedBoundingBox({
          includeNodes: false,
          includeEdges: false,
          includeLabels: true,
          includeOverlays: false,
          includeUnderlays: false,
        }),
      }));
      const overlaps: string[] = [];
      for (let left = 0; left < labels.length; left += 1) {
        for (let right = left + 1; right < labels.length; right += 1) {
          const a = labels[left];
          const b = labels[right];
          const overlapWidth = Math.min(a.box.x2, b.box.x2) - Math.max(a.box.x1, b.box.x1);
          const overlapHeight = Math.min(a.box.y2, b.box.y2) - Math.max(a.box.y1, b.box.y1);
          if (overlapWidth > 1 && overlapHeight > 1) {
            overlaps.push(`${a.label} (${a.id}) / ${b.label} (${b.id})`);
          }
        }
      }
      return overlaps;
    });

    expect(collisions).toEqual([]);
    expect(browserProblems).toEqual([]);
  });
}

test('preserves graph viewport controls and item selection', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  await loadComparisonGraph(page);

  const interaction = await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const originalPan = { ...cy.pan() };
    const originalZoom = cy.zoom();
    cy.panBy({ x: 20, y: 12 });
    const panned = cy.pan();
    cy.zoom(originalZoom * 1.1);

    const node = cy.nodes().first();
    node.select();
    node.emit('tap', { target: node });

    return {
      controlsEnabled:
        cy.panningEnabled()
        && cy.userPanningEnabled()
        && cy.zoomingEnabled()
        && cy.userZoomingEnabled(),
      nodeLabel: node.data('label'),
      nodeSelected: node.selected(),
      panChanged: panned.x !== originalPan.x || panned.y !== originalPan.y,
      zoomChanged: cy.zoom() !== originalZoom,
    };
  });

  expect(interaction.controlsEnabled).toBe(true);
  expect(interaction.panChanged).toBe(true);
  expect(interaction.zoomChanged).toBe(true);
  expect(interaction.nodeSelected).toBe(true);
  await expect(page.locator('#node-summary')).toContainText(interaction.nodeLabel);

  const edgeSelected = await page.evaluate(() => {
    const edge = (window as any).state.cy.edges().first();
    edge.select();
    edge.emit('tap', { target: edge });
    return edge.selected();
  });
  expect(edgeSelected).toBe(true);
  await expect(page.locator('#node-summary')).toContainText('Relationship');

  await page.evaluate(() => (window as any).state.cy.fit(undefined, 48));
  const viewportStateIsFinite = await page.evaluate(() => {
    const cy = (window as any).state.cy;
    return Number.isFinite(cy.zoom())
      && Number.isFinite(cy.pan().x)
      && Number.isFinite(cy.pan().y);
  });
  expect(viewportStateIsFinite).toBe(true);
});
