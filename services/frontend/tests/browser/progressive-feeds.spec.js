// Feeds, daily mixes and the song page open at once and fill in, on the phone and on the tablet
// (issues #110, #111, #99; docs/designs/perceived-performance/).
//
// MuMa's feed and LMS's answers are held back by `page.route` until the test lets them go, so "the
// header is on screen while the rows are still loading" is a fact of this run rather than a race
// with a fast stack. The test stack has one fixture track and no listening history, so the feed
// list, the feed and its songs are all answered here, the way feed-load-more.spec.js does.
//
// Runs in the `desktop` project only and sets its own viewport per layout; running it in the
// `phone` project as well would only repeat it.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE, PHONE_VIEWPORT } from "../../playwright.config.js";

const FEEDS = [
  { slug: "daily-mix-soft", title: "Zachter", subtitle: "≤ 42 hardheid" },
  { slug: "daily-mix-mid", title: "Middenin", subtitle: "42–70 hardheid" },
  { slug: "daily-mix-hard", title: "Harder", subtitle: "≥ 70 hardheid" },
  { slug: "daily-mix-artist", title: "Angerfist", subtitle: "Artiest van de dag" },
  { slug: "daily-mix-label", title: "Dirty Workz", subtitle: "Label van de dag" },
];
const PATHS = Array.from({ length: 12 }, (_, i) => `Feed/p${i}.mp3`);

/** A promise the test resolves by hand, and a count of requests waiting on it. */
function gate() {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const state = { waiting: 0 };
  return {
    held,
    state,
    release: () => release(),
    async wait() {
      state.waiting += 1;
      await held;
      state.waiting -= 1;
    },
  };
}

/** Answers the feed list at once, and the Harder feed plus its songs only after `release()`. */
async function mockSlowFeed(page) {
  const server = gate();
  await page.route(/\/api\/feeds(\?|$)/, (route) =>
    route.fulfill({
      json: { feeds: FEEDS.map((feed) => ({ ...feed, size: 100, window_days: 30 })) },
    }),
  );
  await page.route(/\/api\/feeds\/daily-mix-hard(\?|$)/, async (route) => {
    await server.wait();
    await route.fulfill({
      json: {
        slug: "daily-mix-hard",
        state: "ok",
        title: "Harder",
        subtitle: "≥ 70 hardheid",
        hardness_band: null,
        relaxed_to: null,
        filled_from_unknown: null,
        offset: 0,
        next_offset: null,
        tracks: PATHS.map((path) => ({
          title: path,
          library_path: path,
          file_path: `/mnt/music/${path}`,
        })),
      },
    });
  });
  await page.route(/\/rest\/getSongsByPath\.view/, async (route) => {
    await server.wait();
    const paths = new URLSearchParams(route.request().postData() ?? "").getAll("path");
    const song = paths.map((path) => {
      const n = path.match(/p(\d+)\.mp3$/)[1];
      return {
        id: `feed-${n}`,
        title: `Feed track ${n}`,
        artist: "Artist",
        duration: 200,
        suffix: "mp3",
      };
    });
    await route.fulfill({
      json: { "subsonic-response": { status: "ok", version: "1.16.1", songsByPath: { song } } },
    });
  });
  return { release: server.release, pending: () => server.state.waiting };
}

/** Holds both pages of work 4242's versions until `release()`. */
async function mockSlowVersions(page) {
  const server = gate();
  await page.route(/\/rest\/getSpotifyTracks(\.view)?\?.*workId=4242/, async (route) => {
    await server.wait();
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? 0);
    const track =
      offset === 0
        ? [
            {
              id: "v-1",
              title: "Raise Your Fist",
              artist: "Angerfist",
              duration: 200,
              isCanonical: true,
            },
          ]
        : [
            {
              id: "v-2",
              title: "Raise Your Fist (Extended Mix)",
              artist: "Angerfist",
              duration: 300,
            },
          ];
    await route.fulfill({
      json: {
        "subsonic-response": {
          status: "ok",
          tracks: { track, moreResults: offset === 0, nextOffset: offset === 0 ? 100 : null },
        },
      },
    });
  });
  return { release: server.release, pending: () => server.state.waiting };
}

const LAYOUTS = [
  { name: "phone", viewport: PHONE_VIEWPORT },
  { name: "tablet", viewport: { width: 1024, height: 1366 } },
];

for (const layout of LAYOUTS) {
  test.describe(`on the ${layout.name}`, () => {
    test.use({ storageState: ADMIN_STORAGE_STATE, viewport: layout.viewport, hasTouch: true });

    test("a daily mix card's play button is visible without hovering", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      await mockSlowFeed(page);
      await page.goto("/daily-mixes");

      const play = page.getByTestId("mix-card-play").first();
      await expect(play).toBeVisible({ timeout: 15_000 });
      // toBeVisible ignores opacity; the hover-only button was "visible" at opacity 0.
      await expect(play).toHaveCSS("opacity", "1");
      const box = await play.boundingBox();
      expect(box.width).toBeGreaterThanOrEqual(48);
    });

    test("tapping a daily mix shows its title at once and the rows as they arrive", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockSlowFeed(page);
      await page.goto("/daily-mixes");

      await page
        .getByRole("button", { name: /Harder/ })
        .first()
        .click({ timeout: 15_000 });

      await expect(page).toHaveURL(/\/daily-mix-hard$/);
      await expect(page.getByRole("heading", { level: 1, name: "Harder" })).toBeVisible();
      await expect(page.getByText("≥ 70 hardheid")).toBeVisible();
      await expect(page.getByTestId("skeleton-rows")).toBeVisible();
      await expect(page.getByText("Laden...")).toHaveCount(0);
      await expect.poll(() => server.pending()).toBeGreaterThan(0);

      server.release();
      await expect(page.getByText("Feed track 0")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0);
      await expect(page.getByText("12 nummers")).toBeVisible();
    });

    test("the song page draws its skeleton at once and streams the versions in", async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockSlowVersions(page);
      await page.goto("/song/4242");

      await expect(page.getByTestId("song-header")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("skeleton-rows")).toBeVisible();
      await expect.poll(() => server.pending()).toBeGreaterThan(0);

      server.release();
      await expect(page.getByRole("heading", { level: 2, name: "Raise Your Fist" })).toBeVisible({
        timeout: 10_000,
      });
      await expect(page.getByText("2 versies")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("skeleton-rows")).toHaveCount(0);
    });
  });
}

test.describe("with a mouse", () => {
  test.use({ storageState: ADMIN_STORAGE_STATE });

  test("a daily mix card keeps its play button for hover", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "the desktop layout is the mouse layout");
    await mockSlowFeed(page);
    await page.goto("/daily-mixes");

    const card = page.getByRole("button", { name: /Zachter/ }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    const play = page.getByTestId("mix-card-play").first();
    await expect(play).toHaveCSS("opacity", "0");
    await card.hover();
    await expect(play).toHaveCSS("opacity", "1");
  });
});
