/**
 * An in-memory stale-while-revalidate cache for what a page loads about one thing (an artist,
 * an album...), keyed by a string such as `artist:42`.
 *
 * Why it exists: revisiting a page that was on screen a minute ago used to cost the same full
 * round trip as the first visit, with the page blank in between. With this, a revisit renders
 * the previous answer at once and refreshes it in the background
 * (docs/designs/perceived-performance/technical.md, "Entity cache").
 *
 * Deliberately memory only: nothing is written to storage, so stale data lives at most one
 * session and at most `maxAgeMs`. A failed load is never cached.
 */

/**
 * @typedef {object} CacheEntry
 * @property {any} value
 * @property {number} fetchedAt - Epoch milliseconds of the answer.
 * @property {boolean} fresh - Younger than `freshMs`: no refresh needed.
 */

/**
 * Creates a cache.
 *
 * @param {object} [options]
 * @param {number} [options.maxEntries=100] - Least recently used entries beyond this are evicted.
 * @param {number} [options.freshMs=60000] - Younger than this, `swr` does not refresh at all.
 * @param {number} [options.maxAgeMs=300000] - Older than this, an entry is treated as absent.
 * @param {() => number} [options.now] - Injected by the tests.
 */
export function createEntityCache({
  maxEntries = 100,
  freshMs = 60_000,
  maxAgeMs = 300_000,
  now = () => Date.now(),
} = {}) {
  /** @type {Map<string, {value: any, fetchedAt: number}>} Insertion order is recency order. */
  const entries = new Map();
  /** @type {Map<string, Promise<any>>} One request per key at a time. */
  const inFlight = new Map();

  /**
   * The entry for `key`, or `null` when there is none worth showing.
   *
   * @param {string} key
   * @returns {CacheEntry|null}
   */
  function peek(key) {
    const entry = entries.get(key);
    if (!entry) return null;
    const age = now() - entry.fetchedAt;
    if (age > maxAgeMs) {
      entries.delete(key);
      return null;
    }
    // A read counts as a use: move the entry to the young end of the LRU order.
    entries.delete(key);
    entries.set(key, entry);
    return { value: entry.value, fetchedAt: entry.fetchedAt, fresh: age <= freshMs };
  }

  /**
   * Stores an answer.
   *
   * @param {string} key
   * @param {any} value
   */
  function set(key, value) {
    entries.delete(key);
    entries.set(key, { value, fetchedAt: now() });
    while (entries.size > maxEntries) {
      entries.delete(entries.keys().next().value);
    }
  }

  /**
   * Edits a stored answer in place, keeping its age -- for an optimistic change such as a star
   * toggle, so a revisit shows the edit rather than the copy from before it. Absent keys are
   * left absent.
   *
   * @param {string} key
   * @param {(value: any) => any} fn - Returns the new value.
   */
  function update(key, fn) {
    const entry = entries.get(key);
    if (!entry) return;
    entry.value = fn(entry.value);
  }

  /**
   * Loads `key` through `loader`, sharing a request already under way for the same key -- a
   * prefetch on pointerdown and the page that opens on click end up waiting on one request.
   *
   * @param {string} key
   * @param {() => Promise<any>} loader
   * @param {{force?: boolean}} [options] - `force` skips a fresh entry and asks again.
   * @returns {Promise<any>}
   */
  function load(key, loader, { force = false } = {}) {
    if (!force) {
      const cached = peek(key);
      if (cached?.fresh) return Promise.resolve(cached.value);
    }
    const pending = inFlight.get(key);
    if (pending) return pending;
    const request = (async () => {
      try {
        const value = await loader();
        set(key, value);
        return value;
      } finally {
        inFlight.delete(key);
      }
    })();
    inFlight.set(key, request);
    return request;
  }

  /**
   * Stale-while-revalidate: hands over the cached answer synchronously when there is one, then
   * refreshes it unless it is still fresh.
   *
   * @param {string} key
   * @param {() => Promise<any>} loader
   * @param {(value: any, meta: {fromCache: boolean}) => void} onValue - Called up to twice.
   * @returns {{cached: any, promise: Promise<any>}} `cached` is `null` without a usable entry;
   *   `promise` rejects when the refresh fails, so a caller can tell a section it failed.
   */
  function swr(key, loader, onValue) {
    const cached = peek(key);
    if (cached) onValue(cached.value, { fromCache: true });
    if (cached?.fresh) return { cached: cached.value, promise: Promise.resolve(cached.value) };
    const promise = load(key, loader, { force: true }).then((value) => {
      onValue(value, { fromCache: false });
      return value;
    });
    return { cached: cached ? cached.value : null, promise };
  }

  /**
   * Drops one key, or every key starting with `prefix` when it ends in `:`.
   *
   * @param {string} keyOrPrefix
   */
  function invalidate(keyOrPrefix) {
    if (keyOrPrefix.endsWith(":")) {
      for (const key of [...entries.keys()]) {
        if (key.startsWith(keyOrPrefix)) entries.delete(key);
      }
      return;
    }
    entries.delete(keyOrPrefix);
  }

  /** Forgets everything, e.g. when another account signs in. */
  function clear() {
    entries.clear();
    inFlight.clear();
  }

  return {
    peek,
    set,
    update,
    load,
    swr,
    invalidate,
    clear,
    /** How many answers are held; for the tests. */
    get size() {
      return entries.size;
    },
  };
}
