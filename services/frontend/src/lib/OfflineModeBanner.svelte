<script>
  /**
   * The strip above every page while the app runs in offline mode by the listener's choice
   * ("Offline verder" on the start-up check, docs/designs/app-start-reachability/, styleguide
   * "Offline mode banner").
   *
   * It is what marks everything below it as the device's own copy rather than the server's: the
   * lists are the downloaded library, and the queue holds only downloaded tracks -- how many were
   * left out is said here. "Opnieuw verbinden" asks the server at once instead of waiting for the
   * next background attempt; when the server answers, offline mode ends by itself and this strip
   * goes away.
   */
  import { t } from './i18n/index.js';
  import { offlineMode, reconnectNow } from './offlineMode.js';
  import Throbber from './loading/Throbber.svelte';

  let reconnecting = $state(false);

  /** One attempt now; the strip stays until the background watcher confirms the server. */
  async function reconnect() {
    if (reconnecting) return;
    reconnecting = true;
    try {
      await reconnectNow();
    } finally {
      reconnecting = false;
    }
  }
</script>

{#if $offlineMode.active}
  <div
    class="mb-4 flex items-center gap-3 rounded-md bg-muma-spotify-light px-4 py-3 text-sm"
    role="status"
    data-testid="offline-mode-banner"
  >
    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" class="shrink-0 text-muma-spotify-text" aria-hidden="true">
      <path d="M2.28 3L1 4.27l2.47 2.47C2.35 7.4 1.3 8.24.36 9.2l2.12 2.12a13.9 13.9 0 0 1 3.2-2.24l2.2 2.2a10.9 10.9 0 0 0-3.28 2.16l2.12 2.12a7.9 7.9 0 0 1 3.4-1.99l2.4 2.4A4.9 4.9 0 0 0 9.9 17.1L12 19.2l1.86-1.86L19.73 23 21 21.72 2.28 3zm18.2 8.32l2.12-2.12C20.26 6.9 16.76 5.5 13 5.5c-.7 0-1.4.05-2.08.15l2.5 2.5c2.6.27 4.98 1.4 7.06 3.17z"></path>
    </svg>
    <div class="flex-1 min-w-0">
      <p class="m-0 font-bold text-white">{$t('offlineMode.banner')}</p>
      {#if $offlineMode.skipped > 0}
        <p class="m-0 text-muma-spotify-text" data-testid="offline-mode-skipped">
          {$t('offlineMode.skipped', { count: $offlineMode.skipped })}
        </p>
      {/if}
    </div>
    <button
      class="shrink-0 min-h-12 bg-transparent border border-muma-spotify-muted text-white px-4 py-2 rounded-full font-bold cursor-pointer transition-colors hover:border-white disabled:opacity-50"
      data-testid="offline-mode-reconnect"
      disabled={reconnecting}
      onclick={reconnect}
    >
      {#if reconnecting}<Throbber />{:else}{$t('offlineMode.reconnect')}{/if}
    </button>
  </div>
{/if}
