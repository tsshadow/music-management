// Logs the CI admin in once and saves the browser state for the screenshot
// suite (screenshots.spec.js). Runs as the `setup` project, which the desktop
// and phone projects depend on -- see playwright.config.js.
//
// The functional specs keep their own login: they assert on the login flow
// itself, and smoke.spec.js must start from a browser that has never seen the
// app.
import { test as setup, expect } from "@playwright/test";
import { ADMIN_STORAGE_STATE } from "../../playwright.config.js";
import { SETUP_STEPS } from "../../src/lib/setup.js";

const USERNAME = "ci-contract-admin";
const PASSWORD = "ci-contract-password";

setup("log the admin in and keep the browser state", async ({ page }) => {
  // The stack is created per job, so this is a first run: without these the
  // interface would come up in the browser's language and land in the setup
  // tour. Both keys are plain localStorage values that the saved state carries
  // into every later context. The account never overrides them with anything
  // else -- store.js uploads a language the account has not chosen yet and
  // leaves setup steps local -- so there is nothing to wait for after the
  // login beyond the shell having rendered.
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
  // The overlay goes once the Subsonic ping and the muma login have both
  // answered; on a cold stack that is the slow part of the whole suite.
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: USERNAME })).toBeVisible({ timeout: 15_000 });

  await page.context().storageState({ path: ADMIN_STORAGE_STATE });
});
