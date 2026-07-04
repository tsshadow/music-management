<script>
  /**
   * @typedef {Object} Props
   * @property {any} results - The search results object.
   * @property {string[]} genres - Filtered genres.
   * @property {boolean} loading - Loading state.
   * @property {function(string, string): void} onSelect - Callback when an item is selected.
   * @property {string} mode - The current view mode ('songs' or 'sets').
   */

  /** @type {Props} */
  let { results = {}, genres = [], loading = false, onSelect, mode = 'songs' } = $props();

  import { deduplicateTracks } from './deduplicate.js';

  const artists = $derived(results.artist || []);
  const albums = $derived(results.album || []);
  const tracks = $derived(deduplicateTracks(results.song || []));

  /**
   * Handles the click on a result item.
   * @param {string} type - Item type (artist, album, song, genre).
   * @param {any} item - The item object or name.
   */
  function handleSelect(type, item) {
    if (onSelect) {
      if (type === 'genre') {
        onSelect(type, item);
      } else {
        onSelect(type, item.id);
      }
    }
  }
</script>

<div class="absolute top-full left-0 right-0 mt-2 bg-[#282828] rounded-md shadow-2xl border border-[#3e3e3e] overflow-hidden z-50 max-h-[80vh] overflow-y-auto custom-scrollbar">
  {#if loading}
    <div class="p-4 text-center text-[#b3b3b3]">Laden...</div>
  {:else if artists.length === 0 && albums.length === 0 && tracks.length === 0 && genres.length === 0}
    <div class="p-4 text-center text-[#b3b3b3]">Geen resultaten gevonden.</div>
  {:else}
    <div class="flex flex-col p-2 gap-4">
      
      {#if tracks.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">{mode === 'sets' ? 'Sets' : 'Nummers'}</h3>
            <button class="text-[11px] font-bold text-[#b3b3b3] hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-tracks')}>Zie meer</button>
          </div>
          <div class="flex flex-col">
            {#each tracks.slice(0, 5) as track (track.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-[#3e3e3e] text-left transition-colors group"
                onclick={() => handleSelect('track', track)}
              >
                <div class="w-10 h-10 bg-[#333] rounded flex-shrink-0 flex items-center justify-center overflow-hidden">
                  {#if track.coverArt}
                    <img src={`/rest/getCoverArt?id=${track.coverArt}&size=40`} alt="" class="w-full h-full object-cover" />
                  {:else}
                    <svg viewBox="0 0 24 24" class="w-6 h-6 fill-[#b3b3b3]"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
                  {/if}
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium group-hover:text-white">{track.title}</div>
                  <div class="text-[#b3b3b3] text-xs truncate">{track.artist}</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if artists.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">Artiesten</h3>
            <button class="text-[11px] font-bold text-[#b3b3b3] hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-artists')}>Zie meer</button>
          </div>
          <div class="flex flex-col">
            {#each artists.slice(0, 5) as artist (artist.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-[#3e3e3e] text-left transition-colors group"
                onclick={() => handleSelect('artist', artist)}
              >
                <div class="w-10 h-10 bg-[#333] rounded-full flex-shrink-0 flex items-center justify-center overflow-hidden">
                  <svg viewBox="0 0 24 24" class="w-6 h-6 fill-[#b3b3b3]"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium">{artist.name}</div>
                  <div class="text-[#b3b3b3] text-xs uppercase">Artiest</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if albums.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">Albums</h3>
            <button class="text-[11px] font-bold text-[#b3b3b3] hover:underline uppercase tracking-wider" onclick={() => handleSelect('more-albums')}>Zie meer</button>
          </div>
          <div class="flex flex-col">
            {#each albums.slice(0, 5) as album (album.id)}
              <button 
                class="flex items-center gap-3 p-2 rounded hover:bg-[#3e3e3e] text-left transition-colors group"
                onclick={() => handleSelect('album', album)}
              >
                <div class="w-10 h-10 bg-[#333] rounded flex-shrink-0 flex items-center justify-center overflow-hidden">
                   {#if album.coverArt}
                    <img src={`/rest/getCoverArt?id=${album.coverArt}&size=40`} alt="" class="w-full h-full object-cover" />
                  {:else}
                    <svg viewBox="0 0 24 24" class="w-6 h-6 fill-[#b3b3b3]"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z"/></svg>
                  {/if}
                </div>
                <div class="flex-grow min-w-0">
                  <div class="text-white text-sm truncate font-medium">{album.name}</div>
                  <div class="text-[#b3b3b3] text-xs truncate">{album.artist}</div>
                </div>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      {#if genres.length > 0}
        <section>
          <div class="flex items-center justify-between px-2 mb-2">
            <h3 class="text-white font-bold text-sm">Genres</h3>
          </div>
          <div class="flex flex-wrap gap-2 px-2">
            {#each genres.slice(0, 5) as genre (genre)}
              <button 
                class="px-3 py-1 bg-[#3e3e3e] hover:bg-[#4e4e4e] text-white text-xs rounded-full transition-colors"
                onclick={() => handleSelect('genre', genre)}
              >
                {genre}
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
