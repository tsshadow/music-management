import { defineConfig } from "@playwright/test";

// Browser integration tests (Task 7 / Phase 5.2 of the test plan).
// Assumes the core test stack (docker/compose.test.yml) is already running
// and reachable at the ports it publishes (see scripts/test/frontend-browser.sh).
// Starts the frontend dev server pointed at that stack via VITE_API_TARGET /
// VITE_LMS_TARGET (see vite.config.js), then runs the browser tests against it.
// A dedicated port (not the default dev port 5173) so this never collides with
// a developer's own `npm run dev` session. In CI two pipelines can share one
// runner, so scripts/test/frontend-browser.sh picks a free port per job and
// passes it in here - a fixed port made concurrent jobs fail with
// "http://localhost:5174 is already used".
const devServerPort = process.env.MUMA_TEST_PORT_FRONTEND || "5174";
const devServerUrl = `http://localhost:${devServerPort}`;

export default defineConfig({
  testDir: "./tests/browser",
  // Pays for Vite's cold start once, before the tests, so their timeouts measure
  // the app rather than the runner's load. See tests/browser/global-setup.js.
  globalSetup: "./tests/browser/global-setup.js",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: devServerUrl,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: `npm run dev -- --port ${devServerPort} --strictPort`,
    url: devServerUrl,
    reuseExistingServer: false,
    // Starting the dev server is cheap; it is the first request that compiles.
    // Kept above Vite's own start-up on a loaded runner all the same.
    timeout: 60_000,
    env: {
      VITE_API_TARGET: process.env.VITE_API_TARGET || "http://localhost:18000",
      VITE_LMS_TARGET: process.env.VITE_LMS_TARGET || "http://localhost:15082",
    },
  },
});
