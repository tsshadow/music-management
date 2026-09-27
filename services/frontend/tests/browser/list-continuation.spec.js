// A song list continues in the queue, on the phone and on the tablet
// (docs/designs/list-continuation/, issue #100).
//
// Teun: "Stel je hebt 'recent uitgebracht' en bent bij het eind." The songs list sorted by
// "Recent uitgebracht" is 105 tracks here, in pages of 50. A tapped row starts a queue of what the
// page shows; the queue sheet ends in "Meer laden", which grows it page by page, and in "Einde van
// de lijst" once the list ran out. jsdom proves the pill is rendered; this proves it is on screen
// in both touch layouts, with the real stylesheet. LMS's answers are mocked -- the test stack has
// one fixture track.
//
// Runs in the `desktop` project only and sets its own viewport per layout, like
// feed-load-more.spec.js.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

const TOTAL = 105;
const PAGE = 50;

function song(n) {
  return {
    id: `list-${n}`,
    title: `Lijst track ${n}`,
    artist: "Artist",
    album: "Album",
    duration: 200,
    suffix: "mp3",
  };
}

/**
 * Answers `getSpotifyTracks` with the 105-track list, by offset. Every page after the first is held
 * until `releaseNextPages()`: scrolling the list's own pill into view loads its next page, which
 * appends 50 rows above the pill and pushes it out of the viewport again -- the tablet flake of
 * issue #116. Held, the pill stays where it was scrolled to (as "Laden...") until it is checked.
 */
async function mockSongs(page) {
  let releaseNextPages;
  const nextPages = new Promise((resolve) => {
    releaseNextPages = resolve;
  });
  await page.route(/\/rest\/getSpotifyTracks/, async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset") ?? 0);
    if (offset > 0) await nextPages;
    const count = Number(params.get("count") ?? PAGE);
    const end = Math.min(offset + count, TOTAL);
    const track = [];
    for (let n = offset; n < end; n++) track.push(song(n));
    await route.fulfill({
      json: {
        "subsonic-response": {
          status: "ok",
          version: "1.16.1",
          tracks: { track, moreResults: end < TOTAL, nextOffset: end },
        },
      },
    });
  });
  return { releaseNextPages: () => releaseNextPages() };
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

    test(`a queue from "Recent uitgebracht" loads more and ends, on the ${layout.name}`, async ({
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "sets its own viewport per layout");
      const server = await mockSongs(page);

      await page.goto("/songs");
      const firstRow = page.getByText("Lijst track 0", { exact: true }).first();
      await expect(firstRow).toBeVisible({ timeout: 15_000 });

      // A single tap plays a row on a touch screen and queues the page around it: 50 tracks.
      await firstRow.tap();

      // The page itself ends in the pill. (Scrolling to it loads the page's next page; the queue
      // started above keeps its own continuation.)
      const listPill = page.getByTestId("tracks-load-more");
      await expectScrolledIntoView(listPill);
      server.releaseNextPages();

      // Mini player -> Now Playing -> the queue sheet. The title, not the row's centre: on a
      // 412px phone the centre of the mini player is one of its rating stars.
      // The artwork panel repeats the title; the text line after it is the one to tap.
      await page
        .locator('footer [role="button"]')
        .first()
        .getByText("Lijst track 0", { exact: true })
        .last()
        .tap();
      await page.getByTestId("now-playing").getByRole("button", { name: "Wachtrij" }).tap();

      const sheet = page.getByRole("dialog", { name: "Wachtrij" });
      const queuePill = sheet.getByTestId("queue-load-more");
      await expectScrolledIntoView(queuePill);

      // Two more pages: 100, then the last 5. Each tap waits for its own answer.
      for (const last of ["Lijst track 99", "Lijst track 104"]) {
        await queuePill.scrollIntoViewIfNeeded();
        await queuePill.tap();
        await expect(sheet.getByText(last, { exact: true }).first()).toBeAttached({
          timeout: 15_000,
        });
        if (last === "Lijst track 99") await expect(queuePill).toBeVisible({ timeout: 15_000 });
      }

      const end = sheet.getByTestId("queue-load-more-end");
      await expect(end).toBeAttached({ timeout: 15_000 });
      await expectScrolledIntoView(end);
      await expect(end).toHaveText("Einde van de lijst");
      await expect(queuePill).toHaveCount(0);
    });
  });
}
