<script>
  import { pressEntity, seedEntity } from './entitySeeds.js';
  import { t } from './i18n/index.js';
  /**
   * @typedef {Object} Props
   * @property {any} results - The search results object.
   * @property {string[]} genres - Filtered genres.
   * @property {string[]} labels - Filtered record labels.
   * @property {boolean} loading - A search for the current text is on its way (debounce included).
   * @property {boolean} [error] - The last search failed.
   * @property {() => void} [onretry] - Asks the failed search again.
   * @property {function(string, string): void} onSelect - Callback when an item is selected.
   * @property {string} mode - The current view mode ('songs' or 'sets').
   */

  /** @type {Props} */
  let { results = {}, genres = [], labels = [], loading = false, error = false, onretry, onSelect, mode = 'songs' } = $props();

  import { deduplicateTracks } from './deduplicate.js';
  import { getArtistImageUrl } from './utils.js';
  import { authParams, restUrl } from './store.js';
  import SectionState from './loading/SectionState.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import Throbber from './loading/Throbber.svelte';

  const artists = $derived(results.artist || []);
  const albums = $derived(results.album || []);
  const tracks = $derived(deduplicateTracks(results.song || []));
  const hasResults = $derived(
    artists.length > 0 || albums.length > 0 || tracks.length > 0 || genres.length > 0 || labels.length > 0
  );

  /**
   * Handles the click on a result item.
   * @param {string} type - Item type (artist, album, song, genre).
   * @param {any} item - The item object or name.
   */
  function handleSelect(type, item) {
    if (!onSelect) return;
    // A genre or label is its own value, and the "see more" links carry no item
    // at all -- only an artist, album or track has an id to hand on.
    if (type === 'genre' || type === 'label' || item === undefined) {
      onSelect(type, item);
    } else {
      // What the row shows becomes the next page's header until the server answers.
      if (type === 'artist' || type === 'album') seedEntity(type, item.id, item);
      onSelect(type, item.id);
    }
  }
</script>

<div class="absolute top-full left-0 right-0 mt-2 bg-muma-spotify-light rounded-md shadow-2xl border border-muma-spotify-highlight overflow-hidden z-50 max-h-[80vh] overflow-y-auto custom-scrollbar">
  <!-- Loading states per issue #112 (styleguide, Loading States: Search as you type): a
       "searching" line from the first keystroke, skeleton rows while there is nothing yet, the
       previous text's results dimmed while there is, and "No results" only for an answer. -->
  {#snippet searching()}
    <div class="flex items-center gap-2 px-4 pt-3 pb-1 text-sm text-muma-spotify-text" data-testid="search-searching">
      <Throbber label={$t('search.searching')} />
      <span>{$t('search.searching')}</span>
    </div>
  {/snippet}
  {#if loading && !hasResults}
    {@render searching()}
    <SkeletonRows count={3} />
  {:else if error && !hasResults}
    <SectionState status="error" {onretry} />
  {:else if !hasResults}
    <div class="p-4 text-center text-muma-spotify-text">{$t('search.noResults')}</div>
  {:else}
    {#if loading}
      {@render searching()}
    {/if}
    <div class="flex flex-col p-2 gap-4 transition-opacity duration-200 {loading ? 'opacity-50' : ''}" data-testid="search-dropdown-results" data-stale={loading ? 'true' : undefined}>
      
      {#if tracks.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{mode === 'sets' ? $t('nav.sets') : $t('nav.songs')}</h3>
            <button class="text-[11px] font-bold text-muma-spotify-text hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-tracks')}>{$t('search.seeMore')}</button>
          </div>
          <div class="flex flex-col">
            {#each tracks.slice(0, 5) as track (track.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-muma-spotify-highlight text-left transition-colors group"
                onclick={() => handleSelect('track', track)}
              >
                <div class="w-10 h-10 bg-muma-spotify-hover rounded flex-shrink-0 flex items-center justify-center overflow-hidden">
                  {#if track.coverArt}
                    <img src={restUrl(`/rest/getCoverArt?id=${track.coverArt}&size=40&${$authParams}`)} alt="" class="w-full h-full object-cover" />
                  {:else}
                    <svg viewBox="0 0 24 24" class="w-6 h-6 fill-muma-spotify-text"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
                  {/if}
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium group-hover:text-white">{track.title}</div>
                  <div class="text-muma-spotify-text text-xs truncate">{track.artist}</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if artists.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{$t('nav.artists')}</h3>
            <button class="text-[11px] font-bold text-muma-spotify-text hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-artists')}>{$t('search.seeMore')}</button>
          </div>
          <div class="flex flex-col">
            {#each artists.slice(0, 5) as artist (artist.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-muma-spotify-highlight text-left transition-colors group"
                onpointerdown={() => pressEntity('artist', artist)}
                onclick={() => handleSelect('artist', artist)}
              >
                <div class="w-10 h-10 bg-muma-spotify-hover rounded-full flex-shrink-0 flex items-center justify-center overflow-hidden">
                  <img src={getArtistImageUrl(artist, $authParams)} alt="" class="w-full h-full object-cover" onerror={(e) => e.target.style.display = 'none'} />
                  <svg viewBox="0 0 24 24" class="w-6 h-6 fill-muma-spotify-text absolute"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium">{artist.name}</div>
                  <div class="text-muma-spotify-text text-xs uppercase">{$t('common.artist')}</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if albums.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{$t('nav.albums')}</h3>
            <button class="text-[11px] font-bold text-muma-spotify-text hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-albums')}>{$t('search.seeMore')}</button>
          </div>
          <div class="flex flex-col">
            {#each albums.slice(0, 5) as album (album.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-muma-spotify-highlight text-left transition-colors group"
                onpointerdown={() => pressEntity('album', album)}
                onclick={() => handleSelect('album', album)}
              >
                <div class="w-10 h-10 bg-muma-spotify-hover rounded flex-shrink-0 flex items-center justify-center overflow-hidden">
                   {#if album.coverArt}
                    <img src={restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=40&${$authParams}`)} alt="" class="w-full h-full object-cover" />
                  {:else}
                    <svg viewBox="0 0 24 24" class="w-6 h-6 fill-muma-spotify-text"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z"/></svg>
                  {/if}
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium">{album.name}</div>
                  <div class="text-muma-spotify-text text-xs truncate">{album.artist}</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if genres.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{$t('nav.genres')}</h3>
          </div>
          <div class="flex flex-wrap gap-2 px-2">
            {#each genres.slice(0, 5) as genre (genre)}
              <button 
                class="px-3 py-1 bg-muma-spotify-highlight hover:bg-[#4e4e4e] text-white text-xs rounded-full transition-colors"
                onclick={() => handleSelect('genre', genre)}
              >
                {genre}
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if labels.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{$t('nav.labels')}</h3>
          </div>
          <div class="flex flex-wrap gap-2 px-2">
            {#each labels.slice(0, 5) as label (label)}
              <button
                class="px-3 py-1 bg-muma-spotify-highlight hover:bg-[#4e4e4e] text-white text-xs rounded-full transition-colors"
                onclick={() => handleSelect('label', label)}
              >
                {label}
              </button>
            {/each}
          </div>
        </section>
      {/if}

    </div>
  {/if}
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 8px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #4e4e4e;
    border-radius: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #5e5e5e;
  }
</style>
