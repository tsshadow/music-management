<script>
  import { isAdmin } from './store.js';
  import { platform } from './platform/index.js';
  import { t } from './i18n/index.js';

  const { activeView = 'home', onnavigate } = $props();

  const navItems = $derived([
    { id: 'home', label: $t('nav.home'), icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'songs', label: $t('nav.songs'), icon: 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z' },
    { id: 'sets', label: $t('nav.sets'), icon: 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z' },
    { id: 'playlists', label: $t('nav.library'), icon: 'M3 22a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H3zm13-2V4H4v16h12z' },
    // Shell only. A browser tab cannot keep music, so the tab that lists what
    // it kept is absent rather than empty (criterion 13).
    ...(platform.storage.supported
      ? [{ id: 'downloads', label: $t('nav.downloads'), icon: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z' }]
      : []),
    ...($isAdmin ? [{ id: 'management', label: $t('nav.management'), icon: 'M19.14 12.94C19.18 12.63 19.2 12.32 19.2 12C19.2 11.68 19.18 11.37 19.14 11.06L21.16 9.48C21.34 9.33 21.39 9.08 21.27 8.89L19.37 5.59C19.25 5.4 19.01 5.32 18.81 5.4L16.43 6.36C15.93 5.98 15.39 5.66 14.81 5.42L14.45 2.89C14.41 2.68 14.22 2.52 14.01 2.52H10.19C9.97 2.52 9.79 2.68 9.75 2.89L9.39 5.42C8.81 5.66 8.27 5.98 7.77 6.36L5.39 5.4C5.19 5.32 4.95 5.4 4.83 5.59L2.93 8.89C2.81 9.08 2.86 9.33 3.04 9.48L5.06 11.06C5.02 11.37 5 11.68 5 12C5 12.32 5.02 12.63 5.06 12.94L3.04 14.52C2.86 14.67 2.81 14.92 2.93 15.11L4.83 18.41C4.95 18.6 5.19 18.68 5.39 18.6L7.77 17.64C8.27 18.02 8.81 18.34 9.39 18.58L9.75 21.11C9.79 21.32 9.97 21.48 10.19 21.48H14.01C14.22 21.48 14.41 21.32 14.45 21.11L14.81 18.58C15.39 18.34 15.93 18.02 16.43 17.64L18.81 18.6C19.01 18.68 19.25 18.6 19.37 18.41L21.27 15.11C21.39 14.92 21.34 14.67 21.16 14.52L19.14 12.94ZM12 15.6C10.01 15.6 8.4 13.99 8.4 12C8.4 10.01 10.01 8.4 12 8.4C13.99 8.4 15.6 10.01 15.6 12C15.6 13.99 13.99 15.6 12 15.6Z' }] : [])
  ]);

  /**
   * Triggers navigation to a specific view.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
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
      class="flex flex-col items-center gap-1 bg-transparent border-none py-2 px-4 cursor-pointer transition-colors {activeView === item.id || (item.id === 'playlists' && ['playlists', 'artists', 'albums', 'genres'].includes(activeView)) ? 'text-white' : 'text-[#b3b3b3]'}"
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
