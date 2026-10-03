<script>
  import { t } from './i18n/index.js';
  import { onMount, untrack } from 'svelte';
  import { activeView, currentTrack, playlist, viewMode, activeModal } from './store.js';
  import { subsonicJson } from './subsonic.js';
  import { loadSearchFacets } from './searchFacets.js';
  import SearchResults from './SearchResults.svelte';

  // Bindable so the shell's Android back handler can dismiss the results panel
  // from the outside (via `searchResultsOpen` in the store, bound by TopBar)
  // without SearchBar knowing anything about the shell. Every existing caller
  // renders SearchBar without binding it, which leaves this exactly the local
  // `$state` it always was.
  let { showResults = $bindable(false) } = $props();

  let query = $state('');
  let results = $state({});
  let filteredGenres = $state([]);
  let allGenres = $state([]);
  let filteredLabels = $state([]);
  let allLabels = $state([]);
  // True from the first keystroke until the answer for the current text is in -- the 300ms
  // debounce included, so the panel never says "No results" for a search that has not been
  // asked yet (issue #112).
  let loading = $state(false);
  // The last search failed: the panel offers a retry instead of claiming there is nothing.
  let error = $state(false);
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
      filteredLabels = [];
      loading = false;
      error = false;
      return;
    }

    loading = true;
    error = false;
    try {
      // Search for artists, albums, and songs
      const durationFilter = $viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 };
      const data = await subsonicJson(
        'search3',
        { query, artistCount: 20, albumCount: 20, songCount: 20, ...durationFilter },
        { signal }
      );
      results = data['subsonic-response']?.searchResult3 || {};

      // Filter genres and labels locally
      filteredGenres = allGenres
        .filter(genre => genre.toLowerCase().includes(query.toLowerCase()))
        .map(genre => genre);
      filteredLabels = allLabels
        .filter(label => label.toLowerCase().includes(query.toLowerCase()))
        .map(label => label);

    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error("Search failed:", e);
      // The previous text's results are not this text's answer.
      results = {};
      filteredGenres = [];
      filteredLabels = [];
      error = true;
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
      filteredLabels = [];
      loading = false;
      error = false;
      return;
    }

    // Searching starts now as far as the listener is concerned: what is on screen belongs to
    // the previous text and is shown dimmed until the answer replaces it.
    loading = true;
    error = false;
    debounceTimer = setTimeout(() => {
      performSearch();
    }, 300);
  }

  // The genre and label lists come from a module-level cache shared with any
  // other SearchBar (TopBar swaps between a phone and a desktop one), so a
  // remount does not fetch them again.
  onMount(() => {
    loadSearchFacets().then(({ genres, labels }) => {
      allGenres = genres;
      allLabels = labels;
    });
  });

  // Re-run search when mode changes and search is active
  $effect(() => {
    // We want to trigger when viewMode changes
    const _mode = $viewMode;
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
    } else if (type === 'label') {
      activeView.set(`label:${idOrItem}`);
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

<div class="relative min-w-0 flex-1 md:flex-grow md:max-w-md md:mx-4">
  <div class="relative group">
    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
      <svg class="h-5 w-5 text-muma-spotify-text group-focus-within:text-white transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
      placeholder={$viewMode === 'sets' ? $t('search.placeholderSets') : $t('search.placeholder')}
      class="block w-full pl-10 pr-3 py-1.5 md:py-2 bg-muma-spotify-raised border-none rounded-full text-sm text-white placeholder-muma-spotify-text focus:ring-2 focus:ring-white transition-all hover:bg-[#2a2a2a]"
    />
  </div>

  {#if showResults && query.length > 0}
    <SearchResults
      {results}
      genres={filteredGenres}
      labels={filteredLabels}
      {loading}
      {error}
      onretry={performSearch}
      onSelect={handleSelect}
      mode={$viewMode}
    />
  {/if}
</div>
