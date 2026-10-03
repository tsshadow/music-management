// The views off the first screen load as their own chunks (issue #114,
// docs/designs/perceived-performance/technical.md "Code splitting"). These tests
// run against the built bundle (`vite preview`, see playwright.config.js), which is
// the only place the split exists: in vitest every import is local.
//
// Two ways into a lazily loaded view, both of which must end on the rendered page:
// - by URL, where main.js fetches the chunk behind the boot screen before mounting;
// - by navigating inside the app, where LazyView fetches it and shows skeleton rows
//   meanwhile.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

test.use({ storageState: ADMIN_STORAGE_STATE });

/** Collects the JavaScript files the page fetches, by file name. */
function recordScripts(page) {
  const files = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/assets/") && url.pathname.endsWith(".js")) {
      files.push(url.pathname.slice("/assets/".length));
    }
  });
  return files;
}

/** Fails the test on any uncaught error, a failed chunk import included. */
function recordErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test("a management tab opened by URL renders, fetched as its own chunk", async ({ page }) => {
  const scripts = recordScripts(page);
  const errors = recordErrors(page);

  await page.goto("/management/config");

  await expect(page.getByRole("heading", { name: "Configuratie" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator("#boot-screen")).toHaveCount(0);
  await expect(page.getByTestId("lazy-view-loading")).toHaveCount(0);
  // The shell and the one tab on screen, not every tab.
  expect(scripts.some((file) => /^Management-[\w-]+\.js$/.test(file))).toBe(true);
  expect(scripts.some((file) => /^ConfigTab-[\w-]+\.js$/.test(file))).toBe(true);
  expect(scripts.some((file) => /^UsersTab-[\w-]+\.js$/.test(file))).toBe(false);
  expect(errors).toEqual([]);
});

test("the statistics page reached from the sidebar loads on demand and renders", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "the sidebar is the desktop layout's");
  const scripts = recordScripts(page);
  const errors = recordErrors(page);

  await page.goto("/");
  await expect(page.locator("#boot-screen")).toHaveCount(0, { timeout: 20_000 });
  // Not part of the first screen: nothing has asked for it yet.
  expect(scripts.some((file) => /^ListeningStatsView-[\w-]+\.js$/.test(file))).toBe(false);

  await page.getByRole("button", { name: "Luisterstatistieken" }).first().click();

  await expect(page.getByRole("heading", { name: "Luisterstatistieken", level: 1 })).toBeVisible({
    timeout: 15_000,
  });
  expect(scripts.some((file) => /^ListeningStatsView-[\w-]+\.js$/.test(file))).toBe(true);
  expect(errors).toEqual([]);
});

test("the first screen does not fetch the management or settings code", async ({ page }) => {
  const scripts = recordScripts(page);
  // Hold back the idle preload: this is about what the first paint waits for.
  await page.addInitScript(() => {
    window.requestIdleCallback = () => 0;
  });

  await page.goto("/");
  await expect(page.locator("#boot-screen")).toHaveCount(0, { timeout: 20_000 });

  const lazy = scripts.filter((file) =>
    /^(Management|Settings|GeneralSettings|DeviceSettings|About|Advanced|Help|[A-Za-z]+Tab|ListeningStatsView|SetupWizard)-/.test(
      file,
    ),
  );
  expect(lazy).toEqual([]);
  // The pages one tap away are not first-screen code either (issue #118): they come with the
  // idle preload, held back here.
  const oneTap = scripts.filter((file) =>
    /^(ArtistView|AlbumView|FeedView|PresetView|PlaylistView|FilterBar|CollectionGrid)-/.test(file),
  );
  expect(oneTap).toEqual([]);
  // Nor is the full-screen player (issue #119): the mini player is in the entry, Now Playing
  // comes with the idle preload or a press on the mini player.
  expect(scripts.filter((file) => file.startsWith("NowPlaying-"))).toEqual([]);
});

test("index.html preloads the listener's locale file together with the entry", async ({ page }) => {
  const scripts = recordScripts(page);
  // The browser runs in nl-NL (playwright.config.js), so Dutch is the locale the app starts in.
  await page.goto("/");
  await expect(page.locator("#boot-screen")).toHaveCount(0, { timeout: 20_000 });

  const hints = await page
    .locator('link[rel="modulepreload"]')
    .evaluateAll((links) => links.map((link) => new URL(link.href).pathname));
  expect(hints.some((path) => /^\/assets\/nl-[\w-]+\.js$/.test(path))).toBe(true);
  expect(hints.some((path) => /^\/assets\/en-[\w-]+\.js$/.test(path))).toBe(false);
  // The hint names the file the app itself imports: it is fetched once, not twice.
  expect(scripts.filter((file) => /^nl-[\w-]+\.js$/.test(file))).toHaveLength(1);
});

test("a settings tab opened by URL renders, fetched as its own chunk", async ({ page }) => {
  const scripts = recordScripts(page);
  const errors = recordErrors(page);
  // Hold back the idle preloads, the next settings tab's included: this is about what opening
  // one tab fetches (issue #119).
  await page.addInitScript(() => {
    window.requestIdleCallback = () => 0;
  });

  await page.goto("/settings/about");

  await expect(page.getByRole("heading", { name: "Over MuMa", level: 1 })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator("#boot-screen")).toHaveCount(0);
  await expect(page.getByTestId("settings-tab-loading")).toHaveCount(0);
  expect(scripts.some((file) => /^About-[\w-]+\.js$/.test(file))).toBe(true);
  // Not the other tabs: the 79 kB settings chunk is one file per tab now.
  expect(
    scripts.filter((file) => /^(GeneralSettings|DeviceSettings|Advanced)-/.test(file)),
  ).toEqual([]);
  expect(errors).toEqual([]);
});

test("switching settings tab shows the tab's skeleton until its code is in", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "the settings sidebar is the desktop layout's");
  const errors = recordErrors(page);
  let releaseChunk;
  const chunkHeld = new Promise((resolve) => {
    releaseChunk = resolve;
  });
  let chunkRequested = false;
  await page.route(/\/assets\/Advanced-[\w-]+\.js$/, async (route) => {
    chunkRequested = true;
    await chunkHeld;
    await route.continue();
  });

  await page.goto("/settings/general");
  await expect(page.getByRole("heading", { name: "Algemene Instellingen", level: 1 })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Geavanceerd" }).first().click();

  await expect.poll(() => chunkRequested).toBe(true);
  await expect(page.getByTestId("settings-tab-loading")).toBeVisible();

  releaseChunk();
  await expect(page.getByRole("heading", { name: "Geavanceerd", level: 1 })).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("settings-tab-loading")).toHaveCount(0);
  expect(errors).toEqual([]);
});
