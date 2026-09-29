/**
 * The library destinations, written down once for both shells.
 *
 * The desktop sidebar (`Sidebar.svelte`) and the phone's Browse grid
 * (`BrowseGrid.svelte`) used to each carry their own copy of this list, and the
 * two drifted: a section added to one was quietly missing from the other, and
 * even the shared ones disagreed on icon and order. Both now read from here, and
 * `navigation.test.js` holds them to the same set, so a destination exists on
 * every screen size or on none.
 *
 * Only the *what* lives here -- id, label key, icon, and the platform gate. How
 * it is drawn (a row, a coloured tile) stays with the component.
 */

import { itemsForMode } from "./collections.js";

/**
 * The "everything" list for the current mode, one entry per mode. The sidebar
 * shows the one for the active mode next to its toggle; the phone's grid gets
 * the same entry as its first tile, because the mode chips in its top bar only
 * switch the mode and would otherwise leave the full list unreachable.
 */
export const MODE_SECTIONS = {
  songs: {
    id: "songs",
    labelKey: "nav.songs",
    icon: "M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z",
  },
  sets: {
    id: "sets",
    labelKey: "nav.sets",
    icon: "M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z",
  },
};

/** Playlists sit beside the mode entry rather than inside the library group. */
export const PLAYLISTS_SECTION = {
  id: "playlists",
  labelKey: "nav.playlists",
  icon: "M3 22a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H3zm13-2V4H4v16h12z",
};

/**
 * The browse pages over the library, in sidebar order.
 *
 * `nativeOnly` marks an entry that only makes sense inside a shell that can keep
 * files: a browser tab cannot download, so it never sees the entry at all rather
 * than seeing a page that explains why it is empty. `librarySections` applies
 * that gate together with the per-mode one from `collections.js`.
 */
export const LIBRARY_SECTIONS = [
  {
    id: "artists",
    labelKey: "nav.artists",
    icon: "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z",
  },
  {
    id: "albums",
    labelKey: "nav.albums",
    icon: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z",
  },
  {
    id: "genres",
    labelKey: "nav.genres",
    icon: "M21.41 11.58l-9-9C12.05 2.21 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z",
  },
  {
    id: "labels",
    labelKey: "nav.labels",
    icon: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z",
  },
  {
    id: "podcasts",
    labelKey: "nav.podcasts",
    icon: "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-2.08c3.39-.49 6-3.39 6-6.92h-2z",
  },
  // The same three marks CollectionGrid draws on the cards these lead to.
  {
    id: "festivals",
    labelKey: "nav.festivals",
    icon: "M12 2L2 22h20L12 2zm0 4.8L18.1 20H5.9L12 6.8z",
  },
  {
    id: "years",
    labelKey: "nav.years",
    icon: "M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z",
  },
  { id: "lineups", labelKey: "nav.lineups", icon: "M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z" },
  // Browse by BPM (docs/designs/bpm-browse/): a gauge, the tempo dial.
  {
    id: "bpm",
    labelKey: "nav.bpm",
    icon: "M12 4a10 10 0 0 0-8.66 15h17.32A10 10 0 0 0 12 4zm0 2a8 8 0 0 1 7.43 11H4.57A8 8 0 0 1 12 6zm4.24 2.34-5.66 4.25a2 2 0 1 0 2.83 2.83l2.83-7.08z",
  },
  // Only inside a shell that can actually keep files. Criterion 13: in a
  // plain browser this entry does not exist at all.
  {
    id: "downloads",
    labelKey: "nav.downloads",
    icon: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
    nativeOnly: true,
  },
];

/** The per-account pages after the library group: what you kept, played and were told. */
export const PERSONAL_SECTIONS = [
  {
    id: "starred",
    labelKey: "nav.starred",
    icon: "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z",
  },
  {
    id: "history",
    labelKey: "nav.history",
    icon: "M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z",
  },
  {
    id: "memories",
    labelKey: "nav.memories",
    icon: "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
  },
  {
    id: "listening",
    labelKey: "nav.listening",
    icon: "M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z",
  },
];

/**
 * The library group as this platform and mode can answer it.
 *
 * @param {string} mode - 'songs' or 'sets'.
 * @param {{storage?: {supported?: boolean}}} [platform] - The shell's capabilities.
 * @returns {Array<Object>} The entries worth showing, in sidebar order.
 */
export function librarySections(mode, platform) {
  const native = platform?.storage?.supported === true;
  return itemsForMode(
    LIBRARY_SECTIONS.filter((section) => !section.nativeOnly || native),
    mode,
  );
}

/**
 * Everything the sidebar offers below Home, flattened in sidebar order: the
 * phone's Browse grid is this list, one tile each.
 *
 * @param {string} mode - 'songs' or 'sets'.
 * @param {{storage?: {supported?: boolean}}} [platform] - The shell's capabilities.
 * @returns {Array<Object>}
 */
export function browseSections(mode, platform) {
  return [
    MODE_SECTIONS[mode] ?? MODE_SECTIONS.songs,
    PLAYLISTS_SECTION,
    ...librarySections(mode, platform),
    ...PERSONAL_SECTIONS,
  ];
}
