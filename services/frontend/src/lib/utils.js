import { get } from "svelte/store";
import { mumaApiUrl } from "./store.js";

/**
 * Splits a comma-separated string of artists into an array of trimmed names.
 *
 * @param {string} artistStr - The comma-separated artist string.
 * @returns {string[]} An array of artist names.
 */
export function splitArtists(artistStr) {
  if (!artistStr) return [];
  return artistStr.split(", ").map((name) => name.trim());
}

/**
 * Formats an array of artist names into a human-readable list.
 * e.g., ["Artist A", "Artist B", "Artist C"] -> "Artist A, Artist B and Artist C"
 *
 * @param {string[]} artists - Array of artist names.
 * @returns {string} Formatted artist string.
 */
export function formatArtistList(artists) {
  if (artists.length <= 1) return artists[0] || "";
  const last = artists.at(-1);
  const rest = artists.slice(0, artists.length - 1);
  return rest.join(", ") + " and " + last;
}

/**
 * The argument of a prefixed view id, e.g. "Bad Taste Recordings" out of
 * "label:Bad Taste Recordings".
 *
 * Splitting on ":" and taking element 1 truncates every name that contains a
 * colon of its own -- and plenty of labels, genres and search terms do -- which
 * then filters the track list on a name no track carries. Everything after the
 * first colon is the argument.
 *
 * @param {string} view - A view id of the form "prefix:argument".
 * @returns {string} The argument, or "" when the view has no colon at all.
 */
export function viewArgument(view) {
  const separator = String(view ?? "").indexOf(":");
  return separator === -1 ? "" : view.slice(separator + 1);
}

/**
 * Returns the URL for an artist image.
 *
 * @param {Object} artist - The artist object.
 * @param {string} authParams - Subsonic auth parameters.
 * @returns {string} The image URL.
 */
export function getArtistImageUrl(artist, authParams) {
  const mumaApiBase = get(mumaApiUrl);
  if (artist && artist.coverArt) {
    return `/rest/getCoverArt?id=${artist.coverArt}&size=300&${authParams}`;
  }
  if (artist && artist.name) {
    return `${mumaApiBase}/api/artists/${encodeURIComponent(artist.name)}/image?${authParams}`;
  }
  if (artist && artist.id) {
    return `/media/artist-images/${artist.id}/primary.jpg`;
  }
  return "/images/unknown-artist.svg";
}

/**
 * The failure a Subsonic response describes, if any.
 *
 * Subsonic answers a rejected call with HTTP 200 and a `status: "failed"`
 * body, so `response.ok` is not a success check -- it only says the request
 * reached the server. Callers that only looked at `response.ok` silently
 * treated every server-side rejection as a success.
 *
 * Only an explicit `status: "ok"` counts as success. A 200 whose body will
 * not parse, or which carries no `subsonic-response` at all, is a proxy error
 * page or a login redirect rather than a stored write -- calling that a
 * success is the same silent failure in a different disguise.
 *
 * @param {Response} response - The response from a `/rest/...` call.
 * @returns {Promise<{code: number|null, message: string}|null>} `null` when
 *   the call succeeded, otherwise the reported failure.
 */
export async function subsonicError(response) {
  if (!response.ok) {
    return { code: null, message: response.statusText || `HTTP ${response.status}` };
  }
  let body;
  try {
    body = await response.json();
  } catch {
    return { code: null, message: "unreadable response" };
  }
  const payload = body?.["subsonic-response"];
  if (!payload) return { code: null, message: "unreadable response" };
  if (payload.status === "ok") return null;
  return {
    code: payload.error?.code ?? null,
    message: payload.error?.message ?? payload.status ?? "failed",
  };
}
