import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Hook-error forensic workflow (milestone 14, Phase B). */
test.describe("Hook-error forensics", () => {
  test("forensic analysis renders per-stabilizer table", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", {
      hasText: "Hook-error forensics",
    });
    await expect(panel).toBeVisible();
    await panel.getByRole("button", { name: "Run hook forensics" }).click();
    await expect(panel.getByText(/Total reports/)).toBeVisible({
      timeout: 30_000,
    });
    // The per-stabilizer table has at least one row.
    await expect(panel.locator("table.data-table tbody tr").first()).toBeVisible();
    monitor.assertClean();
  });
});
