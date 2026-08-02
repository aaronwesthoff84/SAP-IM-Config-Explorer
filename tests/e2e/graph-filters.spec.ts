import { expect, test } from '@playwright/test';
import path from 'node:path';

const extractorFamiliesFixture = path.resolve('tests/fixtures/extractor_families.xml');
const minimalPlanFixture = path.resolve('tests/fixtures/minimal_plan.xml');
const duplicateIdsFixture = path.resolve('tests/fixtures/duplicate_ids.xml');

test('combines search, object type, source file, and effective date filters', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(() => {
    const graph = {
      nodes: [
        {
          id: 'node-current-plan',
          label: 'Enterprise Plan',
          type: 'Plan',
          sourceFile: 'north.xml',
          metadata: { effectiveStartDate: '2026-01-01', effectiveEndDate: '2026-12-31' },
        },
        {
          id: 'node-open-plan',
          label: 'Enterprise Open Plan',
          type: 'Plan',
          sourceFile: 'north.xml',
          metadata: {},
        },
        {
          id: 'node-ended-plan',
          label: 'Enterprise Legacy Plan',
          type: 'Plan',
          sourceFile: 'north.xml',
          metadata: { effectiveEndDate: '2025-12-31' },
        },
        {
          id: 'node-current-rule',
          label: 'Enterprise Rule',
          type: 'Rule',
          sourceFile: 'north.xml',
          metadata: {},
        },
        {
          id: 'node-other-plan',
          label: 'Enterprise Plan',
          type: 'Plan',
          sourceFile: 'south.xml',
          metadata: {},
        },
      ],
      links: [
        {
          id: 'link-current-open',
          source: 'node-current-plan',
          target: 'node-open-plan',
          relationship: 'belongs_to_plan',
          confidence: 'high',
        },
        {
          id: 'link-rule-current',
          source: 'node-current-rule',
          target: 'node-current-plan',
          relationship: 'belongs_to_plan_component',
          confidence: 'high',
        },
        {
          id: 'link-other-current',
          source: 'node-other-plan',
          target: 'node-current-plan',
          relationship: 'belongs_to_plan',
          confidence: 'medium',
        },
      ],
    };

    const filtered = (window as any).filterGraphElements(graph, {
      search: 'enterprise',
      type: 'Plan',
      sourceFile: 'north.xml',
      relationship: '',
      confidence: '',
      effectiveDate: '2026-01-01',
    });

    return {
      nodeIds: filtered.nodes.map((node: any) => node.id),
      linkIds: filtered.links.map((link: any) => link.id),
      nodeCount: filtered.nodes.length,
      linkCount: filtered.links.length,
    };
  });

  expect(result).toEqual({
    nodeIds: ['node-current-plan', 'node-open-plan'],
    linkIds: ['link-current-open'],
    nodeCount: 2,
    linkCount: 1,
  });
});

test('combines relationship and confidence filters without unrelated isolated nodes', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(() => {
    const graph = {
      nodes: [
        { id: 'node-rule', label: 'Rule', type: 'Rule', sourceFile: 'full.xml', metadata: {} },
        { id: 'node-formula-high', label: 'High Formula', type: 'Formula', sourceFile: 'full.xml', metadata: {} },
        { id: 'node-formula-medium', label: 'Medium Formula', type: 'Formula', sourceFile: 'full.xml', metadata: {} },
        { id: 'node-isolated', label: 'Isolated Plan', type: 'Plan', sourceFile: 'full.xml', metadata: {} },
      ],
      links: [
        {
          id: 'link-formula-high',
          source: 'node-rule',
          target: 'node-formula-high',
          relationship: 'uses_formula',
          confidence: 'high',
        },
        {
          id: 'link-formula-medium',
          source: 'node-rule',
          target: 'node-formula-medium',
          relationship: 'uses_formula',
          confidence: 'medium',
        },
        {
          id: 'link-unrelated',
          source: 'node-formula-medium',
          target: 'node-isolated',
          relationship: 'belongs_to_plan',
          confidence: 'high',
        },
      ],
    };

    const filtered = (window as any).filterGraphElements(graph, {
      search: '',
      type: '',
      sourceFile: '',
      relationship: 'uses_formula',
      confidence: 'high',
      effectiveDate: '',
    });

    return {
      nodeIds: filtered.nodes.map((node: any) => node.id),
      linkIds: filtered.links.map((link: any) => link.id),
      nodeCount: filtered.nodes.length,
      linkCount: filtered.links.length,
    };
  });

  expect(result).toEqual({
    nodeIds: ['node-rule', 'node-formula-high'],
    linkIds: ['link-formula-high'],
    nodeCount: 2,
    linkCount: 1,
  });
});

test('includes effective date boundaries and treats missing bounds as open ended', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(() => {
    const graph = {
      nodes: [
        { id: 'node-start-boundary', label: 'A', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveStartDate: '2026-01-01', effectiveEndDate: '2026-12-31' } },
        { id: 'node-end-boundary', label: 'B', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveStartDate: '2025-01-01', effectiveEndDate: '2026-01-01' } },
        { id: 'node-open-start', label: 'C', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveEndDate: '2026-06-30' } },
        { id: 'node-open-end', label: 'D', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveStartDate: '2025-06-30' } },
        { id: 'node-no-bounds', label: 'E', type: 'Plan', sourceFile: 'dates.xml', metadata: {} },
        { id: 'node-future', label: 'F', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveStartDate: '2026-01-02' } },
        { id: 'node-expired', label: 'G', type: 'Plan', sourceFile: 'dates.xml', metadata: { effectiveEndDate: '2025-12-31' } },
      ],
      links: [],
    };
    const filtered = (window as any).filterGraphElements(graph, {
      search: '',
      type: '',
      sourceFile: '',
      relationship: '',
      confidence: '',
      effectiveDate: '2026-01-01',
    });
    return filtered.nodes.map((node: any) => node.id);
  });

  expect(result).toEqual([
    'node-start-boundary',
    'node-end-boundary',
    'node-open-start',
    'node-open-end',
    'node-no-bounds',
  ]);
});

test('filters a multi-file Full graph, reports active results, and clears all filters', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto('/');
  await expect(page.locator('#source-file-filter-control')).toBeHidden();
  await expect(page.locator('#relationship-filter-control')).toBeHidden();
  await expect(page.locator('#confidence-filter-control')).toBeHidden();
  await expect(page.locator('#effective-date-filter-control')).toBeHidden();

  await page.getByRole('combobox', { name: 'Graph topology' }).selectOption('full');
  await page.locator('#np-xml-files').setInputFiles([
    extractorFamiliesFixture,
    minimalPlanFixture,
  ]);
  await page.getByRole('button', { name: 'Generate Graph' }).click();

  await expect(page.locator('#status')).toHaveText(
    'Full topology: 23 nodes, 21 links, no findings'
  );
  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 23 of 23 nodes and 21 of 21 links'
  );
  await expect(page.locator('#active-filters')).toHaveText('Active filters: None');
  await expect(page.locator('#clear-filters')).toBeDisabled();
  await expect(page.locator('#source-file-filter option')).toHaveText([
    'All source files',
    'extractor_families.xml',
    'minimal_plan.xml',
  ]);
  await expect(page.locator('#relationship-filter option')).toHaveText([
    'All relationships',
    'belongs_to_plan',
    'belongs_to_plan_component',
    'outputs_credit_type',
    'uses_business_unit',
    'uses_calendar',
    'uses_earning_code',
    'uses_earning_group',
    'uses_event_type',
    'uses_fixed_value',
    'uses_formula',
    'uses_lookup',
    'uses_processing_unit',
    'uses_quota',
    'uses_rate_table',
    'uses_territory',
    'uses_variable',
  ]);
  await expect(page.locator('#confidence-filter option')).toHaveText([
    'All confidence levels',
    'high',
  ]);
  await expect(page.locator('#effective-date-filter')).toBeEnabled();

  const originalGraph = await page.evaluate(() => JSON.stringify((window as any).state.graph));
  await page.locator('#type-filter').selectOption('Plan');
  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 2 of 23 nodes and 0 of 21 links'
  );
  await expect(page.locator('#active-filters')).toHaveText(
    'Active filters: Object type: Plan'
  );
  expect(await page.evaluate(() => ({
    nodeIds: (window as any).state.cy.nodes().map((node: any) => node.id()).sort(),
    linkIds: (window as any).state.cy.edges().map((link: any) => link.id()).sort(),
  }))).toEqual({
    nodeIds: ['node-ac3821b54d37701e374e', 'node-b9b14d7448c5f143f9cb'],
    linkIds: [],
  });
  await page.locator('#type-filter').selectOption('');
  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 23 of 23 nodes and 21 of 21 links'
  );

  await page.locator('#search').fill('e');
  await page.locator('#source-file-filter').selectOption('minimal_plan.xml');
  await page.locator('#relationship-filter').selectOption('uses_formula');
  await page.locator('#confidence-filter').selectOption('high');
  await page.locator('#effective-date-filter').fill('2026-01-01');

  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 2 of 23 nodes and 1 of 21 links'
  );
  await expect(page.locator('#active-filters')).toHaveText(
    'Active filters: Search: e; Source file: minimal_plan.xml; Relationship: uses_formula; Confidence: high; Effective on: 2026-01-01'
  );
  await expect(page.locator('#clear-filters')).toBeEnabled();
  expect(await page.evaluate(() => ({
    nodeIds: (window as any).state.cy.nodes().map((node: any) => node.id()).sort(),
    linkIds: (window as any).state.cy.edges().map((link: any) => link.id()).sort(),
  }))).toEqual({
    nodeIds: ['node-126b8f4882f4baabe4f9', 'node-9b091cd872ac73754d6a'],
    linkIds: ['link-df129b655c86be301ef2'],
  });

  await page.locator('#clear-filters').click();
  await expect(page.locator('#search')).toHaveValue('');
  await expect(page.locator('#source-file-filter')).toHaveValue('');
  await expect(page.locator('#relationship-filter')).toHaveValue('');
  await expect(page.locator('#confidence-filter')).toHaveValue('');
  await expect(page.locator('#effective-date-filter')).toHaveValue('');
  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 23 of 23 nodes and 21 of 21 links'
  );
  await expect(page.locator('#active-filters')).toHaveText('Active filters: None');
  await expect(page.locator('#clear-filters')).toBeDisabled();
  expect(await page.evaluate(() => JSON.stringify((window as any).state.graph))).toBe(originalGraph);
  expect(browserErrors).toEqual([]);
});

test('does not present unavailable relationship, confidence, or date controls as usable', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('combobox', { name: 'Graph topology' }).selectOption('full');
  await page.locator('#np-xml-files').setInputFiles(duplicateIdsFixture);
  await page.getByRole('button', { name: 'Generate Graph' }).click();

  await expect(page.locator('#filter-results')).toHaveText(
    'Showing 2 of 2 nodes and 0 of 0 links'
  );
  await expect(page.locator('#source-file-filter-control')).toBeVisible();
  await expect(page.locator('#source-file-filter')).toBeEnabled();
  await expect(page.locator('#relationship-filter-control')).toBeHidden();
  await expect(page.locator('#relationship-filter')).toBeDisabled();
  await expect(page.locator('#confidence-filter-control')).toBeHidden();
  await expect(page.locator('#confidence-filter')).toBeDisabled();
  await expect(page.locator('#effective-date-filter-control')).toBeHidden();
  await expect(page.locator('#effective-date-filter')).toBeDisabled();
});
