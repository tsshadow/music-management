import { get, writable } from "svelte/store";
import { platform as defaultPlatform } from "./platform/index.js";
import { offline, subsonicJson } from "./subsonic.js";
import { playlist } from "./store.js";
import { startQueue } from "./queue.js";
import { checkServer, waitForServer } from "./serverReachability.js";

/**
 * "Offline verder": the app started without its server, by the listener's choice
 * (docs/designs/app-start-reachability/).
 *
 * Choosing it does three things. The native side is told (`platform.storage.setOfflineMode`), so
 * `isOffline()` answers true on a perfectly good network and every list the web asks for is
 * answered from the downloaded library by the existing `subsonic.js` switch; the native services
 * and the Android Auto tree follow the same flag. The queue is restored with only the tracks that
 * are on the device, and the ones left out are counted. And the server keeps being asked in the
 * background; the moment it answers, offline mode ends and the full queue comes back, unless the
 * listener has started something else in the meantime.
 */

/**
 * What the offline banner reads.
 *
 * @type {import('svelte/store').Writable<{active: boolean, since: number|null, skipped: number,
 *   restored: number, returnedAt: number|null, restoredOnReturn: number}>} `returnedAt` and
 *   `restoredOnReturn` describe the last way back online: when, and how many tracks the queue
 *   holds again (0 when it was left alone).
 */
export const offlineMode = writable({
  active: false,
  since: null,
  skipped: 0,
  restored: 0,
  returnedAt: null,
  restoredOnReturn: 0,
});

/** Where the full queue waits for the server to come back; survives a reclaimed WebView. */
export const QUEUE_STASH_KEY = "muma_offline_queue_stash";

/**
 * Picks the queue an offline start can actually play.
 *
 * `tracks` are the queued tracks that resolved from the downloaded library -- the rest are not
 * on the device and cannot play without the server. The track to show is the one that was
 * playing when it is on the device, else the first downloaded one at or after the old position,
 * else the last one before it: the listener continues as close to where they were as the device
 * allows.
 *
 * @param {object} input
 * @param {string[]} input.ids - The native queue's ids, in order.
 * @param {Array<{id: string|number}>} input.tracks - The ones that resolved offline.
 * @param {string|null} [input.playingId] - What the native player has loaded.
 * @param {number} [input.index] - The native queue's position.
 * @returns {{tracks: Array<object>, index: number, skipped: number, playingKept: boolean}}
 */
export function planOfflineQueue({ ids, tracks, playingId = null, index = 0 }) {
  const position = new Map(ids.map((id, at) => [String(id), at]));
  const kept = (tracks ?? [])
    .filter((track) => position.has(String(track?.id)))
    .sort((a, b) => position.get(String(a.id)) - position.get(String(b.id)));
  const skipped = Math.max(ids.length - kept.length, 0);
  if (!kept.length) return { tracks: [], index: -1, skipped, playingKept: false };

  const playing =
    playingId == null ? -1 : kept.findIndex((t) => String(t.id) === String(playingId));
  if (playing >= 0) return { tracks: kept, index: playing, skipped, playingKept: true };

  const from = Math.max(Number(index) || 0, 0);
  const after = kept.findIndex((track) => position.get(String(track.id)) >= from);
  return { tracks: kept, index: after >= 0 ? after : kept.length - 1, skipped, playingKept: false };
}

/**
 * Keeps the full queue, as the native player held it, for the way back online.
 *
 * @param {{ids: string[], playingId: string|null, index: number, offlineIds: string[]}} stash
 *   `offlineIds` is the queue as the offline start restored it: when the listener's queue still
 *   reads exactly that, they have not replaced it, and it is safe to put the full one back.
 * @param {Storage} [storage] - Injected by the tests.
 */
export function stashOnlineQueue(stash, storage = globalThis.localStorage) {
  try {
    storage?.setItem(QUEUE_STASH_KEY, JSON.stringify(stash));
  } catch (error) {
    console.warn("Could not keep the full queue for later", error);
  }
}

/**
 * @param {Storage} [storage]
 * @returns {{ids: string[], playingId: string|null, index: number, offlineIds: string[]}|null}
 */
export function readStash(storage = globalThis.localStorage) {
  try {
    const stash = JSON.parse(storage?.getItem(QUEUE_STASH_KEY) ?? "null");
    return stash && Array.isArray(stash.ids) && Array.isArray(stash.offlineIds) ? stash : null;
  } catch {
    return null;
  }
}

/** @param {Storage} [storage] */
export function clearStash(storage = globalThis.localStorage) {
  try {
    storage?.removeItem(QUEUE_STASH_KEY);
  } catch {
    // Nothing kept, nothing to clear.
  }
}

/**
 * Turns offline mode on: the native flag, the `offline` store every list reads, and the banner.
 *
 * @param {object} [platform]
 * @param {{skipped?: number, restored?: number}} [counts]
 * @returns {Promise<void>}
 */
export async function enterOfflineMode(
  platform = defaultPlatform,
  { skipped = 0, restored = 0 } = {},
) {
  try {
    await platform?.storage?.setOfflineMode?.(true);
  } catch (error) {
    console.warn("Could not tell the phone about offline mode", error);
  }
  offline.set(true);
  offlineMode.set({
    active: true,
    since: Date.now(),
    skipped,
    restored,
    returnedAt: null,
    restoredOnReturn: 0,
  });
}

/**
 * Records how the offline queue restore went, for the banner.
 *
 * @param {{skipped: number, restored: number}} counts
 */
export function setOfflineCounts({ skipped, restored }) {
  offlineMode.update((current) => ({ ...current, skipped, restored }));
}

/**
 * Turns offline mode off again: the server answered.
 *
 * @param {object} [platform]
 * @returns {Promise<void>}
 */
export async function leaveOfflineMode(platform = defaultPlatform) {
  try {
    await platform?.storage?.setOfflineMode?.(false);
  } catch (error) {
    console.warn("Could not tell the phone that offline mode ended", error);
  }
  offline.set(false);
  offlineMode.update((current) => ({ ...current, active: false, returnedAt: Date.now() }));
}

/**
 * Puts the full queue back once the server answers again.
 *
 * Only when the listener's queue is still the one the offline start restored: anything they
 * started while offline is theirs, and is not swapped for an old queue behind their back. The
 * track that is on screen stays current, so the native player keeps playing it (`queuePlanFor`
 * rebuilds around an unchanged current item instead of reloading it).
 *
 * @param {object} [options]
 * @param {typeof fetch} [options.fetchImpl] - Injected by the tests.
 * @param {Storage} [options.storage] - Injected by the tests.
 * @param {function(function(): void): boolean} [options.write] - Runs the store write; false
 *   when it was dropped. The app-start restore passes its ticket's (`queueRestore.js`), so a
 *   listener who started something else meanwhile keeps it.
 * @returns {Promise<{restored: number, reason: string}>}
 */
export async function reconcileQueue({ fetchImpl, storage, write = runWrite } = {}) {
  const stash = readStash(storage);
  clearStash(storage);
  if (!stash) return { restored: 0, reason: "nothing-kept" };
  const current = get(playlist).map((track) => String(track?.id));
  const offlineIds = stash.offlineIds.map(String);
  const untouched =
    current.length === offlineIds.length && current.every((id, at) => id === offlineIds[at]);
  if (!untouched) return { restored: 0, reason: "queue-changed" };

  const answers = await Promise.all(
    stash.ids.map(async (id) => {
      try {
        const body = await subsonicJson("getSong", { id }, fetchImpl ? { fetchImpl } : {});
        return body?.["subsonic-response"]?.song ?? null;
      } catch (error) {
        console.warn("Could not look up a queued track after reconnecting", id, error);
        return null;
      }
    }),
  );
  const tracks = answers.filter(Boolean);
  if (tracks.length <= current.length) return { restored: 0, reason: "nothing-gained" };
  if (!write(() => startQueue(tracks, { view: null }))) {
    return { restored: 0, reason: "queue-changed" };
  }
  return { restored: tracks.length, reason: "restored" };
}

/**
 * The default writer of `reconcileQueue`: runs the write at once.
 *
 * @param {function(): void} apply
 * @returns {boolean} Always true.
 */
function runWrite(apply) {
  apply();
  return true;
}

/** The background attempt loop while offline mode is on; null otherwise. */
let activeWaiter = null;

/**
 * While offline mode is on, keeps asking the server in the background (the same backoff as
 * "Wachten op server", and at once on every network change). When it answers: offline mode ends
 * and the full queue is put back.
 *
 * @param {object} [platform]
 * @param {object} [options]
 * @param {typeof fetch} [options.fetchImpl] - Injected by the tests.
 * @param {object} [options.timers] - Injected by the tests.
 * @param {function(object): void} [options.onBack] - Told the reconcile result.
 * @returns {function(): void} Stops watching.
 */
export function watchServerReturn(platform = defaultPlatform, { fetchImpl, timers, onBack } = {}) {
  const stop = offlineMode.subscribe(({ active }) => {
    if (active && !activeWaiter) {
      activeWaiter = waitForServer({
        check: () => checkServer(platform),
        onConnectivity: (handler) => platform?.storage?.onConnectivity?.(handler) ?? (() => {}),
        anyChange: true,
        ...(timers ? { timers } : {}),
      });
      activeWaiter.promise.then(async (result) => {
        activeWaiter = null;
        if (!result) return;
        await leaveOfflineMode(platform);
        const outcome = await reconcileQueue({ fetchImpl });
        offlineMode.update((current) => ({ ...current, restoredOnReturn: outcome.restored }));
        platform?.diagnostics?.log?.("shell:online-again", outcome);
        onBack?.(outcome);
      });
    } else if (!active && activeWaiter) {
      activeWaiter.cancel();
      activeWaiter = null;
    }
  });
  return () => {
    stop();
    activeWaiter?.cancel();
    activeWaiter = null;
  };
}

/**
 * The banner's "Opnieuw verbinden": one attempt now instead of waiting for the next one. The
 * background watcher takes it from there when the server answers.
 *
 * @returns {Promise<void>}
 */
export async function reconnectNow() {
  await activeWaiter?.retryNow();
}
