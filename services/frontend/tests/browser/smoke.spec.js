// First frontend browser tests (Task 7 / Phase 5.2 of the test plan).
// Assumes docker/compose.test.yml is already running with the fixture track
// scanned into LMS (see scripts/test/frontend-browser.sh), and that a
// music-manager admin (ci-contract-admin / ci-contract-password) exists,
// matching tests/contracts/test_lms_subsonic_contract.py.
import { test, expect } from "@playwright/test";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";
const FIXTURE_TITLE = "CI Test Track";

// Chromium runs as en-US, so without this the interface would come up in
// English and the assertions below -- which are written against the Dutch the
// app is actually used in -- would fail for the wrong reason.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("muma_locale", JSON.stringify("nl"));
  });
});

test("frontend opens without JavaScript errors", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await page.goto("/");
  // The dev server was warmed up in global-setup.js, so this measures the app,
  // not Vite's cold start. Keep the budget tight enough that an app which fails
  // to mount is still caught.
  await expect(page.locator("#app")).toBeVisible({ timeout: 15_000 });

  expect(pageErrors).toEqual([]);
});

test("login works and the fixture track is visible", async ({ page }) => {
  await page.goto("/");

  // AuthOverlay.svelte: shown until credentials are stored.
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();

  // Overlay disappears once verifyLogin() succeeds.
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 15_000 });

  // Search for the fixture track via SearchBar.svelte.
  const searchInput = page.getByPlaceholder(/Wat wil je luisteren\?/);
  await searchInput.fill(FIXTURE_TITLE);

  await expect(page.getByText(FIXTURE_TITLE).first()).toBeVisible({ timeout: 15_000 });
});
