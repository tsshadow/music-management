/**
 * The source code offer (AGPL-3.0 section 13): the address the server reports as `source_url`
 * in its public `/health` answer. The server already checks it; the client checks again before
 * the value becomes an `href` or goes to the system browser, so a hostile value (`javascript:`,
 * `intent:`, `data:`) never turns into a link.
 */

/**
 * Mirrors the server (`_public_source_url` in services/music_manager/main.py): scheme http or
 * https in any case, a host, no user info. `https:///path` is refused up front because `new URL`
 * would quietly read "path" as the host.
 *
 * @param {unknown} value
 * @returns {string} The address when it is a plain http(s) URL, else an empty string.
 */
export function safeSourceUrl(value) {
  if (typeof value !== "string") return "";
  const url = value.trim();
  if (!/^https?:\/\/[^/]/i.test(url)) return "";
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    if (!parsed.hostname || parsed.username || parsed.password) return "";
  } catch {
    return "";
  }
  return url;
}

/** How long the login screen waits for `/health` before it gives up on the offer. */
export const SOURCE_FETCH_TIMEOUT_MS = 5000;

/**
 * Reads `source_url` from `<apiBase>/health`. A 503 (a sick server) carries it too. Any failure,
 * or no answer within five seconds, gives an empty string: the offer is hidden, never an error
 * on screen. In the native shell an empty base would make `/health` resolve against the app's
 * own origin, so that case does not fetch at all.
 *
 * @param {string} apiBase - The MuMa API base URL.
 * @param {{native?: boolean, timeoutMs?: number}} [options]
 * @returns {Promise<string>}
 */
export async function fetchSourceUrl(
  apiBase,
  { native = false, timeoutMs = SOURCE_FETCH_TIMEOUT_MS } = {},
) {
  if (native && !apiBase) return "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${apiBase}/health`, { signal: controller.signal });
    const body = await response.json();
    return safeSourceUrl(body?.source_url);
  } catch {
    return "";
  } finally {
    clearTimeout(timer);
  }
}
