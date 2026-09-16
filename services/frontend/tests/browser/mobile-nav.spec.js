// Spotify-style phone navigation (see docs/designs/universal-ui/functional.md,
// "Telefoonlayout"). There is no mobile viewport project in playwright.config.js
// yet, so this file sets its own -- 412x915, a common Android phone size -- and
// is the one place that exercises the bottom bar and the browse grid end to end;
// the unit tests (mobileNav.test.js, browseGrid.test.js, app.test.js) cover the
// component and store logic in isolation.
import { test, expect } from "@playwright/test";
import { SETUP_STEPS } from "../../src/lib/setup.js";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";

test.use({ viewport: { width: 412, height: 915 } });

// Chromium runs as en-US, so without this the interface would come up in
// English and the assertions below -- written against the Dutch the app is
// actually used in -- would fail for the wrong reason.
test.beforeEach(async ({ page }) => {
  // The stack here is created per job, so this login is a first run and would land in the
  // setup tour (`SetupWizard.svelte`) -- whenever the account's settings finish loading,
  // which can be after any of the clicks below. Mark every step seen up front instead;
  // the tour itself is covered in app.test.js, this file is about the bottom bar.
  await page.addInitScript(
    (seen) => {
      localStorage.setItem("muma_locale", JSON.stringify("nl"));
      localStorage.setItem("lms_setupStepsSeen", JSON.stringify(seen));
    },
    SETUP_STEPS.map((step) => step.id),
  );

  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 15_000 });
});

test("the phone's three bottom tabs move between Home, Browse and Favourites", async ({ page }) => {
  const bottomBar = page.getByRole("navigation", { name: "Navigatiebalk" });
  await expect(bottomBar).toBeVisible();

  await bottomBar.getByRole("button", { name: "Bladeren" }).click();
  await expect(page).toHaveURL(/\/browse$/);
  await expect(page.getByText("Alles doorbladeren")).toBeVisible();

  await bottomBar.getByRole("button", { name: "Favorieten" }).click();
  await expect(page).toHaveURL(/\/favorites$/);
  await expect(page.getByTestId("favorites-view")).toBeVisible();

  await bottomBar.getByRole("button", { name: "Home" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("a browse tile opens the section it stands for", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Navigatiebalk" })
    .getByRole("button", { name: "Bladeren" })
    .click();

  await page.getByRole("button", { name: "Genres" }).click();

  await expect(page).toHaveURL(/\/genres$/);
  await expect(page.getByRole("heading", { name: "Genres" })).toBeVisible();
});

// `/search` was the tab's URL before it became Browse; a bookmark or a shared link
// from then must still land on the grid rather than on nothing.
test("the old /search URL still opens the browse grid", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByText("Alles doorbladeren")).toBeVisible();
});
