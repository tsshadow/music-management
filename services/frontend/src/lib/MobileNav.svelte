<script>
  import { t } from './i18n/index.js';
  import { phoneTabForView } from './router.js';

  /** The phone's three destinations: Home, Browse and Favorites. */
  const { activeView = 'home', onnavigate } = $props();

  const navItems = $derived([
    { id: 'home', label: $t('nav.home'), icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'browse', label: $t('nav.browse'), icon: 'M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 5L20.49 19l-5-5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z' },
    { id: 'favorites', label: $t('nav.favorites'), icon: 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z' },
  ]);

  /**
   * Triggers navigation to a specific view.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }

  /** Detail pages keep their owning bottom tab active. */
  function isActive(id) {
    return phoneTabForView(activeView) === id;
  }
</script>

<!-- Named because the app has two navigation landmarks: this bar below `md` and
     the sidebar above it. Unnamed they are indistinguishable to a screen reader
     and to a test that has to click one tab and not the other. -->
<nav
  aria-label={$t('nav.bottomBar')}
  class="flex justify-around items-center bg-black border-t border-muma-spotify-light pb-safe pt-1.5"
>
  {#each navItems as item (item.id)}
    <button
      class="flex flex-col items-center gap-1 bg-transparent border-none py-1.5 px-3 cursor-pointer transition-colors {isActive(item.id) ? 'text-white' : 'text-muma-spotify-text'}"
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
