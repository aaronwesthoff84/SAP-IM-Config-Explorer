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
