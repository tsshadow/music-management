import { writable } from "svelte/store";
import { platform as defaultPlatform } from "./platform/index.js";
import { applyServerUrls } from "./nativeSession.js";
import {
  flushFrontendSettings,
  mumaUser,
  resetSessionState,
  signedOut,
  userPermissions,
} from "./store.js";

/**
 * The first-run server screen's state and the steps around it (issue #192,
 * docs/designs/first-run-server/).
 *
 * The Android shell stores the address of the server it talks to; a fresh install has none and
 * asks for it before the login page. The address is entered once, checked natively and kept;
 * the MuMa API address is derived from it on the phone.
 */

/**
 * Which first-run screen the signed-out shell shows instead of the login page: `"first"` on a
 * fresh install, `"change"` when the login page's "Wijzigen" link opened it, `null` for none.
 *
 * @type {import('svelte/store').Writable<null|"first"|"change">}
 */
export const serverScreen = writable(null);

/** How long a logout-like reset waits for the last settings write, as `ProfileButton` does. */
const FLUSH_TIMEOUT_MS = 2000;

/**
 * The host of an address, for the login page's server line: `music.example.org` for
 * `https://music.example.org/lms`. An address that is no URL comes back as it is.
 *
 * @param {string} url
 * @returns {string}
 */
export function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url ?? "";
  }
}

/**
 * The comparable form of an address: lower case, `https://` added when no scheme is given, no
 * trailing slash. Mirrors `ServerAddress.normalize` on the phone, without its refusals.
 *
 * @param {string} url
 * @returns {string}
 */
function comparable(url) {
  const trimmed = (url ?? "").trim();
  const withScheme = trimmed.includes("://") ? trimmed : `https://${trimmed}`;
  try {
    const parsed = new URL(withScheme);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname.replace(/\/+$/, "")}`.toLowerCase();
  } catch {
    return withScheme.toLowerCase();
  }
}

/**
 * Whether two addresses are the same server: the same scheme, host, port and path, whatever
 * the case or a trailing slash. A change between two such spellings keeps the session.
 *
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
export function sameServer(a, b) {
  if (!a || !b) return false;
  return comparable(a) === comparable(b);
}

/**
 * Stores a checked address on the phone and points the web stores at it.
 *
 * @param {string} url The normalized address the check answered with.
 * @param {{signOut?: boolean, platform?: object}} [options] `signOut` for another server.
 * @returns {Promise<{subsonic: string, mumaApi: string, configured: boolean}>}
 */
export async function useServerAddress(url, { signOut = false, platform = defaultPlatform } = {}) {
  await platform.system.setServerAddress({ url, signOut });
  return applyServerUrls(platform);
}

/**
 * Moves a signed-in app to another server, the way a logout ends a session: the last settings
 * write still goes to the old server with the old key, then the phone signs out, drops the old
 * server's cache and stores the new address, and the web clears its MuMa session, every account
 * store and sets the `signedOut` marker. The caller reloads; the boot then shows the login page
 * of the new server.
 *
 * @param {string} url The normalized address the check answered with.
 * @param {{platform?: object}} [options]
 * @returns {Promise<void>}
 */
export async function switchServer(url, { platform = defaultPlatform } = {}) {
  await Promise.race([
    flushFrontendSettings(),
    new Promise((resolve) => setTimeout(resolve, FLUSH_TIMEOUT_MS)),
  ]);
  await useServerAddress(url, { signOut: true, platform });
  userPermissions.set([]);
  mumaUser.set(null);
  resetSessionState();
  signedOut.set(true);
}
