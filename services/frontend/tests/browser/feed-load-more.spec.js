// "Meer laden" under a daily mix, on the phone and on the tablet
// (docs/bug-reports/122-feed-load-more-not-visible.md).
//
// Demo-User saw Harder with 98 tracks and no way to load more. jsdom applies no CSS, so the unit tests
// can prove the button is rendered but not that it is on screen in either touch layout; this is
// the check with the real stylesheet. MuMa's feed and LMS's path lookup are both answered here --
// the test stack has one fixture track and no listening history, so it has no feed of its own:
// a 100-row page of which LMS knows 98, with a next page of three.
//
// Runs in the `desktop` project only and sets its own viewport per layout, the way tablet.spec.js
// does; running it in the `phone` project as well would only repeat both.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

const HEAD = Array.from({ length: 100 }, (_, i) => `Feed/p${i}.mp3`);
const NEXT = ["Feed/p100.mp3", "Feed/p101.mp3", "Feed/p102.mp3"];
// Files MuMa has and LMS does not: they are left out of the list and counted in the header.
const UNKNOWN_TO_LMS = new Set(["Feed/p98.mp3", "Feed/p99.mp3"]);

function feedBody(paths, offset, nextOffset) {
  return {
    slug: "daily-mix-hard",
    state: "ok",
    title: "Harder",
    subtitle: "≥ 70 hardheid",
    hardness_band: null,
    relaxed_to: null,
    filled_from_unknown: null,
    offset,
    next_offset: nextOffset,
    tracks: paths.map((path) => ({
      title: path,
      library_path: path,
      file_path: `/mnt/music/${path}`,
    })),
  };
}

/** Answers MuMa's feed and LMS's getSongsByPath for the Harder mix. */
async function mockFeed(page) {
  await page.route(/\/api\/feeds\/daily-mix-hard(\?|$)/, async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? 0);
    const body = offset === 0 ? feedBody(HEAD, 0, 100) : feedBody(NEXT, offset, null);
    await route.fulfill({ json: body });
  });
  await page.route(/\/rest\/getSongsByPath\.view/, async (route) => {
    const paths = new URLSearchParams(route.request().postData() ?? "").getAll("path");
    const song = paths
      .filter((path) => !UNKNOWN_TO_LMS.has(path))
      .map((path) => {
        const n = path.match(/p(\d+)\.mp3$/)[1];
        return {
          id: `feed-${n}`,
          title: `Feed track ${n}`,
          artist: "Artist",
          album: "Album",
          duration: 200,
          suffix: "mp3",
        };
      });
    await route.fulfill({
      json: { "subsonic-response": { status: "ok", version: "1.16.1", songsByPath: { song } } },
    });
  });
}

/**
 * Scrolls `locator` into view and asserts it is in the viewport, scrolling again on every retry.
 * One scroll followed by `toBeInViewport` fails when the layout moves after the scroll -- a sheet
 * still sliding in, rows appended above -- because the assertion's own retries never scroll back
 * (issue #116).
 */
async function expectScrolledIntoView(locator) {
  await expect(async () => {
    await locator.scrollIntoViewIfNeeded({ timeout: 2_000 });
    await expect(locator).toBeInViewport({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

const LAYOUTS = [
  { name: "phone", viewport: { width: 412, height: 915 } },
  { name: "tablet", viewport: { width: 1280, height: 800 } },
];

for (const layout of LAYOUTS) {
  test.describe(`${layout.name} layout`, () => {
    test.use({ storageState: ADMIN_STORAGE_STATE, viewport: layout.viewport, hasTouch: true });

    test(`a daily mix ends in a visible "Meer laden" on the ${layout.name}`, async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      await mockFeed(page);

      await page.goto("/daily-mix-hard");

      await expect(page.getByText("98 nummers")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("2 niet gevonden op de server")).toBeVisible();

      const loadMore = page.getByTestId("feed-load-more");
      await expectScrolledIntoView(loadMore);
      await loadMore.click();

      await expect(page.getByText("Feed track 102")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("101 nummers")).toBeVisible();
      await expect(page.getByTestId("feed-load-more")).toHaveCount(0);
    });
  });
}
