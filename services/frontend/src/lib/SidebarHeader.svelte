<script>
  import { activeView, isAdmin } from './store.js';
  import { t } from './i18n/index.js';
  import { Music, Settings2 } from '@lucide/svelte';

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
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
          <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.491 17.306c-.215.353-.675.465-1.028.25-2.864-1.75-6.467-2.146-10.713-1.176-.403.092-.806-.16-.898-.563-.092-.403.16-.806.563-.898 4.647-1.064 8.623-.615 11.826 1.34.353.215.465.675.25 1.028zm1.464-3.264c-.272.441-.848.583-1.289.311-3.279-2.015-8.279-2.599-12.158-1.421-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.433-1.345 9.947-.693 13.7 1.613.441.272.583.848.311 1.289zm.126-3.407C15.222 8.356 8.85 8.144 5.122 9.276c-.595.181-1.229-.153-1.409-.748s.153-1.229.748-1.409c4.275-1.299 11.319-1.054 15.767 1.587.535.318.708 1.009.39 1.544-.318.535-1.009.708-1.544.39z"/>
      </svg>
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
