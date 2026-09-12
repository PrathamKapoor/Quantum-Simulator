import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Circuit-level surface-code workflow (§R). */
test.describe("Circuit-level surface code", () => {
  test("decode renders verdict, hooks, and match table", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Circuit-level surface code" });
    await panel.getByRole("button", { name: "Decode circuit-level" }).click();
    await expect(panel.getByText(/Outcome:/)).toBeVisible({ timeout: 30_000 });
    await expect(
      panel.locator(".badge").filter({ hasText: /CORRECTED|LOGICAL_[XYZ]/ }),
    ).toBeVisible();
    await expect(panel.getByText("Hook errors", { exact: true })).toBeVisible();
    await expect(panel.getByText("Data X errors", { exact: true })).toBeVisible();
    monitor.assertClean();
  });

  test("Monte Carlo renders p_L and Wilson CI", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Circuit-level surface code" });
    await panel.getByLabel("MC trials").fill("500");
    await panel.getByRole("button", { name: "Run Monte Carlo (circuit-level)" }).click();
    await expect(panel.getByText(/logical error rate p_L/)).toBeVisible({
      timeout: 90_000,
    });
    await expect(panel.getByText(/Wilson 95% CI/)).toBeVisible();
    monitor.assertClean();
  });

  test("Schedule selector runs MC with optimized schedule", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Circuit-level surface code" });
    await panel.getByLabel("MC trials").fill("200");
    await panel.getByLabel("Schedule").selectOption("optimized");
    await panel.getByRole("button", { name: "Run Monte Carlo (circuit-level)" }).click();
    await expect(panel.getByText(/logical error rate p_L/)).toBeVisible({
      timeout: 90_000,
    });
    monitor.assertClean();
  });

  test("Extraction selector switches to Shor cat-state and renders", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Circuit-level surface code" });
    await panel.getByLabel("Extraction").selectOption("shor_cat_state");
    await panel.getByRole("button", { name: "Decode circuit-level" }).click();
    await expect(panel.getByText(/Outcome:/)).toBeVisible({ timeout: 60_000 });
    // The AD-021 honest caveat must be visible so the user knows the
    // comparison is real, not a recommendation.
    await expect(panel.getByText(/makes p_L/)).toBeVisible();
    monitor.assertClean();
  });
});
  test("Verified Shor selector runs and reports rejection statistics", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Circuit-level surface code" });
    await panel.getByLabel("Extraction").selectOption("shor_cat_state_verified");
    await panel.getByLabel("MC trials").fill("200");
    await panel.getByRole("button", { name: "Run Monte Carlo (circuit-level)" }).click();
    await expect(panel.getByText(/logical error rate p_L/)).toBeVisible({
      timeout: 90_000,
    });
    monitor.assertClean();
  });
