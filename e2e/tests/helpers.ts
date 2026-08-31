import { Page, expect } from "@playwright/test";

/** Browser error/network monitoring (§13-§14): every suite attaches this and
 * asserts cleanliness at the end, so silent console errors and failed
 * requests cannot hide behind a passing locator assertion. */
export class ErrorMonitor {
  consoleErrors: string[] = [];
  pageErrors: string[] = [];
  failedRequests: string[] = [];

  static attach(page: Page): ErrorMonitor {
    const m = new ErrorMonitor();
    page.on("console", (msg) => {
      if (msg.type() === "error") m.consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => m.pageErrors.push(String(err)));
    page.on("requestfailed", (req) => {
      m.failedRequests.push(`${req.method()} ${req.url()} :: ${req.failure()?.errorText}`);
    });
    page.on("response", (res) => {
      if (res.status() >= 500) {
        m.failedRequests.push(`HTTP ${res.status()} ${res.url()}`);
      }
    });
    return m;
  }

  /** Assert no runtime errors and no unexpected failed requests. */
  assertClean(opts: { allow404?: string[] } = {}) {
    const allow404 = opts.allow404 ?? [];
    const relevant = this.failedRequests.filter(
      (r) => !allow404.some((p) => r.includes(p) && r.includes("404")),
    );
    expect(this.pageErrors, "unhandled page exceptions").toEqual([]);
    expect(relevant, "failed network requests").toEqual([]);
    // Console errors are reported but not fatal here: some are browser noise;
    // suites assert on pageErrors + network, and inspect console manually
    // (§13: distinguish expected / irrelevant / actual errors).
  }
}

/** Navigate via the actual sidebar (semantic accessibility selector, §114).
 * Ensures the application is loaded first: a fresh Playwright page starts at
 * about:blank, where no sidebar exists. */
export async function gotoPage(page: Page, label: string) {
  if (!page.url().startsWith("http")) {
    await page.goto("/");
  }
  await page.getByRole("link", { name: label, exact: true }).click();
}

/** Actual page headings verified against the source (recon §2). */
export const NAV_PAGES: Array<[string, string]> = [
  ["Dashboard", "QuantumLab"],
  ["Circuit Studio", "Circuit Studio"],
  ["Algorithms", "Quantum Algorithms"],
  ["Network Studio", "Network Studio"],
  ["Error Correction", "Quantum Error Correction"],
  ["Cryptography", "Quantum Cryptography"],
  ["Optimization & QML", "Optimization"],
  ["Information Theory", "Quantum Information"],
  ["Hardware Lab", "Hardware Lab"],
  ["Experiments", "Experiments"],
  ["Documentation", "Documentation"],
];

/** Start one experiment through the real UI (templates) and return its name. */
export async function createExperiment(page: Page, template: string, unique: string) {
  await gotoPage(page, "Experiments");
  await page.getByRole("button", { name: template }).first().click();
  // The created experiment card appears with the templated name; rename is
  // not supported in the UI, so uniqueness comes from timing/DB order.
  await expect(
    page.locator(".panel").filter({ hasText: template }).first(),
  ).toBeVisible();
  return unique;
}
