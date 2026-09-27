// Linking a channel by hand in Beheer -> Downloaders -> Koppelingen (issue #58,
// docs/designs/channel-links/functional.md "Linking by hand").
//
// The unit tests drive the panel in jsdom; this is the same walk in a real browser with the real
// stylesheet, where the suggestion list has to be on top of the page and clickable. The test stack
// has no downloaded channels, so the three channel-links calls the panel makes are answered here,
// and the PUT is checked for what it sends. The proposal list below the panel is answered empty.
//
// Desktop only: Beheer is a desktop page, and the phone project would only repeat the walk.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

test.use({ storageState: ADMIN_STORAGE_STATE });

const CHANNEL = {
  id: 7,
  platform: "soundcloud",
  name: "Hysta Official",
  track_count: 44,
  label: null,
  artist: null,
  open_proposals: 0,
};

test("a channel without a proposal is linked to an approved artist by typing", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Beheer is a desktop page");
  const puts = [];
  await page.route(/\/api\/channel-links\/proposals(\?|$)/, (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/channel-links\/channels\?/, (route) =>
    route.fulfill({ json: [CHANNEL] }),
  );
  await page.route(/\/api\/channel-links\/targets\?/, (route) =>
    route.fulfill({ json: [{ id: 20, name: "Hysta" }] }),
  );
  await page.route(/\/api\/channel-links\/channels\/7\/artist$/, async (route) => {
    puts.push({ method: route.request().method(), body: route.request().postDataJSON() });
    await route.fulfill({
      json: {
        status: "linked",
        channel_id: 7,
        kind: "artist",
        target_id: 20,
        target_name: "Hysta",
        queued: 44,
      },
    });
  });

  await page.goto("/management/downloaders");
  await page.getByRole("button", { name: "Koppelingen" }).click();
  await expect(page.getByRole("heading", { name: "Handmatig koppelen" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByLabel("Kanaal", { exact: true }).fill("hysta");
  await page.getByRole("button", { name: /Hysta Official/ }).click();
  await page.getByRole("radio", { name: "Artiest" }).click();
  await page.getByLabel("Koppelen aan", { exact: true }).fill("hys");
  await page.getByRole("button", { name: /^Hysta$/ }).click();
  await page.getByRole("button", { name: /^Koppelen$/ }).click();

  await expect.poll(() => puts).toEqual([{ method: "PUT", body: { target_id: 20 } }]);
  await expect(page.getByText(/44 bestanden staan klaar voor de tagger/)).toBeVisible();
});
