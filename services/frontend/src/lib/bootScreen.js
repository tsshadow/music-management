import { get } from "svelte/store";
import { t } from "./i18n/index.js";

/**
 * Drives the boot screen `index.html` paints before the bundle runs: the stage line, the
 * progress bar, the "taking longer than usual" hint, and its removal once the app has mounted
 * (docs/designs/perceived-performance/, styleguide "Boot screen").
 *
 * Every function is a no-op when the screen is not in the document -- a vitest run, a second
 * mount, a page that already dismissed it -- so callers never need to check.
 */

/** The stages the shell walks through, in order. */
export const BOOT_STAGES = Object.freeze(["connecting", "signingIn", "restoringQueue", "starting"]);

/** How long one stage may take before the hint appears. */
export const BOOT_SLOW_AFTER_MS = 8000;

/** How long the fade-out lasts; matches the transition in `index.html`. */
export const BOOT_FADE_MS = 200;

let slowTimer = null;
let lastStage = null;

/** @param {Document} doc */
function screenOf(doc) {
  return doc?.getElementById?.("boot-screen") ?? null;
}

/**
 * Shows a stage.
 *
 * @param {string} stage - One of `BOOT_STAGES`.
 * @param {{done?: number, total?: number}} [progress] - With `total > 0` the bar fills to
 *   `done/total` instead of sliding.
 * @param {Document} [doc] - Injected by the tests.
 */
export function setBootStage(stage, { done = 0, total = 0 } = {}, doc = globalThis.document) {
  const screen = screenOf(doc);
  if (!screen) return;

  const label = screen.querySelector("[data-boot-stage]");
  if (label) label.textContent = get(t)(`boot.${stage}`);

  const bar = screen.querySelector("[data-boot-bar]");
  if (bar) {
    if (total > 0) {
      bar.classList.add("boot-determinate");
      bar.style.width = `${Math.round((Math.min(done, total) / total) * 100)}%`;
    } else {
      bar.classList.remove("boot-determinate");
      bar.style.width = "";
    }
  }

  // Progress within a stage is not a new stage: the hint's clock keeps running.
  if (stage === lastStage) return;
  lastStage = stage;
  const hint = screen.querySelector("[data-boot-hint]");
  if (hint) hint.textContent = "";
  clearTimeout(slowTimer);
  slowTimer = setTimeout(() => {
    if (hint && screen.isConnected) hint.textContent = get(t)("boot.slow");
  }, BOOT_SLOW_AFTER_MS);
}

/**
 * Removes the boot screen: the app is on screen underneath. Also tells the inline script in
 * `index.html` not to offer its retry button any more.
 *
 * @param {Document} [doc] - Injected by the tests.
 * @returns {Promise<void>} Resolves once the screen is gone.
 */
export function dismissBootScreen(doc = globalThis.document) {
  const win = doc?.defaultView;
  if (win) {
    win.__mumaBootDone = true;
    if (win.__mumaBootTimer) clearTimeout(win.__mumaBootTimer);
  }
  clearTimeout(slowTimer);
  slowTimer = null;
  lastStage = null;
  const screen = screenOf(doc);
  if (!screen) return Promise.resolve();
  screen.classList.add("boot-leaving");
  return new Promise((resolve) => {
    setTimeout(() => {
      screen.remove();
      resolve();
    }, BOOT_FADE_MS);
  });
}
