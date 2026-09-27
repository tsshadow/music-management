// Tapping an artist shows the artist page at once, on the phone and on the tablet
// (docs/designs/perceived-performance/). Teun: "klikken op een artiest zou praktisch instant de
// artist page moeten tonen".
//
// The artist list is answered here with one artist, and the artist's own requests (getArtist,
// getSpotifyTracks) are held back until the test lets them go, so "the name is on screen while
// the tracks are still loading" is a fact of this run rather than a race with a fast stack.
// The property is the order, not a stopwatch: the heading (seeded from the tile) is on screen while
// every held request is still unanswered, which is deterministic because nothing is answered until
// the test calls release(). The time from the tap to the frame the heading appears in is measured
// inside the page and recorded as an annotation; it is only held to a loose guard, because a
// tight wall-clock budget measures the runner's load rather than the app (issue #116: 118 ms
// against a 100 ms budget on a busy tablet run).
//
// Runs in the `desktop` project only and sets its own viewport per layout, the way
// feed-load-more.spec.js does; running it in the `phone` project as well would only repeat it.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE, PHONE_VIEWPORT } from "../../playwright.config.js";

const ARTIST = { id: "ar-optimistic-1", name: "Angerfist", albumCount: 1 };

/**
 * A loose guard on the time from the tap to the heading. Well above the 118 ms seen once on CI, well
 * below anything that could be a server round trip the test lets through; the ordering assertions
 * below are what prove the heading came from the tile.
 */
const LOOSE_GUARD_MS = 500;

/**
 * Answers the artist list with ARTIST and holds the artist's page requests until `release()`.
 * `pending()` counts the held requests that have not been answered yet, `answered()` the artist
 * requests that have been fulfilled.
 */
async function mockSlowArtist(page) {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  let waiting = 0;
  let answered = 0;
  const ok = (payload) => ({ json: { "subsonic-response": { status: "ok", ...payload } } });

  await page.route(/\/rest\/getArtistList(\.view)?\?/, (route) =>
    route.fulfill(ok({ artistList: { artist: [ARTIST] } })),
  );
  await page.route(/\/rest\/getArtist(\.view)?\?/, async (route) => {
    waiting += 1;
    await held;
    waiting -= 1;
    await route.fulfill(ok({ artist: { ...ARTIST, album: [] } }));
    answered += 1;
  });
  await page.route(/\/rest\/getSpotifyTracks(\.view)?\?/, async (route) => {
    if (!route.request().url().includes(ARTIST.id)) return route.continue();
    waiting += 1;
    await held;
    waiting -= 1;
    await route.fulfill(ok({ tracks: { track: [], moreResults: false } }));
    answered += 1;
  });
  return { release: () => release(), pending: () => waiting, answered: () => answered };
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
      testInfo.annotations.push({
        type: "tap-to-heading",
        description: `${Math.round(elapsed)} ms (${layout.name})`,
      });

      // The heading is on screen and no artist request has been answered: it came from the tile.
      expect(server.answered()).toBe(0);
      await expect(page).toHaveURL(new RegExp(`/artist/${ARTIST.id}$`));
      // The page did ask for the artist, and those requests are still held.
      await expect.poll(() => server.pending()).toBeGreaterThan(0);
      await expect(page.getByTestId("skeleton-rows")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: ARTIST.name })).toBeVisible();
      expect(server.answered()).toBe(0);
      expect(elapsed).toBeLessThan(LOOSE_GUARD_MS);

      server.release();
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0, { timeout: 10_000 });
      await expect.poll(() => server.answered()).toBeGreaterThan(0);
      await expect(page.getByRole("heading", { level: 1, name: ARTIST.name })).toBeVisible();
    });

    test("the heading does not wait for the artist page's code either", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      // The artist page is its own chunk (issue #118). Hold it back -- the idle preload's request
      // included -- so the tap lands while neither the code nor the data is in: the seeded
      // stand-in (EntityPageShell) must carry the heading on its own.
      let releaseChunk;
      const chunkHeld = new Promise((resolve) => {
        releaseChunk = resolve;
      });
      let chunkRequested = false;
      await page.route(/\/assets\/ArtistView-[\w-]+\.js$/, async (route) => {
        chunkRequested = true;
        await chunkHeld;
        await route.continue();
      });
      const server = await mockSlowArtist(page);
      await page.goto("/artists");

      const elapsed = await tapAndTime(page, ARTIST.name);
      testInfo.annotations.push({
        type: "tap-to-heading-without-chunk",
        description: `${Math.round(elapsed)} ms (${layout.name})`,
      });

      await expect.poll(() => chunkRequested).toBe(true);
      await expect(page.getByTestId("entity-page-shell")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: ARTIST.name })).toBeVisible();
      expect(server.answered()).toBe(0);
      expect(elapsed).toBeLessThan(LOOSE_GUARD_MS);

      releaseChunk();
      server.release();
      await expect(page.getByTestId("artist-page")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("entity-page-shell")).toHaveCount(0);
      await expect(page.getByRole("heading", { level: 1, name: ARTIST.name })).toBeVisible();
    });
  });
}
