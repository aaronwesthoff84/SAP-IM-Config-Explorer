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

  await page.evaluate(() => {
    const cy = (window as any).state.cy;
    cy.fit(cy.elements(), 48);
  });
  const viewportStateIsFinite = await page.evaluate(() => {
    const cy = (window as any).state.cy;
    return Number.isFinite(cy.zoom())
      && Number.isFinite(cy.pan().x)
      && Number.isFinite(cy.pan().y);
  });
  expect(viewportStateIsFinite).toBe(true);
});

test('supports layout selection, relayout, fit, and reset controls', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  await loadComparisonGraph(page);

  await expect(page.locator('#graph-toolbar')).toBeVisible();
  await expect(page.locator('#layout-select')).toBeVisible();

  // Test layout selection
  await page.locator('#layout-select').selectOption('grid');
  await expect(page.locator('#status')).toContainText('Applied Grid layout');

  await page.locator('#layout-select').selectOption('circle');
  await expect(page.locator('#status')).toContainText('Applied Circular layout');

  // Test relayout button
  await page.locator('#relayout-button').click();
  await expect(page.locator('#status')).toContainText('Applied Circular layout');

  // Test fit button
  await page.locator('#fit-button').click();
  await expect(page.locator('#status')).toContainText('Fitted graph to viewport');

  // Test reset button
  await page.locator('#reset-view-button').click();
  await expect(page.locator('#status')).toContainText('Reset graph layout and view');
  await expect(page.locator('#layout-select')).toHaveValue('cose');
});

test('preserves user-adjusted node positions across filtering', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  await loadComparisonGraph(page);

  // Record initial position and manually move a node
  const movedPos = await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const node = cy.nodes().first();
    node.position({ x: 555, y: 777 });
    (window as any).state.nodePositions[node.id()] = { x: 555, y: 777 };
    return { id: node.id(), x: 555, y: 777 };
  });

  // Apply search filter that still matches the node or its label
  await page.locator('#type-filter').selectOption({ index: 1 });
  await page.locator('#clear-filters').click();

  // Check if position was preserved
  const actualPos = await page.evaluate((nodeId) => {
    const cy = (window as any).state.cy;
    const node = cy.getElementById(nodeId);
    return node.length > 0 ? node.position() : null;
  }, movedPos.id);

  expect(actualPos).not.toBeNull();
  expect(actualPos?.x).toBe(555);
  expect(actualPos?.y).toBe(777);
});

test('supports local-first PNG and SVG image exports', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  await loadComparisonGraph(page);

  // Test PNG download
  const [pngDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('#export-png-button').click(),
  ]);
  expect(pngDownload.suggestedFilename()).toMatch(/^sap-im-config-graph-.*\.png$/);

  // Test SVG download
  const [svgDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('#export-svg-button').click(),
  ]);
  expect(svgDownload.suggestedFilename()).toMatch(/^sap-im-config-graph-.*\.svg$/);
});

