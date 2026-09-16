<script>
  import { viewMode, authParams, favoriteGenres, isAdmin } from './store.js';
  import { MODE_SECTIONS, PLAYLISTS_SECTION, PERSONAL_SECTIONS, librarySections } from './navigation.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { platform } from './platform/index.js';
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
        allGenres = listOf(await subsonicJson('getGenres'), 'genres.genre')
            .filter(g => Number(g.songCount) >= 5)
            .sort((a, b) => b.songCount - a.songCount);
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

  /** A shared section with its label resolved for this locale. */
  const labelled = (section) => ({ ...section, label: $t(section.labelKey) });

  const primaryItems = $derived([
    { id: 'home', label: $t('nav.home'), icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    labelled(MODE_SECTIONS[$viewMode] ?? MODE_SECTIONS.songs),
    labelled(PLAYLISTS_SECTION),
  ]);

  // The same list the phone's Browse grid tiles, already cut down to what this
  // shell and mode can answer -- see `navigation.js`.
  const libraryItems = $derived(librarySections($viewMode, platform).map(labelled));

  const tailItems = $derived(PERSONAL_SECTIONS.map(labelled));

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
