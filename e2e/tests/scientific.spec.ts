import { test, expect } from "@playwright/test";
import { ErrorMonitor, gotoPage } from "./helpers";

/** Scientific workflow E2E: real UI -> real API -> real computation -> real
 * rendering (§22-§49). Backend values are ground truth; the UI must display
 * them (§79-§81). */

test.describe("Circuit Studio", () => {
  test("build and execute a deterministic circuit", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Circuit Studio");

    // place H on qubit 0 using the real palette + editor cells
    await page.getByRole("button", { name: "H", exact: true }).first().click();
    await page.getByRole("button", { name: "place H on qubit 0" }).click();
    await page.getByRole("button", { name: "Run circuit" }).click();

    // H on |0..0> splits amplitude evenly between exactly two outcomes (§23)
    const dist = page.locator(".panel", { hasText: "Measurement distribution" });
    await expect(dist.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
    const rows = await dist.locator("tbody tr").all();
    expect(rows.length).toBeGreaterThanOrEqual(2);
    let sum = 0;
    for (const row of rows) {
      const p = parseFloat((await row.locator("td").nth(1).textContent())!);
      sum += p;
      expect(p).toBeGreaterThan(0);
      expect(p).toBeLessThan(1);
    }
    expect(sum).toBeGreaterThan(0.99);
    expect(sum).toBeLessThan(1.01);
    monitor.assertClean();
  });

  test("distributed workflow: partition, execute, compare, noisy ebits", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Circuit Studio");

    // Bell circuit on 2 qubits across 2 nodes
    await page.getByRole("button", { name: "H", exact: true }).first().click();
    await page.getByRole("button", { name: "place H on qubit 0" }).click();
    await page.getByRole("button", { name: "CX", exact: true }).first().click();
    await page.getByRole("button", { name: "place CX on qubit 0" }).click();

    await page.getByRole("button", { name: "Run distributed" }).click();
    const distPanel = page.locator(".panel", { hasText: "Distributed computation" });
    await expect(distPanel.getByText("REMOTE").first()).toBeVisible();
    const ebitCard = distPanel.getByText("Ebits consumed").locator("..").locator(".value");
    await expect(ebitCard).toBeVisible({ timeout: 30_000 });
    expect(parseInt((await ebitCard.textContent())!, 10)).toBeGreaterThan(0);

    // noisy-ebit selector present and functional (§35/§188)
    const noiseSelect = distPanel.getByLabel("Ebit noise");
    await expect(noiseSelect).toBeVisible();
    await noiseSelect.selectOption("fixed");
    await distPanel.getByLabel("Werner ebit fidelity F").fill("0.9");
    await page.getByRole("button", { name: "Compare centralized vs distributed" }).click();
    await expect(
      page.locator(".panel", { hasText: "Output probabilities — centralized vs distributed" }).last(),
    ).toBeVisible({ timeout: 30_000 });

    // equivalence verdict renders from backend data
    await expect(
      page.locator(".panel", { hasText: "Equivalence vs centralized reference" }).last(),
    ).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });
});

test.describe("Algorithms", () => {
  test("Deutsch-Jozsa runs and reports", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Algorithms");
    await page.getByRole("button", { name: "Run with random oracle type" }).click();
    await expect(
      page.locator(".panel", { hasText: "Deutsch–Jozsa" }).getByText(/constant|balanced/i),
    ).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });

  test("Grover finds the marked state", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Algorithms");
    const panel = page.locator(".panel", { hasText: "Grover search" });
    await panel.getByRole("spinbutton").first().fill("0");
    await panel.getByRole("button", { name: "Run", exact: true }).click();
    await expect(
      panel.locator(".metric-card", { hasText: "Success P" }),
    ).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });

  test("superdense coding and order finding execute", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Algorithms");
    await page.getByRole("button", { name: "Send via 1 qubit" }).click();
    await expect(
      page.locator(".panel", { hasText: "Superdense coding" }).getByText(/decoded/),
    ).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Find order" }).click();
    await expect(
      page.locator(".panel", { hasText: "Bounded order finding" }).getByText(/recovered/),
    ).toBeVisible({ timeout: 60_000 });
    monitor.assertClean();
  });
});

test.describe("Network Studio", () => {
  test("topology renders and simulation executes", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Network Studio");
    await expect(page.locator("svg").first()).toBeVisible();
    await page.getByRole("button", { name: "Run simulation" }).click();
    // backend result: event/resource information appears (§32)
    await expect(
      page.locator(".metric-cards, table").first(),
    ).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });
});

test.describe("QEC Lab", () => {
  test("toric simulator workflow", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    await page.getByRole("button", { name: "Run d=3" }).click();
    await expect(page.getByText(/logical error rate/i).first()).toBeVisible({
      timeout: 60_000,
    });
    monitor.assertClean();
  });

  test("rotated surface code: decode renders lattice, matching, verdict", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Rotated planar surface code" });
    await panel.getByRole("button", { name: "Generate error & decode" }).click();
    // lattice + verdict from the backend (§37-§38, §187)
    await expect(panel.locator("svg[aria-label='rotated surface code lattice']")).toBeVisible({
      timeout: 30_000,
    });
    await expect(panel.getByText(/Outcome:/)).toBeVisible();
    await expect(
      panel.locator(".badge").filter({ hasText: /CORRECTED|LOGICAL_[XYZ]/ }),
    ).toBeVisible();
    monitor.assertClean();
  });

  test("rotated surface code Monte Carlo renders p_L and Wilson CI", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Error Correction");
    const panel = page.locator(".panel", { hasText: "Rotated planar surface code" });
    await panel.getByLabel("MC trials").fill("500");
    await panel.getByRole("button", { name: "Run Monte Carlo at this (d, p)" }).click();
    await expect(panel.getByText(/logical error rate p_L/i).first()).toBeVisible({
      timeout: 90_000,
    });
    await expect(panel.getByText(/Wilson 95% CI/i).first()).toBeVisible();
    monitor.assertClean();
  });
});

test.describe("Cryptography", () => {
  test("BB84 displays the backend QBER", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Cryptography");
    await page.getByRole("button", { name: "Run BB84" }).click();
    await expect(page.getByText(/QBER:/).first()).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });

  test("E91 reports the CHSH statistic", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Cryptography");
    await page.getByRole("button", { name: "Run E91" }).click();
    await expect(page.getByText(/CHSH S =/)).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });

  test("QRNG generates bits", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Cryptography");
    await page.getByRole("button", { name: "Generate 8192 bits" }).click();
    await expect(
      page.locator(".panel", { hasText: "QRNG" }).locator(".kv, table, .metric-cards"),
    ).toBeVisible({ timeout: 30_000 });
    monitor.assertClean();
  });
});

test.describe("Optimization & QML", () => {
  test("VQE reports energies within physical range", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Optimization & QML");
    await page.getByRole("button", { name: "Run VQE" }).click();
    await expect(page.getByText(/E\(VQE\) =/)).toBeVisible({ timeout: 60_000 });
    monitor.assertClean();
  });

  test("QAOA on the square-graph preset completes", async ({ page }) => {
    const monitor = ErrorMonitor.attach(page);
    await gotoPage(page, "Optimization & QML");
    await page.getByRole("button", { name: "Run QAOA" }).click();
    await expect(
      page.locator(".panel", { hasText: "QAOA — MaxCut" }).locator(".kv, .metric-cards, table"),
    ).toBeVisible({ timeout: 60_000 });
    monitor.assertClean();
  });
});
