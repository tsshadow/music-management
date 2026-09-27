// No password is kept after a sign-in (issue #101).
//
// Since issue #72 the password signs no Subsonic request; until #101 it was still persisted in
// `lms_credentials` for a re-login when MuMa refused the stored key. That re-login is gone: the
// session lives on as the MuMa key and the Subsonic token, and a refused key brings the login page
// back. These run against the real test stack (docker/compose.test.yml, whose music-manager shares
// LMS's database since !1060), through the UI:
//
// - a sign-in leaves no copy of the password in the browser's storage;
// - a session persisted by an older build loses its stored password on the next start and stays
//   signed in;
// - a key MuMa refuses on start shows the login page and is not traded for a new one.
//
// Desktop project only: none of this depends on the layout.
import { test, expect } from "@playwright/test";
import { SETUP_STEPS } from "../../src/lib/setup.js";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";

test.skip(({ viewport }) => viewport?.width < 1024, "desktop project only");

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    (seen) => {
      localStorage.setItem("muma_locale", JSON.stringify("nl"));
      localStorage.setItem("lms_setupStepsSeen", JSON.stringify(seen));
    },
    SETUP_STEPS.map((step) => step.id),
  );
});

/** Signs in through the login page and waits until it is gone. */
async function signIn(page) {
  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 30_000 });
}

/** Every localStorage key whose value contains the password. */
function keysHoldingPassword(page) {
  return page.evaluate((password) => {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if ((localStorage.getItem(key) ?? "").includes(password)) keys.push(key);
    }
    return keys;
  }, PASSWORD);
}

test("a sign-in leaves no copy of the password in the browser's storage", async ({ page }) => {
  await signIn(page);

  expect(await keysHoldingPassword(page)).toEqual([]);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("lms_credentials")));
  expect(stored.username).toBe(USERNAME);
  expect(stored).not.toHaveProperty("password");
});

test("a session stored by an older build loses its password on the next start", async ({
  page,
}) => {
  await signIn(page);
  // What a build before issue #101 left behind after a sign-in.
  await page.evaluate((password) => {
    const stored = JSON.parse(localStorage.getItem("lms_credentials"));
    localStorage.setItem("lms_credentials", JSON.stringify({ ...stored, password }));
  }, PASSWORD);

  await page.reload();

  // The app shell, not merely a page without a login form: right after the reload neither exists.
  await expect(page.getByPlaceholder(/Wat wil je luisteren\?/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#username")).toHaveCount(0);
  // Polled: the start strips the password asynchronously, and one early read would race it.
  await expect.poll(() => keysHoldingPassword(page)).toEqual([]);
});

test("a key MuMa refuses on start brings the login page back, without a re-login", async ({
  page,
}) => {
  await signIn(page);
  const logins = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/auth/login")) logins.push(request.url());
  });
  // The account's key revoked while the page was away.
  await page.route(/\/api\/auth\/verify(\?|$)/, (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"no"}' }),
  );

  await page.reload();

  await expect(page.locator("#username")).toBeVisible({ timeout: 15_000 });
  expect(logins).toEqual([]);
  const key = await page.evaluate(() => JSON.parse(localStorage.getItem("muma_api_key") ?? '""'));
  expect(key).toBe("");
});
