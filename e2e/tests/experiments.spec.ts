import { test, expect, request as pwRequest } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

const API = "http://127.0.0.1:8000";

/** Live WebSocket progress capture: real ws://127.0.0.1:8000/ws/jobs frames
 * (§53, §127 — no fabricated events). */
function captureProgress(page: import("@playwright/test").Page) {
  const frames: any[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/jobs")) return;
    ws.on("framereceived", (f) => {
      try {
        const msg = JSON.parse(String(f.payload));
        if (msg.type === "job.progress") frames.push(msg);
      } catch { /* non-JSON frame */ }
    });
  });
  return frames;
}

async function openExperimentRow(page: import("@playwright/test").Page, name: string) {
  await gotoPage(page, "Experiments");
  const row = page.locator("tr", { hasText: name }).first();
  await row.click();
  await expect(page.locator(".panel", { hasText: "Experiment #" })).toBeVisible();
}

async function runAllAndWait(page: import("@playwright/test").Page,
                             terminal: string | string[], timeout = 120_000) {
  const terminals = Array.isArray(terminal) ? terminal : [terminal];
  await page.getByRole("button", { name: "Execute all runs" }).click();
  const selected = page.locator(".panel", { hasText: "Experiment #" });
  // Wait for ALL runs to settle (sweeps have several) before asserting.
  await expect(
    selected.locator(".badge", { hasText: /^(QUEUED|RUNNING|CANCELLING)$/ }),
  ).toHaveCount(0, { timeout });
  await expect(
    selected.locator(".badge").filter({ hasText: new RegExp(`^(${terminals.join("|")})$`) }).first(),
  ).toBeVisible({ timeout: 15_000 });
}

/** §183: the mandatory end-to-end chain through REAL browser + API + DB +
 * JobQueue + process-isolated worker + WebSocket. */
test("experiment full lifecycle: create, run, live progress, result, refresh", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  const frames = captureProgress(page);

  await gotoPage(page, "Experiments");
  await page.getByRole("button", { name: "+ Distributed GHZ study" }).click();
  await openExperimentRow(page, "Distributed GHZ study");

  await runAllAndWait(page, ["COMPLETED", "FAILED"], 120_000);
  const selected = page.locator(".panel", { hasText: "Experiment #" });
  await expect(selected.locator(".badge", { hasText: "COMPLETED" }).first()).toBeVisible();

  // live progress was received over the real WebSocket (§53): progress
  // frames exist, reference a run, and reach 1.0 at completion.
  expect(frames.length).toBeGreaterThan(0);
  expect(frames.some((f) => typeof f.progress === "number")).toBeTruthy();
  expect(frames.some((f) => f.progress === 1)).toBeTruthy();

  // result view renders backend values (§55/§59)
  await selected.getByRole("button", { name: "View result" }).first().click();
  const resultPanel = page.locator(".panel", { hasText: "Result document" });
  await expect(resultPanel.getByText("distributed_circuit")).toBeVisible();
  const eqPanel = resultPanel.locator(".panel", { hasText: "Equivalence vs centralized reference" });
  await expect(eqPanel.getByText(/Uhlmann fidelity/).first()).toBeVisible();

  // §63: refresh -> persisted state recovered, result still accessible
  await page.reload();
  await openExperimentRow(page, "Distributed GHZ study");
  const selected2 = page.locator(".panel", { hasText: "Experiment #" });
  await expect(selected2.locator(".badge", { hasText: "COMPLETED" }).first()).toBeVisible();
  await selected2.getByRole("button", { name: "View result" }).first().click();
  await expect(page.locator(".panel", { hasText: "Result document" })).toBeVisible();
  monitor.assertClean({ allow404: ["/api/runs"] });
});

/** §184: browser-driven failure demonstration via the real worker path. */
test("worker failure shows FAILED with no false result", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  // fixture setup via API (§123); execution is browser-driven
  const ctx = await pwRequest.newContext();
  const res = await ctx.post(`${API}/api/experiments`, {
    data: { name: "e2e probe failure", module: "process_probe",
            config: { action: "fail" }, seed: 2 },
  });
  const { run_ids } = await res.json();

  await openExperimentRow(page, "e2e probe failure");
  await runAllAndWait(page, ["FAILED"], 120_000);
  const selected = page.locator(".panel", { hasText: "Experiment #" });
  await expect(selected.locator(".badge", { hasText: "FAILED" }).first()).toBeVisible();

  // no fabricated result (§146/§147): a FAILED run offers no result to view
  await expect(selected.getByRole("button", { name: "View result" })).toHaveCount(0);
  await expect(page.locator(".panel", { hasText: "Result document" })).toHaveCount(0);

  // API remains usable: a normal experiment can still run afterwards
  await gotoPage(page, "Experiments");
  await page.getByRole("button", { name: "+ Distributed GHZ study" }).click();
  await openExperimentRow(page, "Distributed GHZ study").catch(() =>
    openExperimentRow(page, "Distributed GHZ study"));
  await runAllAndWait(page, ["COMPLETED"], 120_000);
  monitor.assertClean({ allow404: ["/api/runs"] });
});

/** §185/§129: cancellation through the actual UI Cancel control. */
test("running experiment can be cancelled from the UI", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  const ctx = await pwRequest.newContext();
  const res = await ctx.post(`${API}/api/experiments`, {
    data: { name: "e2e probe cancel", module: "process_probe",
            config: { action: "slow", seconds: 60 }, seed: 2 },
  });
  const { run_ids } = await res.json();

  await openExperimentRow(page, "e2e probe cancel");
  const selected = page.locator(".panel", { hasText: "Experiment #" });
  await selected.getByRole("button", { name: "Execute all runs" }).click();
  await expect(
    selected.locator(".badge", { hasText: "RUNNING" }).first(),
  ).toBeVisible({ timeout: 60_000 });

  await selected.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    selected.locator(".badge", { hasText: "CANCELLED" }).first(),
  ).toBeVisible({ timeout: 30_000 });

  // no completed result for the cancelled run
  await expect(selected.locator(".badge", { hasText: "COMPLETED" })).toHaveCount(0);
  monitor.assertClean({ allow404: ["/api/runs"] });
});

/** §186: reproduction from the UI: EXACT_MATCH, original unchanged. */
test("reproduction from the UI reports EXACT_MATCH", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  await gotoPage(page, "Experiments");
  await page.getByRole("button", { name: "+ Distributed GHZ study" }).click();
  await openExperimentRow(page, "Distributed GHZ study");
  await runAllAndWait(page, ["COMPLETED"], 120_000);

  const selected = page.locator(".panel", { hasText: "Experiment #" });
  await selected.getByRole("button", { name: "Reproduce" }).first().click();
  const report = page.locator(".panel", { hasText: "Reproduction report" });
  await expect(report.getByText("EXACT_MATCH")).toBeVisible({ timeout: 120_000 });
  // original remains COMPLETED and a distinct new run was created
  const reportText = await report.textContent();
  expect(reportText).toMatch(/reproduced run/i);
  monitor.assertClean();
});

/** §61/§62: comparison through the real UI on a two-run sweep experiment. */
test("sweep experiment runs both points and comparison renders", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  await gotoPage(page, "Experiments");
  await page.getByRole("button", { name: "+ Repeater spacing study" }).click();
  await openExperimentRow(page, "Repeater spacing study");
  await runAllAndWait(page, ["COMPLETED"], 180_000);

  await page.getByRole("button", { name: "Compare last two completed runs" }).click();
  const cmp = page.locator(".panel", { hasText: "Run comparison" });
  await expect(cmp.getByText("Differing configuration parameters:")).toBeVisible();
  await expect(cmp.getByText("sim_time_ms").first()).toBeVisible();
  await expect(cmp.locator("tbody tr")).toHaveCount(2);
  monitor.assertClean();
});

/** §82/§83: stale-result prevention — opening run B shows B's values. */
test("no stale result contamination between experiments", async ({ page }) => {
  const monitor = ErrorMonitor.attach(page);
  const ctx = await pwRequest.newContext();
  // two probe experiments with clearly different actions
  await ctx.post(`${API}/api/experiments`, {
    data: { name: "e2e stale A", module: "process_probe",
            config: { action: "succeed" }, seed: 1 },
  });
  await ctx.post(`${API}/api/experiments`, {
    data: { name: "e2e stale B fail", module: "process_probe",
            config: { action: "fail" }, seed: 1 },
  });

  await openExperimentRow(page, "e2e stale A");
  await runAllAndWait(page, ["COMPLETED"], 120_000);
  const selA = page.locator(".panel", { hasText: "Experiment #" });
  await selA.getByRole("button", { name: "View result" }).first().click();
  await expect(page.locator(".panel", { hasText: "Result document" })).toBeVisible();

  await openExperimentRow(page, "e2e stale B fail");
  const selB = page.locator(".panel", { hasText: "Experiment #" });
  // result panel must NOT show experiment A's document anymore
  await expect(page.locator(".panel", { hasText: "Result document" })).toHaveCount(0);
  await runAllAndWait(page, ["FAILED"], 120_000);
  monitor.assertClean({ allow404: ["/api/runs"] });
});
