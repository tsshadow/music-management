import { chromium, expect } from "@playwright/test";

/**
 * Loads the app once before the suite starts, purely to pay for Vite's
 * cold-start dependency pre-bundling.
 *
 * Without this, the first test in the run doubles as a startup-latency
 * benchmark: `#app` stays an empty div until Vite has finished optimizing and
 * reloaded, which is ~2s on a developer machine but has taken over 30s on a
 * loaded CI runner. That made a green suite depend on how busy the runner was,
 * and it failed release/0.0.58's pipeline while the app itself was fine.
 *
 * Warming up here keeps that cost out of the tests, so their timeouts can stay
 * tight enough to still catch an app that genuinely does not render.
 */
export default async function globalSetup(config) {
  const { baseURL } = config.projects[0].use;
  const browser = await chromium.launch();

  try {
    const page = await browser.newPage();
    await page.goto(baseURL, { waitUntil: "load" });
    // Generous: this is the one place where slow is acceptable.
    await expect(page.locator("#app")).toBeVisible({ timeout: 120_000 });
  } finally {
    await browser.close();
  }
}
