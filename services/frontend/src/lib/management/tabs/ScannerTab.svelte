<script>
  import { t, formatDateTime as formatLocaleDateTime } from '../../i18n/index.js';
  import { onMount, onDestroy } from 'svelte';
  import { authParams, restUrl } from '../../store.js';

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
    { value: 0, labelKey: 'management.scanner.never' },
    { value: 4, labelKey: 'management.scanner.hourly' },
    { value: 1, labelKey: 'management.scanner.daily' },
    { value: 2, labelKey: 'management.scanner.weekly' },
    { value: 3, labelKey: 'management.scanner.monthly' }
  ];

  const similarityEngines = [
    { value: 0, labelKey: 'management.scanner.engines.clusters' },
    { value: 1, labelKey: 'management.scanner.engines.features' },
    { value: 2, labelKey: 'management.scanner.engines.none' }
  ];

  const hours = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}:00:00`);

  const stepLabels = {
    AssociateArtistImages: 'management.scanner.steps.AssociateArtistImages',
    AssociateExternalLyrics: 'management.scanner.steps.AssociateExternalLyrics',
    AssociatePlayListTracks: 'management.scanner.steps.AssociatePlayListTracks',
    AssociateReleaseImages: 'management.scanner.steps.AssociateReleaseImages',
    AssociateTrackImages: 'management.scanner.steps.AssociateTrackImages',
    CheckForDuplicatedFiles: 'management.scanner.steps.CheckForDuplicatedFiles',
    CheckForRemovedFiles: 'management.scanner.steps.CheckForRemovedFiles',
    Compact: 'management.scanner.steps.Compact',
    ComputeClusterStats: 'management.scanner.steps.ComputeClusterStats',
    Optimize: 'management.scanner.steps.Optimize',
    ReconciliateArtists: 'management.scanner.steps.ReconciliateArtists',
    RemoveOrphanedDbEntries: 'management.scanner.steps.RemoveOrphanedDbEntries',
    ReloadSimilarityEngine: 'management.scanner.steps.ReloadSimilarityEngine',
    ScanFiles: 'management.scanner.steps.ScanFiles',
    UpdateLibraryFields: 'management.scanner.steps.UpdateLibraryFields'
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
      const response = await fetch(restUrl(`/rest/getScanStatus?${$authParams}`));
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

      const response = await fetch(restUrl(`/rest/updateScanSettings?${query}`));
      const data = await response.json();
      if (data['subsonic-response']?.status === 'ok') {
        originalSettings = JSON.parse(JSON.stringify(settings));
        onMessage($t('management.scanner.settingsSaved'));
      } else {
        onError(data['subsonic-response']?.error?.message || $t('management.scanner.settingsSaveFailed'));
      }
    } catch (e) {
      console.error(e);
      onError($t('management.scanner.settingsNetworkError'));
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

      const response = await fetch(restUrl(`/rest/startScan?${query}`));
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res?.scanStatus) {
        status = res.scanStatus;
        onMessage($t('management.scanner.scanStarted'));
      } else {
        onError(res?.error?.message || $t('management.scanner.scanStartFailed'));
      }
    } catch (e) {
      console.error(e);
      onError($t('management.scanner.scanNetworkError'));
    }
  }

  function addToList(key) {
    settings[key] = [...settings[key], ''];
  }

  function removeFromList(key, index) {
    settings[key] = settings[key].filter((_, i) => i !== index);
  }

  function formatDateTime(isoString) {
    if (!isoString) return $t('management.scanner.notAvailable');
    try {
      return formatLocaleDateTime(isoString);
    } catch {
      return isoString;
    }
  }

  function getStepLabel(step) {
    return step && stepLabels[step] ? $t(stepLabels[step]) : step || $t('common.busy');
  }

  function getScanDuration() {
    if (!status?.lastScan?.startTime || !status?.lastScan?.stopTime) return $t('management.scanner.notAvailable');
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
      <p class="text-muma-spotify-text">{$t('management.scanner.subtitle')}</p>
    </div>
    {#if status?.lastScan}
      <p class="text-sm text-muma-spotify-text">{$t('management.scanner.lastScanAt', { date: formatDateTime(status.lastScan.stopTime) })}</p>
    {/if}
  </header>

  {#if !$authParams}
    <div class="bg-muma-spotify-panel p-8 rounded-xl border border-white/5 text-center">
      <h3 class="text-xl font-bold mb-2">{$t('management.libraries.noConnection')}</h3>
      <p class="text-muma-spotify-text">
        {$t('management.scanner.noConnectionHelp')}
      </p>
    </div>
  {:else if isLoading && !status}
    <div class="text-muma-spotify-text">{$t('common.loading')}</div>
  {:else}
    <!-- Status -->
    <div class="bg-muma-spotify-panel rounded-xl p-10 flex flex-col items-center justify-center gap-6 border border-white/5">
      {#if status?.scanning}
        <div class="relative w-24 h-24">
          <div class="absolute inset-0 rounded-full border-4 border-muma-spotify-light"></div>
          <div class="absolute inset-0 rounded-full border-4 border-brand border-t-transparent animate-spin"></div>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">{getStepLabel(status.step)}</p>
          <p class="text-muma-spotify-text mt-2">
            {$t('management.scanner.step', { current: status.stepIndex + 1, total: status.stepCount })}
            {#if status.count > 0}
              • {$t('management.scanner.processedCount', { count: status.count })}
            {/if}
          </p>
        </div>
        <div class="w-full max-w-md">
          <div class="flex justify-between text-xs text-muma-spotify-text mb-2 uppercase font-bold tracking-wider">
            <span>{$t('management.scrobble.progress')}</span>
            <span>{Math.round((status.stepIndex / status.stepCount) * 100)}%</span>
          </div>
          <div class="bg-muma-spotify-light h-3 rounded-full overflow-hidden">
            <div
              class="bg-brand h-full transition-all duration-500 ease-out"
              style="width: {((status.stepIndex + 1) / status.stepCount) * 100}%"
            ></div>
          </div>
        </div>
      {:else}
        <div class="w-20 h-20 rounded-full bg-muma-spotify-light flex items-center justify-center">
          <svg viewBox="0 0 24 24" width="40" height="40" fill="#1db954" aria-hidden="true">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"></path>
          </svg>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold text-white">{$t('management.scanner.idle')}</p>
          <p class="text-muma-spotify-text mt-2">{$t('management.scanner.idleHelp')}</p>
        </div>

        <div class="flex flex-col gap-4 w-full max-w-xs mt-4">
          <label class="flex items-center gap-3 text-sm text-muma-spotify-text hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={fullScan} class="accent-brand w-4 h-4" />
            {$t('management.scanner.fullScan')}
          </label>
          <label class="flex items-center gap-3 text-sm text-muma-spotify-text hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={forceOptimize} class="accent-brand w-4 h-4" />
            {$t('management.scanner.forceOptimise')}
          </label>
          <label class="flex items-center gap-3 text-sm text-muma-spotify-text hover:text-white cursor-pointer">
            <input type="checkbox" bind:checked={compact} class="accent-brand w-4 h-4" />
            {$t('management.scanner.compactDatabase')}
          </label>

          <button
            onclick={startScan}
            class="bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 active:scale-95 transition-all border-none shadow-lg"
          >
            {$t('management.scanner.startScan')}
          </button>
        </div>
      {/if}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-4 text-lg">{$t('management.scanner.lastScan')}
</h4>
        {#if status?.lastScan}
          <div class="space-y-4">
            <div class="flex justify-between items-center py-2 border-b border-muma-spotify-light">
              <span class="text-muma-spotify-text">{$t('management.scanner.filesProcessed')}</span>
              <span class="text-white font-medium">{status.lastScan.count}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-muma-spotify-light">
              <span class="text-muma-spotify-text">{$t('management.scanner.errors')}</span>
              <span class={status.lastScan.errors > 0 ? 'text-red-500 font-bold' : 'text-white'}>
                {status.lastScan.errors}
              </span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-muma-spotify-light">
              <span class="text-muma-spotify-text">{$t('library.duration')}</span>
              <span class="text-white font-medium">{getScanDuration()}</span>
            </div>
          </div>
        {:else}
          <p class="text-muma-spotify-text italic text-sm">{$t('management.scanner.noScanData')}</p>
        {/if}
      </div>

      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-4 text-lg">{$t('management.scanner.nextScheduled')}</h4>
        <div class="flex flex-col items-center justify-center h-full pb-6">
          {#if !settings || settings.updatePeriod === 0}
            <div class="text-muma-spotify-text text-center">
              <p class="mb-2">{$t('management.scanner.autoScanOff')}</p>
              <p class="text-xs uppercase font-bold tracking-widest">{$t('management.scanner.never')}</p>
            </div>
          {:else}
            <div class="text-center">
              <p class="text-3xl font-bold text-white mb-2">{settings.updateStartTime || '--:--'}</p>
              <p class="text-muma-spotify-text text-sm uppercase font-bold tracking-widest">
                {$t(updatePeriods.find((p) => p.value === settings.updatePeriod)?.labelKey ?? '')}
              </p>
            </div>
          {/if}
        </div>
      </div>
    </div>

    {#if settings}
      <!-- Schedule -->
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-muma-spotify-light pb-2">{$t('management.scanner.schedule')}</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="flex flex-col gap-2">
            <label for="scan-period" class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider">{$t('management.scanner.frequency')}</label>
            <select
              id="scan-period"
              class="bg-muma-spotify-light text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
              bind:value={settings.updatePeriod}
            >
              {#each updatePeriods as period (period.value)}
                <option value={period.value}>{$t(period.labelKey)}</option>
              {/each}
            </select>
          </div>

          <div class="flex flex-col gap-2" class:opacity-50={settings.updatePeriod === 0 || settings.updatePeriod === 4}>
            <label for="scan-start" class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider">{$t('management.scanner.startTime')}</label>
            <select
              id="scan-start"
              class="bg-muma-spotify-light text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10"
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
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-muma-spotify-light pb-2">{$t('management.scanner.recommendations')}</h4>
        <div class="space-y-6">
          <div class="flex justify-between items-center">
            <div>
              <p class="font-medium text-white">{$t('management.scanner.similarityEngine')}</p>
              <p class="text-sm text-muma-spotify-text">{$t('management.scanner.similarityHelp')}</p>
            </div>
            <select
              aria-label="{$t('management.scanner.similarityEngine')}"
              class="bg-muma-spotify-light text-white border-none rounded px-3 py-2 outline-none cursor-pointer focus:ring-1 focus:ring-brand h-10 w-48"
              bind:value={settings.similarityEngineType}
            >
              {#each similarityEngines as engine (engine.value)}
                <option value={engine.value}>{$t(engine.labelKey)}</option>
              {/each}
            </select>
          </div>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">{$t('management.scanner.skipSingleTrack')}</p>
              <p class="text-sm text-muma-spotify-text">{$t('management.scanner.skipSingleTrackHelp')}</p>
            </div>
            <input type="checkbox" aria-label="{$t('management.scanner.skipSingleTrack')}" bind:checked={settings.skipSingleReleasePlayLists} class="accent-brand w-5 h-5" />
          </label>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">{$t('management.scanner.mergeByMbid')}</p>
              <p class="text-sm text-muma-spotify-text">{$t('management.scanner.mergeByMbidHelp')}</p>
            </div>
            <input type="checkbox" aria-label="{$t('management.scanner.mergeByMbid')}" bind:checked={settings.allowMBIDArtistMerge} class="accent-brand w-5 h-5" />
          </label>

          <label class="flex justify-between items-center cursor-pointer">
            <div>
              <p class="font-medium text-white">{$t('management.scanner.fallbackToCover')}</p>
              <p class="text-sm text-muma-spotify-text">{$t('management.scanner.fallbackToCoverHelp')}</p>
            </div>
            <input type="checkbox" aria-label="{$t('management.scanner.fallbackToCover')}" bind:checked={settings.artistImageFallbackToRelease} class="accent-brand w-5 h-5" />
          </label>
        </div>
      </div>

      <!-- Tags -->
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h4 class="font-bold mb-6 text-lg border-b border-muma-spotify-light pb-2">{$t('management.scanner.tagProcessing')}</h4>

        <div class="space-y-8">
          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider">{$t('management.scanner.extraTags')}</span>
              <button onclick={() => addToList('extraTagsToScan')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                {$t('management.scanner.addTag')}
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.extraTagsToScan as _tag, i (i)}
                <div class="flex items-center bg-muma-spotify-light rounded overflow-hidden">
                  <input aria-label={$t('management.scanner.extraTag')} type="text" bind:value={settings.extraTagsToScan[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-24" />
                  <button onclick={() => removeFromList('extraTagsToScan', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider">{$t('management.scanner.artistSeparators')}</span>
              <button onclick={() => addToList('artistTagDelimiters')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                {$t('management.scanner.addUpper')}
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.artistTagDelimiters as _del, i (i)}
                <div class="flex items-center bg-muma-spotify-light rounded overflow-hidden">
                  <input aria-label={$t('management.scanner.artistSeparator')} type="text" bind:value={settings.artistTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                  <button onclick={() => removeFromList('artistTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <div class="flex justify-between items-center mb-4">
              <span class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider">{$t('management.scanner.defaultSeparators')}</span>
              <button onclick={() => addToList('defaultTagDelimiters')} class="text-xs text-brand hover:underline font-bold bg-transparent border-none cursor-pointer">
                {$t('management.scanner.addUpper')}
              </button>
            </div>
            <div class="flex flex-wrap gap-2">
              {#each settings.defaultTagDelimiters as _del, i (i)}
                <div class="flex items-center bg-muma-spotify-light rounded overflow-hidden">
                  <input aria-label={$t('management.scanner.defaultSeparator')} type="text" bind:value={settings.defaultTagDelimiters[i]} class="bg-transparent border-none text-white px-3 py-1 text-sm outline-none w-16 text-center" />
                  <button onclick={() => removeFromList('defaultTagDelimiters', i)} class="px-2 hover:bg-red-500 transition-colors text-white bg-transparent border-none cursor-pointer">×</button>
                </div>
              {/each}
            </div>
          </div>

          <div>
            <label for="artists-no-split" class="text-sm font-bold text-muma-spotify-text uppercase tracking-wider block mb-4">
              {$t('management.scanner.noSplitArtists')}
            </label>
            <textarea
              id="artists-no-split"
              class="w-full bg-muma-spotify-light text-white border-none rounded p-4 outline-none focus:ring-1 focus:ring-brand min-h-[120px] resize-none"
              placeholder={$t('management.scanner.noSplitPlaceholder')}
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
          class="px-6 py-2 rounded-full font-bold text-white bg-transparent border border-white/10 hover:bg-muma-spotify-light transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {$t('management.scanner.discardChanges')}
        </button>
        <button
          onclick={saveSettings}
          disabled={!hasChanges || isSaving}
          class="bg-brand text-black px-8 py-2 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 border-none"
        >
          {#if isSaving}
            <div class="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
          {/if}
          {$t('common.save')}
        </button>
      </div>
    {/if}
  {/if}
</section>
