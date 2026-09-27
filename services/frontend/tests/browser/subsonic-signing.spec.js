// Every Subsonic request the web player makes is signed with the account's Subsonic token --
// `t`/`s` -- and none carries the password as `p` (issue #72, bug report 103).
//
// Production showed the web shell sending `p=` for hours while the native client signed with the
// token. The cause was not the signing code but when the token was fetched: once, at page load,
// silently. A load whose fetch failed (music-manager restarts on every deploy) kept signing with
// the password for the page's whole lifetime, which in the Android WebView is hours. These run
// against the real test stack (docker/compose.test.yml, whose music-manager shares LMS's
// database since !1060), through the UI:
//
// - a fresh sign-in, then a search and a play: API, cover art and stream requests;
// - an app start with the stored session;
// - an app start with a stored session but no stored token (an upgrade from a password build);
// - an app start whose token fetch fails -- the production case: nothing is sent with the
//   password, the page says why, and the token is fetched again without a reload.
//
// Desktop project only: the signing does not depend on the layout.
import { test, expect } from "@playwright/test";
import { SETUP_STEPS } from "../../src/lib/setup.js";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";
const FIXTURE_TITLE = "CI Test Track";
const TOKEN_ENDPOINT = /\/api\/auth\/subsonic-token(\?|$)/;

test.skip(({ viewport }) => viewport?.width < 1024, "desktop project only");

/**
 * Records every request the page makes to `/rest/` (and the `/muma` image URLs an `<img>` signs
 * the same way), plus every token fetch, in order.
 */
function recordRequests(page) {
  const log = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (TOKEN_ENDPOINT.test(url.pathname)) log.push({ kind: "token", url });
    else if (url.pathname.startsWith("/rest/") || url.searchParams.has("u"))
      log.push({ kind: "subsonic", url });
  });
  return log;
}

/** The Subsonic requests in `log` that are not signed with a token, or that carry `p`. */
function unsigned(log) {
  return log
    .filter((entry) => entry.kind === "subsonic")
    .filter(
      ({ url }) =>
        url.searchParams.has("p") || !url.searchParams.get("t") || !url.searchParams.get("s"),
    )
    .map(
      ({ url }) => `${url.pathname} p=${url.searchParams.has("p")} t=${url.searchParams.has("t")}`,
    );
}

/** The requests in order, for a failure message: which were signed how, and where the token came. */
function sequence(log) {
  return log
    .map(({ kind, url }) =>
      kind === "token"
        ? "TOKEN FETCH"
        : `${url.pathname} ${url.searchParams.has("p") ? "p" : ""}${url.searchParams.has("t") ? "t" : ""}`,
    )
    .join("\n");
}

/** The Subsonic requests that carry the password as `p` -- the property issue #72 is about. */
function withPassword(log) {
  return log
    .filter((entry) => entry.kind === "subsonic" && entry.url.searchParams.has("p"))
    .map(({ url }) => url.pathname);
}

/** Also fails the test if any request carried the password in plain text anywhere in its URL. */
function passwordInAnyUrl(log) {
  return log.filter(({ url }) => url.href.includes(PASSWORD)).map(({ url }) => url.pathname);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    (seen) => {
      localStorage.setItem("muma_locale", JSON.stringify("nl"));
      localStorage.setItem("lms_setupStepsSeen", JSON.stringify(seen));
    },
    SETUP_STEPS.map((step) => step.id),
  );
});

async function signIn(page) {
  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 30_000 });
}

/** Searches the fixture and starts it, so a cover and a stream are requested too. */
async function searchAndPlay(page) {
  const searchInput = page.getByPlaceholder(/Wat wil je luisteren\?/);
  await searchInput.fill(FIXTURE_TITLE);
  const result = page.getByText(FIXTURE_TITLE).first();
  await expect(result).toBeVisible({ timeout: 15_000 });
  const stream = page.waitForRequest((request) => request.url().includes("/rest/stream"), {
    timeout: 15_000,
  });
  await result.click();
  return stream;
}

test("a fresh sign-in signs every API, cover and stream request with the token", async ({
  page,
}) => {
  const log = recordRequests(page);

  await signIn(page);
  const stream = await searchAndPlay(page);

  const streamUrl = new URL(stream.url());
  expect(streamUrl.searchParams.has("p")).toBe(false);
  expect(streamUrl.searchParams.get("t")).toBeTruthy();
  const subsonic = log.filter((entry) => entry.kind === "subsonic");
  expect(subsonic.length).toBeGreaterThan(2);
  expect(withPassword(log), sequence(log)).toEqual([]);
  expect(unsigned(log), sequence(log)).toEqual([]);
  expect(passwordInAnyUrl(log)).toEqual([]);
  // The token is fetched before the first Subsonic request of the sign-in.
  expect(log.findIndex((entry) => entry.kind === "token")).toBeLessThan(
    log.findIndex((entry) => entry.kind === "subsonic"),
  );
});

test("an app start with the stored session signs with the stored token", async ({ page }) => {
  await signIn(page);
  const log = recordRequests(page);

  await page.reload();
  await expect(page.locator("#username")).toHaveCount(0);
  await searchAndPlay(page);

  expect(log.filter((entry) => entry.kind === "subsonic").length).toBeGreaterThan(2);
  expect(withPassword(log), sequence(log)).toEqual([]);
  expect(unsigned(log), sequence(log)).toEqual([]);
  expect(passwordInAnyUrl(log)).toEqual([]);
});

test("a stored session without a token fetches one before its first Subsonic request", async ({
  page,
}) => {
  await signIn(page);
  // What a session persisted by a build that signed with the password looks like.
  await page.evaluate(() => localStorage.removeItem("lms_subsonic_token"));
  const log = recordRequests(page);

  await page.reload();
  await expect(page.locator("#username")).toHaveCount(0);
  await searchAndPlay(page);

  expect(log.some((entry) => entry.kind === "token")).toBe(true);
  expect(withPassword(log), sequence(log)).toEqual([]);
  expect(unsigned(log), sequence(log)).toEqual([]);
  expect(passwordInAnyUrl(log)).toEqual([]);
});

test("an app start whose token fetch fails sends nothing with the password, and recovers without a reload", async ({
  page,
}) => {
  await signIn(page);
  await page.evaluate(() => localStorage.removeItem("lms_subsonic_token"));
  // music-manager restarting during a deploy: the one moment the old code asked for the token.
  await page.route(TOKEN_ENDPOINT, (route) => route.abort("connectionrefused"));
  const log = recordRequests(page);

  await page.reload();
  await expect(page.locator("#username")).toHaveCount(0);
  // Let the page settle the way a phone's WebView does for hours: the shell and its lists load.
  await page.waitForTimeout(5_000);
  expect(withPassword(log), sequence(log)).toEqual([]);
  expect(unsigned(log), sequence(log)).toEqual([]);
  expect(passwordInAnyUrl(log)).toEqual([]);
  await expect(page.getByText("De server geeft geen toegang")).toBeVisible({ timeout: 15_000 });

  // The server is back: the same page gets its token and signs with it.
  await page.unroute(TOKEN_ENDPOINT);
  await page.getByRole("button", { name: "Opnieuw proberen" }).click();
  await expect(page.getByText("De server geeft geen toegang")).toHaveCount(0, { timeout: 15_000 });
  await searchAndPlay(page);

  expect(log.filter((entry) => entry.kind === "subsonic").length).toBeGreaterThan(0);
  expect(withPassword(log), sequence(log)).toEqual([]);
  expect(unsigned(log), sequence(log)).toEqual([]);
  expect(passwordInAnyUrl(log)).toEqual([]);
});
