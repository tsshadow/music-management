<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let settings = null;
  let isLoading = true;

  async function loadSettings() {
    try {
      const response = await fetch(`/rest/getScanStatus?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus && res.scanStatus.scanSettings) {
        settings = res.scanStatus.scanSettings;
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  const updatePeriods = [
    { value: 0, label: 'Never' },
    { value: 1, label: 'Daily' },
    { value: 2, label: 'Weekly' },
    { value: 3, label: 'Monthly' },
    { value: 4, label: 'Hourly' }
  ];

  const similarityEngines = [
    { value: 0, label: 'Clusters' },
    { value: 1, label: 'Features' },
    { value: 2, label: 'None' }
  ];

  onMount(loadSettings);
</script>

<section>
  <h3 class="text-2xl font-bold mb-6">Scan Settings</h3>
  
  {#if isLoading && !settings}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else if settings}
    <div class="flex flex-col gap-8">
      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg">Update Schedule</h4>
        <div class="flex flex-col gap-4">
          <div class="flex justify-between items-center">
            <div>
              <p class="font-medium text-white">Periodic Scan</p>
              <p class="text-sm text-[#b3b3b3]">How often should LMS check for library updates?</p>
            </div>
            <select 
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-spotify-green"
              value={settings.updatePeriod}
            >
              {#each updatePeriods as period (period.value)}
                <option value={period.value}>{period.label}</option>
              {/each}
            </select>
          </div>
        </div>
      </div>

      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg">Recommendation Engine</h4>
        <div class="flex justify-between items-center">
            <div>
              <p class="font-medium text-white">Similarity Engine</p>
              <p class="text-sm text-[#b3b3b3]">Mechanism used to find similar artists and tracks.</p>
            </div>
            <select 
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-spotify-green"
              value={settings.similarityEngineType}
            >
              {#each similarityEngines as engine (engine.value)}
                <option value={engine.value}>{engine.label}</option>
              {/each}
            </select>
          </div>
      </div>

      <div class="p-4 bg-blue-900/20 border border-blue-500/30 rounded-lg text-sm text-blue-200">
        <p><strong>Note:</strong> Changes are currently read-only in this interface. Use the legacy Wt UI for advanced configuration.</p>
      </div>

      <div class="flex justify-end gap-4 mt-4">
        <button class="px-6 py-2 rounded-full font-bold text-white hover:scale-105 transition-transform cursor-pointer border-none bg-transparent">Discard</button>
        <button class="bg-spotify-green text-black px-8 py-2 rounded-full font-bold hover:scale-105 transition-transform cursor-pointer border-none opacity-50 cursor-not-allowed">Save Changes</button>
      </div>
    </div>
  {:else}
    <div class="text-[#b3b3b3]">Geen instellingen gevonden.</div>
  {/if}
</section>
