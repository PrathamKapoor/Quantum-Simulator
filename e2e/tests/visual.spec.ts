import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Visual validation (§68-§69, §112, §116, §189): capture loaded/result
 * states for every major surface, then INSPECT the screenshots. Screenshots
 * go to e2e/screenshots/ (gitignored — evidence, not artifacts). */

const OUT = "screenshots";

async function shot(page: import("@playwright/test").Page, name: string) {
  await page.waitForTimeout(400); // let charts/svg settle
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

test.describe.serial("visual evidence capture", () => {
  test("dashboard", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "QuantumLab" })).toBeVisible();
    await shot(page, "dashboard");
    monitor.assertClean();
  });

  test("circuit studio with executed result", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Circuit Studio");
    await page.getByRole("button", { name: "H", exact: true }).first().click();
    await page.getByRole("button", { name: "place H on qubit 0" }).click();
    await page.getByRole("button", { name: "Run circuit" }).click();
    await expect(
      page.locator(".panel", { hasText: "Measurement distribution" }).locator("tbody tr").first(),
    ).toBeVisible({ timeout: 30_000 });
    await shot(page, "circuit-result");
    monitor.assertClean();
  });

  test("network studio", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Network Studio");
    await page.getByRole("button", { name: "Run simulation" }).click();
    await page.waitForTimeout(1500);
    await shot(page, "network");
    monitor.assertClean();
  });

  test("qec lab with decoded lattice", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Rotated planar surface code" });
    await panel.getByRole("button", { name: "Generate error & decode" }).click();
    await expect(panel.locator("svg[aria-label='rotated surface code lattice']")).toBeVisible({
      timeout: 30_000,
    });
    await shot(page, "qec-lattice");
    monitor.assertClean();
  });

  test("experiments with distributed result", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Experiments");
    await page.getByRole("button", { name: "+ Distributed GHZ study" }).click();
    await page.locator("tr", { hasText: "Distributed GHZ study" }).first().click();
    const selected = page.locator(".panel", { hasText: "Experiment #" });
    await selected.getByRole("button", { name: "Execute all runs" }).click();
    await expect(
      selected.locator(".badge", { hasText: /^(QUEUED|RUNNING|CANCELLING)$/ }),
    ).toHaveCount(0, { timeout: 120_000 });
    await selected.getByRole("button", { name: "View result" }).first().click();
    await expect(page.locator(".panel", { hasText: "Result document" })).toBeVisible();
    await shot(page, "experiments-result");
    monitor.assertClean({ allow404: ["/api/runs"] });
  });

  test("cryptography and optimization", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Cryptography");
    await page.getByRole("button", { name: "Run BB84" }).click();
    await expect(page.getByText(/QBER:/).first()).toBeVisible({ timeout: 30_000 });
    await shot(page, "crypto");
    await gotoPage(page, "Optimization & QML");
    await page.getByRole("button", { name: "Run VQE" }).click();
    await expect(page.getByText(/E\(VQE\) =/)).toBeVisible({ timeout: 60_000 });
    await shot(page, "optimize");
    monitor.assertClean();
  });

  test("documentation", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Documentation");
    await page.waitForTimeout(800);
    await shot(page, "docs");
    monitor.assertClean();
  });

  test("dark theme renders", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Toggle color theme/ }).click();
    await expect(page.getByRole("heading", { name: "QuantumLab" })).toBeVisible();
    await shot(page, "dashboard-dark");
    await gotoPage(page, "Error Correction");
    await shot(page, "qec-dark");
    monitor.assertClean();
  });

  test("reduced-width viewport remains usable", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 820, height: 900 } });
    const page = await context.newPage();
    const monitor = ErrorMonitor.attach(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "QuantumLab" })).toBeVisible();
    // no horizontal overflow of the document (§67/§113)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(8);
    await gotoPage(page, "Experiments");
    await expect(page.getByRole("heading", { name: "Experiments", exact: true })).toBeVisible();
    await shot(page, "experiments-narrow");
    monitor.assertClean();
    await context.close();
  });
});
