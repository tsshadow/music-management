<script>
  import { viewMode, authParams, favoriteGenres, isAdmin } from './store.js';
  import { itemsForMode } from './collections.js';
  import { t } from './i18n/index.js';
  import { ChevronRight } from '@lucide/svelte';
  import SidebarHeader from './SidebarHeader.svelte';
  const { activeView = 'home', onnavigate } = $props();
  let allGenres = $state([]);

  const LIBRARY_OPEN_KEY = 'muma_sidebar_library_open';

  /**
   * Whether the library group was left open the last time this browser was used.
   *
   * @returns {boolean}
   */
  function storedLibraryOpen() {
    try {
      return localStorage.getItem(LIBRARY_OPEN_KEY) === 'true';
    } catch {
      return false;
    }
  }

  let libraryOpen = $state(storedLibraryOpen());

  function toggleLibrary() {
    libraryOpen = !libraryOpen;
    try {
      localStorage.setItem(LIBRARY_OPEN_KEY, String(libraryOpen));
    } catch {
      // A browser that refuses storage still gets a working sidebar, just a forgetful one.
    }
  }

  async function loadGenres() {
    if (!$authParams) return;
    try {
        const response = await fetch(`/rest/getGenres?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            const result = data['subsonic-response']?.genres?.genre || [];
            const resultArr = Array.isArray(result) ? result : [result];
            allGenres = resultArr
                .filter(g => Number(g.songCount) >= 5)
                .sort((a, b) => b.songCount - a.songCount);
        }
    } catch (e) {
        console.error("Failed to fetch genres for sidebar:", e);
    }
  }

  const displayedGenres = $derived(
    $favoriteGenres.length > 0
      ? allGenres.filter(g => $favoriteGenres.includes(g.value)).sort((a, b) => a.value.localeCompare(b.value))
      : allGenres.slice(0, 15).sort((a, b) => a.value.localeCompare(b.value))
  );

  $effect(() => {
    if ($authParams) {
        loadGenres();
    }
  });

  const primaryItems = $derived([
    { id: 'home', label: $t('nav.home'), icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    {
      id: $viewMode === 'sets' ? 'sets' : 'songs',
      label: $viewMode === 'sets' ? $t('nav.sets') : $t('nav.songs'),
      icon: $viewMode === 'sets'
        ? 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z'
        : 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z'
    },
    { id: 'playlists', label: $t('nav.playlists'), icon: 'M3 22a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H3zm13-2V4H4v16h12z' },
  ]);

  const allLibraryItems = $derived([
    { id: 'artists', label: $t('nav.artists'), icon: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z' },
    { id: 'albums', label: $t('nav.albums'), icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z' },
    { id: 'genres', label: $t('nav.genres'), icon: 'M21.41 11.58l-9-9C12.05 2.21 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z' },
    { id: 'labels', label: $t('nav.labels'), icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z' },
    { id: 'podcasts', label: $t('nav.podcasts'), icon: 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-2.08c3.39-.49 6-3.39 6-6.92h-2z' },
    // The same three marks CollectionGrid draws on the cards these lead to.
    { id: 'festivals', label: $t('nav.festivals'), icon: 'M12 2L2 22h20L12 2zm0 4.8L18.1 20H5.9L12 6.8z' },
    { id: 'years', label: $t('nav.years'), icon: 'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z' },
    { id: 'lineups', label: $t('nav.lineups'), icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z' },
  ]);

  // Not every browse view answers in both modes -- see COLLECTION_MODES.
  const libraryItems = $derived(itemsForMode(allLibraryItems, $viewMode));

  const tailItems = $derived([
    { id: 'starred', label: $t('nav.starred'), icon: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z' },
    { id: 'history', label: $t('nav.history'), icon: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z' },
    { id: 'memories', label: $t('nav.memories'), icon: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z' },
  ]);

  // Landing straight on an album or a label — from a deep link, say — should not
  // leave the group that owns that view folded shut.
  const libraryExpanded = $derived(
    libraryOpen || libraryItems.some(item => item.id === activeView)
  );

  /**
   * Triggers navigation to a specific view.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<nav class="flex flex-col gap-6 h-full">
  <SidebarHeader />

  <div class="px-3 py-4">
    <div class="flex items-center gap-3">
      <button class="bg-transparent border-none p-0 text-[13px] font-bold {$viewMode === 'songs' ? 'text-white' : 'text-[#b3b3b3]'} transition-colors cursor-pointer" onclick={() => viewMode.set('songs')}>{$t('nav.songs')}</button>
      <button
        class="relative flex-shrink-0 w-10 h-5 rounded-full bg-[#282828] transition-colors duration-200 hover:bg-[#3e3e3e]"
        onclick={() => viewMode.update(m => m === 'songs' ? 'sets' : 'songs')}
        aria-label={$t('sidebar.toggleMode')}
      >
        <div
          class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full transition-transform duration-200 {$viewMode === 'sets' ? 'translate-x-5 bg-brand-blue' : 'bg-brand-green'}"
        ></div>
      </button>
      <button class="bg-transparent border-none p-0 text-[13px] font-bold {$viewMode === 'sets' ? 'text-white' : 'text-[#b3b3b3]'} transition-colors cursor-pointer" onclick={() => viewMode.set('sets')}>{$t('nav.sets')}</button>
    </div>
  </div>

  <ul class="list-none p-0 m-0">
    {#each primaryItems as item (item.id)}
      <li class="mb-1 {activeView === item.id ? 'text-white' : 'text-[#b3b3b3]'}">
        <button
          class="flex items-center gap-4 w-full px-3 py-2 bg-transparent border-none font-bold text-sm cursor-pointer transition-colors hover:text-white text-left"
          onclick={() => navigate(item.id)}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
            <path d={item.icon}></path>
          </svg>
          {item.label}
        </button>
      </li>
    {/each}

    <li class="mb-1 {libraryExpanded ? 'text-white' : 'text-[#b3b3b3]'}">
      <button
        class="flex items-center gap-4 w-full px-3 py-2 bg-transparent border-none font-bold text-sm cursor-pointer transition-colors hover:text-white text-left"
        onclick={toggleLibrary}
        aria-expanded={libraryExpanded}
        aria-controls="sidebar-library-group"
      >
        <span class="w-6 h-6 flex items-center justify-center">
          <ChevronRight size={18} class="transition-transform duration-200 {libraryExpanded ? 'rotate-90' : ''}" />
        </span>
        {$t('sidebar.library')}
      </button>

      {#if libraryExpanded}
        <ul id="sidebar-library-group" class="list-none p-0 m-0">
          {#each libraryItems as item (item.id)}
            <li class="mb-1 {activeView === item.id ? 'text-white' : 'text-[#b3b3b3]'}">
              <button
                class="flex items-center gap-4 w-full pl-6 pr-3 py-2 bg-transparent border-none font-medium text-sm cursor-pointer transition-colors hover:text-white text-left"
                onclick={() => navigate(item.id)}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d={item.icon}></path>
                </svg>
                {item.label}
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </li>

    {#each tailItems as item (item.id)}
      <li class="mb-1 {activeView === item.id ? 'text-white' : 'text-[#b3b3b3]'}">
        <button
          class="flex items-center gap-4 w-full px-3 py-2 bg-transparent border-none font-bold text-sm cursor-pointer transition-colors hover:text-white text-left"
          onclick={() => navigate(item.id)}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
            <path d={item.icon}></path>
          </svg>
          {item.label}
        </button>
      </li>
    {/each}
  </ul>


  <div class="genres overflow-y-auto scrollbar-hide">
    <h3 class="px-3 text-[12px] text-[#b3b3b3] tracking-[1.5px] mb-3">
        {$favoriteGenres.length > 0 ? $t('sidebar.favoriteGenres') : $t('sidebar.popularGenres')}
    </h3>
    <ul class="list-none p-0 m-0">
      {#each displayedGenres as genre (genre.value)}
        <li>
          <button class="w-full px-3 py-2 bg-transparent border-none {activeView === `genre:${genre.value}` ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate(`genre:${genre.value}`)}>{genre.value}</button>
        </li>
      {/each}
    </ul>
  </div>
</nav>

<style>
</style>
