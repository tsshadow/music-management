<script>
  import { viewMode } from './store.js';
  import { itemsForMode } from './collections.js';
  import { t } from './i18n/index.js';

  /**
   * The phone's "browse everything" grid, shown on the Search tab before a
   * query is typed: one coloured tile per section the desktop sidebar lists
   * (`Sidebar.svelte`), so nothing that lives only in that sidebar is
   * unreachable on a phone. Tapping a tile navigates exactly like its sidebar
   * entry does; the routes themselves do not change.
   *
   * Labels, Lineups, Podcasts and Festivals only answer in one mode -- the
   * same `itemsForMode` the sidebar filters its own library group with keeps
   * this grid from offering a tile that would land on an empty page.
   */
  const { onnavigate } = $props();

  /** Fixed per-section colour, not fetched: these are categories, not genres, so `genreTints.js` (a per-genre colour from the server) does not apply here. */
  const TILE_COLORS = {
    genres: '#8C67AB',
    labels: '#E13300',
    podcasts: '#0D73EC',
    festivals: '#E1118C',
    years: '#1E3264',
    lineups: '#BC5900',
    artists: '#148A08',
    albums: '#7358FF',
    memories: '#503750',
    history: '#477D95',
    listening: '#8C1932',
    starred: '#E8115B',
  };

  const ALL_TILES = [
    { id: 'genres', labelKey: 'nav.genres', icon: 'M21.41 11.58l-9-9C12.05 2.21 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z' },
    { id: 'labels', labelKey: 'nav.labels', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z' },
    { id: 'podcasts', labelKey: 'nav.podcasts', icon: 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-2.08c3.39-.49 6-3.39 6-6.92h-2z' },
    { id: 'festivals', labelKey: 'nav.festivals', icon: 'M12 2L2 22h20L12 2zm0 4.8L18.1 20H5.9L12 6.8z' },
    { id: 'years', labelKey: 'nav.years', icon: 'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z' },
    { id: 'lineups', labelKey: 'nav.lineups', icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z' },
    { id: 'artists', labelKey: 'nav.artists', icon: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z' },
    { id: 'albums', labelKey: 'nav.albums', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z' },
    { id: 'memories', labelKey: 'nav.memories', icon: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z' },
    { id: 'history', labelKey: 'nav.history', icon: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z' },
    { id: 'listening', labelKey: 'nav.listening', icon: 'M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z' },
    { id: 'starred', labelKey: 'nav.starred', icon: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z' },
  ];

  const tiles = $derived(itemsForMode(ALL_TILES, $viewMode));

  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<div class="grid grid-cols-2 gap-3" aria-label={$t('mobile.browseAll')}>
  {#each tiles as tile (tile.id)}
    <button
      type="button"
      class="relative overflow-hidden rounded-lg h-24 p-3 border-none cursor-pointer text-left"
      style="background-color: {TILE_COLORS[tile.id]}"
      onclick={() => navigate(tile.id)}
    >
      <span class="relative z-10 text-white font-bold text-sm">{$t(tile.labelKey)}</span>
      <svg
        viewBox="0 0 24 24"
        width="56"
        height="56"
        fill="white"
        class="absolute -right-3 -bottom-3 rotate-12 opacity-40"
      >
        <path d={tile.icon}></path>
      </svg>
    </button>
  {/each}
</div>
