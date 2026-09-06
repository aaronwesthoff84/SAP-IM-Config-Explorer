import { expect, test } from '@playwright/test';
import path from 'node:path';

const np_fixture = path.resolve('tests/fixtures/risk_high.xml');
const p_fixture = path.resolve('tests/fixtures/risk_low.xml');

test('displays migration risk score when NP and P files are uploaded', async ({ page }) => {
  await page.goto('/');
  await page.locator('#np-xml-files').setInputFiles(np_fixture);
  await page.locator('#p-xml-files').setInputFiles(p_fixture);

  await page.locator('#graph-button').click();

  const riskContainer = page.locator('#migration-risk-container');
  await expect(riskContainer).toBeVisible();

  const riskScore = page.locator('.risk-score-value');
  await expect(riskScore).toBeVisible();
  const scoreText = await riskScore.innerText();
  const score = parseInt(scoreText, 10);
  expect(score).toBeGreaterThan(0);

  await expect(page.locator('.risk-factor').first()).toBeVisible();
});

test('safely renders risk factors containing HTML characters without XSS', async ({ page }) => {
  await page.goto('/');

  await page.evaluate(() => {
    const windowWithState = window as unknown as {
      renderRiskReport?: (risk: { score: number; factors: Array<{ code: string; severity: string; weight: number; message: string }> }) => void;
    };
    if (windowWithState.renderRiskReport) {
      windowWithState.renderRiskReport({
        score: 85,
        factors: [
          {
            code: 'XSS_TEST',
            severity: 'high',
            weight: 10,
            message: 'Testing <img src=x onerror=alert(1)> and <b>bold text</b>'
          }
        ]
      });
    }
  });

  const factor = page.locator('.risk-factor').first();
  await expect(factor).toBeVisible();

  // Ensure <img> and <b> tags were not parsed as DOM elements inside the factor
  await expect(factor.locator('img')).toHaveCount(0);
  await expect(factor.locator('b')).toHaveCount(0);

  // Ensure exact raw text is rendered safely inside text node
  await expect(factor).toContainText('Testing <img src=x onerror=alert(1)> and <b>bold text</b>');
});
