<script>
  import { onMount, onDestroy } from 'svelte';
  import { authParams } from '../../store.js';

  const { onMessage, onError } = $props();

  let settings = $state(null);
  let originalSettings = $state(null);
  let status = $state(null);
  let isLoading = $state(true);
  let isSaving = $state(false);

  let fullScan = $state(false);
  let forceOptimize = $state(false);
  let compact = $state(false);

  let interval;

  const updatePeriods = [
    { value: 0, label: 'Nooit' },
    { value: 4, label: 'Elk uur' },
    { value: 1, label: 'Dagelijks' },
    { value: 2, label: 'Wekelijks' },
    { value: 3, label: 'Maandelijks' }
  ];

  const similarityEngines = [
    { value: 0, label: 'Clusters' },
    { value: 1, label: 'Features' },
    { value: 2, label: 'Geen' }
  ];

  const hours = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}:00:00`);

  const stepLabels = {
    AssociateArtistImages: 'Artiestafbeeldingen koppelen',
    AssociateExternalLyrics: 'Externe songteksten koppelen',
    AssociatePlayListTracks: 'Afspeellijstnummers koppelen',
    AssociateReleaseImages: 'Albumafbeeldingen koppelen',
    AssociateTrackImages: 'Nummerafbeeldingen koppelen',
    CheckForDuplicatedFiles: 'Dubbele bestanden zoeken',
    CheckForRemovedFiles: 'Verwijderde bestanden zoeken',
    Compact: 'Database compacteren',
    ComputeClusterStats: 'Clusterstatistieken berekenen',
    Optimize: 'Database optimaliseren',
    ReconciliateArtists: 'Artiesten samenvoegen',
    RemoveOrphanedDbEntries: 'Wees-entries opruimen',
    ReloadSimilarityEngine: 'Similarity engine herladen',
    ScanFiles: 'Bestanden scannen',
    UpdateLibraryFields: 'Bibliotheekvelden bijwerken'
  };

  /**
   * Extracts a plain list of strings out of a Subsonic array node, which can
   * come back as a bare value, an object wrapper or an array of either.
   *
   * @param {unknown} value
   * @returns {string[]}
   */
  function normalizeList(value) {
    const extract = (item) => {
      if (item === null || item === undefined) return '';
      if (typeof item !== 'object') return String(item);
      if (item.value !== undefined) return extract(item.value);
      const keys = Object.keys(item);
      if (keys.length === 1) return extract(item[keys[0]]);
      return '';
    };

    if (!value) return [];
    if (Array.isArray(value)) return value.map(extract).filter((v) => v !== '');
    if (typeof value === 'object') {
      if (value.value !== undefined) {
        const inner = Array.isArray(value.value) ? value.value : [value.value];
        return inner.map(extract).filter((v) => v !== '');
      }
      const single = extract(value);
      return single !== '' ? [single] : [];
    }
    return [String(value)];
  }

  /**
   * Loads scanner status and, for admins, the scan settings. Settings are only
   * adopted while there are no unsaved edits, so polling can never overwrite
   * what is being typed.
   */
  async function loadStatus() {
    if (!$authParams) {
      isLoading = false;
      return;
    }
    try {
      const response = await fetch(`/rest/getScanStatus?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (!res?.scanStatus) return;

      status = res.scanStatus;

      if (res.scanStatus.scanSettings && !hasChanges) {
        const loaded = JSON.parse(JSON.stringify(res.scanStatus.scanSettings));
        for (const key of ['extraTagsToScan', 'artistTagDelimiters', 'defaultTagDelimiters', 'artistsToNotSplit']) {
          loaded[key] = normalizeList(loaded[key]);
        }
        settings = loaded;
        originalSettings = JSON.parse(JSON.stringify(loaded));
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  async function saveSettings() {
    isSaving = true;
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
        originalSettings = JSON.parse(JSON.stringify(settings));
        onMessage('Scaninstellingen opgeslagen.');
      } else {
        onError(data['subsonic-response']?.error?.message || 'Kon scaninstellingen niet opslaan.');
      }
    } catch (e) {
      console.error(e);
      onError('Netwerkfout bij opslaan van scaninstellingen.');
    } finally {
      isSaving = false;
    }
  }

  function discardChanges() {
    settings = JSON.parse(JSON.stringify(originalSettings));
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
      if (res?.scanStatus) {
        status = res.scanStatus;
        onMessage('Scan gestart.');
      } else {
        onError(res?.error?.message || 'Kon scan niet starten.');
      }
    } catch (e) {
      console.error(e);
      onError('Netwerkfout bij starten van de scan.');
    }
  }

  function addToList(key) {
    settings[key] = [...settings[key], ''];
  }

  function removeFromList(key, index) {
    settings[key] = settings[key].filter((_, i) => i !== index);
  }

  function formatDateTime(isoString) {
    if (!isoString) return 'N/B';
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  function getStepLabel(step) {
    return stepLabels[step] || step || 'Bezig...';
  }

  function getScanDuration() {
    if (!status?.lastScan?.startTime || !status?.lastScan?.stopTime) return 'N/B';
    const ms = new Date(status.lastScan.stopTime).getTime() - new Date(status.lastScan.startTime).getTime();
    return `${Math.round(ms / 1000)}s`;
  }

  let hasChanges = $derived(
    settings && originalSettings && JSON.stringify(settings) !== JSON.stringify(originalSettings)
  );

  onMount(() => {
    loadStatus();
    // Poll fast enough to follow a running scan, but only while one is running.
    interval = setInterval(() => {
      if (status?.scanning) loadStatus();
    }, 2000);
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
  });
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h2 class="text-4xl font-extrabold mb-2">🔍 Scanner</h2>
      <p class="text-[#b3b3b3]">Status, planning en tagverwerking van de bibliotheekscan.</p>
    </div>
    {#if status?.lastScan}
      <p class="text-sm text-[#b3b3b3]">Laatste scan: {formatDateTime(status.lastScan.stopTime)}</p>
    {/if}
  </header>

  {#if !$authParams}
    <div class="bg-[#181818] p-8 rounded-xl border border-white/5 text-center">
      <h3 class="text-xl font-bold mb-2">Geen serververbinding</h3>
      <p class="text-[#b3b3b3]">
        De scanner wordt rechtstreeks door de muziekserver aangestuurd en vereist daarom een login met
        server-inloggegevens. Log in op de playerpagina met je gebruikersnaam en wachtwoord om de scanner te beheren.
      </p>
    </div>
  {:else if isLoading && !status}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else}
    <!-- Status -->
    <div class="bg-[#181818] rounded-xl p-10 flex flex-col items-center justify-center gap-6 border border-white/5">
      {#if status?.scanning}
        <div class="relative w-24 h-24">
          <div class="absolute inset-0 rounded-full border-4 border-[#282828]"></div>
          <div class="absolute inset-0 rounded-full border-4 border-brand border-t-transparent animate-spin"></div>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">{getStepLabel(status.step)}</p>
          <p class="text-[#b3b3b3] mt-2">
            Stap {status.stepIndex + 1} van {status.stepCount}
            {#if status.count > 0}
              • {status.count} verwerkt
            {/if}
          </p>
        </div>
        <div class="w-full max-w-md">
          <div class="flex justify-between text-xs text-[#b3b3b3] mb-2 uppercase font-bold tracking-wider">
            <span>Voortgang</span>
            <span>{Math.round((status.stepIndex / status.stepCount) * 100)}%</span>
          </div>
          <div class="bg-[#282828] h-3 rounded-full overflow-hidden">
            <div
              class="bg-brand h-full transition-all duration-500 ease-out"
              style="width: {((status.stepIndex + 1) / status.stepCount) * 100}%"
            ></div>
          </div>
        </div>
      {:else}
        <div class="w-20 h-20 rounded-full bg-[#282828] flex items-center justify-center">
          <svg viewBox="0 0 24 24" width="40" height="40" fill="#1db954" aria-hidden="true">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"></path>
          </svg>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">Scanner inactief</p>
          <p class="text-[#b3b3b3] mt-2">De bibliotheek is bijgewerkt.</p>
        </div>

        <div class="flex flex-col gap-4 w-full max-w-xs mt-4">
          <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={fullScan} class="accent-brand w-4 h-4" />
            Volledige scan
          </label>
          <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={forceOptimize} class="accent-brand w-4 h-4" />
            Optimalisatie forceren
          </label>
          <label class="flex items-center gap-3 text-sm text-[#b3b3b3] hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={compact} class="accent-brand w-4 h-4" />
            Database compacteren
          </label>

          <button
            onclick={startScan}
            class="bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 active:scale-95 transition-all border-none shadow-lg"
          >
            Scan starten
          </button>
        </div>
      {/if}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-[#181818] p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-4 text-lg">Laatste scan</h4>
        {#if status?.lastScan}
          <div class="space-y-4">
            <div class="flex justify-between items-center py-2 border-b border-[#282828]">
              <span class="text-[#b3b3b3]">Bestanden verwerkt</span>
              <span class="text-white font-medium">{status.lastScan.count}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-[#282828]">
              <span class="text-[#b3b3b3]">Fouten</span>
              <span class={status.lastScan.errors > 0 ? 'text-red-500 font-bold' : 'text-white'}>
                {status.lastScan.errors}
              </span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-[#282828]">
              <span class="text-[#b3b3b3]">Duur</span>
              <span class="text-white font-medium">{getScanDuration()}</span>
            </div>
          </div>
        {:else}
          <p class="text-[#b3b3b3] italic text-sm">Nog geen scangegevens beschikbaar.</p>
        {/if}
      </div>

      <div class="bg-[#181818] p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-4 text-lg">Volgende geplande scan</h4>
        <div class="flex flex-col items-center justify-center h-full pb-6">
          {#if !settings || settings.updatePeriod === 0}
            <div class="text-[#b3b3b3] text-center">
              <p class="mb-2">Automatisch scannen staat uit.</p>
              <p class="text-xs uppercase font-bold tracking-widest">Nooit</p>
            </div>
          {:else}
            <div class="text-center">
              <p class="text-3xl font-bold text-white mb-2">{settings.updateStartTime || '--:--'}</p>
              <p class="text-[#b3b3b3] text-sm uppercase font-bold tracking-widest">
                {updatePeriods.find((p) => p.value === settings.updatePeriod)?.label || ''}
              </p>
            </div>
          {/if}
        </div>
      </div>
    </div>

    {#if settings}
      <!-- Schedule -->
      <div class="bg-[#181818] p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Planning</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="flex flex-col gap-2">
            <label for="scan-period" class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Frequentie</label>
            <select
              id="scan-period"
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
              bind:value={settings.updatePeriod}
            >
              {#each updatePeriods as period (period.value)}
                <option value={period.value}>{period.label}</option>
              {/each}
            </select>
          </div>

          <div class="flex flex-col gap-2" class:opacity-50={settings.updatePeriod === 0 || settings.updatePeriod === 4}>
            <label for="scan-start" class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Starttijd</label>
            <select
              id="scan-start"
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
              bind:value={settings.updateStartTime}
              disabled={settings.updatePeriod === 0 || settings.updatePeriod === 4}
            >
              {#each hours as hour (hour)}
                <option value={hour}>{hour.substring(0, 5)}</option>
              {/each}
            </select>
          </div>
        </div>
      </div>

      <!-- Metadata -->
      <div class="bg-[#181818] p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Aanbevelingen & metadata</h4>
        <div class="space-y-6">
          <div class="flex justify-between items-center">
            <div>
              <p class="font-medium text-white">Similarity engine</p>
              <p class="text-sm text-[#b3b3b3]">Manier waarop vergelijkbare artiesten en nummers worden gevonden.</p>
            </div>
            <select
              aria-label="Similarity engine"
              class="bg-[#282828] text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10 w-48"
              bind:value={settings.similarityEngineType}
            >
              {#each similarityEngines as engine (engine.value)}
                <option value={engine.value}>{engine.label}</option>
              {/each}
            </select>
          </div>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">Enkel-nummer afspeellijsten overslaan</p>
              <p class="text-sm text-[#b3b3b3]">Maak geen afspeellijst voor releases met één nummer.</p>
            </div>
            <input type="checkbox" aria-label="Enkel-nummer afspeellijsten overslaan" bind:checked={settings.skipSingleReleasePlayLists} class="accent-brand w-5 h-5" />
          </label>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">Artiesten samenvoegen op MBID</p>
              <p class="text-sm text-[#b3b3b3]">Voeg artiesten samen op basis van hun MusicBrainz ID.</p>
            </div>
            <input type="checkbox" aria-label="Artiesten samenvoegen op MBID" bind:checked={settings.allowMBIDArtistMerge} class="accent-brand w-5 h-5" />
          </label>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">Terugval op albumhoes</p>
              <p class="text-sm text-[#b3b3b3]">Gebruik de albumhoes als er geen artiestafbeelding is.</p>
            </div>
            <input type="checkbox" aria-label="Terugval op albumhoes" bind:checked={settings.artistImageFallbackToRelease} class="accent-brand w-5 h-5" />
          </label>
        </div>
      </div>

      <!-- Tags -->
      <div class="bg-[#181818] p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-[#282828] pb-2">Tagverwerking</h4>

        <div class="space-y-8">
          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Extra tags om te scannen</span>
              <button onclick={() => addToList('extraTagsToScan')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                TAG TOEVOEGEN
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.extraTagsToScan as _tag, i (i)}
                <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                  <input aria-label="Extra tag" type="text" bind:value={settings.extraTagsToScan[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-24" />
                  <button onclick={() => removeFromList('extraTagsToScan', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Artiest-scheidingstekens</span>
              <button onclick={() => addToList('artistTagDelimiters')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                TOEVOEGEN
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.artistTagDelimiters as _del, i (i)}
                <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                  <input aria-label="Artiest-scheidingsteken" type="text" bind:value={settings.artistTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                  <button onclick={() => removeFromList('artistTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider">Standaard scheidingstekens</span>
              <button onclick={() => addToList('defaultTagDelimiters')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                TOEVOEGEN
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.defaultTagDelimiters as _del, i (i)}
                <div class="flex items-center bg-[#282828] rounded overflow-hidden">
                  <input aria-label="Standaard scheidingsteken" type="text" bind:value={settings.defaultTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                  <button onclick={() => removeFromList('defaultTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <label for="artists-no-split" class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider block mb-4">
              Artiesten die niet gesplitst mogen worden (één per regel)
            </label>
            <textarea
              id="artists-no-split"
              class="w-full bg-[#282828] text-white border-none rounded p-4 outline-none focus:ring-1 focus:ring-brand min-h-[120px] resize-none"
              placeholder="bijv. AC/DC"
              value={settings.artistsToNotSplit.join('\n')}
              oninput={(e) => (settings.artistsToNotSplit = e.target.value.split('\n').filter((s) => s.trim()))}
            ></textarea>
          </div>
        </div>
      </div>

      <div class="flex justify-end gap-4">
        <button
          onclick={discardChanges}
          disabled={!hasChanges || isSaving}
          class="px-6 py-2 rounded-full font-bold text-white bg-transparent border border-white/10 hover:bg-[#282828] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Wijzigingen verwerpen
        </button>
        <button
          onclick={saveSettings}
          disabled={!hasChanges || isSaving}
          class="bg-brand text-black px-8 py-2 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 border-none"
        >
          {#if isSaving}
            <div class="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
          {/if}
          Opslaan
        </button>
      </div>
    {/if}
  {/if}
</section>
