import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apiPort = process.env.QUANTUMLAB_E2E_API_PORT ?? "8100";
const webPort = process.env.QUANTUMLAB_E2E_WEB_PORT ?? "5183";
for (const port of [apiPort, webPort]) {
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535) {
    throw new Error("E2E ports must be integers between 1024 and 65535");
  }
}
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const webOrigin = `http://localhost:${webPort}`;
const directory = path.dirname(fileURLToPath(import.meta.url));
// One database per invocation; workers inherit the parent invocation's path.
process.env.QUANTUMLAB_E2E_DB ??= path.join(directory, `e2e-${process.pid}-${Date.now()}.db`);
process.env.QUANTUMLAB_E2E_API_ORIGIN = apiOrigin;

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
    baseURL: webOrigin,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  outputDir: "./test-results",
  webServer: [
    {
      command: `..\\.venv\\Scripts\\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../backend",
      url: `${apiOrigin}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        QUANTUMLAB_DB: process.env.QUANTUMLAB_E2E_DB,
        QUANTUMLAB_CORS_ORIGINS: `${webOrigin},http://127.0.0.1:${webPort}`,
      },
    },
    {
      command: `npm run dev -- --port ${webPort} --strictPort`,
      cwd: "../frontend",
      url: webOrigin,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_BASE_URL: apiOrigin },
    },
  ],
});
