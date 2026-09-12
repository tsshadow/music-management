<script>
  import { t } from './i18n/index.js';
  import { LIBRARY_TAB_VIEWS } from './router.js';

  /**
   * The phone's bottom bar, cut down to Spotify's three tabs: Home, Search and
   * Library. Songs/Sets is no longer a tab -- it moved to `ModeChips`, a mode
   * switch rather than a destination -- and Downloads and Management moved
   * into the Library chip row and the profile menu respectively, so nothing
   * that used to be reachable here is lost, only relocated.
   */
  const { activeView = 'home', onnavigate } = $props();

  const navItems = $derived([
    { id: 'home', label: $t('nav.home'), icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'search', label: $t('nav.search'), icon: 'M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 5L20.49 19l-5-5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z' },
    { id: 'playlists', label: $t('nav.library'), icon: 'M3 22a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H3zm13-2V4H4v16h12z' },
  ]);

  /**
   * Triggers navigation to a specific view.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }

  /**
   * Whether one bottom-bar tab should read as active. The Library tab covers
   * every view its own chip row can switch to, not only its default
   * ('playlists'), so landing on Artists or Downloads still lights it up.
   *
   * @param {string} id - The tab's own view id.
   * @returns {boolean}
   */
  function isActive(id) {
    if (id === 'playlists') return LIBRARY_TAB_VIEWS.includes(activeView);
    return activeView === id;
  }
</script>

<!-- Named because the app has two navigation landmarks: this bar below `md` and
     the sidebar above it. Unnamed they are indistinguishable to a screen reader
     and to a test that has to click one tab and not the other. -->
<nav
  aria-label={$t('nav.bottomBar')}
  class="flex justify-around items-center bg-black border-t border-[#282828] pb-safe pt-2"
>
  {#each navItems as item (item.id)}
    <button
      class="flex flex-col items-center gap-1 bg-transparent border-none py-2 px-4 cursor-pointer transition-colors {isActive(item.id) ? 'text-white' : 'text-[#b3b3b3]'}"
      onclick={() => navigate(item.id)}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
        <path d={item.icon}></path>
      </svg>
      <span class="text-[10px] font-medium">{item.label}</span>
    </button>
  {/each}
</nav>

<style>
  .pb-safe {
    padding-bottom: env(safe-area-inset-bottom, 0);
  }
</style>
