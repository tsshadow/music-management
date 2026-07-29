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
 * Returns the URL for an artist image.
 * 
 * @param {Object} artist - The artist object.
 * @param {string} authParams - Subsonic auth parameters.
 * @returns {string} The image URL.
 */
export function getArtistImageUrl(artist, authParams) {
  if (artist && artist.coverArt) {
    return `/rest/getCoverArt?id=${artist.coverArt}&size=300&${authParams}`;
  }
  if (artist && artist.name) {
    // Must go through the authenticated /muma proxy (MumaResource.cpp), not a bare
    // "/media/artist-images/{id}/..." path -- nothing on the LMS server serves that
    // path (it's only mounted on music_manager itself), so it fell through to the
    // SPA's index.html fallback and rendered as a broken image for every artist
    // without native LMS artwork.
    return `/muma/api/artists/${encodeURIComponent(artist.name)}/image?${authParams}`;
  }
  return '/images/unknown-artist.svg';
}
