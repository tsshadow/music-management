import { get } from "svelte/store";
import {
  credentials,
  mumaApiKey,
  mumaApiUrl,
  mumaRefreshToken,
  mumaSessionActive,
  mumaUser,
  refreshSubsonicToken,
  restUrl,
  signedOut,
  subsonicToken,
  subsonicTokenProblem,
  subsonicTokenQuery,
  userPermissions,
} from "./store.js";
import { logAction } from "./diagnosticsLog.js";

/**
 * Signing in, once, for everyone who does it.
 *
 * There is exactly one way into this app with a username and a password: ask
 * the muma API for the session, the permissions and the RBAC role that go with
 * the pair (the password travels in a POST body), fetch the account's Subsonic
 * token with the key that returns, and ping `/rest/ping` signed with that token
 * -- so the password never appears in a URL (bug report 103). Without a
 * session or a token there is no sign-in: the password is not a fallback
 * signature any more (issue #72). `LoginPage.svelte` does that when someone
 * types them; the Android shell does it on boot with the pair the phone
 * already had. Making the shell its own path would have meant a second place
 * where "signed in" is decided, and the two would have drifted the first time
 * either changed.
 *
 * Nothing here renders or translates anything: the caller owns the screen, so a
 * failure comes back as a reason rather than as a sentence.
 */

/**
 * Verifies a username and password and, when they hold, starts the session.
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{ok: boolean, username?: string, reason?: 'offline'|'rejected', message?: string}>}
 *   On success `username` is the account's own spelling of the name, which is
 *   what the caller must store or hand on (see `canonicalUsername`).
 *   `offline` means the server could not be reached, or could not hand out a
 *   Subsonic token yet -- a wrong base URL inside the shell looks exactly like
 *   this -- and `rejected` means it answered and said no, with its own message
 *   in `message` when it gave one.
 */
export async function signIn(username, password) {
  // The management session first: it takes the password in a POST body, and its key is what
  // fetches the Subsonic token. It is published only once the ping has passed, together with the
  // credentials: the app treats a stored key as "signed in", and a key published early let the UI
  // run Subsonic calls with no credentials yet.
  const { session, reason: sessionFailure } = await requestManagementSession(username, password);
  if (!session) {
    logAction("auth.login", { ok: false, reason: sessionFailure, step: "session" });
    return { ok: false, reason: sessionFailure, message: "" };
  }
  // Account names are case-insensitive, and the account's own spelling is the
  // one every later call signs in with -- not the one typed. "Teun" typed for
  // the account "user" used to be stored as typed and sent as Subsonic `u=` on
  // every request, and LMS, comparing names byte for byte, created a second
  // user for it (docs/bug-reports/074-login-case-forks-user-identity.md).
  let canonical = canonicalUsername(username, session.user);
  const token = await refreshSubsonicToken(undefined, session.api_key);
  // LMS's own spelling of the login name is what the token opens; adopt it when it is only a case
  // variant of the name we have. A token for any other name is not this account's.
  if (token && token.username.toLowerCase() === canonical.toLowerCase()) canonical = token.username;
  if (!token || token.username !== canonical) {
    if (token) subsonicToken.set({ username: "", token: "" });
    const reason = get(subsonicTokenProblem) === "rejected" ? "rejected" : "offline";
    logAction("auth.login", { ok: false, reason, step: "token" });
    return { ok: false, reason, message: "" };
  }

  const answer = await ping(subsonicTokenQuery(canonical, token.token));
  if (!answer.ok) {
    // A token this server does not accept (issued into another server's database) signs nothing.
    if (answer.reason === "rejected") subsonicToken.set({ username: "", token: "" });
    logAction("auth.login", { ok: false, reason: answer.reason, step: "ping" });
    return { ok: false, reason: answer.reason, message: answer.message };
  }

  publishManagementSession(session);
  credentials.update((current) => ({ ...current, username: canonical, password }));
  // A sign-in ends a logout: the shell's boot may sign itself in again from here on.
  signedOut.set(false);
  logAction("auth.login", { ok: true, signed: "token" });
  return { ok: true, username: canonical };
}

/**
 * One `/rest/ping` with the given query.
 *
 * @param {string} query - An `authParams`-shaped query string.
 * @returns {Promise<{ok: boolean, reason?: 'offline'|'rejected', message?: string}>}
 */
async function ping(query) {
  let body;
  try {
    const response = await fetch(restUrl(`/rest/ping?${query}`));
    body = await response.json();
  } catch (error) {
    return { ok: false, reason: "offline", message: error?.message ?? "" };
  }
  const answer = body?.["subsonic-response"];
  if (answer?.status !== "ok")
    return { ok: false, reason: "rejected", message: answer?.error?.message ?? "" };
  return { ok: true };
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
  const { session } = await requestManagementSession(username, password);
  if (!session) return false;
  publishManagementSession(session);
  return true;
}

/**
 * MuMa's login answer for the pair, or no session with the reason there is
 * none: `rejected` when MuMa refused the pair (HTTP 401/403, or an answer
 * without a key and a `user`), `offline` when it could not be reached or
 * failed. Stores nothing; see `publishManagementSession`.
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{session: object|null, reason?: 'offline'|'rejected'}>}
 */
async function requestManagementSession(username, password) {
  try {
    const response = await fetch(`${get(mumaApiUrl)}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const refused = response.status === 401 || response.status === 403;
      return { session: null, reason: refused ? "rejected" : "offline" };
    }
    const data = await response.json();
    if (!data?.api_key || !data.user || typeof data.user !== "object") {
      console.warn("Management API login answered without a user key");
      return { session: null, reason: "rejected" };
    }
    return { session: data };
  } catch (error) {
    console.warn("Management API login failed", error?.name ?? "error");
    return { session: null, reason: "offline" };
  }
}

/**
 * Stores a management session: the user's own key, refresh token, permissions
 * and account.
 *
 * @param {object} data - A `requestManagementSession` answer.
 */
function publishManagementSession(data) {
  mumaApiKey.set(data.api_key);
  mumaRefreshToken.set(data.refresh_token ?? "");
  userPermissions.set(Array.isArray(data.user.permissions) ? data.user.permissions : []);
  mumaUser.set(data.user);
  mumaSessionActive.set(true);
}
