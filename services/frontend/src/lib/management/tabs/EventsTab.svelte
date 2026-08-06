<script>
  import { onMount, onDestroy } from 'svelte';
  import { ScrollText, Trash2, Clock, ChevronRight } from '@lucide/svelte';
  import { t } from '../../i18n/index.js';

  export let API_BASE;
  export let getHeaders;
  export let onMessage;
  export let onError;
  export let config;

  const LEVELS = ['INFO', 'WARNING', 'ERROR', 'CRITICAL'];
  const SOURCES = ['music-manager', 'downloader', 'importer', 'tagger', 'scanner'];
  const WINDOWS = [
    { value: '-1h', labelKey: 'management.events.windowHour' },
    { value: '-24h', labelKey: 'management.events.windowDay' },
    { value: '-7d', labelKey: 'management.events.windowWeek' },
    { value: '', labelKey: 'management.events.windowAll' },
  ];
  const POLL_INTERVAL_MS = 10000;
  const LEVEL_STYLES = {
    INFO: 'text-spotify-lightgray border-white/10',
    WARNING: 'text-amber-400 border-amber-400/40',
    ERROR: 'text-red-400 border-red-400/40',
    CRITICAL: 'text-red-300 border-red-300/60 bg-red-950/30',
  };

  let events = [];
  let counts = {};
  let total = 0;
  let loading = false;
  let selectedLevels = new Set(LEVELS);
  let selectedSources = new Set();
  let timeWindow = '-24h';
  let search = '';
  let expanded = new Set();
  let searchTimer;
  let pollTimer;

  function buildQuery() {
    const params = new URLSearchParams();
    for (const level of selectedLevels) params.append('level', level);
    for (const source of selectedSources) params.append('source', source);
    if (timeWindow) params.set('since', timeWindow);
    if (search.trim()) params.set('q', search.trim());
    params.set('limit', '200');
    return params.toString();
  }

  async function fetchEvents() {
    if (selectedLevels.size === 0) {
      events = [];
      counts = {};
      total = 0;
      return;
    }
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/events?${buildQuery()}`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        events = body.events;
        counts = body.counts;
        total = body.total;
      } else {
        onError($t('management.events.fetchFailed'));
      }
    } catch (err) {
      console.error(err);
      onError($t('management.events.fetchFailed'));
    } finally {
      loading = false;
    }
  }

  function toggleLevel(level) {
    selectedLevels.has(level) ? selectedLevels.delete(level) : selectedLevels.add(level);
    selectedLevels = new Set(selectedLevels);
    fetchEvents();
  }

  function toggleSource(source) {
    selectedSources.has(source) ? selectedSources.delete(source) : selectedSources.add(source);
    selectedSources = new Set(selectedSources);
    fetchEvents();
  }

  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchEvents, 300);
  }

  function toggleExpanded(id) {
    expanded.has(id) ? expanded.delete(id) : expanded.add(id);
    expanded = new Set(expanded);
  }

  async function deleteEvent(id) {
    try {
      const res = await fetch(`${API_BASE}/api/events/${id}`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) events = events.filter((e) => e.id !== id);
    } catch (err) {
      onError($t('management.events.deleteFailed'));
    }
  }

  async function clearAll() {
    if (!confirm($t('management.events.confirmClear'))) return;
    try {
      const res = await fetch(`${API_BASE}/api/events`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) {
        events = [];
        total = 0;
        onMessage($t('management.events.cleared'));
      }
    } catch (err) {
      onError($t('management.events.clearFailed'));
    }
  }

  function formatDate(value) {
    return new Date(value).toLocaleString('nl-NL');
  }

  onMount(() => {
    fetchEvents();
    pollTimer = setInterval(() => {
      if (!document.hidden) fetchEvents();
    }, POLL_INTERVAL_MS);
  });

  onDestroy(() => {
    clearInterval(pollTimer);
    clearTimeout(searchTimer);
  });

  $: ntfyUrl = config.notify_url || '';
  $: ntfyTopic = config.notify_topic || 'music-management';
  $: ntfyAlertsTopic = config.notify_topic_alerts || 'music-management-alerts';
</script>

<div class="flex flex-col gap-8">
  <div class="flex justify-between items-end">
    <div>
      <h1 class="text-4xl font-black mb-2 flex items-center gap-4">
        <ScrollText size={40} class="text-spotify-green" />
        {$t('management.events.title')}
      </h1>
      <p class="text-spotify-lightgray">{$t('management.events.subtitle')}</p>
    </div>
    <div class="flex gap-4">
      <button on:click={fetchEvents}
        class="bg-white text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider">
        {$t('management.events.refresh')}
      </button>
      {#if events.length > 0}
        <button on:click={clearAll}
          class="bg-red-600 text-white font-bold py-3 px-8 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider flex items-center gap-2">
          <Trash2 size={16} />
          {$t('management.events.clearAll')}
        </button>
      {/if}
    </div>
  </div>

  <div class="bg-black bg-opacity-40 rounded-xl p-6 border border-white border-opacity-10 flex flex-wrap gap-6 items-end">
    <div class="flex flex-col gap-2">
      <span class="text-xs uppercase tracking-wider text-spotify-lightgray">{$t('management.events.levelFilter')}</span>
      <div class="flex gap-2">
        {#each LEVELS as level}
          <button on:click={() => toggleLevel(level)}
            class="px-4 py-2 rounded-full text-xs font-bold border transition-all {selectedLevels.has(level) ? 'bg-white text-black border-white' : 'border-white/20 text-spotify-lightgray hover:text-white'}">
            {level} {counts[level] ?? 0}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex flex-col gap-2">
      <span class="text-xs uppercase tracking-wider text-spotify-lightgray">{$t('management.events.sourceFilter')}</span>
      <div class="flex gap-2 flex-wrap">
        {#each SOURCES as source}
          <button on:click={() => toggleSource(source)}
            class="px-3 py-2 rounded-full text-xs font-bold border transition-all {selectedSources.has(source) ? 'bg-spotify-green text-black border-spotify-green' : 'border-white/20 text-spotify-lightgray hover:text-white'}">
            {source}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex flex-col gap-2">
      <span class="text-xs uppercase tracking-wider text-spotify-lightgray">{$t('management.events.timeFilter')}</span>
      <select bind:value={timeWindow} on:change={fetchEvents}
        class="bg-spotify-gray text-white rounded-lg px-4 py-2 border border-white/10 text-sm">
        {#each WINDOWS as window}
          <option value={window.value}>{$t(window.labelKey)}</option>
        {/each}
      </select>
    </div>

    <div class="flex flex-col gap-2 flex-1 min-w-48">
      <span class="text-xs uppercase tracking-wider text-spotify-lightgray">{$t('management.events.search')}</span>
      <input bind:value={search} on:input={onSearchInput} type="text"
        class="bg-spotify-gray text-white rounded-lg px-4 py-2 border border-white/10 text-sm w-full" />
    </div>
  </div>

  <div class="bg-black bg-opacity-40 rounded-xl p-6 border border-white border-opacity-10">
    <h3 class="text-xl font-bold mb-4">{$t('management.events.subscribeTitle')}</h3>
    <p class="text-sm text-spotify-lightgray mb-4">{$t('management.events.subscribeHelp')}</p>
    <div class="flex flex-col gap-2">
      <code class="text-spotify-green font-mono text-sm">{ntfyUrl}{ntfyTopic}</code>
      <code class="text-amber-400 font-mono text-sm">{ntfyUrl}{ntfyAlertsTopic}</code>
    </div>
  </div>

  <div class="flex flex-col gap-2">
    {#if loading && events.length === 0}
      <div class="text-center py-20 text-spotify-lightgray">{$t('management.events.loading')}</div>
    {:else if events.length === 0}
      <div class="text-center py-20 bg-black bg-opacity-20 rounded-xl border border-dashed border-white border-opacity-10">
        <ScrollText size={48} class="mx-auto mb-4 text-spotify-gray" />
        <p class="text-spotify-lightgray">{$t('management.events.empty')}</p>
      </div>
    {:else}
      <p class="text-xs text-spotify-lightgray">{total} {$t('management.events.matches')}</p>
      {#each events as event (event.id)}
        <div class="bg-black bg-opacity-40 hover:bg-opacity-60 transition-all rounded-lg border {LEVEL_STYLES[event.level] ?? 'border-white/10'} group">
          <button on:click={() => toggleExpanded(event.id)} class="w-full flex items-center gap-4 p-3 text-left">
            <ChevronRight size={16} class="transition-transform {expanded.has(event.id) ? 'rotate-90' : ''}" />
            <span class="font-mono text-xs font-bold w-20 shrink-0">{event.level}</span>
            <span class="text-xs text-spotify-lightgray w-32 shrink-0 flex items-center gap-1">
              <Clock size={12} />{formatDate(event.created_at)}
            </span>
            <span class="text-xs text-spotify-lightgray w-32 shrink-0">{event.source}</span>
            <span class="text-sm text-white truncate flex-1">{event.title}</span>
            <button on:click|stopPropagation={() => deleteEvent(event.id)}
              class="text-spotify-lightgray hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              <Trash2 size={16} />
            </button>
          </button>
          {#if expanded.has(event.id)}
            <div class="px-10 pb-4 flex flex-col gap-3">
              <pre class="text-spotify-lightgray whitespace-pre-wrap font-mono text-xs bg-black bg-opacity-30 p-3 rounded">{event.message}</pre>
              {#if event.context}
                <pre class="text-spotify-green whitespace-pre-wrap font-mono text-xs bg-black bg-opacity-30 p-3 rounded">{event.context}</pre>
              {/if}
              {#if event.logger}
                <span class="text-xs text-spotify-lightgray font-mono">{event.logger}</span>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    {/if}
  </div>
</div>
