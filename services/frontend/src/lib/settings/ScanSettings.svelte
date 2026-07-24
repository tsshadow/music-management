<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let settings = $state(null);
  let originalSettings = $state(null);
  let isLoading = $state(true);
  let isSaving = $state(false);
  let message = $state('');

  /**
   * Loads the scanner settings from the server.
   * Normalizes list-based settings into arrays.
   */
  async function loadSettings() {
    try {
      const response = await fetch(`/rest/getScanStatus?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus && res.scanStatus.scanSettings) {
        let loaded = JSON.parse(JSON.stringify(res.scanStatus.scanSettings));
        // Normalize arrays from Subsonic response
        ['extraTagsToScan', 'artistTagDelimiters', 'defaultTagDelimiters', 'artistsToNotSplit'].forEach(key => {
            let val = loaded[key];
            
            // Helper to recursively extract values from Subsonic objects
            const extractValue = (item) => {
                if (item === null || item === undefined) return '';
                if (typeof item !== 'object') return String(item);
                
                // Try common Subsonic singular value keys
                if (item.value !== undefined) return extractValue(item.value);
                if (item.tag !== undefined) return extractValue(item.tag);
                if (item.entry !== undefined) return extractValue(item.entry);
                
                // If it's an object with only one key, try that key
                const keys = Object.keys(item);
                if (keys.length === 1) return extractValue(item[keys[0]]);
                
                return ''; // Ignore complex/empty objects to avoid [object Object]
            };

            const normalize = (v) => {
                if (!v) return [];
                if (Array.isArray(v)) {
                    return v.map(extractValue).filter(item => item !== '');
                }
                if (typeof v === 'object') {
                    if (v.value !== undefined) {
                        const subVal = Array.isArray(v.value) ? v.value : [v.value];
                        return subVal.map(extractValue).filter(item => item !== '');
                    }
                    // Singular object
                    const extracted = extractValue(v);
                    return extracted !== '' ? [extracted] : [];
                }
                return [String(v)];
            };

            loaded[key] = normalize(val);
        });
        
        // Preserve scanning state from root scanStatus
        loaded.scanning = res.scanStatus.scanning;
        loaded.step = res.scanStatus.step;
        loaded.stepIndex = res.scanStatus.stepIndex;
        loaded.stepCount = res.scanStatus.stepCount;
        loaded.count = res.scanStatus.count;
        loaded.totalCount = res.scanStatus.totalCount;
        loaded.lastScan = res.scanStatus.lastScan;

        settings = loaded;
        if (!originalSettings) {
            originalSettings = JSON.parse(JSON.stringify(loaded));
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Saves the current settings to the server.
   * Joins array-based settings with pipes before sending.
   */
  async function saveSettings() {
    isSaving = true;
    message = '';
    try {
      let query = $authParams.toString();
      query += `&updatePeriod=${settings.updatePeriod}`;
      query += `&updateStartTime=${encodeURIComponent(settings.updateStartTime)}`;
      query += `&similarityEngineType=${settings.similarityEngineType}`;
      query += `&skipSingleReleasePlayLists=${settings.skipSingleReleasePlayLists}`;
      query += `&allowMBIDArtistMerge=${settings.allowMBIDArtistMerge}`;
      query += `&artistImageFallbackToRelease=${settings.artistImageFallbackToRelease}`;

      query += `&extraTagsToScan=${encodeURIComponent(settings.extraTagsToScan.join('|'))}`;
      query += `&artistTagDelimiters=${encodeURIComponent(settings.artistTagDelimiters.join('|'))}`;
      query += `&defaultTagDelimiters=${encodeURIComponent(settings.defaultTagDelimiters.join('|'))}`;
      query += `&artistsToNotSplit=${encodeURIComponent(settings.artistsToNotSplit.join('|'))}`;

      const response = await fetch(`/rest/updateScanSettings?${query}`);
      const data = await response.json();
      if (data['subsonic-response']?.status === 'ok') {
        message = 'Settings saved successfully!';
        originalSettings = JSON.parse(JSON.stringify(settings));
        setTimeout(() => message = '', 3000);
      }
    } catch (e) {
      console.error(e);
      message = 'Error saving settings.';
    } finally {
      isSaving = false;
    }
  }

  /**
   * Discards all unsaved changes and restores settings from original data.
   */
  function discardChanges() {
    settings = JSON.parse(JSON.stringify(originalSettings));
  }

  const updatePeriods = [
    { value: 0, label: 'Never' },
    { value: 4, label: 'Hourly' },
    { value: 1, label: 'Daily' },
    { value: 2, label: 'Weekly' },
    { value: 3, label: 'Monthly' }
  ];

  const similarityEngines = [
    { value: 0, label: 'Clusters' },
    { value: 1, label: 'Features' },
    { value: 2, label: 'None' }
  ];

  const hours = Array.from({length: 24}, (_, i) => `${i.toString().padStart(2, '0')}:00:00`);

  /**
   * Adds an empty entry to a list-based setting.
   *
   * @param {string} key - The key of the setting to modify.
   */
  function addToList(key) {
      settings[key] = [...settings[key], ''];
  }

  /**
   * Removes an entry from a list-based setting by index.
   *
   * @param {string} key - The key of the setting to modify.
   * @param {number} index - The index of the item to remove.
   */
  function removeFromList(key, index) {
      settings[key] = settings[key].filter((_, i) => i !== index);
  }

  onMount(loadSettings);

  let hasChanges = $derived(settings && originalSettings && JSON.stringify(settings) !== JSON.stringify(originalSettings));

  async function startScan(options = {}) {
    try {
      let query = $authParams.toString();
      if (options.fullScan) query += '&fullScan=true';
      if (options.forceOptimize) query += '&forceOptimize=true';
      if (options.compact) query += '&compact=true';
      
      const response = await fetch(`/rest/startScan?${query}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.scanStatus) {
        settings.scanning = res.scanStatus.scanning;
        message = 'Scan gestart!';
        setTimeout(() => message = '', 3000);
      }
    } catch (e) {
      console.error(e);
    }
  }

  // Poll for status when scanning
  onMount(() => {
    const interval = setInterval(async () => {
      if (settings?.scanning) {
        await loadSettings();
      }
    }, 2000);
    return () => clearInterval(interval);
  });
</script>

<section class="max-w-4xl pb-24">
  <div class="flex justify-between items-center mb-8">
    <h1 class="text-3xl font-bold">Scan Instellingen</h1>
    {#if message}
        <span class="text-brand font-medium animate-pulse">{message}</span>
    {/if}
  </div>

  {#if isLoading && !settings}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else if settings}
    <div class="flex flex-col gap-8">
      <!-- Status Card -->
      <div class="bg-brand/5 border border-brand/20 p-6 rounded-lg flex flex-col gap-6">
        <div class="flex justify-between items-start">
            <div>
                <h4 class="text-xl font-bold flex items-center gap-2">
                    Status: 
                    {#if settings.scanning}
                        <span class="text-brand flex items-center gap-2">
                            <div class="w-2 h-2 bg-brand rounded-full animate-ping"></div>
                            Bezig met scannen...
                        </span>
                    {:else}
                        <span class="text-[#b3b3b3]">Inactief</span>
                    {/if}
                </h4>
                {#if settings.scanning && settings.step}
                    <p class="text-sm text-[#b3b3b3] mt-2">
                        Stap: <span class="text-white font-medium">{settings.step}</span> 
                        ({settings.stepIndex}/{settings.stepCount})
                    </p>
                    {#if settings.totalCount > 0}
                        <div class="w-full bg-[#282828] h-2 rounded-full mt-4 overflow-hidden">
                            <div class="bg-brand h-full transition-all duration-500" style="width: {((settings.count / settings.totalCount) * 100) || 0}%"></div>
                        </div>
                        <p class="text-right text-[10px] text-[#b3b3b3] mt-1">{settings.count} / {settings.totalCount}</p>
                    {/if}
                {:else if settings.lastScan}
                    <p class="text-sm text-[#b3b3b3] mt-2">
                        Laatste scan voltooid op <span class="text-white">{new Date(settings.lastScan.stopTime).toLocaleString()}</span>
                        ({settings.lastScan.count} bestanden, {settings.lastScan.errors} fouten)
                    </p>
                {/if}
            </div>
            
            <div class="flex flex-col gap-2">
                <button 
                    onclick={() => startScan()}
                    disabled={settings.scanning}
                    class="bg-brand text-black font-bold py-2 px-6 rounded-full hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100 whitespace-nowrap"
                >
                    Scan Bibliotheek
                </button>
                <div class="flex gap-2">
                    <button 
                        onclick={() => startScan({fullScan: true})}
                        disabled={settings.scanning}
                        title="Volledige scan (Rebuild)"
                        class="bg-[#282828] text-white text-xs font-bold py-1 px-3 rounded-full hover:bg-[#333] transition-colors disabled:opacity-50"
                    >
                        Full Scan
                    </button>
                    <button 
                        onclick={() => startScan({compact: true})}
                        disabled={settings.scanning}
                        title="Database opschonen"
                        class="bg-[#282828] text-white text-xs font-bold py-1 px-3 rounded-full hover:bg-[#333] transition-colors disabled:opacity-50"
                    >
                        Cleanup
                    </button>
                </div>
            </div>
        </div>
      </div>

      <!-- Schedule -->
      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Scan Schedule</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="flex flex-col gap-2">
            <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Update Period</span>
            <select
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
              bind:value={settings.updatePeriod}
            >
              {#each updatePeriods as period (period.value)}
                <option value={period.value}>{period.label}</option>
              {/each}
            </select>
          </div>

          <div class="flex flex-col gap-2" class:opacity-50={settings.updatePeriod == 0 || settings.updatePeriod == 4}>
            <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Start Time</span>
            <select
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
              bind:value={settings.updateStartTime}
              disabled={settings.updatePeriod == 0 || settings.updatePeriod == 4}
            >
              {#each hours as hour (hour)}
                <option value={hour}>{hour.substring(0, 5)}</option>
              {/each}
            </select>
          </div>
        </div>
      </div>

      <!-- Recommendation -->
      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Recommendation & Metadata</h4>
        <div class="space-y-6">
            <div class="flex justify-between items-center">
                <div>
                    <p class="font-medium text-white">Similarity Engine</p>
                    <p class="text-sm text-[#b3b3b3]">Mechanism used to find similar artists and tracks.</p>
                </div>
                <select
                    class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10 w-48"
                    bind:value={settings.similarityEngineType}
                >
                    {#each similarityEngines as engine (engine.value)}
                    <option value={engine.value}>{engine.label}</option>
                    {/each}
                </select>
            </div>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-brand transition-colors">Skip Single Release Playlists</p>
                    <p class="text-sm text-[#b3b3b3]">Do not create playlists for releases with only one track.</p>
                </div>
                <input type="checkbox" bind:checked={settings.skipSingleReleasePlayLists} class="accent-brand w-5 h-5" />
            </label>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-brand transition-colors">Allow MBID Artist Merge</p>
                    <p class="text-sm text-[#b3b3b3]">Merge artists based on MusicBrainz ID.</p>
                </div>
                <input type="checkbox" bind:checked={settings.allowMBIDArtistMerge} class="accent-brand w-5 h-5" />
            </label>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-brand transition-colors">Artist Image Fallback</p>
                    <p class="text-sm text-[#b3b3b3]">Use release cover art if artist image is missing.</p>
                </div>
                <input type="checkbox" bind:checked={settings.artistImageFallbackToRelease} class="accent-brand w-5 h-5" />
            </label>
        </div>
      </div>

      <!-- Tagging -->
      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Tag Management</h4>

        <div class="space-y-8">
            <!-- Extra Tags -->
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Extra Tags to Scan</span>
                    <button onclick={() => addToList('extraTagsToScan')} class="text-xs text-brand hover:underline font-bold">ADD TAG</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.extraTagsToScan as tag, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.extraTagsToScan[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-24" />
                            <button onclick={() => removeFromList('extraTagsToScan', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Artist Delimiters -->
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Artist Tag Delimiters</span>
                    <button onclick={() => addToList('artistTagDelimiters')} class="text-xs text-brand hover:underline font-bold">ADD DELIMITER</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.artistTagDelimiters as del, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.artistTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                            <button onclick={() => removeFromList('artistTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Default Delimiters -->
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Default Tag Delimiters</span>
                    <button onclick={() => addToList('defaultTagDelimiters')} class="text-xs text-brand hover:underline font-bold">ADD DELIMITER</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.defaultTagDelimiters as del, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.defaultTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                            <button onclick={() => removeFromList('defaultTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Artists Not To Split -->
            <div>
                <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider block mb-4">Artists to NOT split (one per line)</span>
                <textarea
                    class="w-full bg-[#282828] text-white border-none rounded p-4 outline-none focus:ring-1 focus:ring-brand min-h-[120px] resize-none"
                    placeholder="e.g. AC/DC"
                    value={settings.artistsToNotSplit.join('\n')}
                    oninput={(e) => settings.artistsToNotSplit = e.target.value.split('\n').filter(s => s.trim())}
                ></textarea>
            </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="fixed bottom-8 right-8 flex gap-4 bg-[#121212] p-4 rounded-full shadow-2xl border border-[#282828]">
        <button
            onclick={discardChanges}
            disabled={!hasChanges || isSaving}
            class="px-6 py-2 rounded-full font-bold text-white hover:bg-[#282828] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
            Discard
        </button>
        <button
            onclick={saveSettings}
            disabled={!hasChanges || isSaving}
            class="bg-brand text-black px-8 py-2 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
            {#if isSaving}
                <div class="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
            {/if}
            Save Changes
        </button>
      </div>
    </div>
  {:else}
    <div class="text-[#b3b3b3]">Geen instellingen gevonden.</div>
  {/if}
</section>
