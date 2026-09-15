/**
 * Splits a genre string into the individual genres and the separators between
 * them, so "hardstyle,hardcore" becomes two links instead of one while still
 * reading as the string the backend stored.
 *
 * Shared between `TrackList.svelte` (the desktop genre column, which keeps
 * the separators to read as one sentence) and `TrackDetailsSheet.svelte`
 * (which only wants the names, for a row of chips) so a track's genres split
 * exactly the same way everywhere they show up.
 *
 * @param {string} genre - The raw genre string from the backend.
 * @returns {Array<{text: string, name: string|null}>} Segments in order; `name` is null for separators.
 */
export function genreSegments(genre) {
  return (genre || "")
    .split(/([,;]\s*)/)
    .filter((part) => part !== "")
    .map((part) =>
      /^[,;]/.test(part) ? { text: part, name: null } : { text: part, name: part.trim() },
    )
    .filter((segment) => segment.name !== "");
}

/**
 * Just the genre names out of a genre string, for a row of chips that has no
 * use for the separators between them.
 *
 * @param {string} genre
 * @returns {string[]}
 */
export function genreNames(genre) {
  return genreSegments(genre)
    .map((segment) => segment.name)
    .filter((name) => name);
}
