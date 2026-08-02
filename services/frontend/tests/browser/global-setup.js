import { chromium, expect } from "@playwright/test";

/**
 * Loads the app once before the suite starts.
 *
 * The browser tests run against `vite preview`, i.e. the built bundle, so there
 * is no dependency pre-bundling to pay for any more -- this is now just a smoke
 * check that the served app renders at all, which makes a broken build fail
 * here with one clear message instead of in every test at once.
 *
 * History, so nobody reintroduces it: the suite used to run against the dev
 * server, where `#app` stays an empty div until Vite finishes optimizing and
 * reloads. That is ~2s locally but has taken over 30s, and once over 120s, on a
 * loaded CI runner -- it failed release/0.0.58's pipeline and later develop's
 * while the app itself was fine.
 */
export default async function globalSetup(config) {
  const { baseURL } = config.projects[0].use;
  const browser = await chromium.launch();

  try {
    const page = await browser.newPage();
    await page.goto(baseURL, { waitUntil: "load", timeout: 60_000 });
    await expect(page.locator("#app")).toBeVisible({ timeout: 30_000 });
  } finally {
    await browser.close();
  }
}
