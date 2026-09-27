// Tapping an artist shows the artist page at once, on the phone and on the tablet
// (docs/designs/perceived-performance/). Teun: "klikken op een artiest zou praktisch instant de
// artist page moeten tonen".
//
// The artist list is answered here with one artist, and the artist's own requests (getArtist,
// getSpotifyTracks) are held back until the test lets them go, so "the name is on screen while
// the tracks are still loading" is a fact of this run rather than a race with a fast stack.
// The time is measured inside the page, from the tap to the frame the heading appears in, so
// Playwright's own polling interval is not part of the number.
//
// Runs in the `desktop` project only and sets its own viewport per layout, the way
// feed-load-more.spec.js does; running it in the `phone` project as well would only repeat it.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE, PHONE_VIEWPORT } from "../../playwright.config.js";

const ARTIST = { id: "ar-optimistic-1", name: "Angerfist", albumCount: 1 };

/** The budget for the name to appear after the tap. */
const INSTANT_MS = 100;

/**
 * Answers the artist list with ARTIST and holds the artist's page requests until `release()`.
 * `pending()` counts the held requests that have not been answered yet.
 */
async function mockSlowArtist(page) {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  let waiting = 0;
  const ok = (payload) => ({ json: { "subsonic-response": { status: "ok", ...payload } } });

  await page.route(/\/rest\/getArtistList(\.view)?\?/, (route) =>
    route.fulfill(ok({ artistList: { artist: [ARTIST] } })),
  );
  await page.route(/\/rest\/getArtist(\.view)?\?/, async (route) => {
    waiting += 1;
    await held;
    waiting -= 1;
    await route.fulfill(ok({ artist: { ...ARTIST, album: [] } }));
  });
  await page.route(/\/rest\/getSpotifyTracks(\.view)?\?/, async (route) => {
    if (!route.request().url().includes(ARTIST.id)) return route.continue();
    waiting += 1;
    await held;
    waiting -= 1;
    await route.fulfill(ok({ tracks: { track: [], moreResults: false } }));
  });
  return { release: () => release(), pending: () => waiting };
}

/** Taps the artist tile and returns how long the heading took to appear, measured in the page. */
async function tapAndTime(page, name) {
  const tile = page.getByRole("button", { name: new RegExp(name) }).first();
  await expect(tile).toBeVisible({ timeout: 15_000 });
  const handle = await tile.elementHandle();
  return page.evaluate(
    ([element, expected]) =>
      new Promise((resolve) => {
        const start = performance.now();
        const found = () =>
          [...document.querySelectorAll("h1")].some((h1) => h1.textContent.trim() === expected);
        const check = () =>
          found() ? resolve(performance.now() - start) : requestAnimationFrame(check);
        element.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
        element.click();
        check();
      }),
    [handle, name],
  );
}

for (const layout of [
  { name: "phone", viewport: PHONE_VIEWPORT, hasTouch: true },
  { name: "tablet", viewport: { width: 1024, height: 1366 }, hasTouch: true },
]) {
  test.describe(`on the ${layout.name}`, () => {
    test.use({
      storageState: ADMIN_STORAGE_STATE,
      viewport: layout.viewport,
      hasTouch: layout.hasTouch,
    });

    test("tapping an artist shows their name at once, while the tracks are still loading", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockSlowArtist(page);
      await page.goto("/artists");

      const elapsed = await tapAndTime(page, ARTIST.name);

      expect(elapsed).toBeLessThan(INSTANT_MS);
      await expect(page).toHaveURL(new RegExp(`/artist/${ARTIST.id}$`));
      // Still loading: the heading came from the tile, not from the server.
      expect(server.pending()).toBeGreaterThan(0);
      await expect(page.getByTestId("skeleton-rows")).toBeVisible();

      server.release();
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0, { timeout: 10_000 });
      await expect(page.getByRole("heading", { level: 1, name: ARTIST.name })).toBeVisible();
    });
  });
}
