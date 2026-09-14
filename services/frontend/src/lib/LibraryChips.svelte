<script>
  import { platform } from './platform/index.js';
  import { t } from './i18n/index.js';

  /**
   * The phone's "Bibliotheek" tab is one screen: this chip row on top picks
   * which of the desktop sidebar's per-account sections shows underneath.
   * `activeView` is the source of truth (same store the bottom bar and the
   * router already share), so the active chip and the URL never disagree.
   *
   * Downloads only exists inside the shell (`platform.storage.supported`):
   * a browser tab cannot keep music, so the chip that lists what it kept is
   * absent here exactly like it is from the sidebar and the old bottom bar.
   */
  const { activeView = 'playlists', onnavigate } = $props();

  const chips = $derived([
    { id: 'playlists', label: $t('nav.playlists') },
    { id: 'artists', label: $t('nav.artists') },
    { id: 'albums', label: $t('nav.albums') },
    { id: 'starred', label: $t('nav.starred') },
    ...(platform.storage.supported ? [{ id: 'downloads', label: $t('nav.downloads') }] : []),
  ]);

  /**
   * Triggers navigation to the section a chip stands for.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<div
  class="flex gap-2 overflow-x-auto scrollbar-hide"
  role="group"
  aria-label={$t('sidebar.library')}
>
  {#each chips as chip (chip.id)}
    <button
      type="button"
      class="px-4 py-1.5 rounded-full text-sm font-medium border-none cursor-pointer whitespace-nowrap transition-colors {activeView === chip.id ? 'bg-white text-black' : 'bg-[#282828] text-white'}"
      onclick={() => navigate(chip.id)}
      aria-pressed={activeView === chip.id}
    >
      {chip.label}
    </button>
  {/each}
</div>
