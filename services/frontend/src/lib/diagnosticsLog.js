import { platform } from "./platform/index.js";

/**
 * The one place every screen calls to add a line to the action trail a crash
 * report reads back.
 *
 * `platform.diagnostics.log` already does the real work -- keeping the ring
 * buffer, and on the Android shell crossing the bridge into `WebActionLog`,
 * the same store `CrashReportManager` reads from for the native side's own
 * actions, so a report reads as one sequence rather than two logs someone has
 * to interleave by hand. This wrapper exists so every call site is one line
 * (`logAction('player.play', {trackId})`) and so a bad `detail` object -- or a
 * bridge call that throws instead of rejecting -- can never break the button
 * press it was only supposed to be reporting on.
 *
 * @param {string} action - A short, stable name. The Kotlin app's own
 *   convention is `subsystem.verb` (`player.play`, `queue.clear`,
 *   `rating.set`); new call sites here follow the same shape so a report from
 *   either UI reads the same way.
 * @param {object} [detail] - Small: an id, a view name, a count. Never a
 *   whole track/album object -- the ring buffer holds at most 50 entries and
 *   a report has to stay readable.
 */
export function logAction(action, detail) {
  try {
    platform.diagnostics.log(action, detail);
  } catch (error) {
    console.warn("Could not record a diagnostics action", action, error);
  }
}

/**
 * The longest a stack trace is allowed to be in a report. A ring buffer entry
 * is meant to be one line (see `WebActionLog.asReportText`); a stack that
 * still has newlines in it would turn one entry into several, so they are
 * flattened here rather than in Kotlin, which sees only the string this
 * builds.
 */
const MAX_STACK_LENGTH = 2000;

/**
 * @param {*} error - Whatever `window.onerror` or `unhandledrejection` handed
 *   over: usually an `Error`, sometimes a string, sometimes anything at all --
 *   a rejected promise can reject with any value.
 * @returns {{message: string, stack?: string}}
 */
export function describeError(error) {
  if (error instanceof Error) {
    const detail = { message: error.message || error.name || "Error" };
    if (typeof error.stack === "string" && error.stack) {
      detail.stack = error.stack.replace(/\s+/g, " ").trim().slice(0, MAX_STACK_LENGTH);
    }
    return detail;
  }
  return { message: typeof error === "string" ? error : (JSON.stringify(error) ?? String(error)) };
}

/**
 * Records an uncaught error or an unhandled promise rejection.
 *
 * Forwarded through `platform.diagnostics` -- which is `logAction` above --
 * only inside the Android shell: that is the one place a report gets built
 * from this ring buffer afterwards. A plain browser tab has no such report,
 * and adding fifty lines of stack traces nobody reads to a buffer that also
 * has to hold navigation and playback would only push those out; it gets a
 * `console.error` instead, which is where a browser tab's own devtools
 * already look.
 *
 * @param {*} error
 * @param {{action?: string}} [options] - `action` distinguishes an uncaught
 *   throw (`js.error`, the default) from a rejected promise (`js.unhandledRejection`).
 */
export function logError(error, { action = "js.error" } = {}) {
  const detail = describeError(error);
  if (platform.system?.isNative) {
    logAction(action, detail);
  } else {
    console.error("Uncaught in the web UI", action, detail.message, error);
  }
}

/**
 * Tells the native side which UI is running, what code it is running, and
 * what rendered it -- the three facts `CrashReportManager` cannot know on its
 * own once the web UI is the one making the report. Fetches the bundle's own
 * `version.json` (see `vite.config.js`), which is absent from a dev server
 * and from any build that ran before this existed; either way the call still
 * goes through with a null version rather than not at all, because a
 * report's "UI: web" line is worth having even without one.
 *
 * Called once, from `main.js`, on every boot -- including a browser tab's,
 * where `platform.diagnostics.identify` is a no-op, so this does not need its
 * own native check.
 *
 * @returns {Promise<void>}
 */
/**
 * Reads `version.json`, the file `bundleVersionFile` in `vite.config.js` stages next to
 * `index.html`: the git short hash the bundle was built from and when. Shared by the crash
 * report's identity line and the About page.
 *
 * @returns {Promise<{version: string, builtAt: string|null}|null>} Null on a dev server or a
 *   build without one -- there is no bundle version to report then, and neither caller minds.
 */
export async function fetchBundleVersion() {
  try {
    const response = await fetch(new URL("version.json", document.baseURI));
    if (!response.ok) return null;
    const body = await response.json();
    if (typeof body?.version !== "string") return null;
    return {
      version: body.version,
      builtAt: typeof body.builtAt === "string" ? body.builtAt : null,
    };
  } catch {
    return null;
  }
}

export async function identifyBundle() {
  const bundleVersion = (await fetchBundleVersion())?.version ?? null;
  try {
    platform.diagnostics.identify({
      bundleVersion,
      userAgent: typeof navigator === "undefined" ? null : navigator.userAgent,
    });
  } catch (error) {
    console.warn("Could not identify the bundle to diagnostics", error);
  }
}
