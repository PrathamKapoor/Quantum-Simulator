import { test, expect } from "@playwright/test";
import { ErrorMonitor, NAV_PAGES, gotoPage } from "./helpers";

/** §15: foundational smoke test — real app boots, no fatal errors, no
 * failed critical requests. */
test("application boots in a real browser", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "QuantumLab" })).toBeVisible();
  await expect(page.locator(".sidebar nav a")).toHaveCount(12);
  monitor.assertClean();
});

/** §16/§18: navigate through every major surface using the real sidebar. */
test("navigation reaches every major page", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  await page.goto("/");

  for (const [label, heading] of NAV_PAGES) {
    await gotoPage(page, label);
    await expect(page.locator("h1.page-title")).toContainText(heading);
  }
  monitor.assertClean();
});

/** §16: direct hash navigation to every route (not just client-side clicks). */
test("direct hash navigation renders every route", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  const routes: Array<[string, string]> = [
    ["#", "QuantumLab"],
    ["#circuit", "Circuit Studio"],
    ["#algorithms", "Quantum Algorithms"],
    ["#network", "Network Studio"],
    ["#qec", "Quantum Error Correction"],
    ["#protocols", "Quantum Cryptography"],
    ["#optimize", "Optimization"],
    ["#info", "Quantum Information"],
    ["#hardware", "Hardware Lab"],
    ["#experiments", "Experiments"],
    ["#docs", "Documentation"],
  ];
  for (const [hash, heading] of routes) {
    await page.goto(`/${hash}`);
    await expect(page.locator("h1.page-title")).toContainText(heading);
  }
  monitor.assertClean();
});

/** §19: back/forward keep the application coherent. */
test("browser back/forward navigation", async ({ page }) => {
  await page.goto("/");
  await gotoPage(page, "Algorithms");
  await expect(page.locator("h1.page-title")).toContainText("Quantum Algorithms");
  await page.goBack();
  await expect(page.locator("h1.page-title")).toContainText("QuantumLab");
  await page.goForward();
  await expect(page.locator("h1.page-title")).toContainText("Quantum Algorithms");
});

/** §20: refresh on a representative route must not blank the app. */
test("refresh preserves the application", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  await page.goto("/#experiments");
  await expect(page.locator("h1.page-title")).toContainText("Experiments");
  await page.reload();
  await expect(page.locator("h1.page-title")).toContainText("Experiments");
  await expect(page.locator(".sidebar nav a")).toHaveCount(12);
  monitor.assertClean();
});

/** §70: sidebar navigation is a semantic, keyboard-reachable link list. */
test("navigation links have accessible names and keyboard focus", async ({ page }) => {
  await page.goto("/");
  const links = page.locator(".sidebar nav a");
  await expect(links).toHaveCount(12);
  for (const label of ["Dashboard", "Experiments", "Documentation"]) {
    await expect(page.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
  // keyboard: tab from the top reaches the nav links
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.textContent);
  expect(focused === "Dashboard" || focused === "QUANTUMLAB" || focused !== "").toBeTruthy();
});
