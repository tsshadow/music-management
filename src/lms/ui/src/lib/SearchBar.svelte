<script>
  import { onMount, untrack } from 'svelte';
  import { authParams, activeView, currentTrack, playlist, viewMode, activeModal } from './store.js';
  import SearchResults from './SearchResults.svelte';

  let query = $state('');
  let results = $state({});
  let filteredGenres = $state([]);
  let allGenres = $state([]);
  let loading = $state(false);
  let showResults = $state(false);
  let debounceTimer;
  let searchController;

  /**
   * Fetches search results from the Subsonic API.
   */
  async function performSearch() {
    if (searchController) {
      searchController.abort();
    }
    searchController = new AbortController();
    const { signal } = searchController;

    if (!query.trim()) {
      results = {};
      filteredGenres = [];
      loading = false;
      return;
    }

    loading = true;
    try {
      // Search for artists, albums, and songs
      const durationFilter = $viewMode === 'sets' ? '&minDuration=10' : '&maxDuration=10';
      const response = await fetch(`/rest/search3?${$authParams}&query=${encodeURIComponent(query)}&artistCount=20&albumCount=20&songCount=20${durationFilter}`, { signal });
      const data = await response.json();
      results = data['subsonic-response']?.searchResult3 || {};

      // Filter genres locally
      filteredGenres = allGenres
        .filter(genre => genre.toLowerCase().includes(query.toLowerCase()))
        .map(genre => genre);
      
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error("Search failed:", e);
    } finally {
      if (!signal.aborted) {
        loading = false;
      }
    }
  }

  /**
   * Handles input changes with debouncing.
   */
  function handleInput() {
    showResults = true;
    clearTimeout(debounceTimer);

    if (!query.trim()) {
      if (searchController) {
        searchController.abort();
        searchController = null;
      }
      results = {};
      filteredGenres = [];
      loading = false;
      return;
    }

    debounceTimer = setTimeout(() => {
      performSearch();
    }, 300);
  }

  /**
   * Loads all genres once on mount to enable local filtering.
   */
  async function loadAllGenres() {
    try {
      const response = await fetch(`/rest/getGenres?${$authParams}`);
      const data = await response.json();
      const genreList = data['subsonic-response']?.genres?.genre || [];
      allGenres = genreList.map(g => typeof g === 'string' ? g : (g.value || g.name));
    } catch (e) {
      console.error("Failed to load genres for search:", e);
    }
  }

  onMount(() => {
    loadAllGenres();
  });

  // Re-run search when mode changes and search is active
  $effect(() => {
    // We want to trigger when viewMode changes
    const mode = $viewMode;
    untrack(() => {
      if (showResults && query.trim()) {
        performSearch();
      }
    });
  });

  /**
   * Handles item selection from search results.
   * @param {string} type - The type of the selected item.
   * @param {any} idOrItem - The ID or name of the selected item.
   */
  function handleSelect(type, idOrItem) {
    showResults = false;
    if (type === 'artist') {
      activeView.set(`artist:${idOrItem}`);
    } else if (type === 'album') {
      activeView.set(`album:${idOrItem}`);
    } else if (type === 'track') {
      // Find the track object from results
      const track = (results.song || []).find(t => t.id === idOrItem);
      if (track) {
        currentTrack.set(track);
        // Add to playlist if not already there
        playlist.update(p => {
          if (!p.find(t => t.id === track.id)) {
            return [track, ...p];
          }
          return p;
        });
      }
    } else if (type === 'genre') {
      activeView.set(`genre:${idOrItem}`);
    } else if (type.startsWith('more-')) {
       const category = type.replace('more-', '');
       activeModal.set({ type: 'search-results', data: { query, category } });
    }
  }

  /**
   * Closes results when clicking outside.
   */
  function handleBlur() {
    // Small delay to allow click events on results to fire
    setTimeout(() => {
      showResults = false;
    }, 200);
  }
</script>

<div class="relative flex-grow max-w-md mx-4">
  <div class="relative group">
    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
      <svg class="h-5 w-5 text-[#b3b3b3] group-focus-within:text-white transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
    </div>
    <input
      type="text"
      bind:value={query}
      oninput={handleInput}
      onfocus={() => showResults = query.length > 0}
      onblur={handleBlur}
      placeholder={$viewMode === 'sets' ? "Zoeken in sets..." : "Wat wil je luisteren?"}
      class="block w-full pl-10 pr-3 py-2 bg-[#242424] border-none rounded-full text-sm text-white placeholder-[#b3b3b3] focus:ring-2 focus:ring-white transition-all hover:bg-[#2a2a2a]"
    />
  </div>

  {#if showResults && query.length > 0}
    <SearchResults 
      {results} 
      genres={filteredGenres} 
      {loading} 
      onSelect={handleSelect}
      mode={$viewMode}
    />
  {/if}
</div>
