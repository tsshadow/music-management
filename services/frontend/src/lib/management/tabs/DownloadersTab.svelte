<script >
  import { t, locale } from '../../i18n/index.js';
  import { onDestroy } from 'svelte';
  import { Cloud, ExternalLink, Trash2, Plus, Search, Play, Timer, RotateCcw, AlertTriangle } from '@lucide/svelte';
  import { formatDuration, describeBackoff, changedValues } from '../downloaderTiming';
  import DownloaderCoverage from '../DownloaderCoverage.svelte';

  export let API_BASE;
  export let getHeaders;
  export let accounts;
  export let youtubeAccounts;
  export let onMessage;
  export let onError;
  export let refreshDownloaders;

  let downloaderSubTab = 'soundcloud';
  let newAccountName = '';
  let newAccountId = '';
  let newYoutubeDownloadType = 'audio';

  const SOURCE_LABELS = { soundcloud: 'SoundCloud', youtube: 'YouTube', telegram: 'Telegram' };
  const RATE_STATE_POLL_MS = 30000;

  let timingSources = [];
  let rateStates = {};
  let edited = {};
  let timingLoaded = false;
  let timingLoading = false;
  let timingError = '';
  let saveErrors = {};
  let savingSource = '';
  let pollTimer = null;

  // Depend on downloaderSubTab only. Reading timingLoaded/timingLoading inside the callee keeps
  // them out of this statement's dependency set, so loadTiming() writing them cannot re-trigger it.
  $: onSubTabChange(downloaderSubTab);

  function onSubTabChange(tab) {
    syncPolling(tab);
    if (tab === 'timing' && !timingLoaded && !timingLoading) loadTiming();
  }

  function syncPolling(tab) {
    if (tab === 'timing' && !pollTimer) {
      pollTimer = setInterval(loadRateState, RATE_STATE_POLL_MS);
    } else if (tab !== 'timing' && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  /** The API's own explanation when it gave one, so an outage is more than a status code. */
  async function reasonFor(res) {
    const detail = await res.json().catch(() => ({}));
    return detail.detail || `HTTP ${res.status}`;
  }

  async function loadTiming() {
    timingLoading = true;
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/settings`, { headers: getHeaders() });
      if (!res.ok) throw new Error(await reasonFor(res));
      const data = await res.json();
      timingSources = data.sources || [];
      edited = Object.fromEntries(
        timingSources.map((entry) => [
          entry.source,
          Object.fromEntries(entry.fields.map((field) => [field.key, field.value])),
        ])
      );
      timingLoaded = true;
      timingError = '';
      await loadRateState();
    } catch (err) {
      // Without this the tab is an empty pane with no save button anywhere in it,
      // which reads as "my settings were never saved" rather than "the API is down".
      timingError = err.message;
      timingSources = [];
      onError(`${$t('management.downloaders.timingLoadFailed')} ${err.message}`);
    } finally {
      timingLoading = false;
    }
  }

  async function loadRateState() {
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/rate-state`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      rateStates = Object.fromEntries((data.sources || []).map((entry) => [entry.source, entry]));
    } catch (err) {
      // The status panel is informational; a hiccup here must not clear the form.
    }
  }

  async function saveTiming(source) {
    const entry = timingSources.find((item) => item.source === source);
    if (!entry) return;
    const updates = changedValues(entry.fields, edited[source] || {});
    if (!Object.keys(updates).length) {
      onMessage($t('management.downloaders.nothingChanged'));
      return;
    }
    savingSource = source;
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/settings`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ source, updates }),
      });
      if (!res.ok) throw new Error(await reasonFor(res));
      onMessage(`${SOURCE_LABELS[source] || source} timing opgeslagen.`);
      saveErrors = { ...saveErrors, [source]: '' };
      timingLoaded = false;
      await loadTiming();
    } catch (err) {
      // A toast is gone by the time you look back at the form, and the field it
      // failed on is still showing the value you typed, as if it had been accepted.
      saveErrors = { ...saveErrors, [source]: err.message };
      onError(`Opslaan mislukt: ${err.message}`);
    } finally {
      savingSource = '';
    }
  }

  async function resetBackoff(source) {
    if (!confirm(`Backoff van ${SOURCE_LABELS[source] || source} terugzetten naar normaal tempo?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/rate-state/${source}/reset`, {
        method: 'POST',
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onMessage("Backoff teruggezet.");
      await loadRateState();
    } catch (err) {
      onError("Kon de backoff niet terugzetten.");
    }
  }

  function toneClass(tone) {
    if (tone === 'parked') return 'text-red-400';
    if (tone === 'slowed') return 'text-yellow-400';
    if (tone === 'ok') return 'text-brand';
    return 'text-muma-spotify-text';
  }

  async function addAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName, id: newAccountId || null })
      });
      if (res.ok) {
        onMessage($t('management.downloaders.accountAdded'));
        newAccountName = '';
        newAccountId = '';
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon account niet toevoegen.");
    }
  }

  async function deleteSoundcloudAccount(name) {
    if (!confirm(`Weet je zeker dat je ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud/${name}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Account verwijderd.");
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon account niet verwijderen.");
    }
  }

  async function addYoutubeAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName, download_type: newYoutubeDownloadType })
      });
      if (res.ok) {
        onMessage($t('management.downloaders.channelAdded'));
        newAccountName = '';
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon kanaal niet toevoegen.");
    }
  }

  async function deleteYoutubeAccount(name, downloadType) {
    if (!confirm(`Weet je zeker dat je kanaal ${name} (${downloadType}) wilt verwijderen?`)) return;
    try {
      // A channel can have both an audio and a video row; without the type the
      // API would delete both of them.
      const res = await fetch(`${API_BASE}/api/youtube/${name}?download_type=${downloadType}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.downloaders.channelDeleted'));
        refreshDownloaders();
      }
    } catch (err) {
      onError($t('management.downloaders.channelDeleteFailed'));
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">{$t('management.tabs.downloaders')}</h1>
    <p class="text-muma-spotify-text text-lg">{$t('management.downloaders.subtitle')}</p>
  </header>

  <div class="flex gap-6 border-b border-white/10">
    <button 
      on:click={() => downloaderSubTab = 'soundcloud'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'soundcloud' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      SoundCloud
      {#if downloaderSubTab === 'soundcloud'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => downloaderSubTab = 'youtube'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'youtube' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      YouTube
      {#if downloaderSubTab === 'youtube'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button
      on:click={() => downloaderSubTab = 'timing'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'timing' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      Timing
      {#if downloaderSubTab === 'timing'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button
      on:click={() => downloaderSubTab = 'coverage'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'coverage' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      {$t('management.downloaders.tabCoverage')}
      {#if downloaderSubTab === 'coverage'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
  </div>

  {#if downloaderSubTab === 'soundcloud'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Plus class="text-brand" /> {$t('management.downloaders.addAccount')}</h3>
        <form on:submit|preventDefault={addAccount} class="space-y-4">
          <div>
            <label for="accountSlug" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('management.downloaders.accountSlug')}</label>
            <input id="accountSlug" type="text" bind:value={newAccountName} placeholder={$t('management.downloaders.accountSlugPlaceholder')} class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-white focus:outline-none focus:border-brand" />
          </div>
          <div>
            <label for="soundcloudId" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('management.downloaders.soundcloudId')}</label>
            <input id="soundcloudId" type="text" bind:value={newAccountId} placeholder="123456" class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-white focus:outline-none focus:border-brand" />
          </div>
          <button type="submit" class="w-full bg-brand text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform">{$t('management.downloaders.add')}</button>
        </form>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
            <tr><th class="p-4">{$t('management.downloaders.account')}</th><th class="p-4 text-right">{$t('management.genres.actions')}</th></tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each accounts as account (account.name)}
              <tr class="hover:bg-white/5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://soundcloud.com/{account.name}" target="_blank" class="flex items-center gap-2 hover:text-brand">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteSoundcloudAccount(account.name)} class="text-muma-spotify-text hover:text-red-500">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if downloaderSubTab === 'youtube'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5 space-y-6">
        <h3 class="text-xl font-bold mb-6 flex items-center gap-2"><Search class="text-brand" /> {$t('management.downloaders.quickAdd')}</h3>
        <form on:submit|preventDefault={addYoutubeAccount} class="space-y-4">
          <div class="flex gap-2">
            <input type="text" bind:value={newAccountName} placeholder={$t('management.downloaders.channelPlaceholder')} class="flex-1 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-white focus:outline-none focus:border-brand" />
            <select bind:value={newYoutubeDownloadType} aria-label={$t('management.downloaders.downloadType')} class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-white focus:outline-none focus:border-brand">
              <option value="audio">{$t('management.downloaders.typeAudio')}</option>
              <option value="video">{$t('management.downloaders.typeVideo')}</option>
            </select>
            <button type="submit" class="bg-brand text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">{$t('management.downloaders.addShort')}</button>
          </div>
          <p class="text-xs text-muma-spotify-text italic">{$t('management.downloaders.quickAddHelp')}</p>
        </form>

        <div class="pt-6 border-t border-white/5">
          <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Play class="text-red-500" /> {$t('management.downloaders.manualDownload')}</h3>
          <div class="flex gap-2">
            <input type="text" placeholder={$t('management.downloaders.videoUrlPlaceholder')} class="flex-1 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-white focus:outline-none focus:border-brand" />
            <button class="bg-white text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">{$t('management.downloaders.fetch')}</button>
          </div>
        </div>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
            <tr><th class="p-4">{$t('management.downloaders.channel')}</th><th class="p-4">{$t('management.downloaders.downloadType')}</th><th class="p-4 text-right">{$t('management.genres.actions')}</th></tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            <!-- The table's key is (name, download_type): a channel can appear once
                 as audio and once as video, so the name alone is not a unique key. -->
            {#each youtubeAccounts as account (account.name + '/' + (account.download_type || 'audio'))}
              <tr class="hover:bg-white/5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://youtube.com/{account.name.startsWith('@') ? account.name : 'channel/'+account.name}" target="_blank" class="flex items-center gap-2 hover:text-brand">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4">
                  <span class="text-xs font-bold uppercase px-2 py-1 rounded-full {account.download_type === 'video' ? 'bg-red-500/20 text-red-400' : 'bg-brand/20 text-brand'}">
                    {account.download_type === 'video' ? $t('management.downloaders.typeVideo') : $t('management.downloaders.typeAudio')}
                  </span>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteYoutubeAccount(account.name, account.download_type || 'audio')} class="text-muma-spotify-text hover:text-red-500">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if downloaderSubTab === 'coverage'}
    <DownloaderCoverage {API_BASE} {getHeaders} />
  {:else if downloaderSubTab === 'timing'}
    <div class="space-y-6 animate-in fade-in duration-300">
      <p class="text-muma-spotify-text text-sm max-w-3xl">
        {$t('management.downloaders.timingHelp')}
      </p>

      {#if timingLoading && !timingLoaded}
        <p class="text-muma-spotify-text">{$t('management.downloaders.loadingSettings')}</p>
      {/if}

      {#if timingError}
        <div class="bg-red-500/10 border border-red-500/30 rounded-xl p-6 space-y-3">
          <h3 class="text-lg font-bold flex items-center gap-2 text-red-400">
            <AlertTriangle size={20} /> {$t('management.downloaders.timingUnavailable')}
          </h3>
          <p class="text-sm text-muma-spotify-text">{$t('management.downloaders.timingUnavailableHelp')}</p>
          <p class="text-xs font-mono text-red-300 break-all">{timingError}</p>
          <button
            on:click={loadTiming}
            class="flex items-center gap-2 text-sm font-bold text-white border border-white/20 rounded-full px-4 py-2 hover:bg-white/5"
          >
            <RotateCcw size={14} /> {$t('management.downloaders.retry')}
          </button>
        </div>
      {/if}

      {#each timingSources as entry (entry.source)}
        {@const state = rateStates[entry.source]}
        {@const backoff = describeBackoff(state)}
        <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-4 p-6 bg-black/20">
            <div>
              <h3 class="text-xl font-bold flex items-center gap-2">
                <Timer class="text-brand" size={20} /> {SOURCE_LABELS[entry.source] || entry.source}
              </h3>
              <p class="text-sm font-bold mt-1 {toneClass(backoff.tone)}">{backoff.label}</p>
              {#if state}
                <p class="text-xs text-muma-spotify-text mt-1">
                  {$t('management.downloaders.cadence', { sweep: formatDuration(state.effective_sweep_interval), cooldown: formatDuration(state.effective_account_cooldown) })}
                  {#if state.last_429_at} · {$t('management.downloaders.last429', { date: new Date(state.last_429_at).toLocaleString($locale) })}{/if}
                </p>
              {/if}
            </div>
            <div class="flex gap-3">
              <button
                on:click={() => resetBackoff(entry.source)}
                class="flex items-center gap-2 text-sm font-bold text-muma-spotify-text hover:text-white border border-white/10 rounded-full px-4 py-2"
              >
                <RotateCcw size={14} /> {$t('management.downloaders.resetBackoff')}
              </button>
              <button
                on:click={() => saveTiming(entry.source)}
                disabled={savingSource === entry.source}
                class="bg-brand text-black font-extrabold px-6 py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
              >
                {savingSource === entry.source ? 'OPSLAAN...' : 'OPSLAAN'}
              </button>
            </div>
          </div>

          {#if saveErrors[entry.source]}
            <p class="px-6 pt-4 text-sm text-red-400 flex items-start gap-2">
              <AlertTriangle size={16} class="shrink-0 mt-0.5" />
              <span>
                {$t('management.downloaders.saveFailed')}
                <span class="font-mono text-xs text-red-300 break-all">{saveErrors[entry.source]}</span>
              </span>
            </p>
          {/if}

          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 p-6">
            {#each entry.fields as field (field.key)}
              <div>
                <label for="{entry.source}-{field.key}" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">
                  {field.key.replace(/_/g, ' ')}
                </label>
                <div class="flex items-center gap-2">
                  <input
                    id="{entry.source}-{field.key}"
                    type="number"
                    min={field.minimum}
                    max={field.maximum}
                    bind:value={edited[entry.source][field.key]}
                    class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white focus:outline-none focus:border-brand"
                  />
                  <span class="text-xs text-muma-spotify-text whitespace-nowrap">{field.unit}</span>
                </div>
                <p class="text-xs text-muma-spotify-text mt-1">{field.description}</p>
                <p class="text-xs text-muma-spotify-text opacity-60 mt-1">
                  standaard {field.default}
                  {#if field.unit === 'seconden'} ({formatDuration(field.default)}){/if}
                  · toegestaan {field.minimum}–{field.maximum}
                </p>
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</section>
