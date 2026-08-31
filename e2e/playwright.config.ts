import { defineConfig } from "@playwright/test";

/**
 * QuantumLab end-to-end browser validation (E2E milestone).
 *
 * Launches the REAL backend (uvicorn, isolated QUANTUMLAB_DB test database)
 * and the REAL frontend (vite dev server) — no mocks anywhere in the
 * acceptance suite. Chromium only; desktop + reduced-width viewports.
 */
export default defineConfig({
  globalSetup: "./global-setup.ts",
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,          // shared server state; deterministic order
  workers: 1,
  retries: 0,                    // flakiness must be root-caused (§103)
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  outputDir: "./test-results",
  webServer: [
    {
      command: "..\\.venv\\Scripts\\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
      env: {
        QUANTUMLAB_DB: "../e2e/e2e-test.db",
      },
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      cwd: "../frontend",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
