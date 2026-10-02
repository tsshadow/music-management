import { get, writable } from "svelte/store";
import { currentTrack, playlist } from "./store.js";

/**
 * The app-start queue restore, once it runs behind a mounted UI (issue #113,
 * docs/designs/deferred-queue-restore/).
 *
 * Inside the Android shell the app used to wait for the restore before it mounted: one `getSong`
 * per queued id, up to 200. Now it mounts first and the restore fills the queue afterwards. That
 * opens a window in which two things can go wrong, and this module closes both:
 *
 * - **Nothing half-done reaches the player service.** While a restore runs, `status` is
 *   `restoring`, and `Player.svelte`'s queue sync pushes nothing at all -- not the empty queue
 *   the UI starts with, not a partial one. The service keeps playing what it holds.
 * - **A late restore never overwrites a newer choice.** Every write the restore makes goes through
 *   its ticket's `write`. Any other write that puts a track into `currentTrack` meanwhile is the
 *   listener starting something else: the restore is cancelled on the spot, its answers are
 *   dropped when they arrive, and `status` says `cancelled` so the first sync plays the new
 *   choice. A queue edit that starts nothing ("add to queue") does not cancel it; the restore
 *   keeps those tracks behind the ones it restores (`withQueuedMeanwhile`).
 *
 * The UI's queue stores are emptied when a restore begins. What `localStorage` still held from the
 * previous session is stale next to the service's queue, so it is neither shown nor pushed; it is
 * kept on the ticket (`leftover`) for the one case it is still the best answer -- the service
 * holds no queue at all.
 */

/**
 * `idle` before any restore, `restoring` while one runs, `restored` when it finished (with or
 * without tracks), `cancelled` when the listener started something else first. `done`/`total`
 * count the queued tracks looked up so far.
 *
 * @type {import('svelte/store').Writable<{status: 'idle'|'restoring'|'restored'|'cancelled',
 *   done: number, total: number}>}
 */
export const queueRestore = writable({ status: "idle", done: 0, total: 0 });

/** The ticket of the restore that is running, or null. */
let running = null;
/** True while a ticket's own write is in progress, so the guard lets it through. */
let writing = false;

/**
 * Starts a restore: empties the UI's queue stores, sets `status` to `restoring` and starts
 * watching for the listener's own choice. A restore that was still running is cancelled first.
 *
 * @returns {{isCurrent: function(): boolean,
 *            progress: function({done: number, total: number}): void,
 *            write: function(function(): void): boolean,
 *            finish: function(): void,
 *            leftover: {tracks: Array<object>, track: object|null}}}
 */
export function beginQueueRestore() {
  if (running) stop(running, "cancelled");

  const leftover = { tracks: get(playlist) ?? [], track: get(currentTrack) ?? null };
  writing = true;
  try {
    playlist.set([]);
    currentTrack.set(null);
  } finally {
    writing = false;
  }

  const ticket = {
    leftover,
    unsubscribes: [],
    isCurrent: () => running === ticket,
    progress({ done, total }) {
      if (ticket.isCurrent()) queueRestore.set({ status: "restoring", done, total });
    },
    write(apply) {
      if (!ticket.isCurrent()) return false;
      writing = true;
      try {
        apply();
      } finally {
        writing = false;
      }
      return true;
    },
    finish() {
      if (ticket.isCurrent()) stop(ticket, "restored");
    },
  };
  running = ticket;
  queueRestore.set({ status: "restoring", done: 0, total: 0 });

  // `subscribe` calls back at once with the value just set; only later writes count.
  let primed = false;
  ticket.unsubscribes.push(
    currentTrack.subscribe((track) => {
      if (!primed || writing || track == null || !ticket.isCurrent()) return;
      stop(ticket, "cancelled");
    }),
  );
  primed = true;
  return ticket;
}

/**
 * The queue the restore should write: the restored [tracks], followed by whatever the listener
 * queued while it ran ("add to queue" and "play next" edit `playlist` without starting a track,
 * and do not cancel the restore). Those go at the end, after the restored queue they were added
 * to, minus any track the restored queue already holds.
 *
 * @param {Array<object>} tracks - What the restore found, in queue order.
 * @returns {Array<object>}
 */
export function withQueuedMeanwhile(tracks) {
  const known = new Set(tracks.map((track) => String(track?.id)));
  const meanwhile = (get(playlist) ?? []).filter((track) => !known.has(String(track?.id)));
  return meanwhile.length ? [...tracks, ...meanwhile] : tracks;
}

/**
 * Cancels the running restore, if any, as if the listener had started something else.
 *
 * @returns {boolean} Whether there was one to cancel.
 */
export function cancelQueueRestore() {
  if (!running) return false;
  stop(running, "cancelled");
  return true;
}

/**
 * Whether a restore is running right now.
 *
 * @returns {boolean}
 */
export function isRestoringQueue() {
  return running !== null;
}

/**
 * Ends [ticket]: stops watching the stores and records how it ended.
 *
 * @param {object} ticket
 * @param {'restored'|'cancelled'} status
 */
function stop(ticket, status) {
  if (running !== ticket) return;
  running = null;
  for (const unsubscribe of ticket.unsubscribes) unsubscribe();
  queueRestore.update((current) => ({ ...current, status }));
}
