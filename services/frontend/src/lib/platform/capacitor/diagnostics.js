import { createBrowserDiagnostics } from "../browser/diagnostics.js";
import { fireAndForget } from "./listen.js";

/**
 * `platform.diagnostics` inside the Android shell: the same ring buffer the
 * browser keeps, plus a copy of every line in `WebActionLog` and the Timber
 * buffer on the Kotlin side.
 *
 * Writing to both is the point. `report()` has to answer synchronously -- a
 * screen renders it -- so the in-memory buffer stays; and a crash report has to
 * read as one sequence of what the user did rather than as two logs somebody
 * has to interleave by hand, so the same line also crosses the bridge. The two
 * cannot drift, because there is one call site for both.
 */

/**
 * Builds the shell's diagnostics implementation.
 *
 * @param {object} plugin - The registered `MumaDiagnostics` plugin.
 * @returns {object} An implementation of the `platform.diagnostics` interface.
 */
export function createCapacitorDiagnostics(plugin) {
  const local = createBrowserDiagnostics();

  return {
    supported: true,

    /**
     * @param {string} action - A short, stable name: "play", "open:album".
     * @param {object} [detail]
     */
    log(action, detail = null) {
      local.log(action, detail);
      fireAndForget(
        "diagnostics.log",
        plugin.log({ action: String(action), detail: detail ?? {} }),
      );
    },

    /**
     * @returns {Array<{action: string, at: number, detail: object|null}>} The
     *   web side's own buffer. The native one holds these lines and the Kotlin
     *   app's too; `nativeReport()` is how to read that.
     */
    report() {
      return local.report();
    },

    /**
     * The whole trail, the native app's actions included.
     *
     * @returns {Promise<Array<object>>}
     */
    async nativeReport() {
      try {
        const answer = await plugin.report();
        return Array.isArray(answer?.entries) ? answer.entries : [];
      } catch (error) {
        console.warn("Could not read the native action log", error);
        return [];
      }
    },

    clear() {
      local.clear();
      fireAndForget("diagnostics.clear", plugin.clear());
    },

    /** Sends the log now, through the crash-report path the Kotlin app uses. */
    send() {
      fireAndForget("diagnostics.send", plugin.send());
    },
  };
}
