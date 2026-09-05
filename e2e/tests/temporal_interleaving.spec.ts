import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Temporal-interleaving workflow (milestone 15, AD-020). */
test.describe("Temporal interleaving", () => {
  test("paired comparison renders standard vs alternating", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Temporal interleaving",
    });
    await expect(panel).toBeVisible();
    await panel.getByLabel("Trials").fill("100");
    await panel.getByRole("button", { name: "Run paired comparison" }).click();
    await expect(panel.getByText(/standard \(all stabilizers per round\)/)).toBeVisible({
      timeout: 90_000,
    });
    await expect(panel.getByText(/alternating \(X in odd, Z in even rounds\)/)).toBeVisible();
    monitor.assertClean();
  });
});
