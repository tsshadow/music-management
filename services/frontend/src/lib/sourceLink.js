/**
 * The source code offer (AGPL-3.0 section 13): the address the server reports as `source_url`
 * in its public `/health` answer. The server already checks it; the client checks again before
 * the value becomes an `href` or goes to the system browser, so a hostile value (`javascript:`,
 * `intent:`, `data:`) never turns into a link.
 */

/**
 * @param {unknown} value
 * @returns {string} The address when it is an http(s) URL, else an empty string.
 */
export function safeSourceUrl(value) {
  if (typeof value !== "string") return "";
  const url = value.trim();
  return /^https?:\/\//i.test(url) ? url : "";
}

/**
 * Reads `source_url` from `<apiBase>/health`. A 503 (a sick server) carries it too. Any failure
 * gives an empty string: the offer is hidden, never an error on screen.
 *
 * @param {string} apiBase - The MuMa API base URL.
 * @returns {Promise<string>}
 */
export async function fetchSourceUrl(apiBase) {
  try {
    const response = await fetch(`${apiBase}/health`);
    const body = await response.json();
    return safeSourceUrl(body?.source_url);
  } catch {
    return "";
  }
}
