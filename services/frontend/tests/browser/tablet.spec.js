// A tablet in landscape: wide enough for the desktop layout (Tailwind's `md` and up), but a
// touch screen, so `App.svelte` sets `isMobile` from `(pointer: coarse)`. That combination fell
// between the two top bars in TopBar.svelte -- the phone bar was rendered and then hidden by its
// own `md:hidden`, the desktop bar was never rendered -- and the tablet showed no search box and
// no profile button (docs/bug-reports/090-tablet-landscape-topbar.md). jsdom applies no CSS, so
// this is the one place the real stylesheet proves both are on screen.
//
// Runs in the `desktop` project only (playwright.config.js ignores it in `phone`); the viewport
// and the touch flag are set here.
import { test, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";

test.use({
  storageState: ADMIN_STORAGE_STATE,
  viewport: { width: 1280, height: 800 },
  hasTouch: true,
});

test("a tablet in landscape shows the search box and the profile button", async ({ page }) => {
  await page.goto("/");

  // hasTouch alone is what makes Chromium report a coarse pointer; without it this test would
  // be a plain desktop run and prove nothing.
  expect(await page.evaluate(() => window.matchMedia("(pointer: coarse)").matches)).toBe(true);

  await expect(page.getByPlaceholder(/Wat wil je luisteren\?/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('button[aria-haspopup="true"]').first()).toBeVisible();
});
