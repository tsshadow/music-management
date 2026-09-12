import { listen } from "./listen.js";

/**
 * `platform.storage` inside the Android shell: `DownloadService` and the files
 * on disk, reached through the `MumaStorage` plugin.
 *
 * The plugin speaks in batches (`{ids}`) because that is what a list needs --
 * one bridge hop per screen rather than one per row -- while the contract's
 * single-id calls are what a detail view wants. Both are offered: the batched
 * calls pass through, and the single-id ones wrap their argument.
 *
 * `query` is a phase-1 stub on the Kotlin side and answers the empty Subsonic
 * body, exactly as the browser implementation does. Phase 2 routes it to
 * `OfflineMusicService`; nothing here has to change when it does.
 */

/** What a list component gets for an id this device has never seen. */
const UNKNOWN = "none";

/**
 * Builds the shell's storage implementation.
 *
 * @param {object} plugin - The registered `MumaStorage` plugin.
 * @returns {object} An implementation of the `platform.storage` interface.
 */
export function createCapacitorStorage(plugin) {
  /**
   * @param {string|string[]} ids
   * @returns {string[]}
   */
  function idsOf(ids) {
    if (Array.isArray(ids)) return ids.map(String).filter(Boolean);
    return ids == null || ids === "" ? [] : [String(ids)];
  }

  return {
    supported: true,

    /**
     * A Subsonic-shaped request answered from local files.
     *
     * @param {object} request
     * @returns {Promise<object>}
     */
    async query(request) {
      return await plugin.query(request ?? {});
    },

    /**
     * @param {string|string[]} ids - Track ids.
     * @param {{pin?: boolean}} [options] - `pin` keeps the files through a cache
     *   sweep; without it they are downloaded into the cache, which is what the
     *   Kotlin UI's "download" has always done.
     * @returns {Promise<{requested: number, unknown: number}>}
     */
    async download(ids, options = {}) {
      return await plugin.download({ ids: idsOf(ids), pin: options.pin === true });
    },

    /** @returns {Promise<Array<object>>} What is on the device. */
    async list() {
      const answer = await plugin.list();
      return Array.isArray(answer?.items) ? answer.items : [];
    },

    /**
     * @param {string|string[]} ids
     * @returns {Promise<void>}
     */
    async remove(ids) {
      await plugin.remove({ ids: idsOf(ids) });
    },

    /**
     * @param {string[]} ids
     * @returns {Promise<Record<string, string>>} Every id mapped to its state;
     *   an id the plugin did not answer for reads as `none` rather than
     *   `undefined`, so a row can render it without a check.
     */
    async stateOf(ids) {
      const wanted = idsOf(ids);
      if (!wanted.length) return {};
      const answer = await plugin.stateOf({ ids: wanted });
      return Object.fromEntries(wanted.map((id) => [id, answer?.[id] ?? UNKNOWN]));
    },

    /**
     * @param {string} id
     * @returns {Promise<boolean>}
     */
    async isLocal(id) {
      const answer = await plugin.isLocal({ id: String(id ?? "") });
      return answer?.value === true;
    },

    /** @returns {Promise<number>} Bytes used on the device. */
    async size() {
      const answer = await plugin.size();
      return typeof answer?.value === "number" ? answer.value : 0;
    },

    /**
     * @param {function({id: string, state: string, progress: number}): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onProgress(handler) {
      return listen(plugin, "progress", (event) =>
        handler({
          id: String(event?.id ?? ""),
          state: event?.state ?? UNKNOWN,
          progress: typeof event?.progress === "number" ? event.progress : 0,
        }),
      );
    },
  };
}
