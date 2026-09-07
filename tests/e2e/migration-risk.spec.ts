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

test('displays every migration-risk factor associated with a selected node in details panel', async ({ page }) => {
  await page.goto('/');

  await page.evaluate(() => {
    const mockNode = {
      id: 'node-risk-test-1',
      label: 'Multi-Risk Rule',
      type: 'Rule',
      sourceFile: 'test.xml',
      xmlPath: '/DATA_IMPORT/RULE_SET/RULE',
      metadata: {},
      rawXml: '<RULE NAME="Multi-Risk Rule" />'
    };
    (window as any).state = (window as any).state || {};
    (window as any).state.graph = {
      nodes: [mockNode],
      links: [],
      findings: [],
      migrationRisk: {
        score: 50,
        factors: [
          {
            code: 'duplicate_object',
            severity: 'high',
            weight: 40,
            message: 'Duplicate object detected in NP',
            nodeIds: ['node-risk-test-1']
          },
          {
            code: 'changed_containment',
            severity: 'medium',
            weight: 10,
            message: 'Rule containment moved to different component',
            nodeIds: ['node-risk-test-1']
          }
        ]
      }
    };
    (window as any).showNodeDetails(mockNode);
  });

  const summary = page.locator('#node-summary');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText('Migration risk (2)');
  await expect(summary).toContainText('duplicate_object');
  await expect(summary).toContainText('(Weight: 40): Duplicate object detected in NP');
  await expect(summary).toContainText('changed_containment');
  await expect(summary).toContainText('(Weight: 10): Rule containment moved to different component');
});

