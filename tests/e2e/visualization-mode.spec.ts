import { expect, test } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('tests/fixtures/extractor_families.xml');

test.describe('Optional 3D Visualization Mode', () => {
  test('gracefully falls back to 2D mode if WebGL is unsupported', async ({ page }) => {
    const browserErrors: string[] = [];
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });

    await page.goto('/');

    // Upload XML and generate graph
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await expect(page.locator('#status')).toHaveText(
      'Core topology: 3 nodes, 2 links, no findings'
    );

    // Mock WebGL to be unsupported
    await page.evaluate(() => {
      (window as any).isWebGLSupported = () => false;
    });

    // Switch to 3D mode
    const modeSelect = page.locator('#visualization-mode');
    await modeSelect.selectOption('3d');

    // Should stay in 2D or fall back, and show a status message
    await expect(page.locator('#status')).toHaveText(
      '3D rendering is unsupported on this browser/device.'
    );
    await expect(modeSelect).toHaveValue('2d');
    await expect(page.locator('#graph')).toBeVisible();
    await expect(page.locator('#graph-3d')).toBeHidden();

    expect(browserErrors).toEqual([]);
  });

  test('successfully switches to 3D mode when WebGL is supported', async ({ page }) => {
    const browserErrors: string[] = [];
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });

    await page.goto('/');

    // Upload XML and generate graph
    await page.locator('#np-xml-files').setInputFiles(fixture);
    await page.getByRole('button', { name: 'Generate Graph' }).click();
    await expect(page.locator('#status')).toHaveText(
      'Core topology: 3 nodes, 2 links, no findings'
    );

    // Mock WebGL supported and stub the ForceGraph3D library
    await page.evaluate(() => {
      (window as any).isWebGLSupported = () => true;
      (window as any).load3DLibrary = async () => {
        (window as any).ForceGraph3D = () => {
          const mockInstance: any = {
            nodeColor: () => mockInstance,
            nodeLabel: () => mockInstance,
            linkLabel: () => mockInstance,
            linkColor: () => mockInstance,
            onNodeClick: () => mockInstance,
            onBackgroundClick: () => mockInstance,
            onLinkClick: () => mockInstance,
            backgroundColor: () => mockInstance,
            width: () => mockInstance,
            height: () => mockInstance,
            graphData: () => mockInstance,
          };
          return () => mockInstance;
        };
      };
    });

    const modeSelect = page.locator('#visualization-mode');
    await modeSelect.selectOption('3d');

    // 3D container should be visible, 2D container should be hidden
    await expect(page.locator('#graph-3d')).toBeVisible();
    await expect(page.locator('#graph')).toBeHidden();

    // Switch back to 2D
    await modeSelect.selectOption('2d');
    await expect(page.locator('#graph')).toBeVisible();
    await expect(page.locator('#graph-3d')).toBeHidden();

    expect(browserErrors).toEqual([]);
  });
});
