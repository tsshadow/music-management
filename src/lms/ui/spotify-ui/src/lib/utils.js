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
