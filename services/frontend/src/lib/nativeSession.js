import { get } from "svelte/store";
import { platform as defaultPlatform } from "./platform/index.js";
import { credentials, currentTrack, mumaApiKey, mumaApiUrl, playerState } from "./store.js";
import { subsonicJson } from "./subsonic.js";
import { signIn } from "./login.js";
import { startQueue } from "./queue.js";

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
 * 2. **The session.** The phone already holds a username and a password for
 *    that server. They go through exactly the sign-in a typed login uses, so
 *    there is one definition of "signed in" rather than two. A blank password
 *    is how the native app says "logged out": nothing is attempted, whatever
 *    the web session already had is left alone, and the login page appears.
 * 3. **The queue.** The WebView is reclaimed whenever Android feels like it,
 *    while `PlaybackService` keeps playing. A rebuilt UI therefore starts by
 *    asking the service what it is holding and rebuilding its own queue around
 *    that -- without touching playback. This is the phase-1 proof: play, kill
 *    the WebView, reopen, and the mini player is where the music is.
 *
 * In a browser tab every one of these is skipped and nothing changes.
 */

/** How many tracks a rehydrate will fetch. A longer queue is truncated. */
export const MAX_REHYDRATED_TRACKS = 200;

/**
 * Runs the shell's boot sequence.
 *
 * Never rejects: a shell that cannot reach its server must still show a login
 * page rather than a blank screen.
 *
 * @param {object} [platform] - Injected by the tests.
 * @param {typeof fetch} [fetchImpl] - Injected by the tests.
 * @returns {Promise<{native: boolean, signedIn: boolean, restored: number}>}
 */
export async function bootstrapShell(platform = defaultPlatform, fetchImpl = undefined) {
  if (!platform?.system?.isNative) return { native: false, signedIn: false, restored: 0 };

  try {
    await applyServerUrls(platform);
    const signedIn = await restoreSession(platform);
    const restored = signedIn ? await rehydrateQueue(platform, fetchImpl) : 0;
    platform.diagnostics.log("shell:boot", { signedIn, restored });
    return { native: true, signedIn, restored };
  } catch (error) {
    console.error("The shell could not be bootstrapped", error);
    return { native: true, signedIn: false, restored: 0 };
  }
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
 * Signs in with what the phone stored, unless it is already signed in with it.
 *
 * @param {object} platform
 * @returns {Promise<boolean>} Whether there is a usable session afterwards.
 */
export async function restoreSession(platform) {
  const stored = await platform.system.credentials();
  const web = get(credentials);

  // Blank means logged out on the phone. It does not mean "log the web out":
  // somebody may have signed in on this screen, and throwing that away would be
  // a sign-out nobody asked for.
  if (!stored.password) return Boolean(web.username && web.password);

  if (web.username === stored.username && web.password === stored.password) {
    if (stored.mumaApiKey && !get(mumaApiKey)) mumaApiKey.set(stored.mumaApiKey);
    return true;
  }

  const result = await signIn(stored.username, stored.password);
  if (!result.ok) {
    console.warn("The phone's credentials were not accepted", result.reason, result.message);
    // The key the phone holds is worth keeping even so: it is what lets the
    // management half answer while the login page is up.
    if (stored.mumaApiKey) mumaApiKey.set(stored.mumaApiKey);
    return false;
  }
  if (stored.mumaApiKey && !get(mumaApiKey)) mumaApiKey.set(stored.mumaApiKey);
  await adoptCanonicalUsername(platform, stored, result.username);
  return true;
}

/**
 * Writes the account's own spelling of the name back to the phone when what it
 * stored was typed in another case. The phone signs its own Subsonic calls with
 * the stored name, and a case variant made LMS create a second user for the same
 * account (docs/bug-reports/074-login-case-forks-user-identity.md); a phone that
 * signed in before the fix repairs itself on its next boot this way. A bridge
 * failure only means the repair waits for the next boot.
 *
 * @param {object} platform
 * @param {{username?: string, password?: string}} stored
 * @param {string|undefined} canonical
 */
async function adoptCanonicalUsername(platform, stored, canonical) {
  if (!canonical || canonical === stored.username) return;
  try {
    await platform.system.saveCredentials({ username: canonical, password: stored.password });
  } catch (error) {
    console.warn("Could not store the account's own spelling of the name on the phone", error);
  }
}

/**
 * Rebuilds the UI's queue from the one the platform service is holding.
 *
 * Reads, never writes: no `load`, no `play`, no `seek`. The service is possibly
 * still playing, and the point of this is that it should not notice a thing.
 *
 * @param {object} platform
 * @param {typeof fetch} [fetchImpl]
 * @returns {Promise<number>} How many tracks were restored.
 */
export async function rehydrateQueue(platform, fetchImpl = undefined) {
  const [state, queue] = await Promise.all([
    platform.player.refresh(),
    platform.player.queueState(),
  ]);

  const ids = queue.trackIds.slice(0, MAX_REHYDRATED_TRACKS);
  if (!ids.length) return 0;

  const tracks = await fetchTracks(ids, fetchImpl);
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
 * @returns {Promise<Array<object>>} In queue order, without the failures.
 */
async function fetchTracks(ids, fetchImpl = undefined) {
  const call = fetchImpl ?? fetch;
  const answers = await Promise.all(
    ids.map(async (id) => {
      try {
        const body = await subsonicJson("getSong", { id }, { fetchImpl: call });
        return body?.["subsonic-response"]?.song ?? null;
      } catch (error) {
        console.warn("Could not look up a queued track", id, error);
        return null;
      }
    }),
  );
  return answers.filter(Boolean);
}
