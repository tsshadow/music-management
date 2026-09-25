<script>
  import { activeView, pushedHistoryEntries } from './store.js';
  import { t } from './i18n/index.js';
  import { ArrowLeft } from '@lucide/svelte';
  import MumaMark from './MumaMark.svelte';

  // The player/management toggle used to live here. Management is a normal page with
  // its own URL now, so what it needs is a way back rather than a second mode to sit
  // in -- and the browser's own back button does the same thing.
  const canLeave = $derived($activeView === 'management' || $activeView === 'settings');

  /**
   * Goes back the way the listener came.
   *
   * Falls through to the home screen when this session pushed nothing: arriving
   * straight on `/management/config` from a bookmark leaves no entry of ours behind,
   * and `history.back()` would walk out of the app.
   */
  function goBack() {
    if ($pushedHistoryEntries > 0) window.history.back();
    else activeView.set('home');
  }
</script>

<div class="px-4 pt-5 pb-2 flex flex-col gap-5">
  <div class="flex items-center gap-2 text-xl font-bold text-white px-2">
    <div class="w-8 h-8 bg-brand rounded-full flex items-center justify-center text-black">
      <MumaMark size={18} />
    </div>
    <span>MuMa</span>
  </div>

  {#if canLeave}
    <button
      class="flex items-center gap-2 py-2 px-3 rounded-md text-[13px] font-bold bg-muma-spotify-dark border border-white/5 text-muma-spotify-text hover:text-white transition-all mx-1"
      onclick={goBack}
    >
      <ArrowLeft size={14} strokeWidth={2.5} />
      {$t('sidebar.back')}
    </button>
  {/if}
</div>
