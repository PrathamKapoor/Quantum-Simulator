import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Circuit-aware hybrid decoder workflow (milestone 13, AD-019). */
test.describe("Circuit-aware hybrid decoder", () => {
  test("decoder comparison renders p_L and Wilson CI", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Circuit-aware hybrid decoder",
    });
    await expect(panel).toBeVisible();
    await panel.getByLabel("MC trials").fill("200");
    await panel.getByRole("button", { name: "Run hybrid decoder MC" }).click();
    await expect(panel.getByText(/Decoder:.*circuit_aware_hybrid/)).toBeVisible({
      timeout: 60_000,
    });
    await expect(panel.getByText(/Multi-event mechanisms considered/)).toBeVisible();
    monitor.assertClean();
  });
});
