// Tag lists and search show loading states instead of stale or false results, on the phone and on
// the tablet (issues #109 and #112, docs/designs/perceived-performance/).
//
// The genre list and the search requests are answered here, and the second genre's tracks and the
// search sections are held back until the test lets them go, so "the previous genre's rows are
// gone while the next one loads" and "no 'No results' before the answer" are facts of this run
// rather than a race with a fast stack. The held requests are counted with expect.poll, not read
// once: the page can draw its skeleton before Playwright's route handler has seen the request
// (issue #116).
//
// Runs in the `desktop` project only and sets its own viewport per layout, the way
// optimistic-navigation.spec.js does.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE, PHONE_VIEWPORT } from "../../playwright.config.js";

const FIRST = "Loadstate Alpha";
const SECOND = "Loadstate Beta";
const ok = (payload) => ({ json: { "subsonic-response": { status: "ok", ...payload } } });
const track = (id, title) => ({ id, title, artist: "Fixture Artist", duration: 200 });

/** A promise with its resolver, for a request the test releases by hand. */
function gate() {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  return { held, release: () => release() };
}

/**
 * Answers the genre grid with FIRST and SECOND, FIRST's tracks at once, and holds SECOND's
 * tracks until `release()`.
 */
async function mockGenres(page) {
  const second = gate();
  let waiting = 0;
  await page.route(/\/rest\/getGenres(\.view)?\?/, (route) =>
    route.fulfill(
      ok({
        genres: {
          genre: [
            { value: FIRST, songCount: 5000, albumCount: 10 },
            { value: SECOND, songCount: 4000, albumCount: 8 },
          ],
        },
      }),
    ),
  );
  await page.route(/\/rest\/getSpotifyTracks(\.view)?\?/, async (route) => {
    const genre = new URL(route.request().url()).searchParams.get("genre");
    if (genre === FIRST) {
      return route.fulfill(
        ok({ tracks: { track: [track("ls-a1", "Alpha Only Track")], moreResults: false } }),
      );
    }
    if (genre === SECOND) {
      waiting += 1;
      await second.held;
      waiting -= 1;
      return route.fulfill(
        ok({ tracks: { track: [track("ls-b1", "Beta Only Track")], moreResults: false } }),
      );
    }
    return route.continue();
  });
  return { release: second.release, pending: () => waiting };
}

/** Holds the search page's three requests until `release()`, then answers them empty. */
async function mockSlowSearch(page) {
  const all = gate();
  let waiting = 0;
  const hold = (payload) => async (route) => {
    waiting += 1;
    await all.held;
    waiting -= 1;
    await route.fulfill(ok(payload));
  };
  await page.route(
    /\/rest\/getSpotifyTracks(\.view)?\?/,
    hold({ tracks: { track: [], moreResults: false } }),
  );
  await page.route(/\/rest\/getArtistList(\.view)?\?/, hold({ artistList: { artist: [] } }));
  await page.route(/\/rest\/getAlbumList2(\.view)?\?/, hold({ albumList2: { album: [] } }));
  return { release: all.release, pending: () => waiting };
}

/** Opens a genre card from the grid. */
async function openGenre(page, name) {
  const card = page.getByRole("button", { name: new RegExp(name) }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.click();
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

    test("the next genre shows skeleton rows under its name, never the previous genre's list", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockGenres(page);

      await page.goto("/genres");
      await openGenre(page, FIRST);
      await expect(page.getByText("Alpha Only Track")).toBeVisible({ timeout: 10_000 });

      await page.goBack();
      await openGenre(page, SECOND);

      await expect(page.getByRole("heading", { level: 2, name: new RegExp(SECOND) })).toBeVisible();
      await expect(page.getByTestId("skeleton-rows")).toBeVisible();
      await expect(page.getByText("Alpha Only Track")).toHaveCount(0);
      await expect.poll(() => server.pending()).toBeGreaterThan(0);

      server.release();
      await expect(page.getByText("Beta Only Track")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0);

      // Back to the first genre: straight from the cache, no skeleton.
      await page.goBack();
      await openGenre(page, FIRST);
      await expect(page.getByText("Alpha Only Track")).toBeVisible();
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0);
    });

    test("the search page shows skeleton sections and says 'No results' only after the answer", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockSlowSearch(page);

      await page.goto("/search/loadstate-nothing");

      await expect(page.getByTestId("skeleton-rows")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("skeleton-tiles")).toHaveCount(2);
      await expect(page.getByTestId("search-pending")).toBeVisible();
      await expect(page.getByText(/No results found\.|Geen resultaten gevonden\./)).toHaveCount(0);
      await expect.poll(() => server.pending()).toBeGreaterThan(0);

      server.release();
      await expect(page.getByText(/No results found\.|Geen resultaten gevonden\./)).toBeVisible({
        timeout: 10_000,
      });
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0);
      await expect(page.getByTestId("search-pending")).toHaveCount(0);
    });
  });
}
