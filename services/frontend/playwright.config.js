import { defineConfig } from "@playwright/test";

// Browser integration tests (Task 7 / Phase 5.2 of the test plan).
// Assumes the core test stack (docker/compose.test.yml) is already running
// and reachable at the ports it publishes (see scripts/test/frontend-browser.sh).
// Builds the frontend and serves it with `vite preview`, pointed at that stack
// via VITE_API_TARGET / VITE_LMS_TARGET (see vite.config.js), then runs the
// browser tests against it.
//
// Deliberately the built bundle rather than the dev server. The dev server
// serves an empty #app until Vite has finished dependency pre-bundling and
// triggered a full reload -- ~2s locally, but repeatedly over 30s and once
// over 120s on a loaded runner, which failed release/0.0.58's pipeline and
// then develop's while the app itself was fine. A built bundle has no
// pre-bundling step, so the page either renders or it does not. It is also
// what users actually get.
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
  // junit next to list: .gitlab-ci.yml uploads test-results/junit-browser.xml
  // into the GitLab test tab, so a browser failure is visible without reading
  // the raw job log. Harmless locally -- the file just lands in test-results/.
  reporter: [["list"], ["junit", { outputFile: "test-results/junit-browser.xml" }]],
  use: {
    baseURL: devServerUrl,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    // The build happens here rather than in the shell script so that running
    // `npx playwright test` by hand works the same way CI does.
    command: `npm run build && npm run preview -- --port ${devServerPort} --strictPort`,
    url: devServerUrl,
    reuseExistingServer: false,
    // Covers the production build on a busy runner; serving is instant after.
    timeout: 180_000,
    env: {
      VITE_API_TARGET: process.env.VITE_API_TARGET || "http://localhost:18000",
      VITE_LMS_TARGET: process.env.VITE_LMS_TARGET || "http://localhost:15082",
    },
  },
});
