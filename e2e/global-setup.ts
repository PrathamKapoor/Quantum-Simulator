/** The Playwright config assigns a unique database before servers start.
 * Never delete a database here: global setup can run after webServer startup.
 */
export default function globalSetup() {
  if (!process.env.QUANTUMLAB_E2E_DB) {
    throw new Error("E2E database isolation was not configured");
  }
}
