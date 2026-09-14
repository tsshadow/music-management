/**
 * What the user did, kept in memory and nowhere else.
 *
 * On the phone this feeds `CrashReportManager`, so a crash report says which
 * screens and buttons led up to it. In the browser there is nothing to send it
 * to: the ring buffer is kept anyway -- the cost is 50 small objects -- so a
 * screen that shows the log works the same everywhere, and so the call sites
 * that log actions do not need a platform check around them.
 */

/** How many actions are kept. The oldest is dropped to make room. */
export const CAPACITY = 50;

/**
 * Builds a diagnostics recorder.
 *
 * Exported for the tests; the app imports the default instance.
 *
 * @returns {import('../index.js').PlatformDiagnostics}
 */
export function createBrowserDiagnostics() {
  /** @type {Array<{action: string, at: number, detail: object|null}>} */
  let entries = [];

  return {
    supported: true,

    /**
     * @param {string} action - A short, stable name: "play", "open:album".
     * @param {object} [detail] - Anything small that helps read it back.
     */
    log(action, detail = null) {
      entries.push({ action: String(action), at: Date.now(), detail });
      if (entries.length > CAPACITY) entries = entries.slice(-CAPACITY);
    },

    /**
     * @returns {Array<{action: string, at: number, detail: object|null}>}
     *   The last {@link CAPACITY} actions, oldest first. A copy: a caller that
     *   mutates the report cannot corrupt the buffer.
     */
    report() {
      return entries.map((entry) => ({ ...entry }));
    },

    /** Throws the buffer away. */
    clear() {
      entries = [];
    },

    /**
     * A browser tab has no crash report to attach this to -- there is nothing
     * downstream of the ring buffer above -- so it is a no-op. Kept as part of
     * the contract anyway, so a call site never needs a platform check around
     * it.
     */
    identify() {},
  };
}

export default createBrowserDiagnostics();
