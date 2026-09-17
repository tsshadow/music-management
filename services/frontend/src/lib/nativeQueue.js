import { logAction } from "./diagnosticsLog.js";

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
 * - **The whole list, every time.** Every queue mutation -- add to queue, play
 *   next, remove, reorder, play-this-list-from-index, clear -- is one
 *   `setQueue` carrying the complete ordered queue and the position of the
 *   current track in it. Nothing is ever pushed as a fragment: the plugin
 *   compares the item at `index` with the item it has loaded and rebuilds the
 *   rest around it, so a list is the only honest way to describe an edit.
 * - **The current track is always in the list that goes across.** A track
 *   playing from somewhere with no list behind it -- a card on the home screen,
 *   a search result -- sets `currentTrack` and leaves `playlist` alone. The
 *   service can only play what it holds, so that track goes in *front of* the
 *   queue rather than instead of it. Sending it instead of the queue is what
 *   made "add to queue" disappear on the emulator: every later edit was pushed
 *   as a one-item list holding only what was already playing.
 * - **Never send back what just came in.** When the service moves the track by
 *   itself, the UI mirrors it into `currentTrack`, and that write looks just
 *   like a listener pressing next. The guard is the service's own snapshot: if
 *   it already holds this list and has that track loaded, there is nothing to
 *   ask it for.
 *
 * The third rule is also why `setQueue` carries the autoplay rather than a
 * `load` behind it: the plugin positions the service on `index` as part of
 * accepting the queue, so by the time a follow-up call is considered the
 * service is *already* on that track and the guard swallows it. A queue pushed
 * with `autoplay: false` and nothing after it is a queue that never starts,
 * which is what a tapped track did on the phone while every unit test here
 * passed.
 *
 * Every call is serialised onto one promise chain: a `setQueue` is a bridge hop
 * and two of them racing would leave the service on whichever landed last
 * rather than on whichever was asked for last.
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
 * The list to send across, and where the current track sits in it.
 *
 * Almost always the UI's queue unchanged. The exception is the second rule: a
 * current track that is not in the queue is put in front of it, because the
 * service can only play what it holds. That also matches what a browser does
 * with the same stores -- `playNext` from a track outside the queue plays the
 * queue's first entry.
 *
 * @param {Array<object>} tracks - The UI's queue, in order.
 * @param {object|null} current - The track the UI wants playing.
 * @param {boolean} [adopting=false] - True on the boot sync, where the UI is
 *   following the service rather than steering it. A leftover `currentTrack`
 *   outside the restored queue is stale there, not an instruction, and putting
 *   it in front would replace a queue the listener is halfway through.
 * @returns {{queue: Array<object>, index: number}} `index` is -1 when there is
 *   no track to point the service at.
 */
export function queueToPush(tracks, current, adopting = false) {
  const currentId = current == null ? null : String(current.id);
  const index =
    currentId === null ? -1 : tracks.findIndex((track) => String(track.id) === currentId);
  if (index >= 0 || currentId === null || adopting) return { queue: tracks, index };
  return { queue: [current, ...tracks], index: 0 };
}

/**
 * Which track the UI should show as playing after the service moved by itself.
 *
 * The service is the one that advances on a native shell, and it reports the
 * move as a `command` event. Normally the snapshot that comes with it already
 * names the new track and this is a lookup. It does not always: the plugin
 * notifies the new state and the move as two separate bridge messages, and a
 * `command` read before the state caught up still says "next" while the
 * snapshot still says the old track. Stepping the UI's own queue by one is then
 * the answer, and it is a safe one -- the plugin only reports a move when the
 * track actually changed, and a step past either end returns nothing rather
 * than guessing at a wrap.
 *
 * @param {Array<object>} queue - The UI's queue, in order.
 * @param {string|number|null} currentId - Id of the track the UI shows now.
 * @param {{name?: string, trackId?: string|null, queueLength?: number|null}} command - The event.
 *   `queueLength` is the native side's own queue length, carried in the snapshot every command
 *   arrives with.
 * @returns {object|null} The queue entry to move to, or null to stay put.
 */
export function trackAfterCommand(
  queue,
  currentId,
  { name = "", trackId = null, queueLength = null } = {},
) {
  const current = currentId == null ? null : String(currentId);
  const playing = trackId == null ? null : String(trackId);
  if (playing !== null && playing !== current) {
    return queue.find((entry) => String(entry.id) === playing) ?? null;
  }

  // No track and nothing queued is not a lagging snapshot catching up -- it is the transient
  // state a self-inflicted queue replacement produces while it clears the old timeline before the
  // new one loads (`status: "ended", queueLength: 0`). Stepping the UI's own queue on it invents a
  // move nobody made; staying put and waiting for the snapshot that actually names a track is the
  // only safe response to an empty one.
  if (playing === null && queueLength === 0) return null;

  const step = name === "next" ? 1 : name === "previous" ? -1 : 0;
  if (step === 0 || current === null) return null;
  const position = queue.findIndex((entry) => String(entry.id) === current);
  if (position < 0) return null;
  return queue[position + step] ?? null;
}

/**
 * Builds the thing that owns the hand-off.
 *
 * @param {object} player - `platform.player`, with `ownsQueue` true.
 * @param {{artworkUrlFor: function(object): string,
 *          onError?: function(Error): void}} options
 * @returns {{adopt: function(): Promise<string[]>,
 *            sync: function(Array<object>, object|null, {autoplay?: boolean}=): Promise<void>,
 *            pushedIds: function(): string[]|null,
 *            currentIndex: function(): number}}
 */
export function createNativeQueue(player, { artworkUrlFor, onError = () => {} }) {
  /** The ids last known to be on the far side; null until `adopt` or a push. */
  let pushed = null;
  /** The index last known to be on the far side, alongside [pushed]; -1 until `adopt` or a push. */
  let pushedIndex = -1;
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
        pushedIndex = queue.index;
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
   * @param {object|null} current - The track the UI wants playing, as the
   *   library returned it. The whole track rather than its id, because it is
   *   not always in `tracks`: see [queueToPush].
   * @param {{autoplay?: boolean}} [options] - Whether a move should start
   *   playback. False on the first sync after a boot and true on every sync
   *   after it, so restoring a queue does not start the music by itself while
   *   an intent that fills the queue ("play something", from a car or a tile)
   *   still does. It is not the UI's play/pause state: the plugin ignores it
   *   for an edit that keeps the current item, which is what makes re-sending
   *   the queue on every change safe.
   * @returns {Promise<void>}
   */
  function sync(tracks, current, { autoplay = true } = {}) {
    chain = chain.then(() => push(tracks, current, autoplay)).catch((error) => onError(error));
    return chain;
  }

  async function push(tracks, current, autoplay) {
    // `autoplay` false is the boot sync and nothing else; see [sync].
    const { queue, index } = queueToPush(tracks, current, !autoplay);
    const ids = queue.map((track) => String(track.id));
    const same = !isDifferentQueue(pushed, ids);

    // Nothing the service does not already know. Either the last push already told it this exact
    // list and index -- including a push it drove itself, which the UI mirrors back through
    // `currentTrack` and would otherwise ask for again -- or there is no track to point it at, or
    // it is already on that one. Re-sending an identical list with the same current item makes the
    // plugin rebuild the queue around it for no reason; re-sending it with an index the native side
    // never actually reached (a stale mirror of a transient event) would ask for a real move.
    if (same && index === pushedIndex) return;
    if (same && index < 0) return;
    if (same && String(player.state().trackId) === ids[index]) {
      // The service moved by itself (a command, or a plugin-driven advance) and the UI is only
      // mirroring that into `currentTrack`; no call is needed, but `pushedIndex` still has to catch
      // up to the position the service actually reached -- otherwise `currentIndex()` (what "now
      // playing" and "next up" are built from) would keep reporting the position of the last edit
      // this side made rather than where playback actually is.
      pushedIndex = index;
      return;
    }

    logAction("queue.replace", { length: ids.length, index: Math.max(index, 0) });

    // One call for every kind of change. A different list is a new queue; the
    // same list with a different `index` is "play that one instead", and the
    // plugin tells those apart by comparing the item at `index` with the item
    // it has loaded. The autoplay rides along because the plugin positions the
    // service on `index` while accepting the queue; it is ignored on an edit
    // that leaves the current item where it is, so a queue that keeps being
    // re-sent cannot un-pause the player.
    await player.setQueue({
      tracks: queue.map((track) => toQueueTrack(track, artworkUrlFor)),
      index: Math.max(index, 0),
      autoplay: autoplay && index >= 0,
    });
    pushed = ids;
    pushedIndex = index;
  }

  return {
    adopt,
    sync,
    pushedIds: () => (pushed === null ? null : pushed.slice()),
    // Where the service is now, for `Player.svelte`'s `queueIndex` (what "now playing" and the
    // continuation sections in `NowPlaying.svelte` are built from). -1 before the first
    // `adopt`/push, same as `pushedIndex` itself.
    currentIndex: () => pushedIndex,
  };
}
