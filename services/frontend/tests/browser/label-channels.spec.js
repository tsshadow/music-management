// A label page lists the channels linked to it (issue #122, docs/designs/channel-links/
// functional.md "A label page lists its channels").
//
// The unit tests drive the section in jsdom; this is the same page with the real stylesheet, at
// phone, tablet and desktop widths, where the row of channel cards has to scroll sideways inside
// the page instead of pushing the page wider than the screen. The test stack has no downloaded
// channels, so the one call the section makes is answered here.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

test.use({ storageState: ADMIN_STORAGE_STATE });

const CHANNELS = [
  {
    id: 3,
    platform: "soundcloud",
    name: "Traxtorm Records Official Channel",
    track_count: 812,
    artist: null,
    album: "Soundcloud (Traxtorm Records Official Channel)",
    source_url: "https://soundcloud.com/traxtormrecords",
  },
  {
    id: 4,
    platform: "youtube",
    name: "Traxtorm TV",
    track_count: 97,
    artist: null,
    album: "Youtube (Traxtorm TV)",
    source_url: null,
  },
  {
    id: 5,
    platform: "telegram",
    name: "Traxtorm Leaks",
    track_count: 1,
    artist: null,
    album: "Telegram (Traxtorm Leaks)",
    source_url: null,
  },
];

async function openLabel(page) {
  const asked = [];
  await page.route(/\/api\/channel-links\/by-label\?/, (route) => {
    asked.push(new URL(route.request().url()).searchParams.get("name"));
    return route.fulfill({ json: CHANNELS });
  });
  await page.goto(`/label/${encodeURIComponent("Traxtorm Records")}`);
  const section = page.getByTestId("label-channels");
  await expect(section).toBeVisible({ timeout: 20_000 });
  return { section, asked };
}

async function expectNoSidewaysPage(page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test("the label page shows its linked channels without widening the page", async ({ page }) => {
  const { section, asked } = await openLabel(page);
  await expect(section.getByRole("heading", { name: "Kanalen" })).toBeVisible();
  await expect(section.getByTestId("label-channel")).toHaveCount(3);
  await expect(section.getByText("812 nummers")).toBeVisible();
  expect(asked).toEqual(["Traxtorm Records"]);
  // The admin session sees the way to Koppelingen.
  await expect(section.getByTestId("label-channels-manage")).toBeVisible();
  await expectNoSidewaysPage(page);
});

test("the curator's link lands on Koppelingen", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Beheer is a desktop page");
  await page.route(/\/api\/channel-links\/(proposals|channels)(\?|$)/, (route) =>
    route.fulfill({ json: [] }),
  );
  const { section } = await openLabel(page);
  await section.getByTestId("label-channels-manage").click();
  await expect(page).toHaveURL(/\/management\/downloaders$/);
  await expect(page.getByRole("heading", { name: "Handmatig koppelen" })).toBeVisible({
    timeout: 20_000,
  });
});

test.describe("tablet in portrait", () => {
  test.use({ viewport: { width: 800, height: 1280 }, hasTouch: true });

  test("the channel cards fit the tablet page", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "the viewport is set here; once is enough");
    const { section } = await openLabel(page);
    await expect(section.getByTestId("label-channel")).toHaveCount(3);
    await expectNoSidewaysPage(page);
  });
});
