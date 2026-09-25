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

// The two layouts the app is designed for. `App.svelte` switches to the phone
// shell below 1024px (or on a coarse pointer), so the desktop width must stay
// above that and the phone width below it; 412x915 is a common Android phone.
export const DESKTOP_VIEWPORT = { width: 1280, height: 800 };
export const PHONE_VIEWPORT = { width: 412, height: 915 };

// Where the `setup` project leaves the logged-in browser state for the
// screenshot suite. Under test-results/ so it is gitignored and uploaded with
// the rest of the run.
export const ADMIN_STORAGE_STATE = "test-results/.auth/admin.json";

export default defineConfig({
  testDir: "./tests/browser",
  // Pays for Vite's cold start once, before the tests, so their timeouts measure
  // the app rather than the runner's load. See tests/browser/global-setup.js.
  globalSetup: "./tests/browser/global-setup.js",
  timeout: 60_000,
  retries: 0,
  // The stack behind the app is created cold per job and the LMS proxy to MuMa
  // is a serial queue, so the forty-odd screenshot tests are throttled in CI
  // rather than let loose at the runner's core count: a burst of first
  // requests there turns into timeouts that read as broken views.
  workers: process.env.CI ? 2 : undefined,
  // junit next to list: .gitlab-ci.yml uploads test-results/junit-browser.xml
  // into the GitLab test tab, so a browser failure is visible without reading
  // the raw job log. Harmless locally -- the file just lands in test-results/.
  reporter: [["list"], ["junit", { outputFile: "test-results/junit-browser.xml" }]],
  // Reference screenshots live next to the spec, one folder per layout, named
  // after the route: tests/browser/__screenshots__/phone/browse.png. The
  // default template appends the platform (`-linux`) and the browser, which is
  // noise here -- the suite only ever renders on the one CI runner (see
  // scripts/test/frontend-browser.sh) -- and would stop the folder from
  // doubling as the documentation set docs/frontend-screenshots.md points at.
  snapshotPathTemplate: "{testDir}/__screenshots__/{projectName}/{arg}{ext}",
  expect: {
    toHaveScreenshot: {
      // Half a percent: 5.000 pixels on the desktop, 1.900 on the phone. The
      // per-pixel colour threshold Playwright applies on top already absorbs
      // anti-aliasing; this is for a line of text that wraps differently,
      // which is a diff to look at, not to hide.
      maxDiffPixelRatio: 0.005,
      // CSS transitions and the blinking caret are the two classic sources of
      // a diff that means nothing.
      animations: "disabled",
      caret: "hide",
    },
  },
  use: {
    baseURL: devServerUrl,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Explicit for both projects: a retina-style factor would double the
    // reference image size for no extra information.
    deviceScaleFactor: 1,
    // Pinned so a date, a number or a weekday renders the same regardless of
    // what the runner's environment says; the app's own language comes from
    // the account (see tests/browser/auth.setup.js), this is the browser's.
    locale: "nl-NL",
    timezoneId: "Europe/Amsterdam",
  },
  projects: [
    // Logs the admin in once and saves the browser state; the screenshot suite
    // starts from that instead of repeating the login for every route.
    { name: "setup", testMatch: /auth\.setup\.js/ },
    {
      name: "desktop",
      use: { viewport: DESKTOP_VIEWPORT },
      dependencies: ["setup"],
      // The bottom bar and browse grid only exist in the phone shell.
      testIgnore: /mobile-nav\.spec\.js/,
    },
    {
      name: "phone",
      use: { viewport: PHONE_VIEWPORT },
      dependencies: ["setup"],
      // smoke.spec.js is the same login and search on either layout; once is
      // enough, and the phone project already exercises its own navigation.
      // tablet.spec.js sets its own viewport, so it would only run twice.
      testIgnore: /(smoke|tablet)\.spec\.js/,
    },
  ],
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
