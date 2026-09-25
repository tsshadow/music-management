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
import { logAction } from "./diagnosticsLog.js";

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
 * @returns {Promise<{ok: boolean, username?: string, reason?: 'offline'|'rejected', message?: string}>}
 *   On success `username` is the account's own spelling of the name, which is
 *   what the caller must store or hand on (see `canonicalUsername`).
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
    logAction("auth.login", { ok: false, reason: "offline" });
    return { ok: false, reason: "offline", message: error?.message ?? "" };
  }

  const answer = body?.["subsonic-response"];
  if (answer?.status !== "ok") {
    logAction("auth.login", { ok: false, reason: "rejected" });
    return { ok: false, reason: "rejected", message: answer?.error?.message ?? "" };
  }

  // Deliberately before the credentials are stored: the management session is
  // a bonus, not a condition. A server without the muma API still gives a
  // working player, which is what the original inline version did too.
  const started = await startManagementSession(username, password);
  // Account names are case-insensitive, and the account's own spelling is the
  // one every later call signs in with -- not the one typed. "Teun" typed for
  // the account "user" used to be stored as typed and sent as Subsonic `u=` on
  // every request, and LMS, comparing names byte for byte, created a second
  // user for it (docs/bug-reports/074-login-case-forks-user-identity.md).
  const canonical = canonicalUsername(username, started ? get(mumaUser) : null);
  credentials.update((current) => ({ ...current, username: canonical, password }));
  logAction("auth.login", { ok: true });
  return { ok: true, username: canonical };
}

/**
 * The name to sign in under from now on: the account's own spelling as MuMa's
 * login returned it, or the typed name when there is no answer to go by (no
 * muma API, or an answer without a user). Only a spelling of the same name is
 * adopted; anything else is not an answer about this login.
 *
 * @param {string} typed
 * @param {{username?: string}|null|undefined} account
 * @returns {string}
 */
export function canonicalUsername(typed, account) {
  const returned = account?.username;
  if (typeof returned !== "string" || !returned) return typed;
  return returned.toLowerCase() === String(typed ?? "").toLowerCase() ? returned : typed;
}

/**
 * Trades the same pair for the user's own muma API key, their permissions and
 * their RBAC role. A failure here is a warning: the player works without it,
 * only the management half does not.
 *
 * The answer is MuMa's own login (`services/music_manager/routers/users.py`):
 * `api_key`, `refresh_token`, and the account under `user`, carrying
 * `permissions` and `is_admin`. LMS used to answer this call itself, flat and
 * with its own shared `api-key` for everybody; an answer without a key and a
 * `user` is not a session and stores nothing, so a half-written session can
 * never outlive the call.
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
    if (!data?.api_key || !data.user || typeof data.user !== "object") {
      console.warn("Management API login answered without a user key");
      return false;
    }
    mumaApiKey.set(data.api_key);
    mumaRefreshToken.set(data.refresh_token ?? "");
    userPermissions.set(Array.isArray(data.user.permissions) ? data.user.permissions : []);
    mumaUser.set(data.user);
    mumaSessionActive.set(true);
    return true;
  } catch (error) {
    console.warn("Management API login failed during Subsonic login", error);
    return false;
  }
}
