import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** SAT-SA (Supervisory Analytics Tool for SOC Assessment) end-to-end
 * workflow. Phase 13 + 14 + 15. */
test.describe("SAT-SA", () => {
  test("demo loads and pipeline runs", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "SAT-SA");
    // Navigate to Demo tab.
    await page.getByRole("button", { name: "Demo" }).click();
    await expect(page.getByText(/Load Demonstration Assessment/)).toBeVisible();
    // Click the Load demo button (default CSE-002).
    await page.getByRole("button", { name: "Load demo" }).click();
    // Submission summary appears.
    await expect(page.getByText(/Ground truth:/)).toBeVisible({
      timeout: 30_000,
    });
    monitor.assertClean();
  });

  test("run pipeline produces risk + observations", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "SAT-SA");
    // Click Overview; the panel has a "Load Demo Assessment" button.
    await page.getByRole("button", { name: "Overview" }).click();
    await page.getByRole("button", { name: /Load Demo Assessment/ }).click();
    // Wait for risk panel with "Overall risk" text.
    await expect(page.getByText(/Overall risk/)).toBeVisible({
      timeout: 30_000,
    });
    monitor.assertClean();
  });
});
