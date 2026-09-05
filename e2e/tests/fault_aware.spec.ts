import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Fault-aware schedule analysis + circuit-derived decoder graph (AD-018,
 * milestone 12). */
test.describe("Fault-aware scheduling & circuit-derived decoder graph", () => {
  test("schedule analysis reports per-stabilizer risk", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Fault-aware scheduling & circuit-derived decoder graph",
    });
    await expect(panel).toBeVisible();
    await panel.getByRole("button", { name: "Run schedule analysis" }).click();
    await expect(panel.getByText(/Changed stabilizers:/)).toBeVisible({
      timeout: 30_000,
    });
    // The table has at least one stabilizer row.
    await expect(panel.locator("table.data-table tbody tr").first()).toBeVisible();
    monitor.assertClean();
  });

  test("circuit-derived graph coverage reported", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Fault-aware scheduling & circuit-derived decoder graph",
    });
    await panel.getByRole("button", { name: "Build graph" }).click();
    await expect(panel.getByText(/Vertices:/)).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByText(/Exact pairwise coverage/)).toBeVisible();
    await expect(panel.getByText(/Multi-event excluded/)).toBeVisible();
    monitor.assertClean();
  });

  test("Monte Carlo renders p_L with graph coverage", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Fault-aware scheduling & circuit-derived decoder graph",
    });
    await panel.getByLabel("MC trials").fill("300");
    await panel.getByRole("button", { name: "Run MC with graph coverage" }).click();
    await expect(panel.getByText(/Graph coverage:/)).toBeVisible({
      timeout: 90_000,
    });
    monitor.assertClean();
  });
});
