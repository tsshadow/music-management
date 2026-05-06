<script>
  import { onMount, onDestroy } from 'svelte';
  import { authParams } from '../store.js';

  let status = null;
  let isLoading = true;
  let interval;

  async function loadStatus() {
    try {
      const response = await fetch(`/rest/getScanStatus?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus) {
        status = res.scanStatus;
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  async function startScan() {
    try {
      const response = await fetch(`/rest/startScan?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus) {
        status = res.scanStatus;
      }
    } catch (e) {
      console.error(e);
    }
  }

  onMount(() => {
    loadStatus();
    interval = setInterval(loadStatus, 2000);
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
  });
</script>

<section>
  <h3 class="text-2xl font-bold mb-6">Scanner Status</h3>
  
  {#if isLoading && !status}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else if status}
    <div class="bg-[#181818] rounded-lg p-10 flex flex-col items-center justify-center gap-6">
      {#if status.scanning}
        <div class="w-20 h-20 rounded-full border-4 border-spotify-green border-t-transparent animate-spin"></div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">Scanning...</p>
          {#if status.count}
            <p class="text-[#b3b3b3] mt-2">Processed {status.count} elements</p>
          {:else}
            <p class="text-[#b3b3b3] mt-2">Initializing...</p>
          {/if}
        </div>
        <div class="w-full max-w-md bg-[#282828] h-3 rounded-full overflow-hidden mt-4">
            <div class="bg-spotify-green h-full animate-pulse transition-all duration-500" style="width: 100%"></div>
        </div>
      {:else}
        <div class="w-20 h-20 rounded-full bg-[#282828] flex items-center justify-center">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="#1db954">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"></path>
            </svg>
        </div>
        <div class="text-center">
            <p class="text-2xl font-bold text-white">Scanner Idle</p>
            <p class="text-[#b3b3b3] mt-2">The library is up to date.</p>
        </div>
        <button 
            on:click={startScan}
            class="mt-4 bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 transition-transform cursor-pointer border-none"
        >
            Start Scan
        </button>
      {/if}
    </div>
  {/if}

  <div class="mt-8 bg-[#181818] p-6 rounded-lg">
    <h4 class="font-bold mb-4">Scanner Statistics</h4>
    <div class="grid grid-cols-2 gap-4">
        <div class="bg-[#282828] p-4 rounded-md">
            <p class="text-xs text-[#b3b3b3] uppercase font-bold">Last Run</p>
            <p class="text-lg font-medium text-white">Yesterday, 22:45</p>
        </div>
        <div class="bg-[#282828] p-4 rounded-md">
            <p class="text-xs text-[#b3b3b3] uppercase font-bold">Total Items</p>
            <p class="text-lg font-medium text-white">Calculating...</p>
        </div>
    </div>
  </div>
</section>
