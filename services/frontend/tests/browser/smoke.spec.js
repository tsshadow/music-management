// First frontend browser tests (Task 7 / Phase 5.2 of the test plan).
// Assumes docker/compose.test.yml is already running with the fixture track
// scanned into LMS (see scripts/test/frontend-browser.sh), and that a
// music-manager admin (ci-contract-admin / ci-contract-password) exists,
// matching tests/contracts/test_lms_subsonic_contract.py.
import { test, expect } from "@playwright/test";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";
const FIXTURE_TITLE = "CI Test Track";

test("frontend opens without JavaScript errors", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await page.goto("/");
  // This is the first page load of the run, so it pays for Vite's dependency
  // pre-bundling and the full reload that follows it: on a CI runner #app stays
  // an empty div for well over the 5s default, while the second test in this
  // file then loads in ~1.5s against the warm server. That is a slow first
  // paint, not a broken app, so wait long enough to tell the two apart.
  await expect(page.locator("#app")).toBeVisible({ timeout: 30_000 });

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
