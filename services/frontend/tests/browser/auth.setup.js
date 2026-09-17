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
  // Chromium runs as en-US and the stack is created per job, so this is a first
  // run: without these the interface would come up in English and land in the
  // setup tour. Both keys are read by store.js (`applyAccountSettings`) after
  // the login. The language is one the account has not chosen yet, so it is
  // uploaded and comes back from the account on every later page load; the
  // steps stay a local value, which the saved storage state carries along.
  await page.addInitScript(
    (seen) => {
      localStorage.setItem("muma_locale", JSON.stringify("nl"));
      localStorage.setItem("lms_setupStepsSeen", JSON.stringify(seen));
    },
    SETUP_STEPS.map((step) => step.id),
  );

  // Armed before the click: the upload happens some time after the overlay
  // has gone, and a state captured before it would leave the language to the
  // browser default on the next context.
  const languageSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/settings/frontend") &&
      (response.request().postData() || "").includes("language"),
    { timeout: 15_000 },
  );

  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Verbinden|Account Aanmaken/ }).click();
  await expect(page.locator("#username")).toHaveCount(0, { timeout: 15_000 });
  await languageSaved;

  await page.context().storageState({ path: ADMIN_STORAGE_STATE });
});
