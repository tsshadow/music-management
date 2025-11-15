<script lang="ts">
  /** Leaderboard view for top albums over configurable periods. */
  import { onMount } from 'svelte';
  import { scrobblerApi } from '$lib/api';
  import DetailPanel from '../components/DetailPanel.svelte';
  import StatsLeaderboard from '../components/StatsLeaderboard.svelte';
  import { type LeaderboardRow } from '../types';

  export let title = 'Most played albums';
  export let description = 'See which releases you return to on repeat.';
  export let endpoint = scrobblerApi.url('/stats/albums');
  export let supportsPeriods = true;
  export let countHeading = 'Listens';
  export let showInsights = true;

  type Period = 'all' | 'day' | 'month' | 'year';

  interface AlbumRow extends LeaderboardRow {
    album_id: number;
    release_year: number | null;
  }

  interface AlbumInsight {
    album_id: number;
    title: string;
    release_year: number | null;
    mbid: string | null;
    listen_count: number;
    first_listen: string | null;
    last_listen: string | null;
    artists: { artist_id: number; artist: string; listen_count: number }[];
    genres: { genre_id: number | null; genre: string; count: number }[];
    tracks: {
      track_id: number;
      track: string;
      track_no: number | null;
      disc_no: number | null;
      duration_secs: number | null;
      count: number;
    }[];
  }

  const pageSize = 100;

  let period: Period = supportsPeriods ? 'year' : 'all';
  let value = supportsPeriods ? getDefaultValue(period) : '';
  let loading = false;
  let error: string | null = null;
  let rows: AlbumRow[] = [];
  let total = 0;
  let page = 1;

  let panelOpen = false;
  let panelLoading = false;
  let panelError: string | null = null;
  let panelTitle = '';
  let insight: AlbumInsight | null = null;

  const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
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
        throw new Error('Failed to load albums');
      }
      const data: {
        items: { album: string; count: number; album_id: number; release_year: number | null }[];
        total: number;
      } = await response.json();
      rows = data.items.map((item) => ({
        label: item.album,
        count: item.count,
        album_id: item.album_id,
        release_year: item.release_year,
      }));
      total = data.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error';
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

  async function openInsight(row: AlbumRow) {
    if (!showInsights) {
      return;
    }
    panelOpen = true;
    panelTitle = row.label;
    panelLoading = true;
    panelError = null;
    insight = null;
    try {
      const response = await fetch(scrobblerApi.url(`/library/albums/${row.album_id}/insights`));
      if (!response.ok) {
        throw new Error('Failed to load album insights');
      }
      insight = (await response.json()) as AlbumInsight;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Unexpected error';
    } finally {
      panelLoading = false;
    }
  }

  function onSelect(event: CustomEvent<LeaderboardRow>) {
    if (!showInsights) {
      return;
    }
    openInsight(event.detail as AlbumRow);
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

  function formatDuration(seconds: number | null | undefined) {
    if (seconds == null) {
      return '—';
    }
    const totalSeconds = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${minutes}:${String(secs).padStart(2, '0')}`;
  }

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
        Period
        <select bind:value={period} on:change={onPeriodChange}>
          <option value="all">All time</option>
          <option value="day">Day</option>
          <option value="month">Month</option>
          <option value="year">Year</option>
        </select>
      </label>

      <label class:disabled={period === 'all'}>
        Value
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
          <span class="all-time-pill">All</span>
        {/if}
      </label>
    </div>
  {/if}

  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <StatsLeaderboard
        rows={rows}
        labelHeading="Album"
        {countHeading}
        clickable={showInsights}
        on:select={onSelect}
      />
      <footer class="pagination">
        {#if total === 0}
          <span>No data available for this period.</span>
        {:else}
          <span>Showing {showingStart}–{showingEnd} of {total}</span>
        {/if}
        <div class="pager-controls">
          <button type="button" on:click={() => changePage(page - 1)} disabled={page === 1}>
            Previous page
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            type="button"
            on:click={() => changePage(page + 1)}
            disabled={page === totalPages || total === 0}
          >
            Next page
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
        <h4>Album info</h4>
        <dl>
          <dt>Name</dt>
          <dd>{insight.title}</dd>
          <dt>Year</dt>
          <dd>{insight.release_year ?? '—'}</dd>
          <dt>MBID</dt>
          <dd>{insight.mbid ?? '—'}</dd>
          <dt>Total listens</dt>
          <dd>{insight.listen_count.toLocaleString()}</dd>
          <dt>First listen</dt>
          <dd>{formatDateTime(insight.first_listen)}</dd>
          <dt>Most recent listen</dt>
          <dd>{formatDateTime(insight.last_listen)}</dd>
        </dl>
      </section>
      <section class="detail-section">
        <h4>Artists</h4>
        <ul>
          {#each insight.artists as artist}
            <li class="artist-row">
              <span>{artist.artist}</span>
              <span class="count">{artist.listen_count.toLocaleString()}× played</span>
            </li>
          {/each}
        </ul>
      </section>
      <section class="detail-section">
        <h4>Genres</h4>
        <ul>
          {#each insight.genres as item}
            <li>{item.genre} — {item.count.toLocaleString()} listens</li>
          {/each}
        </ul>
      </section>
      <section class="detail-section">
        <h4>Tracks</h4>
        <ol>
          {#each insight.tracks as track}
            <li>
              {track.track}
              <span class="muted">
                {#if track.track_no != null}
                  #{track.track_no}
                {/if}
                {#if track.disc_no != null}
                  · Disc {track.disc_no}
                {/if}
                · {formatDuration(track.duration_secs)}
              </span>
              <span class="count">{track.count.toLocaleString()}×</span>
            </li>
          {/each}
        </ol>
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

  ul,
  ol {
    margin: 0;
    padding-left: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .artist-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
  }

  .muted {
    color: rgba(255, 255, 255, 0.6);
  }

  .count {
    margin-left: 0.5rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
