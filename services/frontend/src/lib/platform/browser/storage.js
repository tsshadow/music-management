/**
 * Offline storage in a plain browser tab: there is none.
 *
 * `supported` is false and stays false, and every method answers with the
 * emptiest honest value rather than throwing -- a caller that forgets to check
 * `supported` gets "nothing is downloaded", which is the truth here, instead of
 * an exception halfway down a list render. The Downloads tab reads `supported`
 * and hides itself.
 *
 * The Capacitor implementation of this interface wraps the existing
 * `DownloadService` and `OfflineMusicService`; a later PWA implementation would
 * use Cache Storage. Both answer the same calls, which is why the shape is
 * fixed here and not when the first of them is written.
 */

const UNSUPPORTED = "Downloads are not available in the browser";

/** @type {import('../index.js').PlatformStorage} */
const storage = {
  supported: false,

  /**
   * A Subsonic-shaped query answered from what is on the device.
   *
   * @param {object} _request - The same parameters a Subsonic call takes.
   * @returns {Promise<object>} An empty `subsonic-response` body, so list
   *   components can read it the way they read the server's.
   */
  async query(_request) {
    return { "subsonic-response": { status: "ok", version: "1.16.1" } };
  },

  /**
   * @param {string} _id - Track, album or playlist id.
   * @returns {Promise<never>} Always rejects with {@link UNSUPPORTED}.
   */
  async download(_id) {
    throw new Error(UNSUPPORTED);
  },

  /** @returns {Promise<Array<object>>} Always empty. */
  async list() {
    return [];
  },

  /**
   * @param {string} _id
   * @returns {Promise<void>} Resolves; removing what is not there is not an error.
   */
  async remove(_id) {},

  /**
   * Download state per id, batched per list.
   *
   * @param {string[]} ids
   * @returns {Promise<Record<string, 'none'|'queued'|'running'|'done'|'failed'>>}
   *   Every id mapped to `none`.
   */
  async stateOf(ids) {
    return Object.fromEntries((ids ?? []).map((id) => [id, "none"]));
  },

  /**
   * @param {string} _id
   * @returns {Promise<boolean>} Always false.
   */
  async isLocal(_id) {
    return false;
  },

  /** @returns {Promise<number>} Bytes used on the device; always 0. */
  async size() {
    return 0;
  },

  /** @returns {Promise<void>} There is nothing to delete in a browser tab. */
  async clearCache() {},

  /**
   * Whether there is no route to the music server.
   *
   * A browser tab never answers `true`: it has no offline library to switch
   * to, so "offline" would only mean "show nothing", and a failing request
   * already says that more accurately than a guess made in advance does.
   *
   * @returns {Promise<boolean>} Always false.
   */
  async isOffline() {
    return false;
  },

  /**
   * The start-up check (docs/designs/app-start-reachability/). A browser tab has no start-up
   * sequence to pause and no offline library to continue with, so it never runs one: the answer
   * is always "reachable", and a failing request says the rest.
   *
   * @param {{timeoutMs?: number}} [_options]
   * @returns {Promise<{state: string, elapsedMs: number, offlineChosen: boolean}>}
   */
  async checkServer(_options) {
    return { state: "reachable", elapsedMs: 0, offlineChosen: false };
  },

  /**
   * "Offline verder" on or off. Nothing to switch in a browser tab.
   *
   * @param {boolean} _enabled
   * @returns {Promise<void>}
   */
  async setOfflineMode(_enabled) {},

  /**
   * @param {function({online: boolean}): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onConnectivity(_handler) {
    return () => {};
  },

  /**
   * @param {function(object): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onProgress(_handler) {
    return () => {};
  },
};

export default storage;
