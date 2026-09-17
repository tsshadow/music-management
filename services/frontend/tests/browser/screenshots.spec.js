// Visual regression: one screenshot per route per layout, compared against the
// references in __screenshots__/<project>/<route>.png. Runs in both the
// `desktop` and the `phone` project (playwright.config.js), so a change that
// only breaks one of the two layouts still shows up.
//
// The references are also the documentation set (docs/frontend-screenshots.md),
// and the only rendering of the app a reviewer -- or an agent without a
// browser -- gets to see of a merge request. That is why the job uploads the
// freshly taken screenshots even when they match.
//
// Refreshing after an intended change: scripts/test/frontend-browser.sh honours
// MUMA_UPDATE_SNAPSHOTS=1 and runs this suite with --update-snapshots; see the
// doc above for how to get the result back into the tree.
//
// What keeps a screenshot stable, and why each rule exists:
// - `page.clock.setFixedTime` pins Date, so a date-driven view (memories,
//   greetings) renders the same day on every run.
// - `networkidle` plus "no spinner left" waits for the data, not for a fixed
//   number of milliseconds; the stack is created per job and cold.
// - `document.fonts.ready`: the first paint may still be in the fallback font.
// - Animations are disabled and the caret hidden in the shared expect options.
// - Viewport only, not fullPage: a list that grows with the fixture set would
//   otherwise change the image height and fail on data, not on layout.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

test.use({ storageState: ADMIN_STORAGE_STATE });

// A Monday in summer, before noon: memories and greetings are date and time
// bound. Change it and every reference needs refreshing.
const FIXED_TIME = new Date("2026-06-15T10:00:00");

// Routes from src/lib/router.js worth a picture. Deliberately not every view:
// the management tabs that show live data (overview's version, health's
// uptime, scanner's timestamps, events) would go stale on every release and
// prove nothing about layout, and the `kind:argument` views need an id the
// fixture does not promise. Each entry is a path, the file name it is stored
// under, and optionally the one layout it exists in: `/browse` is the phone's
// middle tab and renders nothing on the desktop (`App.svelte` wraps it in
// `md:hidden`), and `/search` is that same grid under its old URL.
const ROUTES = [
  { path: "/", name: "home" },
  { path: "/browse", name: "browse", only: "phone" },
  { path: "/favorites", name: "favorites" },
  { path: "/songs", name: "songs" },
  // An empty state for now: the fixture track is a few seconds long and a
  // set starts at ten minutes (SearchBar.svelte's minDuration).
  { path: "/sets", name: "sets" },
  { path: "/albums", name: "albums" },
  { path: "/artists", name: "artists" },
  { path: "/genres", name: "genres" },
  { path: "/labels", name: "labels" },
  { path: "/playlists", name: "playlists" },
  { path: "/memories", name: "memories" },
  { path: "/history", name: "history" },
  { path: "/listening", name: "listening" },
  { path: "/daily-mixes", name: "daily-mixes" },
  { path: "/release-radar", name: "release-radar" },
  { path: "/settings/general", name: "settings-general" },
  { path: "/management/libraries", name: "management-libraries" },
  { path: "/management/users", name: "management-users" },
  { path: "/management/config", name: "management-config" },
];

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(FIXED_TIME);
});

for (const { path, name, only } of ROUTES) {
  test(`${path} renders as before`, async ({ page }, testInfo) => {
    test.skip(
      Boolean(only) && only !== testInfo.project.name,
      `${path} only exists in the ${only} layout`,
    );

    await page.goto(path);
    await expect(page.locator("#app")).toBeVisible({ timeout: 15_000 });

    // The app has no polling loop while nothing plays, so the network does go
    // idle; a page that keeps a request open would only cost the timeout, not
    // the test. Neither this nor the spinner check proves a view has its data
    // -- a route that turns out to be captured half-loaded gets its own
    // assertion here, not a longer sleep.
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    await expect(page.locator(".animate-spin")).toHaveCount(0, { timeout: 10_000 });
    // Cover art and the fallback it swaps to on error both arrive after the
    // layout has settled; a picture taken in between shows a blank tile.
    await page.evaluate(() => {
      const settled = (image) =>
        new Promise((done) => {
          image.addEventListener("load", done, { once: true });
          image.addEventListener("error", done, { once: true });
        });
      const pending = Array.from(document.images).filter((image) => !image.complete);
      return Promise.all([document.fonts.ready, ...pending.map(settled)]);
    });

    await expect(page).toHaveScreenshot(`${name}.png`);
  });
}
