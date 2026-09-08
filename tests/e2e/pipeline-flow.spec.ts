import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

const knownOrderFixture = path.resolve('tests/fixtures/pipeline_known_order.xml');
const unknownOrderFixture = path.resolve('tests/fixtures/pipeline_unknown_order.xml');

function collectBrowserErrors(page: Page, errors: string[]) {
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('Failed to load resource')) {
      errors.push(message.text());
    }
  });
}

test.describe('Pipeline execution flow view', () => {
  test('pipeline tab is disabled initially and enabled after graph generation', async ({ page }) => {
    await page.goto('/');

    const pipelineTab = page.locator('#pipeline-tab');
    await expect(pipelineTab).toBeDisabled();

    // Upload XML and generate graph
    const fileInput = page.locator('#np-xml-files');
    await fileInput.setInputFiles(knownOrderFixture);
    await page.click('#graph-button');

    // Wait for graph status to be populated
    await expect(page.locator('#status')).toContainText('topology:');

    // Tab should now be enabled
    await expect(pipelineTab).toBeEnabled();
  });

  test('renders known-order pipeline flow with stages and evidence', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');

    // Upload known order fixture
    const fileInput = page.locator('#np-xml-files');
    await fileInput.setInputFiles(knownOrderFixture);
    await page.click('#graph-button');
    await expect(page.locator('#status')).toContainText('topology:');

    // Switch to Pipeline Flow view
    await page.click('#pipeline-tab');
    const pipelineView = page.locator('#pipeline-view');
    await expect(pipelineView).toHaveClass(/active/);

    // Summary banner should report steps and transitions
    const summaryText = page.locator('#pipeline-summary-text');
    await expect(summaryText).toContainText('Pipeline execution flow');
    await expect(summaryText).toContainText('steps');

    // Known order badge should be visible
    const knownBadge = page.locator('#pipeline-summary-metrics .pipeline-badge.known');
    await expect(knownBadge).toBeVisible();
    await expect(knownBadge).toContainText('Known Order');

    // Pipeline graph container should have cytoscape canvas elements
    const pipelineGraph = page.locator('#pipeline-graph');
    await expect(pipelineGraph).toBeVisible();

    // Verify browser state has pipelineCytoscape elements
    const cyData = await page.evaluate(() => {
      const cy = (window as any).state.pipelineCy;
      if (!cy) return null;
      return {
        nodeCount: cy.nodes().length,
        edgeCount: cy.edges().length,
        nodeLabels: cy.nodes().map((n: any) => n.data('label')),
      };
    });

    expect(cyData).not.toBeNull();
    expect(cyData!.nodeCount).toBeGreaterThan(0);
    expect(cyData!.edgeCount).toBeGreaterThan(0);

    // Trigger step evidence panel
    await page.evaluate(() => {
      const cy = (window as any).state.pipelineCy;
      const firstNode = cy.nodes().first();
      firstNode.emit('tap');
    });

    const evidencePanel = page.locator('#pipeline-evidence-panel');
    await expect(evidencePanel).toBeVisible();
    await expect(page.locator('#pipeline-evidence-title')).toContainText('Pipeline Step');
    await expect(page.locator('#pipeline-evidence-body')).toContainText('Classification Evidence');

    // Trigger transition evidence panel
    await page.evaluate(() => {
      const cy = (window as any).state.pipelineCy;
      const firstEdge = cy.edges().first();
      firstEdge.emit('tap');
    });

    await expect(page.locator('#pipeline-evidence-title')).toContainText('Pipeline Transition Evidence');
    await expect(page.locator('#pipeline-evidence-body')).toContainText('Order Determination Evidence');

    // Close button hides evidence panel
    await page.click('#pipeline-evidence-close');
    await expect(evidencePanel).toBeHidden();

    expect(errors).toHaveLength(0);
  });

  test('flags and filters unknown execution order correctly', async ({ page }) => {
    const errors: string[] = [];
    collectBrowserErrors(page, errors);

    await page.goto('/');

    // Upload unknown order fixture
    const fileInput = page.locator('#np-xml-files');
    await fileInput.setInputFiles(unknownOrderFixture);
    await page.click('#graph-button');
    await expect(page.locator('#status')).toContainText('topology:');

    // Switch to Pipeline Flow view
    await page.click('#pipeline-tab');

    // Unknown order badge should be visible
    const unknownBadge = page.locator('#pipeline-summary-metrics .pipeline-badge.unknown');
    await expect(unknownBadge).toBeVisible();
    await expect(unknownBadge).toContainText('Unknown Execution Order');

    // Filter by unknown order only
    await page.selectOption('#pipeline-order-filter', 'unknown');

    const filteredCyData = await page.evaluate(() => {
      const cy = (window as any).state.pipelineCy;
      if (!cy) return null;
      return {
        hasNodes: cy.nodes().length > 0,
        allUnknownOrConnected: cy.edges().every((e: any) => e.data('orderStatus') === 'unknown'),
      };
    });

    expect(filteredCyData).not.toBeNull();
    expect(filteredCyData!.hasNodes).toBe(true);
    expect(filteredCyData!.allUnknownOrConnected).toBe(true);

    // Plan selector filter
    const planFilter = page.locator('#pipeline-plan-filter');
    const options = await planFilter.locator('option').allTextContents();
    expect(options.some((opt) => opt.includes('Ambiguous Execution Plan'))).toBe(true);

    expect(errors).toHaveLength(0);
  });
});
