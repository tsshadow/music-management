<script>
  import { activeView, isAdmin } from './store.js';
  import { t } from './i18n/index.js';
  import { Music, Settings2 } from '@lucide/svelte';
  import MumaMark from './MumaMark.svelte';

  const { onnavigate } = $props();

  function setMode(mode) {
    if (mode === 'player') {
      onnavigate('home');
    } else {
      onnavigate('management');
    }
  }

  const isManagement = $derived($activeView === 'management' || $activeView === 'settings');
</script>

<div class="px-4 pt-5 pb-2 flex flex-col gap-5">
  <div class="flex items-center gap-2 text-xl font-bold text-white px-2">
    <div class="w-8 h-8 bg-brand rounded-full flex items-center justify-center text-black">
      <MumaMark size={18} />
    </div>
    <span>MuMa</span>
  </div>

  {#if $isAdmin}
    <div class="flex bg-[#121212] rounded-lg p-1 border border-white/5 shadow-inner mx-1">
      <button 
        class="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-[13px] font-bold transition-all { !isManagement ? 'bg-[#282828] text-white shadow-md scale-[1.02]' : 'text-[#b3b3b3] hover:text-white' }"
        onclick={() => setMode('player')}
      >
        <Music size={14} strokeWidth={2.5} />
        {$t('nav.player')}
      </button>
      <button 
        class="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-[13px] font-bold transition-all { isManagement ? 'bg-[#282828] text-white shadow-md scale-[1.02]' : 'text-[#b3b3b3] hover:text-white' }"
        onclick={() => setMode('management')}
      >
        <Settings2 size={14} strokeWidth={2.5} />
        {$t('nav.management')}
      </button>
    </div>
  {:else if $activeView === 'settings'}
    <button 
      class="flex items-center justify-center gap-2 py-2 px-3 rounded-md text-[13px] font-bold bg-[#121212] border border-white/5 text-[#b3b3b3] hover:text-white transition-all mx-1"
      onclick={() => setMode('player')}
    >
      <Music size={14} strokeWidth={2.5} />
      {$t('sidebar.backToPlayer')}
    </button>
  {/if}
</div>
