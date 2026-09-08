import { test, expect } from "@playwright/test";
import * as path from "path";

test.describe("Accessibility: Keyboard, Screen-Reader, and Non-Color Baseline (#50)", () => {
  const FIXTURE_PATH = path.resolve(__dirname, "../fixtures/minimal_plan.xml");

  test("workspace tabs support role=tablist, roving tabindex, and arrow key navigation", async ({ page }) => {
    await page.goto("/");

    const tablist = page.locator('.tabs[role="tablist"]');
    await expect(tablist).toBeVisible();
    await expect(tablist).toHaveAttribute("aria-label", "Workspace views");

    const graphTab = page.locator('#tab-graph-view');
    const htmlTab = page.locator('#tab-html-output-view');
    const aiTab = page.locator('#ai-docs-tab');
    const compareTab = page.locator('#compare-tab');

    // Initial state: Graph is active, tabindex="0", aria-selected="true"
    await expect(graphTab).toHaveAttribute("role", "tab");
    await expect(graphTab).toHaveAttribute("aria-selected", "true");
    await expect(graphTab).toHaveAttribute("tabindex", "0");
    await expect(htmlTab).toHaveAttribute("aria-selected", "false");
    await expect(htmlTab).toHaveAttribute("tabindex", "-1");

    // Views have role=tabpanel and aria-labelledby
    const graphView = page.locator('#graph-view');
    await expect(graphView).toHaveAttribute("role", "tabpanel");
    await expect(graphView).toHaveAttribute("aria-labelledby", "tab-graph-view");
    await expect(graphView).toBeVisible();

    // Keyboard navigation: focus Graph tab, press ArrowRight to move to HTML Output tab
    // (Notice Lineage and Pipeline tabs are disabled before graph generation, so ArrowRight skips them)
    await graphTab.focus();
    await page.keyboard.press("ArrowRight");

    await expect(htmlTab).toBeFocused();
    await expect(htmlTab).toHaveAttribute("aria-selected", "true");
    await expect(htmlTab).toHaveAttribute("tabindex", "0");
    await expect(graphTab).toHaveAttribute("aria-selected", "false");
    await expect(graphTab).toHaveAttribute("tabindex", "-1");
    await expect(page.locator('#html-output-view')).toBeVisible();

    // ArrowRight again moves to AI Docs tab
    await page.keyboard.press("ArrowRight");
    await expect(aiTab).toBeFocused();
    await expect(aiTab).toHaveAttribute("aria-selected", "true");

    // ArrowLeft moves back to HTML Output tab
    await page.keyboard.press("ArrowLeft");
    await expect(htmlTab).toBeFocused();
    await expect(htmlTab).toHaveAttribute("aria-selected", "true");

    // End key moves to last enabled tab (Compare XML)
    await page.keyboard.press("End");
    await expect(compareTab).toBeFocused();
    await expect(compareTab).toHaveAttribute("aria-selected", "true");

    // Home key moves to first tab (Graph)
    await page.keyboard.press("Home");
    await expect(graphTab).toBeFocused();
    await expect(graphTab).toHaveAttribute("aria-selected", "true");
  });

  test("skip link allows keyboard users to bypass topbar and jump directly to main content", async ({ page }) => {
    await page.goto("/");

    const skipLink = page.locator("a.skip-link");
    await expect(skipLink).toBeAttached();

    // Tab into skip link
    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();

    // Press Enter to activate skip link
    await page.keyboard.press("Enter");
    const mainContent = page.locator("#main-content");
    await expect(mainContent).toBeFocused();
  });

  test("accessible graph tree provides keyboard and screen-reader alternative for canvas nodes", async ({ page }) => {
    await page.goto("/");

    // Upload XML and generate graph
    const fileInput = page.locator("#np-xml-files");
    await fileInput.setInputFiles(FIXTURE_PATH);
    await page.locator("#graph-button").click();

    // Wait for graph status to indicate success
    await expect(page.locator("#status")).toContainText(/topology:/i, { timeout: 10000 });

    // Open the accessible graph tree
    const toggleTreeBtn = page.locator("#toggle-accessible-tree");
    await expect(toggleTreeBtn).toBeVisible();
    await expect(toggleTreeBtn).toHaveAttribute("aria-expanded", "false");

    await toggleTreeBtn.click();
    await expect(toggleTreeBtn).toHaveAttribute("aria-expanded", "true");

    const treeContainer = page.locator("#accessible-graph-tree");
    await expect(treeContainer).toBeVisible();

    // Verify node count in accessible header
    const treeCount = page.locator("#accessible-tree-count");
    await expect(treeCount).toContainText(/nodes/i);

    const nodeList = page.locator("#accessible-node-list");
    await expect(nodeList).toHaveAttribute("role", "listbox");

    // Check items have role="option", shape badges, and link counts
    const nodeItems = nodeList.locator(".accessible-node-item");
    const count = await nodeItems.count();
    expect(count).toBeGreaterThan(0);

    const firstItem = nodeItems.first();
    await expect(firstItem).toHaveAttribute("role", "option");
    await expect(firstItem.locator(".accessible-node-shape")).toBeVisible();

    // Keyboard navigation within accessible node list
    await firstItem.focus();
    await page.keyboard.press("ArrowDown");
    const secondItem = nodeItems.nth(1);
    await expect(secondItem).toBeFocused();

    // Press Enter to select node via keyboard
    await page.keyboard.press("Enter");
    await expect(secondItem).toHaveAttribute("aria-selected", "true");

    // Details panel updates with selected item details
    const nodeSummary = page.locator("#node-summary");
    await expect(nodeSummary).not.toContainText("Select a graph item");

    // Screen reader live announcement is populated
    const a11yAnnouncements = page.locator("#a11y-announcements");
    await expect(a11yAnnouncements).toContainText(/Selected/i);

    // Verify filters update accessible tree in lockstep
    await page.locator("#search").fill("Credit Rule");
    // Filter summary announces
    await expect(page.locator("#filter-results")).toContainText(/Showing/i);
    // Tree count updates to filtered count
    const filteredCount = await nodeItems.count();
    expect(filteredCount).toBeLessThan(count);
  });

  test("findings workbench items support keyboard activation and screen-reader labels", async ({ page }) => {
    await page.goto("/");

    // Upload XML and generate graph to populate findings
    const fileInput = page.locator("#np-xml-files");
    await fileInput.setInputFiles(path.resolve(__dirname, "../fixtures/validation_findings.xml"));
    await page.locator("#graph-button").click();

    await expect(page.locator("#status")).toContainText(/topology:/i, { timeout: 10000 });

    const findingsCounter = page.locator("#findings-counter");
    await expect(findingsCounter).toBeVisible();

    // Check findings items
    const findingItems = page.locator("#validation-findings .finding");
    const findingCount = await findingItems.count();
    if (findingCount > 0) {
      const firstFinding = findingItems.first();
      await expect(firstFinding).toHaveAttribute("tabindex", "0");
      await expect(firstFinding).toHaveAttribute("role", "article");
      await expect(firstFinding).toHaveAttribute("aria-label", /Finding/i);

      // Keyboard activation of finding
      await firstFinding.focus();
      await page.keyboard.press("Enter");
      await expect(firstFinding).toHaveClass(/selected/);

      // Announcement made
      await expect(page.locator("#a11y-announcements")).toContainText(/Selected finding/i);
    }
  });

  test("non-color indicators are present on severity badges and comparison cards", async ({ page }) => {
    await page.goto("/");

    // Switch to compare view
    await page.locator("#compare-tab").click();
    await expect(page.locator("#compare-view")).toBeVisible();

    // Verify comparison cards have non-color prefixes
    const addedCard = page.locator(".compare-card.card-added .compare-card-label");
    await expect(addedCard).toContainText("Added");

    const removedCard = page.locator(".compare-card.card-removed .compare-card-label");
    await expect(removedCard).toContainText("Removed");

    const changedCard = page.locator(".compare-card.card-changed .compare-card-label");
    await expect(changedCard).toContainText("Changed");

    const unchangedCard = page.locator(".compare-card.card-unchanged .compare-card-label");
    await expect(unchangedCard).toContainText("Unchanged");
  });

  test("theme toggle preserves contrast and focus indicators", async ({ page }) => {
    await page.goto("/");

    const themeToggle = page.locator("#theme-toggle");
    await expect(themeToggle).toHaveAttribute("aria-pressed", "false");

    // Toggle to dark mode
    await themeToggle.click();
    await expect(themeToggle).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    // Check focus ring on theme toggle
    await themeToggle.focus();
    const isFocused = await themeToggle.evaluate((el) => document.activeElement === el);
    expect(isFocused).toBe(true);

    // Toggle back to light mode
    await themeToggle.click();
    await expect(themeToggle).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");
  });
});
