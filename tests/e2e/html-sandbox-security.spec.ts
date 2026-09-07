import { expect, test } from '@playwright/test';
import path from 'node:path';

const maliciousFixture = path.resolve('tests/fixtures/malicious_payloads.xml');

function collectBrowserErrors(page, errors: string[]) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') {
      const text = message.text();
      // Sandboxed frame script execution blocking logs are expected and part of browser defense
      if (text.includes("Blocked script execution") && text.includes("sandboxed")) return;
      errors.push(text);
    }
  });
}

test.describe('HTML Preview Sandbox and XSS Defense', () => {
  test('iframe is sandboxed and neutralizes malicious XML payloads', async ({ page }) => {
    const browserErrors: string[] = [];
    collectBrowserErrors(page, browserErrors);

    await page.goto('/');

    // 1. Verify iframe has sandbox="allow-same-origin" attribute
    const iframeElement = page.locator('#html-output-preview');
    await expect(iframeElement).toHaveAttribute('sandbox', 'allow-same-origin');

    // 2. Set canaries on parent window and local storage
    await page.evaluate(() => {
      (window as any).__pwned = undefined;
      (window as any).parentCanary = 'secure_canary_value';
      window.localStorage.setItem('canary_storage_key', 'canary_storage_value');
    });

    // 3. Upload malicious XML and generate graph & HTML
    await page.locator('#np-xml-files').setInputFiles(maliciousFixture);
    await page.locator('#graph-button').click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');
    await page.locator('#html-button').click();
    await expect(page.locator('#status')).toContainText('Generated');

    // 4. Verify preview iframe rendered
    const preview = page.frameLocator('#html-output-preview');
    await expect(preview.locator('body')).toBeVisible();

    // 5. Verify parent window was NOT compromised
    const parentStatus = await page.evaluate(() => ({
      pwned: (window as any).__pwned,
      canary: (window as any).parentCanary,
      storage: window.localStorage.getItem('canary_storage_key'),
    }));
    expect(parentStatus.pwned).toBeUndefined();
    expect(parentStatus.canary).toBe('secure_canary_value');
    expect(parentStatus.storage).toBe('canary_storage_value');

    // 6. Verify iframe document context was not compromised
    const framePwned = await preview.locator('body').evaluate(() => (window as any).__pwned);
    expect(framePwned).toBeUndefined();

    // 7. Verify hostile payloads rendered as safe text, not active HTML tags
    const iframeContent = await page.evaluate(() => {
      const iframe = document.getElementById('html-output-preview') as HTMLIFrameElement;
      return iframe.srcdoc || '';
    });
    expect(iframeContent).toContain('Content-Security-Policy');
    expect(iframeContent).not.toContain('<script>window.__pwned');
    expect(iframeContent).toContain('&lt;script&gt;window.__pwned=true;&lt;/script&gt;');

    // 8. Verify internal links still navigate inside the preview
    const linkLocator = preview.locator('a[href^="#"]').first();
    await expect(linkLocator).toBeVisible();
    await linkLocator.click();

    // 9. Verify downloaded report contains CSP meta tag for offline safety
    const downloadedHtml = await page.evaluate(async () => {
      const downloadLink = document.getElementById('html-output-download') as HTMLAnchorElement;
      if (!downloadLink || !downloadLink.href) return '';
      const response = await fetch(downloadLink.href);
      return response.text();
    });
    expect(downloadedHtml).toContain('Content-Security-Policy');
    expect(downloadedHtml).toContain('&lt;script&gt;');
    expect(downloadedHtml).not.toContain('<script>window.__pwned');

    expect(browserErrors).toEqual([]);
  });
});
