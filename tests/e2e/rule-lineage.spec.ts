import { expect, test } from '@playwright/test';
import path from 'node:path';

const minimalPlanFixture = path.resolve('tests/fixtures/minimal_plan.xml');
const sharedRuleFixture = path.resolve('tests/fixtures/shared_rule_lineage.xml');
const uncontainedRuleFixture = path.resolve('tests/fixtures/uncontained_rule_lineage.xml');

function collectBrowserErrors(page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

test('selects a shared Rule lineage by exact snapshot identity in stable canonical order', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(() => {
    const graph = {
      nodes: [
        { id: 'plan-zulu-np', canonicalKey: 'plan:zulu', snapshotId: 'np', label: 'Zulu Plan', type: 'Plan' },
        { id: 'formula-np', canonicalKey: 'formula:eligibility', snapshotId: 'np', label: 'Eligibility', type: 'Formula' },
        { id: 'component-beta-np', canonicalKey: 'plan_component:beta', snapshotId: 'np', label: 'Beta Component', type: 'PlanComponent' },
        { id: 'rule-shared-production', canonicalKey: 'rule:shared', snapshotId: 'production', label: 'Shared Rule', type: 'Rule' },
        { id: 'plan-alpha-np', canonicalKey: 'plan:alpha', snapshotId: 'np', label: 'Alpha Plan', type: 'Plan' },
        { id: 'component-alpha-np', canonicalKey: 'plan_component:alpha', snapshotId: 'np', label: 'Alpha Component', type: 'PlanComponent' },
        { id: 'rule-shared-np', canonicalKey: 'rule:shared', snapshotId: 'np', label: 'Shared Rule', type: 'Rule' },
        { id: 'component-production', canonicalKey: 'plan_component:production', snapshotId: 'production', label: 'Production Component', type: 'PlanComponent' },
      ],
      links: [
        { id: 'link-plan-alpha', source: 'component-alpha-np', target: 'plan-alpha-np', relationship: 'belongs_to_plan' },
        { id: 'link-cross-snapshot', source: 'rule-shared-np', target: 'component-production', relationship: 'belongs_to_plan_component' },
        { id: 'link-component-beta', source: 'rule-shared-np', target: 'component-beta-np', relationship: 'belongs_to_plan_component' },
        { id: 'link-plan-zulu', source: 'component-beta-np', target: 'plan-zulu-np', relationship: 'belongs_to_plan' },
        { id: 'link-component-alpha', source: 'rule-shared-np', target: 'component-alpha-np', relationship: 'belongs_to_plan_component' },
        { id: 'link-component-alpha', source: 'rule-shared-np', target: 'component-alpha-np', relationship: 'belongs_to_plan_component' },
        { id: 'link-formula', source: 'rule-shared-np', target: 'formula-np', relationship: 'uses_formula' },
      ],
    };
    const before = JSON.stringify(graph);
    const lineage = (window as any).selectRuleLineage(graph, 'rule-shared-np', 'np');
    const repeatedLineage = (window as any).selectRuleLineage(graph, 'rule-shared-np', 'np');

    return {
      unchanged: JSON.stringify(graph) === before,
      nodeIds: lineage.nodes.map((node: any) => node.id),
      linkIds: lineage.links.map((link: any) => link.id),
      repeatedNodeIds: repeatedLineage.nodes.map((node: any) => node.id),
      repeatedLinkIds: repeatedLineage.links.map((link: any) => link.id),
      hasResolvedContainment: lineage.hasResolvedContainment,
    };
  });

  expect(result).toEqual({
    unchanged: true,
    nodeIds: [
      'component-alpha-np',
      'component-beta-np',
      'plan-alpha-np',
      'plan-zulu-np',
      'rule-shared-np',
    ],
    linkIds: [
      'link-plan-alpha',
      'link-plan-zulu',
      'link-component-alpha',
      'link-component-beta',
    ],
    repeatedNodeIds: [
      'component-alpha-np',
      'component-beta-np',
      'plan-alpha-np',
      'plan-zulu-np',
      'rule-shared-np',
    ],
    repeatedLinkIds: [
      'link-plan-alpha',
      'link-plan-zulu',
      'link-component-alpha',
      'link-component-beta',
    ],
    hasResolvedContainment: true,
  });
});

test('opens a selected Rule lineage and returns to the preserved graph without a new API request', async ({ page }) => {
  const browserErrors: string[] = [];
  let apiRequestCount = 0;
  collectBrowserErrors(page, browserErrors);
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequestCount += 1;
  });

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(minimalPlanFixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();
  await expect(page.locator('#status')).toHaveText('Core topology: 3 nodes, 2 links, no findings');

  await page.getByRole('button', { name: 'Dark mode' }).click();
  await page.locator('#search').fill('Credit');
  await page.locator('#type-filter').selectOption('Rule');
  await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const rule = cy.nodes().filter((node: any) => node.data('type') === 'Rule')[0];
    rule.select();
    rule.emit('tap', { target: rule });
    (window as any).__lineageMainCy = cy;
  });

  await expect(page.locator('#node-summary')).toContainText('Credit Rule');
  const requestCountBeforeOpen = apiRequestCount;
  const graphBeforeOpen = await page.evaluate(() => JSON.stringify((window as any).state.graph));
  await page.getByRole('button', { name: 'Open lineage' }).click();

  await expect(page.locator('#lineage-view')).toBeVisible();
  await expect(page.locator('#lineage-summary')).toHaveText(
    'Credit Rule: 1 plan component and 1 plan.'
  );
  await expect(page.locator('#lineage-graph')).toHaveAttribute(
    'aria-describedby',
    'lineage-summary lineage-description'
  );
  await expect(page.locator('#lineage-description li')).toHaveText([
    'Selected Rule: Credit Rule',
    'Plan Components: Core Component',
    'Plans: Enterprise Plan',
    'Resolved containment relationships: Core Component belongs to plan Enterprise Plan; Credit Rule belongs to plan component Core Component',
  ]);
  await expect(page.locator('#lineage-graph canvas').first()).toBeVisible();
  expect(apiRequestCount).toBe(requestCountBeforeOpen);

  await page.getByRole('button', { name: 'Back to Graph' }).click();
  await page.locator('#lineage-tab').click();
  await expect(page.locator('#lineage-summary')).toHaveText(
    'Credit Rule: 1 plan component and 1 plan.'
  );
  expect(apiRequestCount).toBe(requestCountBeforeOpen);
  await page.getByRole('button', { name: 'Back to Graph' }).click();
  await expect(page.locator('#graph-view')).toBeVisible();
  await expect(page.locator('#search')).toHaveValue('Credit');
  await expect(page.locator('#type-filter')).toHaveValue('Rule');
  await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#node-summary')).toContainText('Credit Rule');
  expect(await page.locator('#np-xml-files').evaluate((input: HTMLInputElement) =>
    [...(input.files ?? [])].map(file => file.name)
  )).toEqual(['minimal_plan.xml']);
  expect(await page.evaluate(() => (window as any).state.cy === (window as any).__lineageMainCy)).toBe(true);
  expect(await page.evaluate(() => JSON.stringify((window as any).state.graph))).toBe(graphBeforeOpen);
  expect(apiRequestCount).toBe(requestCountBeforeOpen);

  await page.getByRole('button', { name: 'Clear all filters' }).click();
  await expect.poll(async () => page.evaluate(() => (window as any).state.cy.edges().length))
    .toBeGreaterThan(0);
  await page.evaluate(() => {
    const edge = (window as any).state.cy.edges()[0];
    edge.emit('tap', { target: edge });
  });
  await expect(page.locator('#node-summary')).toContainText('Relationship');
  await expect(page.locator('#lineage-tab')).toBeDisabled();
  expect(browserErrors).toEqual([]);
});

test('renders every resolved parent of a shared Rule from the Full graph without Formula nodes', async ({ page }) => {
  const browserErrors: string[] = [];
  collectBrowserErrors(page, browserErrors);

  await page.goto('/');
  await page.getByRole('combobox', { name: 'Graph topology' }).selectOption('full');
  await page.locator('#np-xml-files').setInputFiles(sharedRuleFixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...');
  await expect(page.locator('#graph canvas').first()).toBeVisible();
  await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const rule = cy.nodes().filter((node: any) => node.data('label') === 'Shared Rule')[0];
    rule.emit('tap', { target: rule });
  });

  await page.getByRole('button', { name: 'Open lineage' }).click();
  await expect(page.locator('#lineage-summary')).toHaveText(
    'Shared Rule: 2 plan components and 2 plans.'
  );
  await expect(page.locator('#lineage-description li')).toHaveText([
    'Selected Rule: Shared Rule',
    'Plan Components: Alpha Component, Beta Component',
    'Plans: Alpha Plan, Zulu Plan',
    'Resolved containment relationships: Alpha Component belongs to plan Alpha Plan; Beta Component belongs to plan Zulu Plan; Shared Rule belongs to plan component Alpha Component; Shared Rule belongs to plan component Beta Component',
  ]);
  expect(await page.evaluate(() => {
    const lineageCy = (window as any).state.lineageCy;
    return {
      labels: lineageCy.nodes().map((node: any) => node.data('label')).sort(),
      types: [...new Set(lineageCy.nodes().map((node: any) => node.data('type')))].sort(),
      relationships: lineageCy.edges().map((edge: any) => edge.data('relationship')).sort(),
    };
  })).toEqual({
    labels: ['Alpha Component', 'Alpha Plan', 'Beta Component', 'Shared Rule', 'Zulu Plan'],
    types: ['Plan', 'PlanComponent', 'Rule'],
    relationships: [
      'belongs_to_plan',
      'belongs_to_plan',
      'belongs_to_plan_component',
      'belongs_to_plan_component',
    ],
  });
  expect(browserErrors).toEqual([]);
});

test('shows an empty lineage state when a Rule has no resolved containment path', async ({ page }) => {
  const browserErrors: string[] = [];
  collectBrowserErrors(page, browserErrors);

  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(uncontainedRuleFixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...');
  await page.evaluate(() => {
    const cy = (window as any).state.cy;
    const rule = cy.nodes().filter((node: any) => node.data('label') === 'Uncontained Rule')[0];
    rule.emit('tap', { target: rule });
  });

  await page.getByRole('button', { name: 'Open lineage' }).click();
  await expect(page.locator('#lineage-summary')).toHaveText(
    'Uncontained Rule: 0 plan components and 0 plans.'
  );
  await expect(page.locator('#lineage-empty')).toHaveText(
    'No resolved containment path for Uncontained Rule.'
  );
  await expect(page.locator('#lineage-empty')).toBeVisible();
  await expect(page.locator('#lineage-graph')).toBeHidden();
  await expect(page.locator('#lineage-description li')).toHaveText([
    'Selected Rule: Uncontained Rule',
    'Plan Components: None',
    'Plans: None',
    'Resolved containment relationships: None',
  ]);
  expect(browserErrors).toEqual([]);
});
