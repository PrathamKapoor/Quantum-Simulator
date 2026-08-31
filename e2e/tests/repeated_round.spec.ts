import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Repeated-round (space-time) surface-code workflow through the real
 * browser + backend (§75-§80). */
test.describe("Repeated-round surface code", () => {
  test("decode renders space-time lattice, events, verdict", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Repeated-round surface code" });
    await panel.getByRole("button", { name: "Decode repeated rounds" }).click();
    await expect(panel.getByText(/Outcome:/)).toBeVisible({ timeout: 30_000 });
    await expect(
      panel.locator(".badge").filter({ hasText: /CORRECTED|LOGICAL_[XYZ]/ }),
    ).toBeVisible();
    // space-time lattice SVG is rendered from backend data
    await expect(
      panel.locator("svg[aria-label='space-time detection lattice']"),
    ).toBeVisible();
    // match table and observed-syndrome history available
    await expect(panel.getByText(/detection events/i).first()).toBeVisible();
    await expect(panel.getByText("Observed syndrome history")).toBeVisible();
    monitor.assertClean();
  });

  test("Monte Carlo renders p_L and Wilson CI", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Repeated-round surface code" });
    await panel.getByLabel("MC trials").fill("500");
    await panel.getByRole("button", { name: "Run Monte Carlo (repeated-round)" }).click();
    await expect(panel.getByText(/logical error rate p_L/)).toBeVisible({
      timeout: 90_000,
    });
    await expect(panel.getByText(/Wilson 95% CI/)).toBeVisible();
    monitor.assertClean();
  });

  test("rounds input is clamped and the app stays usable", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Repeated-round surface code" });
    // The rounds control clamps out-of-range values to [1, 16] in the UI; a
    // value of 0 is coerced to 1 rather than sent to the backend, so no error
    // state appears (invalid-input REJECTION is enforced by the backend API,
    // covered by backend tests §58).
    const roundsInput = panel.getByLabel("Rounds");
    await roundsInput.fill("0");
    await expect(roundsInput).toHaveValue("1");
    await page.getByRole("button", { name: "Decode repeated rounds" }).first().click();
    await expect(panel.getByText(/Outcome:/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Quantum Error Correction" }))
      .toBeVisible();
    monitor.assertClean();
  });
});