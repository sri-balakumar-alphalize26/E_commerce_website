/* End-to-end tests for the admin console.
 *
 * Drives the Edge that is already on the machine (`channel: "msedge"`), so
 * nothing is downloaded and the tests run against the same browser the shop is
 * checked in by hand.
 *
 * No `webServer`: the dev server and Odoo are long-running and shared, and
 * starting a second Next dev server against the same .next directory breaks
 * hydration in the one already running. Start them yourself; the tests fail
 * with a clear message if they are not up.
 */
import { defineConfig, devices } from "@playwright/test";

const BASE = process.env.MART_BASE_URL || "http://localhost:3000";

export default defineConfig({
  testDir: "./tests/e2e",
  /* A cold Next route can take well over a minute to compile the first time it
     is asked for, and these tests are usually the first to ask. */
  timeout: 180000,
  expect: { timeout: 30000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE,
    viewport: { width: 1600, height: 1100 },
    actionTimeout: 30000,
    navigationTimeout: 120000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "edge", use: { ...devices["Desktop Edge"], channel: "msedge" } }],
});
