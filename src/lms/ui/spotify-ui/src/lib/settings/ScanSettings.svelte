<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let settings = null;
  let originalSettings = null;
  let isLoading = true;
  let isSaving = false;
  let message = '';

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
        settings = JSON.parse(JSON.stringify(res.scanStatus.scanSettings));
        // Normalize arrays from Subsonic response
        ['extraTagsToScan', 'artistTagDelimiters', 'defaultTagDelimiters', 'artistsToNotSplit'].forEach(key => {
            if (settings[key] && settings[key].value) {
                settings[key] = Array.isArray(settings[key].value) ? settings[key].value : [settings[key].value];
            } else {
                settings[key] = [];
            }
        });
        originalSettings = JSON.parse(JSON.stringify(settings));
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
      if (response.ok) {
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

  $: hasChanges = JSON.stringify(settings) !== JSON.stringify(originalSettings);
</script>

<section class="max-w-4xl pb-20">
  <div class="flex justify-between items-center mb-8">
    <h3 class="text-2xl font-bold">Scan Settings</h3>
    {#if message}
        <span class="text-spotify-green font-medium animate-pulse">{message}</span>
    {/if}
  </div>
  
  {#if isLoading && !settings}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else if settings}
    <div class="flex flex-col gap-8">
      <!-- Schedule -->
      <div class="bg-[#181818] p-6 rounded-lg">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Scan Schedule</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="flex flex-col gap-2">
            <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Update Period</span>
            <select 
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-spotify-green h-10"
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
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-spotify-green h-10"
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
                    class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-spotify-green h-10 w-48"
                    bind:value={settings.similarityEngineType}
                >
                    {#each similarityEngines as engine (engine.value)}
                    <option value={engine.value}>{engine.label}</option>
                    {/each}
                </select>
            </div>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-spotify-green transition-colors">Skip Single Release Playlists</p>
                    <p class="text-sm text-[#b3b3b3]">Do not create playlists for releases with only one track.</p>
                </div>
                <input type="checkbox" bind:checked={settings.skipSingleReleasePlayLists} class="accent-spotify-green w-5 h-5" />
            </label>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-spotify-green transition-colors">Allow MBID Artist Merge</p>
                    <p class="text-sm text-[#b3b3b3]">Merge artists based on MusicBrainz ID.</p>
                </div>
                <input type="checkbox" bind:checked={settings.allowMBIDArtistMerge} class="accent-spotify-green w-5 h-5" />
            </label>

            <label class="flex justify-between items-center cursor-pointer group">
                <div>
                    <p class="font-medium text-white group-hover:text-spotify-green transition-colors">Artist Image Fallback</p>
                    <p class="text-sm text-[#b3b3b3]">Use release cover art if artist image is missing.</p>
                </div>
                <input type="checkbox" bind:checked={settings.artistImageFallbackToRelease} class="accent-spotify-green w-5 h-5" />
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
                    <button on:click={() => addToList('extraTagsToScan')} class="text-xs text-spotify-green hover:underline font-bold">ADD TAG</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.extraTagsToScan as _, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.extraTagsToScan[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-24" />
                            <button on:click={() => removeFromList('extraTagsToScan', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Artist Delimiters -->
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Artist Tag Delimiters</span>
                    <button on:click={() => addToList('artistTagDelimiters')} class="text-xs text-spotify-green hover:underline font-bold">ADD DELIMITER</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.artistTagDelimiters as _, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.artistTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                            <button on:click={() => removeFromList('artistTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Default Delimiters -->
            <div>
                <div class="flex justify-between items-center mb-4">
                    <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Default Tag Delimiters</span>
                    <button on:click={() => addToList('defaultTagDelimiters')} class="text-xs text-spotify-green hover:underline font-bold">ADD DELIMITER</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each settings.defaultTagDelimiters as _, i (i)}
                        <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                            <input type="text" bind:value={settings.defaultTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                            <button on:click={() => removeFromList('defaultTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white">×</button>
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Artists Not To Split -->
            <div>
                <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider block mb-4">Artists to NOT split (one per line)</span>
                <textarea 
                    class="w-full bg-[#282828] text-white border-none rounded p-4 outline-none focus:ring-1 focus:ring-spotify-green min-h-[120px] resize-none"
                    placeholder="e.g. AC/DC"
                    value={settings.artistsToNotSplit.join('\n')}
                    on:input={(e) => settings.artistsToNotSplit = e.target.value.split('\n').filter(s => s.trim())}
                ></textarea>
            </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="fixed bottom-8 right-8 flex gap-4 bg-[#121212] p-4 rounded-full shadow-2xl border border-[#282828]">
        <button 
            on:click={discardChanges}
            disabled={!hasChanges || isSaving}
            class="px-6 py-2 rounded-full font-bold text-white hover:bg-[#282828] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
            Discard
        </button>
        <button 
            on:click={saveSettings}
            disabled={!hasChanges || isSaving}
            class="bg-spotify-green text-black px-8 py-2 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
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
