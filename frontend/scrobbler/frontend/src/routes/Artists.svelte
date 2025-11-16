<script lang="ts">
  import { onMount } from 'svelte';
  import DetailPanel from '../lib/components/DetailPanel.svelte';
  import HypeGraph, { type HypePoint } from '../lib/components/HypeGraph.svelte';
  import StatsLeaderboard, {
    type LeaderboardRow,
  } from '../lib/components/StatsLeaderboard.svelte';

  export let title = 'Meest geluisterde artiesten';
  export let description = 'Ontdek wie jouw soundtrack domineert per gekozen periode.';
  export let endpoint = '/api/v1/stats/artists';
  export let supportsPeriods = true;
  export let countHeading = 'Listens';
  export let showInsights = true;

  type Period = 'all' | 'day' | 'month' | 'year';

  interface ArtistRow extends LeaderboardRow {
    artist_id: number;
  }

  interface ArtistInsight {
    artist_id: number;
    name: string;
    mbid: string | null;
    listen_count: number;
    first_listen: string | null;
    last_listen: string | null;
    top_genres: { genre_id: number | null; genre: string; count: number }[];
    top_tracks: {
      track_id: number;
      track: string;
      album_id: number | null;
      album_title: string | null;
      count: number;
    }[];
    top_albums: {
      album_id: number;
      album: string;
      release_year: number | null;
      count: number;
    }[];
    listen_history: { period: string; count: number }[];
  }

  const pageSize = 100;

  let period: Period = supportsPeriods ? 'year' : 'all';
  let value = supportsPeriods ? getDefaultValue(period) : '';
  let loading = false;
  let error: string | null = null;
  let rows: ArtistRow[] = [];
  let total = 0;
  let page = 1;

  let panelOpen = false;
  let panelLoading = false;
  let panelError: string | null = null;
  let panelTitle = '';
  let insight: ArtistInsight | null = null;

  const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  });
  const monthFormatter = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    year: 'numeric',
  });

  function getDefaultValue(current: Period): string {
    const now = new Date();
    if (current === 'all') {
      return '';
    }
    if (current === 'day') {
      return now.toISOString().slice(0, 10);
    }
    if (current === 'month') {
      const month = String(now.getMonth() + 1).padStart(2, '0');
      return `${now.getFullYear()}-${month}`;
    }
    return String(now.getFullYear());
  }

  async function loadData() {
    if (supportsPeriods && period !== 'all' && !value) {
      rows = [];
      total = 0;
      return;
    }
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (supportsPeriods) {
        params.set('period', period);
        if (period !== 'all') {
          params.set('value', value);
        }
      }
      const response = await fetch(`${endpoint}?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de artiesten niet laden');
      }
      const data: {
        items: { artist: string; count: number; artist_id: number }[];
        total: number;
      } = await response.json();
      rows = data.items.map((item) => ({
        label: item.artist,
        count: item.count,
        artist_id: item.artist_id,
      }));
      total = data.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Onbekende fout';
      rows = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function onPeriodChange(event: Event) {
    if (!supportsPeriods) {
      return;
    }
    period = (event.target as HTMLSelectElement).value as Period;
    value = getDefaultValue(period);
    page = 1;
    loadData();
  }

  function onValueChange(event: Event) {
    if (!supportsPeriods) {
      return;
    }
    value = (event.target as HTMLInputElement).value;
    page = 1;
    loadData();
  }

  function changePage(newPage: number) {
    if (newPage < 1 || newPage > totalPages) {
      return;
    }
    page = newPage;
    loadData();
  }

  async function openInsight(row: ArtistRow) {
    if (!showInsights) {
      return;
    }
    panelOpen = true;
    panelTitle = row.label;
    panelLoading = true;
    panelError = null;
    insight = null;
    try {
      const response = await fetch(`/api/v1/library/artists/${row.artist_id}/insights`);
      if (!response.ok) {
        throw new Error('Kon artiestinformatie niet ophalen');
      }
      insight = (await response.json()) as ArtistInsight;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Onbekende fout';
    } finally {
      panelLoading = false;
    }
  }

  function onSelect(event: CustomEvent<ArtistRow>) {
    if (!showInsights) {
      return;
    }
    openInsight(event.detail);
  }

  function closePanel() {
    panelOpen = false;
    panelError = null;
    insight = null;
  }

  function formatDateTime(value: string | null) {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return dateTimeFormatter.format(date);
  }

  function formatPeriodLabel(period: string) {
    const [year, month] = period.split('-').map((part) => Number.parseInt(part, 10));
    if (!Number.isFinite(year)) {
      return period;
    }
    if (Number.isFinite(month)) {
      const date = new Date(Date.UTC(year, month - 1, 1));
      return monthFormatter.format(date);
    }
    return String(year);
  }

  $: hypePoints = showInsights
    ? (insight?.listen_history ?? []).map<HypePoint>((entry) => ({
        label: formatPeriodLabel(entry.period),
        value: entry.count,
      }))
    : [];

  $: hypeHighlights = showInsights
    ? [...(insight?.listen_history ?? [])]
        .sort((a, b) => b.count - a.count)
        .slice(0, 3)
        .map((entry) => ({
          period: formatPeriodLabel(entry.period),
          count: entry.count,
        }))
    : [];

  $: totalPages = Math.max(1, Math.ceil(total / pageSize));
  $: showingStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  $: showingEnd = total === 0 ? 0 : Math.min(total, page * pageSize);

  onMount(() => {
    loadData();
  });
</script>

<section class="page">
  <header>
    <h2>{title}</h2>
    <p>{description}</p>
  </header>

  {#if supportsPeriods}
    <div class="controls">
      <label>
        Periode
        <select bind:value={period} on:change={onPeriodChange}>
          <option value="all">Altijd</option>
          <option value="day">Dag</option>
          <option value="month">Maand</option>
          <option value="year">Jaar</option>
        </select>
      </label>

      <label class:disabled={period === 'all'}>
        Waarde
        {#if period === 'year'}
          <input
            type="text"
            inputmode="numeric"
            maxlength="4"
            bind:value={value}
            on:change={onValueChange}
          />
        {:else if period === 'month'}
          <input type="month" bind:value={value} on:change={onValueChange} />
        {:else if period === 'day'}
          <input type="date" bind:value={value} on:change={onValueChange} />
        {:else}
          <span class="all-time-pill">Alles</span>
        {/if}
      </label>
    </div>
  {/if}

  {#if loading}
    <p class="status">Bezig met laden…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <StatsLeaderboard
        rows={rows}
        labelHeading="Artiest"
        {countHeading}
        clickable={showInsights}
        on:select={onSelect}
      />
      <footer class="pagination">
        {#if total === 0}
          <span>Geen data beschikbaar voor deze periode.</span>
        {:else}
          <span>Toont {showingStart}–{showingEnd} van {total}</span>
        {/if}
        <div class="pager-controls">
          <button type="button" on:click={() => changePage(page - 1)} disabled={page === 1}>
            Vorige pagina
          </button>
          <span>Pagina {page} van {totalPages}</span>
          <button
            type="button"
            on:click={() => changePage(page + 1)}
            disabled={page === totalPages || total === 0}
          >
            Volgende pagina
          </button>
        </div>
      </footer>
    </div>
  {/if}
</section>

{#if showInsights}
  <DetailPanel
    title={panelTitle}
    open={panelOpen}
    loading={panelLoading}
    error={panelError}
    on:close={closePanel}
  >
    {#if insight}
      <section class="detail-section">
        <h4>Statistieken</h4>
        <dl>
          <dt>Totaal aantal listens</dt>
          <dd>{insight.listen_count.toLocaleString()}</dd>
          <dt>Eerste luisterbeurt</dt>
          <dd>{formatDateTime(insight.first_listen)}</dd>
          <dt>Laatste luisterbeurt</dt>
          <dd>{formatDateTime(insight.last_listen)}</dd>
          <dt>MBID</dt>
          <dd>{insight.mbid ?? '—'}</dd>
        </dl>
      </section>
      <section class="detail-section">
        <h4>Luisterhype</h4>
        <HypeGraph {hypePoints} />
        {#if hypeHighlights.length > 0}
          <p class="muted">
            Pieken in {hypeHighlights
              .map((highlight) => `${highlight.period} (${highlight.count.toLocaleString()}×)`)
              .join(', ')}.
          </p>
        {:else}
          <p class="muted">Nog geen luistergeschiedenis voor deze artiest.</p>
        {/if}
      </section>
      <section class="detail-section">
        <h4>Topgenres</h4>
        <ul>
          {#each insight.top_genres as item}
            <li>{item.genre} — {item.count.toLocaleString()} listens</li>
          {/each}
        </ul>
      </section>
      <section class="detail-section">
        <h4>Toptracks</h4>
        <ul>
          {#each insight.top_tracks as item}
            <li>
              {item.track}
              {#if item.album_title}
                — <span class="muted">{item.album_title}</span>
              {/if}
              <span class="count">{item.count.toLocaleString()}×</span>
            </li>
          {/each}
        </ul>
      </section>
      <section class="detail-section">
        <h4>Topalbums</h4>
        <ul>
          {#each insight.top_albums as item}
            <li>
              {item.album}
              {#if item.release_year}
                <span class="muted">({item.release_year})</span>
              {/if}
              <span class="count">{item.count.toLocaleString()}×</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  </DetailPanel>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
  }

  header {
    text-align: center;
  }

  .controls {
    display: flex;
    gap: 1rem;
    background: rgba(0, 0, 0, 0.15);
    padding: 1rem 1.5rem;
    border-radius: 999px;
    flex-wrap: wrap;
    justify-content: center;
  }

  label {
    display: flex;
    flex-direction: column;
    font-size: 0.9rem;
    gap: 0.35rem;
    color: rgba(255, 255, 255, 0.75);
  }

  label.disabled {
    opacity: 0.6;
  }

  select,
  input {
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(20, 20, 30, 0.8);
    color: var(--text-color);
  }

  .all-time-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.75rem;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    font-weight: 600;
    color: var(--text-color);
  }

  .table-wrapper {
    width: min(720px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .status {
    color: rgba(255, 255, 255, 0.75);
  }

  .status.error {
    color: #ff8080;
  }

  .pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.9rem;
    color: rgba(255, 255, 255, 0.75);
  }

  .pager-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .pager-controls button {
    background: rgba(255, 255, 255, 0.08);
    border: none;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    color: var(--text-color);
    cursor: pointer;
  }

  .pager-controls button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .detail-section {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0.75rem;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .detail-section h4 {
    margin: 0;
    font-size: 1rem;
  }

  dl {
    margin: 0;
    display: grid;
    grid-template-columns: 1fr 2fr;
    gap: 0.35rem 1rem;
  }

  dt {
    font-weight: 600;
    color: rgba(255, 255, 255, 0.75);
  }

  dd {
    margin: 0;
  }

  ul {
    margin: 0;
    padding-left: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .muted {
    color: rgba(255, 255, 255, 0.6);
  }

  .count {
    margin-left: 0.5rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
