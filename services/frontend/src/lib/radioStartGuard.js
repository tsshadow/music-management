/**
 * Serialises the asynchronous "tune in to a channel" steps in `Player.svelte`.
 *
 * Starting radio is two awaits long (the native service call, then the controller's clock
 * measurement and first state fetch). Two quick taps, or a tap on a second channel while the first
 * is still starting, used to run both starts to completion: two `platform.player.startRadio` calls,
 * two controllers both loading their stream into the one audio element, and a late failure of the
 * first tearing down the display of the second. Every start now takes a ticket; only the newest
 * ticket may touch shared state once its await returns, and a repeat of the start already in
 * flight is dropped outright.
 */

/**
 * @typedef {object} RadioTicket
 * @property {function(): boolean} isCurrent - Whether no newer start (or a stop) has happened since.
 * @property {function(): void} done - Marks this start finished, so the same key may start again.
 */

/**
 * Creates a guard. One per player.
 *
 * @returns {{begin: function(string=): (RadioTicket|null), invalidate: function(): void, pending: function(): (string|null)}}
 */
export function createRadioStartGuard() {
  let generation = 0;
  /** @type {string|null} */
  let pendingKey = null;

  return {
    /**
     * Starts a new attempt and makes every earlier ticket stale.
     *
     * @param {string} [key] - What is being started (a channel slug). When the same key is
     *   already in flight the call is a duplicate tap and `null` comes back: do nothing.
     *   Without a key there is no duplicate check.
     * @returns {RadioTicket|null}
     */
    begin(key) {
      if (key !== undefined && key === pendingKey) return null;
      generation += 1;
      const mine = generation;
      pendingKey = key ?? null;
      return {
        isCurrent: () => mine === generation,
        done: () => {
          if (mine === generation) pendingKey = null;
        },
      };
    },

    /** Makes every outstanding ticket stale -- radio was switched off while one was starting. */
    invalidate() {
      generation += 1;
      pendingKey = null;
    },

    /** The key of the start in flight, or `null`. */
    pending() {
      return pendingKey;
    },
  };
}
