// Spotify-style phone navigation (see docs/designs/universal-ui/functional.md,
// "Telefoonlayout"). There is no mobile viewport project in playwright.config.js
// yet, so this file sets its own -- 412x915, a common Android phone size -- and
// is the one place that exercises the bottom bar and the browse grid end to end;
// the unit tests (mobileNav.test.js, browseGrid.test.js, app.test.js) cover the
// component and store logic in isolation.
import { test, expect } from "@playwright/test";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";

test.use({ viewport: { width: 412, height: 915 } });

// Chromium runs as en-US, so without this the interface would come up in
// English and the assertions below -- written against the Dutch the app is
// actually used in -- would fail for the wrong reason.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("muma_locale", JSON.stringify("nl"));
  });

  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 15_000 });
});

test("the phone's three bottom tabs move between Home, Search and Library", async ({ page }) => {
  const bottomBar = page.getByRole("navigation", { name: "Navigatiebalk" });
  await expect(bottomBar).toBeVisible();

  await bottomBar.getByRole("button", { name: "Zoeken" }).click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(page.getByText("Alles doorbladeren")).toBeVisible();

  await bottomBar.getByRole("button", { name: "Bieb" }).click();
  await expect(page).toHaveURL(/\/playlists$/);

  await bottomBar.getByRole("button", { name: "Home" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("a browse tile under Search opens the section it stands for", async ({ page }) => {
  await page.getByRole("navigation", { name: "Navigatiebalk" }).getByRole("button", { name: "Zoeken" }).click();

  await page.getByRole("button", { name: "Genres" }).click();

  await expect(page).toHaveURL(/\/genres$/);
  await expect(page.getByRole("heading", { name: "Genres" })).toBeVisible();
});
