<script>
  import { platform as defaultPlatform } from './platform/index.js';
  import { viewMode } from './store.js';
  import { browseSections } from './navigation.js';
  import { t } from './i18n/index.js';

  /**
   * The phone's "browse everything" grid, shown on the Browse tab before a
   * query is typed: one coloured tile per section the desktop sidebar lists,
   * so nothing that lives only in that sidebar is unreachable on a phone. The
   * list itself is `browseSections` in `navigation.js`, the same one the
   * sidebar renders, so the two cannot drift apart again; it already leaves
   * out what this shell (Downloads) or this mode (Labels, Lineups, Podcasts,
   * Festivals) cannot answer. Tapping a tile navigates exactly like its
   * sidebar entry does; the routes themselves do not change.
   */
  const { onnavigate, platform = defaultPlatform } = $props();

  /**
   * Fixed per-section colour, not fetched: these are categories, not genres, so
   * `genreTints.js` (a per-genre colour from the server) does not apply here.
   * Songs and Sets wear the two brand colours the mode toggle uses.
   */
  const TILE_COLORS = {
    songs: '#1DB954',
    sets: '#2D5AFC',
    playlists: '#1E3264',
    downloads: '#148A08',
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

  const tiles = $derived(browseSections($viewMode, platform));

  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<div class="grid grid-cols-2 gap-3" aria-label={$t('mobile.browseAll')}>
  {#each tiles as tile (tile.id)}
    <button
      type="button"
      class="relative overflow-hidden rounded-lg h-[68px] px-3 py-2 border-none cursor-pointer text-left"
      style="background-color: {TILE_COLORS[tile.id]}"
      onclick={() => navigate(tile.id)}
    >
      <span class="relative z-10 text-white font-bold text-sm">{$t(tile.labelKey)}</span>
      <svg
        viewBox="0 0 24 24"
        width="36"
        height="36"
        fill="white"
        class="absolute -right-2 -bottom-2 rotate-12 opacity-40"
      >
        <path d={tile.icon}></path>
      </svg>
    </button>
  {/each}
</div>
