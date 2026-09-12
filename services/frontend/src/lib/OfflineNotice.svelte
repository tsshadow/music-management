<script>
  /**
   * What a screen says when there is no connection.
   *
   * Two messages, not one, because they ask for different things from the
   * reader. `empty` is a list that could have had downloaded content and has
   * none -- go and download something. `unavailable` is a screen that cannot
   * exist without a server whatever you download, because its data is not in
   * the offline library at all (playlists are m3u files with no server id; the
   * feeds, memories and the listening stats are muma endpoints). Showing a
   * spinner there would be a lie that never resolves.
   */
  import { t } from './i18n/index.js';

  const { kind = 'unavailable', onnavigate = null } = $props();
</script>

<div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5" data-testid="offline-notice">
  <svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor" class="mb-4 opacity-20 inline-block" aria-hidden="true">
    <path d="M2.28 3L1 4.27l2.47 2.47C2.35 7.4 1.3 8.24.36 9.2l2.12 2.12a13.9 13.9 0 0 1 3.2-2.24l2.2 2.2a10.9 10.9 0 0 0-3.28 2.16l2.12 2.12a7.9 7.9 0 0 1 3.4-1.99l2.4 2.4A4.9 4.9 0 0 0 9.9 17.1L12 19.2l1.86-1.86L19.73 23 21 21.72 2.28 3zm18.2 8.32l2.12-2.12C20.26 6.9 16.76 5.5 13 5.5c-.7 0-1.4.05-2.08.15l2.5 2.5c2.6.27 4.98 1.4 7.06 3.17z"></path>
  </svg>
  <p class="text-xl font-bold mb-2 text-white">{$t(`offline.${kind}Title`)}</p>
  <p class="text-sm opacity-60">{$t(`offline.${kind}Help`)}</p>
  {#if kind === 'empty' && onnavigate}
    <button
      class="mt-4 bg-transparent border border-[#727272] text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
      onclick={() => onnavigate('downloads')}
    >{$t('nav.downloads')}</button>
  {/if}
</div>
