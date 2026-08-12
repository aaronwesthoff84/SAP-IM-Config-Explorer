import { expect, test } from '@playwright/test';
import path from 'node:path';

const nonProductionFixture = path.resolve('tests/fixtures/risk_high.xml');
const productionFixture = path.resolve('tests/fixtures/risk_low.xml');

test.describe('Saved Graph Exploration Sessions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Clear localStorage to ensure a clean state
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('allows naming, saving, and restoring a session with correct files loaded', async ({ page }) => {
    // 1. Upload files and generate graph
    await page.locator('#np-xml-files').setInputFiles(nonProductionFixture);
    await page.locator('#graph-button').click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');
    await expect(page.locator('#graph canvas').first()).toBeVisible();

    // Select a node to verify selection state restores
    await page.evaluate(() => {
      const cy = (window as any).state.cy;
      const node = cy.nodes().first();
      node.select();
      node.emit('tap', { target: node });
    });
    const firstNodeLabel = await page.evaluate(() => (window as any).state.cy.nodes().first().data('label'));
    await expect(page.locator('#node-summary')).toContainText(firstNodeLabel);

    // Save named session
    await page.locator('#session-name-input').fill('Test Session Alpha');
    await page.locator('#save-session-button').click();

    // Verify success message and element in the sessions list
    await expect(page.locator('#session-message-box')).toContainText('saved successfully');
    await expect(page.locator('#saved-sessions-list')).toContainText('Test Session Alpha');

    // Reload page to simulate restarting the app
    await page.reload();
    await expect(page.locator('#saved-sessions-list')).toContainText('Test Session Alpha');

    // Restore button triggers reselection warning because no files are currently loaded
    const restoreBtn = page.locator('#saved-sessions-list button', { hasText: 'Restore' });
    await restoreBtn.click();
    await expect(page.locator('#session-message-box')).toContainText('reselect');
    await expect(page.locator('#session-explanation')).toBeVisible();

    // Reselect original files and click Restore again
    await page.locator('#np-xml-files').setInputFiles(nonProductionFixture);
    await restoreBtn.click();

    await expect(page.locator('#session-message-box')).toContainText('restored successfully');
    await expect(page.locator('#session-explanation')).toBeHidden();
    await expect(page.locator('#graph canvas').first()).toBeVisible();
    await expect(page.locator('#node-summary')).toContainText(firstNodeLabel);
  });

  test('supports renaming and deleting a session', async ({ page }) => {
    // 1. Upload files and generate graph to enable session saving
    await page.locator('#np-xml-files').setInputFiles(nonProductionFixture);
    await page.locator('#graph-button').click();
    await expect(page.locator('#status')).not.toHaveText('Generating graph...');

    // Save session
    await page.locator('#session-name-input').fill('Original Name');
    await page.locator('#save-session-button').click();
    await expect(page.locator('#saved-sessions-list')).toContainText('Original Name');

    // Rename session
    page.once('dialog', async dialog => {
      await dialog.accept('Renamed Session');
    });
    await page.locator('#saved-sessions-list button', { hasText: 'Rename' }).click();
    await expect(page.locator('#saved-sessions-list')).toContainText('Renamed Session');
    await expect(page.locator('#saved-sessions-list')).not.toContainText('Original Name');

    // Delete session
    page.once('dialog', async dialog => {
      await dialog.accept();
    });
    await page.locator('#saved-sessions-list button', { hasText: 'Delete' }).click();
    await expect(page.locator('#saved-sessions-list')).toContainText('No saved sessions.');
  });

  test('fails safely with invalid or outdated session data', async ({ page }) => {
    // Directly inject invalid session data into localStorage
    await page.evaluate(() => {
      const invalidSessions = [
        {
          id: 'corrupted-session',
          name: 'Corrupted Session',
          // Missing required properties like createdAt, files, graph etc.
        }
      ];
      localStorage.setItem('sap-im-config-explorer-sessions', JSON.stringify(invalidSessions));
    });

    await page.reload();

    // Verify list indicates No saved sessions or invalid session is ignored/fails safely
    await expect(page.locator('#saved-sessions-list')).toContainText('No saved sessions.');

    // Inject half-valid but outdated data (fails custom validateSessionData)
    await page.evaluate(() => {
      const badSession = {
        id: 'bad-data',
        name: 'Bad Data',
        createdAt: 'invalid-date',
        themePreference: 'light',
        files: {}, // wrong shape
        filters: {},
        graph: {}
      };
      // Forcing state to contain it, then trying to restore
      (window as any).state.sessions = [badSession];
    });

    // Wait and click Restore if dynamically rendered (our code automatically ignores it, but let's test handleRestoreSession behavior)
    await page.evaluate(() => {
      (window as any).handleRestoreSession('bad-data');
    });

    await expect(page.locator('#session-message-box')).toContainText('Invalid or outdated session data');
  });
});
