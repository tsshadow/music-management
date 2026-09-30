import { get } from "svelte/store";
import { platform as defaultPlatform } from "./platform/index.js";
import {
  credentials,
  currentTrack,
  hydrateMumaUserFromApiKey,
  mumaApiKey,
  mumaApiUrl,
  mumaSessionActive,
  ensureSubsonicToken,
  playerState,
  signedOut,
  subsonicToken,
  tokenSignsFor,
  withoutPassword,
} from "./store.js";
import { subsonicJson } from "./subsonic.js";
import { startQueue } from "./queue.js";
import { checkServer, isUnreachable } from "./serverReachability.js";
import {
  clearStash,
  enterOfflineMode,
  leaveOfflineMode,
  planOfflineQueue,
  readStash,
  reconcileQueue,
  setOfflineCounts,
  stashOnlineQueue,
} from "./offlineMode.js";

/**
 * What the web player has to do before it renders anything, but only inside the
 * Android shell.
 *
 * Three things, in this order, and the order is the whole design:
 *
 * 1. **The server.** The page's own origin inside the shell is
 *    `https://localhost`, which is not a music server. Every call in the app
 *    goes through `restUrl()` or `mumaApiUrl`, so putting the phone's server
 *    into those two stores before the first fetch is all it takes -- and it has
 *    to be before, because `store.js` starts an admin check the moment
 *    credentials appear.
 * 2. **The session.** The phone says whether it is signed in (an explicit
 *    flag) and hands over its MuMa API key and Subsonic token. The web takes
 *    that session over with the key -- no password is stored on either side
 *    to sign in again with (issue #101). Signed out on the phone, nothing is
 *    attempted, whatever the web session already had is left alone, and the
 *    login page appears when there is none. After a deliberate logout
 *    (`signedOut` in store.js) nothing is attempted either, whatever the
 *    phone still holds, until someone signs in again.
 * 3. **The queue.** The WebView is reclaimed whenever Android feels like it,
 *    while `PlaybackService` keeps playing. A rebuilt UI therefore starts by
 *    asking the service what it is holding and rebuilding its own queue around
 *    that -- without touching playback. This is the phase-1 proof: play, kill
 *    the WebView, reopen, and the mini player is where the music is.
 *
 * In a browser tab every one of these is skipped and nothing changes.
 *
 * Before the session and the queue, the server is asked once whether it answers at all
 * (docs/designs/app-start-reachability/). The check leaves at the same moment as step 1 and is
 * only waited for after it, so a reachable server costs one ping round trip. When a signed-in
 * phone cannot reach its server, the start pauses on the boot screen's choice -- try again, wait
 * for the server, or continue offline -- and "offline" restores only the tracks on the device.
 */

/** How many tracks a rehydrate will fetch. A longer queue is truncated. */
export const MAX_REHYDRATED_TRACKS = 200;

/**
 * Runs the shell's boot sequence.
 *
 * Never rejects: a shell that cannot reach its server must still show a login
 * page rather than a blank screen.
 *
 * Reports each step through `onStage` so the boot screen can say what it is waiting for
 * (`bootScreen.js`); the order of the steps is the same with or without it.
 *
 * @param {object} [platform] - Injected by the tests.
 * @param {typeof fetch} [fetchImpl] - Injected by the tests.
 * @param {(stage: string, progress?: {done: number, total: number}) => void} [onStage] - Told
 *   `connecting`, `offlineStart` (after "Offline verder"), `signingIn` and `restoringQueue` (with
 *   a count as the tracks come back).
 * @param {object} [options]
 * @param {function({state: string}): Promise<'online'|'offline'>} [options.decide] - Asked when a
 *   signed-in phone cannot reach its server; `bootUnreachable.js` in the app. Without one the
 *   start goes on as it always did.
 * @returns {Promise<{native: boolean, signedIn: boolean, restored: number, offline: boolean}>}
 */
export async function bootstrapShell(
  platform = defaultPlatform,
  fetchImpl = undefined,
  onStage = () => {},
  { decide = async () => "online" } = {},
) {
  if (!platform?.system?.isNative) {
    return { native: false, signedIn: false, restored: 0, offline: false };
  }

  const report = (stage, progress) => {
    // The boot screen is decoration: a failure there must never stop the boot itself.
    try {
      onStage(stage, progress);
    } catch (error) {
      console.warn("Could not show the boot stage", stage, error);
    }
  };

  try {
    report("connecting");
    // Leaves now and is waited for after the server URLs: the native side pings with its own
    // client and settings, so it needs nothing from the stores below.
    const reachability = checkServer(platform);
    await applyServerUrls(platform);
    const offlineStart = await decideStart(platform, reachability, decide);
    if (offlineStart) report("offlineStart");
    report("signingIn");
    const signedIn = await restoreSession(platform);
    if (signedIn) report("restoringQueue");
    const onProgress = (progress) => report("restoringQueue", progress);
    let restored = 0;
    if (signedIn && offlineStart) {
      restored = await rehydrateOfflineQueue(platform, fetchImpl, onProgress);
    } else if (signedIn) {
      restored = await rehydrateQueue(platform, fetchImpl, onProgress);
      restored = await putBackStashedQueue(fetchImpl, restored);
    }
    platform.diagnostics.log("shell:boot", { signedIn, restored, offline: offlineStart });
    return { native: true, signedIn, restored, offline: offlineStart };
  } catch (error) {
    console.error("The shell could not be bootstrapped", error);
    return { native: true, signedIn: false, restored: 0, offline: false };
  }
}

/**
 * What the start-up check means for this start: online (false) or offline (true).
 *
 * Only a phone with a session to restore waits for the check at all: signed out, the login page
 * appears at once and says for itself when it cannot reach the server. A process that is still in
 * offline mode from before (the WebView was reclaimed and rebuilt) stays offline without asking
 * again while the server is away, and leaves offline mode when it is back.
 *
 * @param {object} platform
 * @param {Promise<{state: string, elapsedMs: number, offlineChosen: boolean, skipped: boolean}>}
 *   pending - The check, already on its way.
 * @param {function({state: string}): Promise<'online'|'offline'>} decide
 * @returns {Promise<boolean>}
 */
async function decideStart(platform, pending, decide) {
  if (!(await phoneHasSession(platform))) {
    // Nothing to be offline with: a flag left from an earlier offline start must not make the
    // login page believe there is no route.
    pending.then((check) => {
      logCheck(platform, check);
      if (check.offlineChosen) leaveOfflineMode(platform);
    });
    return false;
  }
  const check = await pending;
  logCheck(platform, check);
  if (!isUnreachable(check.state)) {
    if (check.offlineChosen) await leaveOfflineMode(platform);
    return false;
  }
  const offline = check.offlineChosen || (await decide(check)) === "offline";
  if (offline) await enterOfflineMode(platform);
  return offline;
}

/**
 * Writes the check into the diagnostics trail: the answer, how long the ping took (the number
 * that shows whether the check slows a normal start down) and whether it ran at all.
 *
 * @param {object} platform
 * @param {{state: string, elapsedMs: number, skipped: boolean}} check
 */
function logCheck(platform, check) {
  try {
    platform.diagnostics.log("shell:reachability", {
      state: check.state,
      elapsedMs: check.elapsedMs,
      skipped: check.skipped,
    });
  } catch (error) {
    console.warn("Could not log the start-up check", error);
  }
}

/**
 * Whether the phone holds a session this start would restore -- the same test `restoreSession`
 * makes, without taking anything over.
 *
 * @param {object} platform
 * @returns {Promise<boolean>}
 */
async function phoneHasSession(platform) {
  if (get(signedOut)) return false;
  try {
    const stored = await platform.system.credentials();
    return Boolean(stored?.signedIn && stored.username && stored.mumaApiKey);
  } catch (error) {
    console.warn("Could not read the phone's session", error);
    return false;
  }
}

/**
 * The offline twin of `rehydrateQueue`: the same read of the native queue, answered from the
 * downloaded library (offline mode is on, so `subsonicJson` never tries the server), then cut down
 * to what can play by `planOfflineQueue`. The tracks left out are counted for the banner, and the
 * full queue is kept for the way back online.
 *
 * @param {object} platform
 * @param {typeof fetch} [fetchImpl]
 * @param {(progress: {done: number, total: number}) => void} [onProgress]
 * @returns {Promise<number>} How many tracks were restored.
 */
export async function rehydrateOfflineQueue(
  platform,
  fetchImpl = undefined,
  onProgress = () => {},
) {
  const [state, queue] = await Promise.all([
    platform.player.refresh(),
    platform.player.queueState(),
  ]);
  const ids = queue.trackIds.slice(0, MAX_REHYDRATED_TRACKS).map(String);
  if (!ids.length) return 0;

  const found = await fetchTracks(ids, fetchImpl, onProgress, platform);
  const plan = planOfflineQueue({
    ids,
    tracks: found,
    playingId: state.trackId,
    index: queue.index,
  });
  setOfflineCounts({ skipped: plan.skipped, restored: plan.tracks.length });
  if (plan.skipped > 0) {
    stashOnlineQueue({
      ids,
      playingId: state.trackId == null ? null : String(state.trackId),
      index: queue.index,
      offlineIds: plan.tracks.map((track) => String(track.id)),
    });
  } else {
    clearStash();
  }
  if (!plan.tracks.length) return 0;

  startQueue(plan.tracks, { view: null });
  currentTrack.set(plan.tracks[plan.index]);
  // A different track than the one the player had is loaded paused, from its start.
  playerState.update((current) => ({
    ...current,
    playing: plan.playingKept && state.status === "playing",
    progress: plan.playingKept ? state.position : 0,
    duration: (plan.playingKept && state.duration) || plan.tracks[plan.index]?.duration || 0,
    volume: Math.round(state.volume * 100),
  }));
  return plan.tracks.length;
}

/**
 * An online start after an offline one -- the app was closed or its WebView rebuilt while offline
 * -- finds the native queue cut down to the downloaded tracks. The full queue was kept; put it
 * back, on the same terms as the background reconnect (`reconcileQueue`).
 *
 * @param {typeof fetch} [fetchImpl]
 * @param {number} restored - What the ordinary restore brought back.
 * @returns {Promise<number>} How many tracks the queue holds now.
 */
async function putBackStashedQueue(fetchImpl, restored) {
  if (!readStash()) return restored;
  const outcome = await reconcileQueue({ fetchImpl });
  return outcome.restored || restored;
}

/**
 * Puts the phone's server into the two stores every URL is built from.
 *
 * @param {object} platform
 * @returns {Promise<{subsonic: string, mumaApi: string}>}
 */
export async function applyServerUrls(platform) {
  const urls = await platform.system.loadServerUrl();
  if (urls.subsonic) credentials.update((current) => ({ ...current, url: urls.subsonic }));
  if (urls.mumaApi) mumaApiUrl.set(urls.mumaApi);
  return urls;
}

/**
 * Takes over the session the phone holds, unless a deliberate logout came first.
 *
 * The phone no longer stores the password, so there is nothing to sign in with again (issue
 * #101): its session is its name, its MuMa API key and its Subsonic token. The web adopts them,
 * checks the key when it is not the one it already had (`hydrateMumaUserFromApiKey` -- a key MuMa
 * refuses ends the session and brings the login page back), and fetches a missing token.
 *
 * @param {object} platform
 * @returns {Promise<boolean>} Whether there is a usable session afterwards.
 */
export async function restoreSession(platform) {
  // A deliberate logout outranks whatever the phone still holds. Normally the native sign-out has
  // already emptied it; when that failed or never answered, the phone still counts itself signed
  // in and adopting that would undo the logout the user just asked for (bug report 106). Ask the
  // phone to forget it once more and show the login page either way.
  if (get(signedOut)) {
    try {
      await platform.system.signOut();
    } catch (error) {
      console.warn("The phone's session could not be cleared after a logout", error);
    }
    return false;
  }

  const stored = await platform.system.credentials();
  const web = get(credentials);

  // Signed out on the phone (or signed in without a key, which cannot be taken over). It does not
  // mean "log the web out": somebody may have signed in on this screen, and throwing that away
  // would be a sign-out nobody asked for.
  if (!stored.signedIn || !stored.username || !stored.mumaApiKey) return Boolean(web.username);

  if (web.username !== stored.username) {
    // Another account than the one this page had: its token signs for nobody here.
    if (web.username) subsonicToken.set({ username: "", token: "" });
    credentials.update((current) => ({ ...withoutPassword(current), username: stored.username }));
  }
  if (get(mumaApiKey) !== stored.mumaApiKey) {
    mumaApiKey.set(stored.mumaApiKey);
    await hydrateMumaUserFromApiKey();
    // A refused key ended the session there; the login page takes it from here.
    if (!get(mumaApiKey)) return false;
  }
  mumaSessionActive.set(true);
  adoptPhoneToken(stored);
  // No Subsonic request is made without a token (issue #72): a session from a build that signed
  // with the password, or one whose fetch failed, gets it here, before the queue is rebuilt.
  // Signed in either way -- without a token the app shows why instead of an empty library.
  await ensureSubsonicToken();
  return Boolean(get(credentials).username);
}

/**
 * Takes over the Subsonic token the phone's native client signs with, when it was issued for the
 * name this session signs in under: one token for both halves of the app, and no fetch of our own.
 * A token for any other name is ignored.
 *
 * @param {{username?: string, subsonicToken?: string, subsonicTokenUser?: string}} stored
 */
function adoptPhoneToken(stored) {
  const name = get(credentials).username;
  const phone = { username: stored.subsonicTokenUser ?? "", token: stored.subsonicToken ?? "" };
  if (!tokenSignsFor(name, phone)) return;
  const current = get(subsonicToken);
  if (current.username !== phone.username || current.token !== phone.token)
    subsonicToken.set(phone);
}

/**
 * Rebuilds the UI's queue from the one the platform service is holding.
 *
 * Reads, never writes: no `load`, no `play`, no `seek`. The service is possibly
 * still playing, and the point of this is that it should not notice a thing.
 *
 * @param {object} platform
 * @param {typeof fetch} [fetchImpl]
 * @param {(progress: {done: number, total: number}) => void} [onProgress] - Told how many of
 *   the queued ids have been answered, as they are.
 * @returns {Promise<number>} How many tracks were restored.
 */
export async function rehydrateQueue(platform, fetchImpl = undefined, onProgress = () => {}) {
  const [state, queue] = await Promise.all([
    platform.player.refresh(),
    platform.player.queueState(),
  ]);

  const ids = queue.trackIds.slice(0, MAX_REHYDRATED_TRACKS);
  if (!ids.length) return 0;

  const tracks = await fetchTracks(ids, fetchImpl, onProgress, platform);
  if (!tracks.length) return 0;

  // Matched on the id rather than on the queue index: a track the server no
  // longer knows drops out of the list, and an index taken from the service
  // would then point one place too far.
  const byPlayingId = tracks.findIndex((track) => String(track.id) === String(state.trackId));
  const index =
    byPlayingId >= 0 ? byPlayingId : Math.min(Math.max(queue.index, 0), tracks.length - 1);

  // This restores a queue the native side already had, it does not start one -- 'view: null'
  // clears queueSource rather than crediting the restore to whatever view loads first.
  startQueue(tracks, { view: null });
  currentTrack.set(tracks[index]);
  playerState.update((current) => ({
    ...current,
    playing: state.status === "playing",
    progress: state.position,
    duration: state.duration || tracks[index]?.duration || 0,
    volume: Math.round(state.volume * 100),
  }));
  return tracks.length;
}

/**
 * Looks the queued ids up in the library.
 *
 * One `getSong` per id, in parallel: there is no batch endpoint for an
 * arbitrary set of ids, and a queue is tens of items rather than thousands. An
 * id that no longer resolves is dropped instead of failing the whole restore --
 * a single deleted track must not cost the listener the rest of their queue.
 *
 * Through `subsonicJson`, so that a WebView rebuilt in a tunnel restores the
 * queue from the downloaded library instead of coming back empty. That is the
 * one path where the tracks are known to be local: they were playing.
 *
 * @param {string[]} ids
 * @param {typeof fetch} [fetchImpl]
 * @param {(progress: {done: number, total: number}) => void} [onProgress]
 * @param {object} [platform] - The shell whose downloaded library answers when offline.
 * @returns {Promise<Array<object>>} In queue order, without the failures.
 */
async function fetchTracks(
  ids,
  fetchImpl = undefined,
  onProgress = () => {},
  platform = undefined,
) {
  const call = fetchImpl ?? fetch;
  const total = ids.length;
  let done = 0;
  onProgress({ done, total });
  const answers = await Promise.all(
    ids.map(async (id) => {
      try {
        const body = await subsonicJson(
          "getSong",
          { id },
          platform ? { fetchImpl: call, platform } : { fetchImpl: call },
        );
        return body?.["subsonic-response"]?.song ?? null;
      } catch (error) {
        console.warn("Could not look up a queued track", id, error);
        return null;
      } finally {
        done += 1;
        onProgress({ done, total });
      }
    }),
  );
  return answers.filter(Boolean);
}
