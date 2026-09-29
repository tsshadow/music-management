/**
 * The fixed colour per Browse category. Pulled out of `BrowseGrid.svelte` so
 * `RecentPlacesRow.svelte` can colour a recent place the same as its category
 * tile without a second, driftable copy of the table.
 */
export const TILE_COLORS = {
  songs: "#1DB954",
  sets: "#2D5AFC",
  playlists: "#1E3264",
  downloads: "#148A08",
  genres: "#8C67AB",
  labels: "#E13300",
  podcasts: "#0D73EC",
  festivals: "#E1118C",
  years: "#1E3264",
  lineups: "#BC5900",
  // Browse by BPM (docs/designs/bpm-browse/).
  bpm: "#006450",
  artists: "#148A08",
  albums: "#7358FF",
  memories: "#503750",
  history: "#477D95",
  listening: "#8C1932",
  starred: "#E8115B",
};
