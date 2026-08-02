import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/minimal_plan.xml');

function collectBrowserErrors(page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

async function generateGraphAndHtml(page) {
  await page.locator('#np-xml-files').setInputFiles(fixture);
  await page.locator('#graph-button').click();
  await expect(page.locator('#status')).not.toHaveText('Generating graph...');
  await page.locator('#html-button').click();
  await expect(page.locator('#status')).toContainText('Generated');
}

async function selectedSourceXml(page) {
  return page.locator('#np-xml-files').evaluate(async (input: HTMLInputElement) => {
    const sourceFile = input.files?.[0];
    return sourceFile ? sourceFile.text() : null;
  });
}

test('filters the generated HTML preview and download by the active name search', async ({ page }) => {
  const browserErrors: string[] = [];
  let htmlRequestCount = 0;
  collectBrowserErrors(page, browserErrors);
  page.on('request', request => {
    if (request.url().endsWith('/api/convert/html')) htmlRequestCount += 1;
  });

  await page.goto('/');
  await page.locator('#search').fill('eligibility');
  expect(htmlRequestCount).toBe(0);
  expect(await page.evaluate(() => (window as any).state.html)).toBeNull();
  await page.locator('#search').fill('');
  await generateGraphAndHtml(page);
  expect(htmlRequestCount).toBe(1);

  const originalGraph = await page.evaluate(() => JSON.stringify((window as any).state.graph));
  await expect.poll(async () => page.evaluate(() => (window as any).state.html?.originalHtml))
    .toContain('<section data-object-type="Formula" data-object-label="Eligibility Formula">');

  await page.locator('#search').fill('eligibility');

  const preview = page.frameLocator('#html-output-preview');
  await expect(preview.locator('section[data-object-type]')).toHaveCount(1);
  await expect(preview.locator('section[data-object-type]')).toHaveAttribute('data-object-type', 'Formula');
  await expect(preview.locator('section[data-object-type]')).toHaveAttribute('data-object-label', 'Eligibility Formula');
  await expect(preview.getByText('Enterprise Plan', { exact: true })).toHaveCount(0);

  const downloadedSections = await page.evaluate(async () => {
    const href = (document.getElementById('html-output-download') as HTMLAnchorElement).href;
    const html = await (await fetch(href)).text();
    const documentForDownload = new DOMParser().parseFromString(html, 'text/html');
    return [...documentForDownload.querySelectorAll('section[data-object-type]')].map(section => ({
      type: section.getAttribute('data-object-type'),
      label: section.getAttribute('data-object-label'),
    }));
  });
  expect(downloadedSections).toEqual([
    { type: 'Formula', label: 'Eligibility Formula' },
  ]);
  expect(await page.evaluate(() => JSON.stringify((window as any).state.graph))).toBe(originalGraph);
  expect(browserErrors).toEqual([]);
});

test('filters HTML by object type, restores the original download, and preserves surviving anchors', async ({ page }) => {
  const browserErrors: string[] = [];
  collectBrowserErrors(page, browserErrors);

  await page.goto('/');
  await generateGraphAndHtml(page);

  const original = await page.evaluate(() => ({
    html: (window as any).state.html.originalHtml,
    graph: JSON.stringify((window as any).state.graph),
  }));
  const originalSourceXml = await selectedSourceXml(page);
  await page.locator('#type-filter').selectOption('Plan');

  const preview = page.frameLocator('#html-output-preview');
  await expect(preview.locator('section[data-object-type]')).toHaveCount(1);
  await expect(preview.locator('section[data-object-type]')).toHaveAttribute('data-object-type', 'Plan');
  await expect(preview.locator('section[data-object-type]')).toHaveAttribute('data-object-label', 'Enterprise Plan');

  await page.locator('#search').fill('eligibility');
  await expect(preview.locator('section[data-object-type]')).toHaveCount(0);
  await page.locator('#type-filter').selectOption('');
  await expect(preview.locator('section[data-object-type]')).toHaveCount(1);
  await expect(preview.locator('section[data-object-type]')).toHaveAttribute('data-object-type', 'Formula');
  await expect(preview.locator('a[name="formulas"]')).toHaveCount(1);
  const anchorBefore = await preview.locator('a[name="formulas"]').evaluate(
    element => element.getBoundingClientRect().top,
  );
  await preview.locator('a[href="#formulas"]').click();
  const anchorAfter = await preview.locator('a[name="formulas"]').evaluate(
    element => element.getBoundingClientRect().top,
  );
  expect(Math.abs(anchorAfter)).toBeLessThan(Math.abs(anchorBefore));

  await page.locator('#clear-filters').click();
  await expect(page.locator('#search')).toHaveValue('');
  await expect(page.locator('#type-filter')).toHaveValue('');
  await expect(preview.locator('section[data-object-type]')).toHaveCount(5);

  const restored = await page.evaluate(async () => {
    const previewHtml = (document.getElementById('html-output-preview') as HTMLIFrameElement).srcdoc;
    const href = (document.getElementById('html-output-download') as HTMLAnchorElement).href;
    return {
      previewHtml,
      downloadHtml: await (await fetch(href)).text(),
      graph: JSON.stringify((window as any).state.graph),
    };
  });
  expect(restored.previewHtml).toBe(original.html);
  expect(restored.downloadHtml).toBe(original.html);
  expect(restored.graph).toBe(original.graph);
  expect(await selectedSourceXml(page)).toBe(originalSourceXml);
  expect(browserErrors).toEqual([]);
});
