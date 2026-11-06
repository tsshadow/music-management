/**
 * What a live station from outside MuMa looks like to the player.
 *
 * Pure, so it can be tested without a DOM. A station has no library track behind it: the id is
 * null, which is what keeps it out of ratings and scrobbles
 * (docs/designs/live-radio-stations/technical.md).
 */

/**
 * The station as the track the player draws. A stream that sends a title shows it, with the station
 * name under it. Otherwise the station name is the title.
 *
 * @param {{name: string, title?: string|null}} station
 * @returns {{id: null, title: string, artist: string, album: string, coverArt: null}}
 */
export function stationAsTrack(station) {
  const title = station.title?.trim();
  const hasOwnTitle = Boolean(title) && title !== station.name;
  return {
    id: null,
    title: hasOwnTitle ? title : station.name,
    artist: hasOwnTitle ? station.name : "",
    album: "",
    coverArt: null,
  };
}

/**
 * The station the native service reports, with the name of the list when the list is known.
 *
 * @param {{stationSlug?: string|null, stationTitle?: string|null}} state - `platform.player.state()`.
 * @param {Array<{slug: string, name: string, stream_url?: string}>} known - The loaded stations.
 * @param {{slug: string, name: string}|null} current - The station the player shows now.
 * @returns {{slug: string, name: string, stream_url: string|null, title: string|null}|null}
 */
export function stationFromNativeState(state, known, current) {
  const slug = state.stationSlug ?? null;
  if (!slug) return null;
  const listed = known.find((station) => station.slug === slug);
  const same = current?.slug === slug ? current : null;
  return {
    slug,
    name: listed?.name ?? same?.name ?? state.stationTitle ?? slug,
    stream_url: listed?.stream_url ?? same?.stream_url ?? null,
    title: state.stationTitle ?? null,
  };
}
