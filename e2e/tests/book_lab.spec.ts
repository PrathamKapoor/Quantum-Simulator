import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Book Laboratory (milestone 22): chapter experiments through the real
 * process-isolated worker, with backend-computed validation. */
test.describe("Book Laboratory", () => {
  test("runs an experiment end to end and renders validation", async ({
    page,
  }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Book Lab");
    const panel = page.locator(".panel", {
      hasText: "Book Laboratory",
    });
    await panel
      .getByRole("button", { name: "Run experiment" })
      .click();
    await expect(panel.getByText(/Result:/)).toBeVisible({
      timeout: 120_000,
    });
    await expect(
      panel.locator(".badge").filter({ hasText: /PASSED|FAILED/ }),
    ).toBeVisible();
    await expect(panel.getByText(/Validation \(backend-computed\)/)).toBeVisible();
    monitor.assertClean();
  });
});
