import { expect, test } from '@playwright/test';
import path from 'node:path';

const minimalPlanFixture = path.resolve('tests/fixtures/minimal_plan.xml');
const sharedRuleFixture = path.resolve('tests/fixtures/shared_rule_lineage.xml');
const validationFindingsFixture = path.resolve('tests/fixtures/validation_findings.xml');
const duplicateRulesFixture = path.resolve('tests/fixtures/duplicate_rules_components.xml');

function collectBrowserErrors(page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test.describe('Cross-view Navigation', () => {
  test('navigates from a graph node to its HTML section', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(minimalPlanFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    // Verify HTML is generated and active workspace is HTML Output
    await expect(page.locator('#html-output-view')).toBeVisible();

    // Switch back to Graph view to select a node
    await page.locator('.tab[data-view="graph-view"]').click();
    await expect(page.locator('#graph-view')).toBeVisible();

    // Select 'Credit Rule' node
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Credit Rule')[0];
      node.emit('tap', { target: node });
    });

    // Check if the HTML Preview section is populated in Details
    const detailsPanel = page.locator('#node-summary');
    await expect(detailsPanel).toContainText('Credit Rule');
    await expect(detailsPanel).toContainText('View in HTML (under Core Component / Enterprise Plan)');

    // Click the HTML representation button in the Details panel
    await page.locator('.view-html-anchor-btn').click();

    // Verify workspace changed to HTML Output
    await expect(page.locator('#html-output-view')).toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test('navigates from supported HTML sections back to Graph', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(minimalPlanFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    // Click '[View in Graph]' inside HTML Preview
    const frame = page.frameLocator('#html-output-preview');
    await frame.locator('text=[View in Graph]').first().click();

    // Verify workspace changes to Graph and Credit Rule is selected/shown
    await expect(page.locator('#graph-view')).toBeVisible();
    await expect(page.locator('#node-summary')).toContainText('Credit Rule');
    expect(browserErrors).toEqual([]);
  });

  test('navigates from HTML index entries back to Graph', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(minimalPlanFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    // Find the summary table index in HTML Preview and click [Graph] for a formula
    const frame = page.frameLocator('#html-output-preview');
    // For minimal_plan.xml, let's click on the rule index entry
    await frame.locator('span[data-object-type="Rule"] >> text=[Graph]').click();

    // Verify workspace changes to Graph and Credit Rule is selected/shown
    await expect(page.locator('#graph-view')).toBeVisible();
    await expect(page.locator('#node-summary')).toContainText('Credit Rule');
    expect(browserErrors).toEqual([]);
  });

  test('handles multi-container rule representations without ambiguity', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(sharedRuleFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    // Switch back to Graph view to select the rule
    await page.locator('.tab[data-view="graph-view"]').click();

    // Select 'Shared Rule' node
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Shared Rule')[0];
      node.emit('tap', { target: node });
    });

    const detailsPanel = page.locator('#node-summary');
    await expect(detailsPanel).toContainText('Shared Rule');

    // Verify two HTML navigation buttons are rendered for each of its containers
    const buttons = page.locator('.view-html-anchor-btn');
    await expect(buttons).toHaveCount(2);
    await expect(buttons.first()).toHaveText('View in HTML (under Alpha Component / Alpha Plan)');
    await expect(buttons.last()).toHaveText('View in HTML (under Beta Component / Zulu Plan)');

    // Click the first button
    await buttons.first().click();
    await expect(page.locator('#html-output-view')).toBeVisible();

    expect(browserErrors).toEqual([]);
  });

  test('displays clear unavailable/missing representation state', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(minimalPlanFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');

    // 1. Select node without generating HTML
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Credit Rule')[0];
      node.emit('tap', { target: node });
    });

    const detailsPanel = page.locator('#node-summary');
    await expect(detailsPanel).toContainText('Unavailable (HTML not generated)');

    // 2. Generate HTML, then select a node from a mismatching file/scenario (e.g. if we mock it)
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    // Select node in Graph
    await page.locator('.tab[data-view="graph-view"]').click();
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().filter(n => n.data('label') === 'Credit Rule')[0];
      node.emit('tap', { target: node });
    });

    // It should be available now
    await expect(detailsPanel).not.toContainText('Unavailable (HTML not generated)');
    await expect(detailsPanel).toContainText('View in HTML (under Core Component / Enterprise Plan)');

    expect(browserErrors).toEqual([]);
  });

  test('navigates from findings to Graph, HTML and XML evidence', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(validationFindingsFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();

    // Findings are displayed
    const findingsList = page.locator('#validation-findings');
    await expect(findingsList).toContainText('Unattached Rule');

    // Locate the finding for Unattached Rule specifically and get its buttons
    const unattachedFinding = findingsList.locator('li.finding').filter({ hasText: 'Unattached Rule' });
    const goToNodeBtn = unattachedFinding.locator('.finding-action-btn.go-to-node').first();
    const viewXmlBtn = unattachedFinding.locator('.finding-action-btn.view-xml').first();
    const viewHtmlBtn = unattachedFinding.locator('.finding-action-btn.view-html').first();

    await expect(goToNodeBtn).toBeVisible();
    await expect(viewXmlBtn).toBeVisible();
    await expect(viewHtmlBtn).toBeVisible();

    // Clicking Go to Node
    await goToNodeBtn.click();
    await expect(page.locator('#graph-view')).toBeVisible();
    await expect(page.locator('#node-summary')).toContainText('Unattached Rule');

    // Clicking View XML (preserves workspace)
    await viewXmlBtn.click();
    await expect(page.locator('#graph-view')).toBeVisible(); // workspace preserved
    await expect(page.locator('#raw-xml')).toContainText('<RULE NAME="Unattached Rule"');

    // Click View HTML
    await viewHtmlBtn.click();
    // Since HTML is not generated, it should set appropriate status message
    await expect(page.locator('#status')).toContainText('HTML representation unavailable');

    expect(browserErrors).toEqual([]);
  });

  test('navigates from duplicate object findings to each distinct HTML instance', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');
    await page.locator('#np-xml-files').setInputFiles(duplicateRulesFixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await page.getByRole('button', { name: 'Generate HTML' }).click();

    await expect(page.locator('#html-output-view')).toBeVisible();

    // Verify findings list has duplicate findings
    const findingsList = page.locator('#validation-findings');
    const dupFindings = findingsList.locator('li.finding').filter({ hasText: 'Shared Component' });
    await expect(dupFindings.first()).toBeVisible();

    // The findings have view-html buttons pointing to different nodeIds
    const viewHtmlBtns = dupFindings.locator('.finding-action-btn.view-html');
    const count = await viewHtmlBtns.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // Click the first duplicate finding's View HTML button
    await viewHtmlBtns.first().click();
    await expect(page.locator('#html-output-view')).toBeVisible();
    await expect(page.locator('#status')).toContainText('Navigated to HTML section');

    // Click the second duplicate finding's View HTML button
    await viewHtmlBtns.nth(1).click();
    await expect(page.locator('#html-output-view')).toBeVisible();
    await expect(page.locator('#status')).toContainText('Navigated to HTML section');

    // Verify preview frame contains the duplicate metadata and badges
    const preview = page.frameLocator('#html-output-preview');
    await expect(preview.locator('text=Duplicate instance (1 of 2)').first()).toBeVisible();
    await expect(preview.locator('text=Duplicate instance (2 of 2)').first()).toBeVisible();

    expect(browserErrors).toEqual([]);
  });
});
