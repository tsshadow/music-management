<script lang="ts">
  import { onMount } from 'svelte';
  import DetailPanel from '../lib/components/DetailPanel.svelte';
  import StatsLeaderboard, {
    type LeaderboardRow,
  } from '../lib/components/StatsLeaderboard.svelte';

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
    artists: { artist_id: number; artist: string }[];
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

  let period: Period = 'year';
  let value = getDefaultValue(period);
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
    if (period !== 'all' && !value) {
      rows = [];
      total = 0;
      return;
    }
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({ period, page: String(page), page_size: String(pageSize) });
      if (period !== 'all') {
        params.set('value', value);
      }
      const response = await fetch(`/api/v1/stats/albums?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de albums niet laden');
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
      error = err instanceof Error ? err.message : 'Onbekende fout';
      rows = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function onPeriodChange(event: Event) {
    period = (event.target as HTMLSelectElement).value as Period;
    value = getDefaultValue(period);
    page = 1;
    loadData();
  }

  function onValueChange(event: Event) {
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
    panelOpen = true;
    panelTitle = row.label;
    panelLoading = true;
    panelError = null;
    insight = null;
    try {
      const response = await fetch(`/api/v1/library/albums/${row.album_id}/insights`);
      if (!response.ok) {
        throw new Error('Kon albuminformatie niet ophalen');
      }
      insight = (await response.json()) as AlbumInsight;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Onbekende fout';
    } finally {
      panelLoading = false;
    }
  }

  function onSelect(event: CustomEvent<AlbumRow>) {
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
    <h2>Meest geluisterde albums</h2>
    <p>Bekijk welke releases je keer op keer hebt gedraaid.</p>
  </header>

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

  {#if loading}
    <p class="status">Bezig met laden…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <StatsLeaderboard rows={rows} labelHeading="Album" clickable on:select={onSelect} />
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

<DetailPanel
  title={panelTitle}
  open={panelOpen}
  loading={panelLoading}
  error={panelError}
  on:close={closePanel}
>
  {#if insight}
    <section class="detail-section">
      <h4>Albuminfo</h4>
      <dl>
        <dt>Naam</dt>
        <dd>{insight.title}</dd>
        <dt>Jaar</dt>
        <dd>{insight.release_year ?? '—'}</dd>
        <dt>MBID</dt>
        <dd>{insight.mbid ?? '—'}</dd>
        <dt>Totaal aantal listens</dt>
        <dd>{insight.listen_count.toLocaleString()}</dd>
        <dt>Eerste luisterbeurt</dt>
        <dd>{formatDateTime(insight.first_listen)}</dd>
        <dt>Laatste luisterbeurt</dt>
        <dd>{formatDateTime(insight.last_listen)}</dd>
      </dl>
    </section>
    <section class="detail-section">
      <h4>Artiesten</h4>
      <ul>
        {#each insight.artists as artist}
          <li>{artist.artist}</li>
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

  .muted {
    color: rgba(255, 255, 255, 0.6);
  }

  .count {
    margin-left: 0.5rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
