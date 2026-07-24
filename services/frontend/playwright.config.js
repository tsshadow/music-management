import { defineConfig } from "@playwright/test";

// Browser integration tests (Task 7 / Phase 5.2 of the test plan).
// Assumes the core test stack (docker/compose.test.yml) is already running
// and reachable at the ports it publishes (see scripts/test/frontend-browser.sh).
// Starts the frontend dev server pointed at that stack via VITE_API_TARGET /
// VITE_LMS_TARGET (see vite.config.js), then runs the browser tests against it.
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5174",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    // A dedicated port (5174, not the default dev port 5173) so this never
    // collides with a developer's own `npm run dev` session.
    command: "npm run dev -- --port 5174 --strictPort",
    url: "http://localhost:5174",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      VITE_API_TARGET: process.env.VITE_API_TARGET || "http://localhost:18000",
      VITE_LMS_TARGET: process.env.VITE_LMS_TARGET || "http://localhost:15082",
    },
  },
});
