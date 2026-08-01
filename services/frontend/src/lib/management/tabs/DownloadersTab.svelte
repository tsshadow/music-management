<script >
  import { t, locale } from '../../i18n/index.js';
  import { onDestroy } from 'svelte';
  import { Cloud, ExternalLink, Trash2, Plus, Search, Play, Timer, RotateCcw } from '@lucide/svelte';
  import { formatDuration, describeBackoff, changedValues } from '../downloaderTiming';

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

  const SOURCE_LABELS = { soundcloud: 'SoundCloud', youtube: 'YouTube', telegram: 'Telegram' };
  const RATE_STATE_POLL_MS = 30000;

  let timingSources = [];
  let rateStates = {};
  let edited = {};
  let timingLoaded = false;
  let timingLoading = false;
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

  async function loadTiming() {
    timingLoading = true;
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/settings`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      timingSources = data.sources || [];
      edited = Object.fromEntries(
        timingSources.map((entry) => [
          entry.source,
          Object.fromEntries(entry.fields.map((field) => [field.key, field.value])),
        ])
      );
      timingLoaded = true;
      await loadRateState();
    } catch (err) {
      onError($t('management.downloaders.timingLoadFailed'));
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
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      onMessage(`${SOURCE_LABELS[source] || source} timing opgeslagen.`);
      timingLoaded = false;
      await loadTiming();
    } catch (err) {
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
    if (tone === 'ok') return 'text-spotify-green';
    return 'text-spotify-lightgray';
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
        body: JSON.stringify({ name: newAccountName })
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

  async function deleteYoutubeAccount(name) {
    if (!confirm(`Weet je zeker dat je kanaal ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube/${name}`, {
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
    <p class="text-spotify-lightgray text-lg">{$t('management.downloaders.subtitle')}</p>
  </header>

  <div class="flex gap-6 border-b border-white border-opacity-10">
    <button 
      on:click={() => downloaderSubTab = 'soundcloud'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'soundcloud' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      SoundCloud
      {#if downloaderSubTab === 'soundcloud'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => downloaderSubTab = 'youtube'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'youtube' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      YouTube
      {#if downloaderSubTab === 'youtube'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button
      on:click={() => downloaderSubTab = 'timing'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'timing' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      Timing
      {#if downloaderSubTab === 'timing'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
  </div>

  {#if downloaderSubTab === 'soundcloud'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Plus class="text-spotify-green" /> {$t('management.downloaders.addAccount')}</h3>
        <form on:submit|preventDefault={addAccount} class="space-y-4">
          <div>
            <label for="accountSlug" class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">{$t('management.downloaders.accountSlug')}</label>
            <input id="accountSlug" type="text" bind:value={newAccountName} placeholder={$t('management.downloaders.accountSlugPlaceholder')} class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
          </div>
          <div>
            <label for="soundcloudId" class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">{$t('management.downloaders.soundcloudId')}</label>
            <input id="soundcloudId" type="text" bind:value={newAccountId} placeholder="123456" class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
          </div>
          <button type="submit" class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform">{$t('management.downloaders.add')}</button>
        </form>
      </div>
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
            <tr><th class="p-4">{$t('management.downloaders.account')}</th><th class="p-4 text-right">{$t('management.genres.actions')}</th></tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30">
            {#each accounts as account (account.name)}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://soundcloud.com/{account.name}" target="_blank" class="flex items-center gap-2 hover:text-spotify-green">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteSoundcloudAccount(account.name)} class="text-spotify-lightgray hover:text-red-500">
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
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold mb-6 flex items-center gap-2"><Search class="text-spotify-green" /> {$t('management.downloaders.quickAdd')}</h3>
        <form on:submit|preventDefault={addYoutubeAccount} class="space-y-4">
          <div class="flex gap-2">
            <input type="text" bind:value={newAccountName} placeholder={$t('management.downloaders.channelPlaceholder')} class="flex-1 bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
            <button type="submit" class="bg-spotify-green text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">{$t('management.downloaders.addShort')}</button>
          </div>
          <p class="text-xs text-spotify-lightgray italic">{$t('management.downloaders.quickAddHelp')}</p>
        </form>

        <div class="pt-6 border-t border-white border-opacity-5">
          <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Play class="text-red-500" /> {$t('management.downloaders.manualDownload')}</h3>
          <div class="flex gap-2">
            <input type="text" placeholder={$t('management.downloaders.videoUrlPlaceholder')} class="flex-1 bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
            <button class="bg-white text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">{$t('management.downloaders.fetch')}</button>
          </div>
        </div>
      </div>
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
            <tr><th class="p-4">{$t('management.downloaders.channel')}</th><th class="p-4 text-right">{$t('management.genres.actions')}</th></tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30">
            {#each youtubeAccounts as account (account.name)}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://youtube.com/{account.name.startsWith('@') ? account.name : 'channel/'+account.name}" target="_blank" class="flex items-center gap-2 hover:text-spotify-green">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteYoutubeAccount(account.name)} class="text-spotify-lightgray hover:text-red-500">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if downloaderSubTab === 'timing'}
    <div class="space-y-6 animate-in fade-in duration-300">
      <p class="text-spotify-lightgray text-sm max-w-3xl">
        {$t('management.downloaders.timingHelp')}
      </p>

      {#if timingLoading && !timingLoaded}
        <p class="text-spotify-lightgray">{$t('management.downloaders.loadingSettings')}</p>
      {/if}

      {#each timingSources as entry (entry.source)}
        {@const state = rateStates[entry.source]}
        {@const backoff = describeBackoff(state)}
        <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-4 p-6 bg-black bg-opacity-20">
            <div>
              <h3 class="text-xl font-bold flex items-center gap-2">
                <Timer class="text-spotify-green" size={20} /> {SOURCE_LABELS[entry.source] || entry.source}
              </h3>
              <p class="text-sm font-bold mt-1 {toneClass(backoff.tone)}">{backoff.label}</p>
              {#if state}
                <p class="text-xs text-spotify-lightgray mt-1">
                  {$t('management.downloaders.cadence', { sweep: formatDuration(state.effective_sweep_interval), cooldown: formatDuration(state.effective_account_cooldown) })}
                  {#if state.last_429_at} · {$t('management.downloaders.last429', { date: new Date(state.last_429_at).toLocaleString($locale) })}{/if}
                </p>
              {/if}
            </div>
            <div class="flex gap-3">
              <button
                on:click={() => resetBackoff(entry.source)}
                class="flex items-center gap-2 text-sm font-bold text-spotify-lightgray hover:text-white border border-white border-opacity-10 rounded-full px-4 py-2"
              >
                <RotateCcw size={14} /> {$t('management.downloaders.resetBackoff')}
              </button>
              <button
                on:click={() => saveTiming(entry.source)}
                disabled={savingSource === entry.source}
                class="bg-spotify-green text-black font-extrabold px-6 py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
              >
                {savingSource === entry.source ? 'OPSLAAN...' : 'OPSLAAN'}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 p-6">
            {#each entry.fields as field (field.key)}
              <div>
                <label for="{entry.source}-{field.key}" class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">
                  {field.key.replace(/_/g, ' ')}
                </label>
                <div class="flex items-center gap-2">
                  <input
                    id="{entry.source}-{field.key}"
                    type="number"
                    min={field.minimum}
                    max={field.maximum}
                    bind:value={edited[entry.source][field.key]}
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 text-white focus:outline-none focus:border-spotify-green"
                  />
                  <span class="text-xs text-spotify-lightgray whitespace-nowrap">{field.unit}</span>
                </div>
                <p class="text-xs text-spotify-lightgray mt-1">{field.description}</p>
                <p class="text-xs text-spotify-lightgray opacity-60 mt-1">
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
