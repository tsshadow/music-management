import { get } from "svelte/store";
import {
  credentials,
  mumaApiKey,
  mumaApiUrl,
  mumaRefreshToken,
  mumaSessionActive,
  mumaUser,
  restUrl,
  userPermissions,
} from "./store.js";

/**
 * Signing in, once, for everyone who does it.
 *
 * There is exactly one way into this app with a username and a password: ping
 * `/rest/ping` with them, and if LMS accepts them, ask the muma API for the
 * permissions and the RBAC role that go with the same pair. `LoginPage.svelte`
 * does that when someone types them; the Android shell does it on boot with the
 * pair the phone already had. Making the shell its own path would have meant a
 * second place where "signed in" is decided, and the two would have drifted the
 * first time either changed.
 *
 * Nothing here renders or translates anything: the caller owns the screen, so a
 * failure comes back as a reason rather than as a sentence.
 */

/**
 * The query string every Subsonic call is signed with.
 *
 * `c=spotify` is the client id the web has always sent and the one the server
 * records sessions against; the phone's native client sends `Ultrasonic` for
 * the same account, and the server is happy with either.
 *
 * @param {string} username
 * @param {string} password
 * @returns {string}
 */
export function subsonicAuthQuery(username, password) {
  return `u=${encodeURIComponent(username)}&p=${encodeURIComponent(password)}&v=1.12.0&c=spotify&f=json`;
}

/**
 * Verifies a username and password and, when they hold, starts the session.
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{ok: boolean, reason?: 'offline'|'rejected', message?: string}>}
 *   `offline` means the server could not be reached at all -- a wrong base URL
 *   inside the shell looks exactly like this -- and `rejected` means it answered
 *   and said no, with its own message in `message`.
 */
export async function signIn(username, password) {
  let body;
  try {
    const response = await fetch(restUrl(`/rest/ping?${subsonicAuthQuery(username, password)}`));
    body = await response.json();
  } catch (error) {
    return { ok: false, reason: "offline", message: error?.message ?? "" };
  }

  const answer = body?.["subsonic-response"];
  if (answer?.status !== "ok") {
    return { ok: false, reason: "rejected", message: answer?.error?.message ?? "" };
  }

  // Deliberately before the credentials are stored: the management session is
  // a bonus, not a condition. A server without the muma API still gives a
  // working player, which is what the original inline version did too.
  await startManagementSession(username, password);
  credentials.update((current) => ({ ...current, username, password }));
  return { ok: true };
}

/**
 * Trades the same pair for a muma API key, the user's permissions and their
 * RBAC role. A failure here is a warning: the player works without it, only the
 * management half does not.
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<boolean>} Whether a management session was started.
 */
export async function startManagementSession(username, password) {
  try {
    const response = await fetch(`${get(mumaApiUrl)}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) return false;
    const data = await response.json();
    mumaApiKey.set(data.api_key);
    mumaRefreshToken.set(data.refresh_token);
    userPermissions.set(data.user.permissions);
    mumaUser.set(data.user);
    mumaSessionActive.set(true);
    return true;
  } catch (error) {
    console.warn("Management API login failed during Subsonic login", error);
    return false;
  }
}
