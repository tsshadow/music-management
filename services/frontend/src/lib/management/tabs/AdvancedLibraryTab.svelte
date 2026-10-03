<script>
  import { t, format } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { Search, Filter, List, Info, PieChart, X } from '@lucide/svelte';
  import { apiGet, emptyFilters } from '../library/api.js';
  import FacetSidebar from '../library/FacetSidebar.svelte';
  import TrackTable from '../library/TrackTable.svelte';
  import TrackInspector from '../library/TrackInspector.svelte';
  import AnalyticsPanel from '../library/AnalyticsPanel.svelte';

  export let API_BASE;
  export let getHeaders;
  export let onMessage;
  export let onError;

  const BPM_BUCKET = 5;
  const LIMIT = 100;

  let filters = emptyFilters();
  let searchInput = '';
  let page = 1;
  let sort = 'created';
  let direction = 'desc';

  let tracks = [];
  let total = 0;
  let genres = [];
  let summary = { tracks: 0, artists: 0, labels: 0, genres: 0, total_duration_secs: 0,
                  coverage: { bpm: 0, genre: 0, artist: 0, analyzed: 0 } };
  let genreDistribution = [];
  let bpmHistogram = [];
  let yearHistogram = [];
  let topArtists = [];
  let topLabels = [];

  let loading = true;
  let loadError = null;
  let selectedTrack = null;
  let view = 'library';
  let showFilters = true;
  let showInspector = true;
  let reloadTimer;
  // Which request is current, per loader. A slow answer for an older filter set is dropped
  // instead of overwriting the answer for the filters the user has since picked.
  let tracksSeq = 0;
  let aggregationsSeq = 0;

  /** Loads one page of tracks for the current filters, sort and page. */
  async function loadTracks() {
    const seq = ++tracksSeq;
    loading = true;
    loadError = null;
    try {
      const data = await apiGet(API_BASE, '/api/library/advanced', filters, getHeaders,
                                { page, limit: LIMIT, sort, direction });
      if (seq !== tracksSeq) return;
      tracks = data.tracks;
      total = data.total;
    } catch (err) {
      if (seq !== tracksSeq) return;
      loadError = err.message;
      tracks = [];
      total = 0;
    } finally {
      if (seq === tracksSeq) loading = false;
    }
  }

  /** Loads the analytics panels for the current filters. */
  async function loadAggregations() {
    const seq = ++aggregationsSeq;
    try {
      const [s, gd, bpm, years, artists, labels] = await Promise.all([
        apiGet(API_BASE, '/api/analytics/summary', filters, getHeaders),
        apiGet(API_BASE, '/api/analytics/genre-distribution', filters, getHeaders, { limit: 40 }),
        apiGet(API_BASE, '/api/analytics/bpm-histogram', filters, getHeaders, { bucket: BPM_BUCKET }),
        apiGet(API_BASE, '/api/analytics/year-histogram', filters, getHeaders),
        apiGet(API_BASE, '/api/analytics/top-artists', filters, getHeaders, { limit: 12 }),
        apiGet(API_BASE, '/api/analytics/top-labels', filters, getHeaders, { limit: 12 }),
      ]);
      if (seq !== aggregationsSeq) return;
      summary = s;
      genreDistribution = gd;
      bpmHistogram = bpm;
      yearHistogram = years;
      topArtists = artists;
      topLabels = labels;
    } catch (err) {
      if (seq !== aggregationsSeq) return;
      onError(err.message);
    }
  }

  async function loadGenres() {
    try {
      genres = await apiGet(API_BASE, '/api/library/genres', {}, getHeaders);
    } catch (err) {
      onError(err.message);
    }
  }

  /** One batch per filter change, so a click does not fire seven requests. */
  function reload({ resetPage = true } = {}) {
    if (resetPage) page = 1;
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      loadTracks();
      loadAggregations();
    }, 200);
  }

  function onFilterChange(next) {
    filters = { ...next };
    reload();
  }

  function addFilter(key, value) {
    if (!filters[key].includes(value)) {
      filters = { ...filters, [key]: [...filters[key], value] };
      reload();
    }
  }

  function submitSearch(event) {
    if (event.key !== 'Enter') return;
    filters = { ...filters, q: searchInput.trim() };
    reload();
  }

  function clearAll() {
    filters = emptyFilters();
    searchInput = '';
    selectedTrack = null;
    reload();
  }

  function goToPage(next) {
    page = next;
    reload({ resetPage: false });
  }

  /** A different sort reorders the whole library, not the current page, so it starts from page 1. */
  function changeSort(key, nextDirection) {
    sort = key;
    direction = nextDirection;
    page = 1;
    reload({ resetPage: false });
  }

  /** A tempo corrected in the inspector: the list row and the selection show the new value. */
  function bpmChanged(updated) {
    tracks = tracks.map((row) => (row.id === updated.id ? { ...row, ...updated } : row));
    if (selectedTrack?.id === updated.id) selectedTrack = updated;
  }

  /** POST, so it does not go through apiGet, which only issues GETs. */
  async function rerunParse(track) {
    if (!confirm($t('management.library.confirmRerunParse', { title: track.title }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/library/tracks/${track.id}/rerun-parse`, {
        method: 'POST', headers: getHeaders(),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        onMessage($t('management.library.rerunStarted', { title: track.title }));
      } else {
        onError(body.detail || $t('management.library.rerunFailed', { status: res.status }));
      }
    } catch {
      onError($t('management.library.serverUnreachable'));
    }
  }

  async function redownload(track) {
    if (!confirm($t('management.library.confirmRedownload', { title: track.title }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/library/tracks/${track.id}/redownload`, {
        method: 'POST', headers: getHeaders(),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        onMessage(body.message || $t('management.library.redownloadStarted'));
      } else {
        onError(body.detail || $t('management.library.redownloadFailed', { status: res.status }));
      }
    } catch {
      onError($t('management.library.serverUnreachable'));
    }
  }

  $: activeFilterCount =
    filters.genre.length + filters.artist.length + filters.label.length +
    (filters.q ? 1 : 0) +
    (filters.bpm_min !== null || filters.bpm_max !== null ? 1 : 0) +
    (filters.year_min !== null || filters.year_max !== null ? 1 : 0) +
    (filters.analyzed !== null ? 1 : 0);

  $: hours = Math.round(summary.total_duration_secs / 3600);
  const pct = (v) => `${Math.round(v * 100)}%`;

  onMount(() => {
    loadGenres();
    loadTracks();
    loadAggregations();
  });
</script>

<div class="flex flex-col gap-6">

  <div class="bg-muma-spotify-panel border border-white/5 rounded-xl p-4 flex flex-col md:flex-row justify-between md:items-center gap-4">
    <div class="flex gap-7 overflow-x-auto no-scrollbar py-1">
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-muma-spotify-text font-bold">{$t('management.library.tracks')}</span>
        <span class="text-xl font-black text-white tabular-nums">{$format.number(summary.tracks)}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-muma-spotify-text font-bold">{$t('nav.artists')}</span>
        <span class="text-xl font-black text-white tabular-nums">{$format.number(summary.artists)}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-muma-spotify-text font-bold">{$t('nav.labels')}</span>
        <span class="text-xl font-black text-white tabular-nums">{$format.number(summary.labels)}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-muma-spotify-text font-bold">{$t('library.duration')}</span>
        <span class="text-xl font-black text-white tabular-nums">{$t('management.library.hoursShort', { hours: $format.number(hours) })}</span>
      </div>
      <div class="flex flex-col border-l border-white/10 pl-7">
        <span class="text-[10px] uppercase tracking-widest text-muma-spotify-text font-bold">{$t('management.library.coverage')}</span>
        <span class="text-xs font-mono text-muma-spotify-text tabular-nums">
          {$t('management.library.coverageDetail', { bpm: pct(summary.coverage.bpm), genre: pct(summary.coverage.genre), artist: pct(summary.coverage.artist) })}
        </span>
      </div>
    </div>

    <div class="flex gap-2 shrink-0">
      <button class="p-2 rounded-md transition-colors {view === 'library' ? 'bg-brand text-black' : 'hover:bg-white/5 text-white'}"
              on:click={() => view = 'library'} title={$t('management.library.trackList')}><List size={20} /></button>
      <button class="p-2 rounded-md transition-colors {view === 'analytics' ? 'bg-brand text-black' : 'hover:bg-white/5 text-white'}"
              on:click={() => view = 'analytics'} title={$t('management.library.analysis')}><PieChart size={20} /></button>
    </div>
  </div>

  <div class="bg-muma-spotify-panel border border-white/5 rounded-xl p-4 flex flex-col sm:flex-row gap-4 sm:items-center">
    <div class="relative flex-1">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" size={18} />
      <input
        type="text"
        bind:value={searchInput}
        on:keydown={submitSearch}
        placeholder={$t('management.library.searchPlaceholder')}
        class="w-full bg-muma-spotify-raised border-none rounded-full py-2.5 pl-10 pr-4 text-sm focus:ring-2 focus:ring-brand outline-none"
      />
    </div>
    <div class="flex gap-3">
      {#if activeFilterCount > 0}
        <button on:click={clearAll}
                class="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:bg-white/5 text-sm font-bold text-white">
          <X size={15} /> {$t('management.library.clearFilters', { count: activeFilterCount })}
        </button>
      {/if}
      <button on:click={() => showFilters = !showFilters}
              class="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:bg-white/5 text-sm font-bold {showFilters ? 'text-brand border-brand/50' : 'text-white'}">
        <Filter size={15} /> {$t('management.library.filters')}
      </button>
      <button on:click={() => showInspector = !showInspector}
              class="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:bg-white/5 text-sm font-bold {showInspector ? 'text-brand border-brand/50' : 'text-white'}">
        <Info size={15} /> {$t('management.library.inspector')}
      </button>
    </div>
  </div>

  <div class="flex flex-col lg:flex-row gap-6 items-start">
    {#if showFilters}
      <FacetSidebar {API_BASE} {getHeaders} {filters} {genres} onChange={onFilterChange} />
    {/if}

    <div class="flex-1 min-w-0 w-full bg-muma-spotify-panel border border-white/5 rounded-xl overflow-hidden">
      {#if view === 'library'}
        <TrackTable {tracks} {total} {page} limit={LIMIT} {loading} error={loadError}
                    {selectedTrack} onSelect={(t) => selectedTrack = t} onPage={goToPage}
                    {sort} {direction} onSort={changeSort} />
      {:else}
        <AnalyticsPanel {genreDistribution} {bpmHistogram} {yearHistogram}
                        {topArtists} {topLabels} bpmBucket={BPM_BUCKET}
                        onFilterAdd={addFilter} />
      {/if}
    </div>

    {#if showInspector}
      <TrackInspector track={selectedTrack} onRerunParse={rerunParse} onRedownload={redownload} onBpmChange={bpmChanged} />
    {/if}
  </div>
</div>

<style>
  .no-scrollbar::-webkit-scrollbar { display: none; }
  .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
