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

/** How many stations the Radio page remembers as played last. */
export const RECENT_STATIONS_KEPT = 6;

/**
 * The logo of a station. The file ships with the web bundle, so a phone without a connection to the
 * broadcaster still shows it. A station a curator added has no file: the image fails to load, and
 * the caller shows the name instead.
 *
 * @param {string} slug
 * @returns {string}
 */
export function stationLogoUrl(slug) {
  return `/images/stations/${encodeURIComponent(slug)}.png`;
}

/**
 * The list of last played stations after a station started: newest first, each station once.
 *
 * @param {Array<string>} recent
 * @param {string} slug
 * @returns {Array<string>}
 */
export function withRecentStation(recent, slug) {
  return [slug, ...recent.filter((other) => other !== slug)].slice(0, RECENT_STATIONS_KEPT);
}

/**
 * The favorites after a tap on the star of a station. A new favorite goes to the end.
 *
 * @param {Array<string>} favorites
 * @param {string} slug
 * @returns {Array<string>}
 */
export function withFavoriteToggled(favorites, slug) {
  return favorites.includes(slug)
    ? favorites.filter((other) => other !== slug)
    : [...favorites, slug];
}

/**
 * What the Radio page shows. A search shows only the matches, because a listener who types wants
 * one station. A slug of a station that is gone is skipped, and a favorite is not also recent.
 *
 * @param {Array<{slug: string, name: string}>} stations - In the order of the server.
 * @param {Array<string>} favorites
 * @param {Array<string>} recent
 * @param {string} query
 * @returns {{favorites: Array<object>, recent: Array<object>, all: Array<object>}}
 */
export function stationSections(stations, favorites, recent, query = "") {
  const needle = query.trim().toLowerCase();
  if (needle) {
    return {
      favorites: [],
      recent: [],
      all: stations.filter((station) => station.name.toLowerCase().includes(needle)),
    };
  }
  const bySlug = new Map(stations.map((station) => [station.slug, station]));
  const pick = (slugs) => slugs.map((slug) => bySlug.get(slug)).filter(Boolean);
  return {
    favorites: pick(favorites),
    recent: pick(recent.filter((slug) => !favorites.includes(slug))),
    all: stations,
  };
}
