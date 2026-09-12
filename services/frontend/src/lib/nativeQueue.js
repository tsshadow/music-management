/**
 * Keeping the platform service's queue in step with the UI's.
 *
 * On a native shell the queue lives in two places and only one of them is
 * allowed to be right. The web module still *decides* what is in it -- shuffle,
 * the news, a playlist, a search result -- but it cannot *hold* it: the WebView
 * is reclaimed whenever Android feels like it, and "next" has to keep working.
 * So the list is pushed across and the service drives from there.
 *
 * Three rules, and every subtle bug in this area is one of them being broken:
 *
 * - **The whole list, or nothing.** `setQueue` replaces it wholesale. A
 *   different set of ids is a new queue; the same ids in the same order is not,
 *   however many times a store fired.
 * - **A move inside the queue is a `load`, not a `setQueue`.** Re-pushing an
 *   identical list makes the service seek to the start of the item, which is
 *   exactly how a restored position gets thrown away.
 * - **Never send back what just came in.** When the service moves the track by
 *   itself, the UI mirrors it into `currentTrack`, and that write looks just
 *   like a listener pressing next. The guard is the service's own snapshot: if
 *   it already has that track loaded, there is nothing to ask it for.
 *
 * Every call is serialised onto one promise chain. `setQueue` and `load` are
 * bridge hops, and a `load` that overtook the `setQueue` that put the track in
 * the queue is rejected by the plugin with "not in the queue and not in this
 * device's cache" -- a real failure, reported as a missing track.
 */

/**
 * The shape the `MumaPlayer` plugin wants each queue entry in.
 *
 * Only what the notification, the lock screen and a head unit draw. The id is
 * what everything else is resolved from on the far side.
 *
 * @param {object} track - A Subsonic track as the library returned it.
 * @param {function(object): string} artworkUrlFor - Builds a cover URL; it
 *   carries credentials, so the web module is the only side that can.
 * @returns {{id: string, title: string, artist: string, album: string,
 *   artworkUrl: string, duration: number}}
 */
export function toQueueTrack(track, artworkUrlFor) {
  return {
    id: String(track.id),
    title: track.title ?? "",
    artist: track.artist ?? "",
    album: track.album ?? "",
    artworkUrl: artworkUrlFor(track) ?? "",
    duration: Number(track.duration) || 0,
  };
}

/**
 * @param {string[]|null} previous
 * @param {string[]} next
 * @returns {boolean} Whether this is a different queue rather than the same one
 *   reported again.
 */
export function isDifferentQueue(previous, next) {
  if (previous === null) return true;
  if (previous.length !== next.length) return true;
  return previous.some((id, position) => id !== next[position]);
}

/**
 * Builds the thing that owns the hand-off.
 *
 * @param {object} player - `platform.player`, with `ownsQueue` true.
 * @param {{artworkUrlFor: function(object): string,
 *          onError?: function(Error): void}} options
 * @returns {{adopt: function(): Promise<string[]>,
 *            sync: function(Array<object>, string|null, {autoplay?: boolean}=): Promise<void>,
 *            pushedIds: function(): string[]|null}}
 */
export function createNativeQueue(player, { artworkUrlFor, onError = () => {} }) {
  /** The ids last known to be on the far side; null until `adopt` or a push. */
  let pushed = null;
  let chain = Promise.resolve();

  /**
   * Takes over the queue the service is already holding.
   *
   * Called once, before the first sync. Without it the first store change would
   * push an identical list and restart the track the listener is halfway
   * through -- which is the whole thing phase 1 has to get right.
   *
   * @returns {Promise<string[]>}
   */
  function adopt() {
    chain = chain
      .then(async () => {
        const queue = await player.queueState();
        pushed = queue.trackIds.slice();
        return pushed;
      })
      .catch((error) => {
        onError(error);
        return [];
      });
    return chain;
  }

  /**
   * Makes the service's queue match this one.
   *
   * @param {Array<object>} tracks - The UI's queue, in order.
   * @param {string|null} currentId - The track the UI wants playing.
   * @param {{autoplay?: boolean}} [options] - Whether a move should start
   *   playback. False on the first sync after a boot, so restoring a queue does
   *   not start the music by itself.
   * @returns {Promise<void>}
   */
  function sync(tracks, currentId, { autoplay = true } = {}) {
    chain = chain.then(() => push(tracks, currentId, autoplay)).catch((error) => onError(error));
    return chain;
  }

  async function push(tracks, currentId, autoplay) {
    const ids = tracks.map((track) => String(track.id));
    const index = currentId == null ? -1 : ids.indexOf(String(currentId));

    if (isDifferentQueue(pushed, ids)) {
      await player.setQueue({
        tracks: tracks.map((track) => toQueueTrack(track, artworkUrlFor)),
        index: Math.max(index, 0),
        autoplay: false,
      });
      pushed = ids;
    }

    if (index < 0) return;
    // The service is already on this track: either it moved there itself and
    // the UI is following, or nothing changed. Asking again would seek to the
    // start of it.
    if (String(player.state().trackId) === ids[index]) return;

    await player.load({ trackId: ids[index], autoplay });
  }

  return { adopt, sync, pushedIds: () => (pushed === null ? null : pushed.slice()) };
}
