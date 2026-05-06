<script>
  import { onMount, onDestroy } from 'svelte';
  import { authParams } from '../store.js';

  let status = null;
  let isLoading = true;
  let interval;

  let fullScan = false;
  let forceOptimize = false;
  let compact = false;

  async function loadStatus() {
    try {
      const response = await fetch(`/rest/getScanStatus?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus) {
        status = res.scanStatus;
      }
    } catch (_) {
      // ignore
    } finally {
      isLoading = false;
    }
  }

  async function startScan() {
    try {
      let query = $authParams.toString();
      if (fullScan) query += '&fullScan=true';
      if (forceOptimize) query += '&forceOptimize=true';
      if (compact) query += '&compact=true';

      const response = await fetch(`/rest/startScan?${query}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus) {
        status = res.scanStatus;
      }
    } catch (_) {
      // ignore
    }
  }

  function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    try {
      return new Date(isoString).toLocaleString();
    } catch (_) {
      return isoString;
    }
  }

  function getStepLabel(step) {
    const labels = {
      'AssociateArtistImages': 'Associating artist images',
      'AssociateExternalLyrics': 'Associating external lyrics',
      'AssociatePlayListTracks': 'Associating playlist tracks',
      'AssociateReleaseImages': 'Associating release images',
      'AssociateTrackImages': 'Associating track images',
      'CheckForDuplicatedFiles': 'Checking for duplicate files',
      'CheckForRemovedFiles': 'Checking for removed files',
      'Compact': 'Compacting database',
      'ComputeClusterStats': 'Computing cluster statistics',
      'Optimize': 'Optimizing database',
      'ReconciliateArtists': 'Reconciling artists',
      'RemoveOrphanedDbEntries': 'Removing orphaned entries',
      'ReloadSimilarityEngine': 'Reloading similarity engine',
      'ScanFiles': 'Scanning files',
      'UpdateLibraryFields': 'Updating library fields'
    };
    return labels[step] || step || 'Processing...';
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
  <div class="flex justify-between items-end mb-6">
    <h3 class="text-2xl font-bold">Scanner Status</h3>
    {#if status?.lastScan}
      <p class="text-sm text-[#b3b3b3]">Last updated: {formatDateTime(status.lastScan.stopTime)}</p>
    {/if}
  </div>
  
  {#if isLoading && !status}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else if status}
    <div class="bg-[#181818] rounded-lg p-10 flex flex-col items-center justify-center gap-6">
      {#if status.scanning}
        <div class="relative w-24 h-24">
          <div class="absolute inset-0 rounded-full border-4 border-[#282828]"></div>
          <div class="absolute inset-0 rounded-full border-4 border-spotify-green border-t-transparent animate-spin"></div>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">{getStepLabel(status.step)}</p>
          <p class="text-[#b3b3b3] mt-2">
            Step {status.stepIndex + 1} of {status.stepCount}
            {#if status.count > 0}
              • {status.count} elements processed
            {/if}
          </p>
        </div>
        
        <div class="w-full max-w-md">
            <div class="flex justify-between text-xs text-[#b3b3b3] mb-2 uppercase font-bold tracking-wider">
                <span>Progress</span>
                <span>{Math.round(((status.stepIndex) / status.stepCount) * 100)}%</span>
            </div>
            <div class="bg-[#282828] h-3 rounded-full overflow-hidden">
                <div 
                    class="bg-spotify-green h-full transition-all duration-500 ease-out" 
                    style="width: {((status.stepIndex + 1) / status.stepCount) * 100}%"
                ></div>
            </div>
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

        <div class="flex flex-col gap-4 w-full max-w-xs mt-4">
            <div class="flex flex-col gap-2">
                <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer group">
                    <input type="checkbox" bind:checked={fullScan} class="accent-spotify-green w-4 h-4" />
                    Full Scan
                </label>
                <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer group">
                    <input type="checkbox" bind:checked={forceOptimize} class="accent-spotify-green w-4 h-4" />
                    Force Optimize
                </label>
                <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer group">
                    <input type="checkbox" bind:checked={compact} class="accent-spotify-green w-4 h-4" />
                    Compact Database
                </label>
            </div>

            <button 
                on:click={startScan}
                class="bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 active:scale-95 transition-all cursor-pointer border-none shadow-lg"
            >
                Start Scan
            </button>
        </div>
      {/if}
    </div>
  {/if}

  <div class="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-4 text-lg">Last Scan Statistics</h4>
        {#if status?.lastScan}
            <div class="space-y-4">
                <div class="flex justify-between items-center py-2 border-b border-[#282828]">
                    <span class="text-[#b3b3b3]">Files processed</span>
                    <span class="text-white font-medium">{status.lastScan.count}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-[#282828]">
                    <span class="text-[#b3b3b3]">Errors encountered</span>
                    <span class={status.lastScan.errors > 0 ? "text-red-500 font-bold" : "text-white"}>
                        {status.lastScan.errors}
                    </span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-[#282828]">
                    <span class="text-[#b3b3b3]">Duration</span>
                    <span class="text-white font-medium">
                        {status.lastScan.startTime && status.lastScan.stopTime ? 
                            Math.round((new Date(status.lastScan.stopTime) - new Date(status.lastScan.startTime)) / 1000) + 's' 
                            : 'N/A'}
                    </span>
                </div>
            </div>
        {:else}
            <p class="text-[#b3b3b3] italic text-sm">No recent scan data available.</p>
        {/if}
    </div>

    <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-4 text-lg">Next Scheduled Scan</h4>
        <div class="flex flex-col items-center justify-center h-full pb-6">
            {#if status?.scanSettings?.updatePeriod === 0}
                <div class="text-[#b3b3b3] text-center">
                    <p class="mb-2">Automatic scanning is disabled.</p>
                    <p class="text-xs uppercase font-bold tracking-widest">Never</p>
                </div>
            {:else}
                <div class="text-center">
                    <p class="text-3xl font-bold text-white mb-2">
                        {status?.scanSettings?.updateStartTime || '--:--'}
                    </p>
                    <p class="text-[#b3b3b3] text-sm uppercase font-bold tracking-widest">
                        {['Never', 'Daily', 'Weekly', 'Monthly', 'Hourly'][status?.scanSettings?.updatePeriod || 0]}
                    </p>
                </div>
            {/if}
        </div>
    </div>
  </div>
</section>
