<script lang="ts">
  import { onMount } from 'svelte';
  import DetailPanel from '../lib/components/DetailPanel.svelte';
  import KpiCard from '../lib/components/KpiCard.svelte';
  import RecentListensTable, {
    type ListenArtist,
    type ListenRow,
  } from '../lib/components/RecentListensTable.svelte';

  type Period = 'day' | 'week' | 'month' | 'all';

  interface ListenDetail {
    id: number;
    listened_at: string;
    source: string;
    source_track_id: string | null;
    position_secs: number | null;
    duration_secs: number | null;
    user_id: number;
    username: string;
    track_id: number;
    track_title: string;
    track_duration_secs: number | null;
    disc_no: number | null;
    track_no: number | null;
    track_mbid: string | null;
    isrc: string | null;
    album_id: number | null;
    album_title: string | null;
    album_release_year: number | null;
    album_mbid: string | null;
    artists: ListenArtist[];
    genres: { id: number | null; name: string }[];
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

  let totalListens = 0;
  let listens: ListenRow[] = [];
  let loading = false;
  let error: string | null = null;

  let period: Period = 'day';
  let value = getDefaultValue(period);
  let page = 1;
  let total = 0;

  let panelType: 'listen' | 'artist' | 'album' | null = null;
  let panelTitle = '';
  let panelLoading = false;
  let panelError: string | null = null;
  let listenDetail: ListenDetail | null = null;
  let artistInsight: ArtistInsight | null = null;
  let albumInsight: AlbumInsight | null = null;

  const dayFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });
  const monthFormatter = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' });
  const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  });

  function getDefaultValue(current: Period): string {
    const now = new Date();
    if (current === 'day') {
      return now.toISOString().slice(0, 10);
    }
    if (current === 'month') {
      const month = String(now.getMonth() + 1).padStart(2, '0');
      return `${now.getFullYear()}-${month}`;
    }
    if (current === 'week') {
      return toISOWeekString(now);
    }
    return '';
  }

  function toISOWeekString(date: Date): string {
    const temp = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
    const day = temp.getUTCDay() || 7;
    temp.setUTCDate(temp.getUTCDate() + 4 - day);
    const isoYear = temp.getUTCFullYear();
    const yearStart = new Date(Date.UTC(isoYear, 0, 1));
    const week = Math.ceil(((temp.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
    return `${isoYear}-W${String(week).padStart(2, '0')}`;
  }

  function startOfISOWeek(year: number, week: number): Date {
    const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
    const day = simple.getUTCDay() || 7;
    simple.setUTCDate(simple.getUTCDate() - (day - 1));
    return simple;
  }

  function parseWeek(value: string) {
    const match = value.match(/^(\d{4})-W(\d{2})$/);
    if (!match) {
      throw new Error('Ongeldig weekformaat');
    }
    const year = Number(match[1]);
    const week = Number(match[2]);
    const start = startOfISOWeek(year, week);
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 6);
    return { year, week, start, end };
  }

  function formatRange(): string {
    if (period === 'all') {
      return 'Alle tijd';
    }
    if (!value) {
      return '';
    }
    if (period === 'day') {
      return dayFormatter.format(new Date(`${value}T00:00:00Z`));
    }
    if (period === 'month') {
      const [year, month] = value.split('-').map(Number);
      const date = new Date(Date.UTC(year, month - 1, 1));
      return monthFormatter.format(date);
    }
    if (period === 'week') {
      try {
        const info = parseWeek(value);
        return `Week ${info.week} ${info.year} (${dayFormatter.format(info.start)} – ${dayFormatter.format(info.end)})`;
      } catch (err) {
        return value;
      }
    }
    return value;
  }

  async function loadSummary() {
    const response = await fetch('/api/v1/listens/count');
    if (response.ok) {
      const data = await response.json();
      totalListens = data.count;
    }
  }

  async function loadListens() {
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({
        period,
        page: String(page),
        page_size: String(pageSize),
      });
      if (period !== 'all' && value) {
        params.set('value', value);
      }
      const response = await fetch(`/api/v1/listens?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de listens niet laden');
      }
      const data: { items: ListenRow[]; total: number } = await response.json();
      listens = data.items;
      total = data.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Onbekende fout';
      listens = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function onPeriodChange(event: Event) {
    period = (event.target as HTMLSelectElement).value as Period;
    value = getDefaultValue(period);
    page = 1;
    loadListens();
  }

  function onValueChange(event: Event) {
    value = (event.target as HTMLInputElement).value;
    page = 1;
    loadListens();
  }

  function shiftPeriod(direction: number) {
    if (period === 'all') {
      return;
    }
    if (!value) {
      value = getDefaultValue(period);
    }
    try {
      if (period === 'day') {
        const current = new Date(`${value}T00:00:00Z`);
        current.setUTCDate(current.getUTCDate() + direction);
        value = current.toISOString().slice(0, 10);
      } else if (period === 'month') {
        const [year, month] = value.split('-').map(Number);
        const date = new Date(Date.UTC(year, month - 1 + direction, 1));
        value = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
      } else if (period === 'week') {
        const info = parseWeek(value);
        const nextStart = new Date(info.start);
        nextStart.setUTCDate(nextStart.getUTCDate() + direction * 7);
        value = toISOWeekString(nextStart);
      }
      page = 1;
      loadListens();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Kon periode niet aanpassen';
    }
  }

  function changePage(newPage: number) {
    if (newPage < 1 || newPage > totalPages) {
      return;
    }
    page = newPage;
    loadListens();
  }

  function resetPanel() {
    panelError = null;
    panelLoading = false;
    listenDetail = null;
    artistInsight = null;
    albumInsight = null;
  }

  async function showListenDetail(event: CustomEvent<ListenRow>) {
    const listen = event.detail;
    panelType = 'listen';
    panelTitle = listen.track_title;
    resetPanel();
    panelLoading = true;
    try {
      const response = await fetch(`/api/v1/listens/${listen.id}`);
      if (!response.ok) {
        throw new Error('Kon de luisterdetails niet laden');
      }
      listenDetail = (await response.json()) as ListenDetail;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Onbekende fout';
    } finally {
      panelLoading = false;
    }
  }

  async function showArtistDetail(event: CustomEvent<{ listen: ListenRow; artist: ListenArtist }>) {
    const { artist, listen } = event.detail;
    if (!artist.id) {
      panelType = 'artist';
      panelTitle = artist.name;
      resetPanel();
      panelError = 'Geen aanvullende gegevens beschikbaar voor deze artiest.';
      return;
    }
    panelType = 'artist';
    panelTitle = artist.name;
    resetPanel();
    panelLoading = true;
    try {
      const response = await fetch(`/api/v1/library/artists/${artist.id}/insights`);
      if (!response.ok) {
        throw new Error('Kon de artiestgegevens niet laden');
      }
      artistInsight = (await response.json()) as ArtistInsight;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Onbekende fout';
    } finally {
      panelLoading = false;
    }
  }

  async function showAlbumDetail(event: CustomEvent<{ listen: ListenRow }>) {
    const { listen } = event.detail;
    if (!listen.album_id) {
      panelType = 'album';
      panelTitle = listen.album_title ?? 'Album';
      resetPanel();
      panelError = 'Geen aanvullende gegevens beschikbaar voor dit album.';
      return;
    }
    panelType = 'album';
    panelTitle = listen.album_title ?? 'Album';
    resetPanel();
    panelLoading = true;
    try {
      const response = await fetch(`/api/v1/library/albums/${listen.album_id}/insights`);
      if (!response.ok) {
        throw new Error('Kon de albumgegevens niet laden');
      }
      albumInsight = (await response.json()) as AlbumInsight;
    } catch (err) {
      panelError = err instanceof Error ? err.message : 'Onbekende fout';
    } finally {
      panelLoading = false;
    }
  }

  function closePanel() {
    panelType = null;
    panelError = null;
    listenDetail = null;
    artistInsight = null;
    albumInsight = null;
    panelTitle = '';
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
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
  }

  $: totalPages = Math.max(1, Math.ceil(total / pageSize));
  $: showingStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  $: showingEnd = total === 0 ? 0 : Math.min(total, page * pageSize);

  onMount(() => {
    loadSummary();
    loadListens();
  });
</script>

<section class="home">
  <div class="summary">
    <KpiCard label="Totaal aantal listens" value={totalListens.toLocaleString()} />
    <div class="controls">
      <label>
        Periode
        <select bind:value={period} on:change={onPeriodChange}>
          <option value="day">Dag</option>
          <option value="week">Week</option>
          <option value="month">Maand</option>
          <option value="all">Altijd</option>
        </select>
      </label>
      <label class:disabled={period === 'all'}>
        Waarde
        {#if period === 'day'}
          <input type="date" bind:value={value} on:change={onValueChange} />
        {:else if period === 'month'}
          <input type="month" bind:value={value} on:change={onValueChange} />
        {:else if period === 'week'}
          <input type="week" bind:value={value} on:change={onValueChange} />
        {:else}
          <span class="all-pill">Alles</span>
        {/if}
      </label>
      <div class="range">
        <button type="button" on:click={() => shiftPeriod(-1)} disabled={period === 'all'}>
          ← Vorige
        </button>
        <span>{formatRange()}</span>
        <button type="button" on:click={() => shiftPeriod(1)} disabled={period === 'all' || !value}>
          Volgende →
        </button>
      </div>
    </div>
  </div>

  {#if loading}
    <p class="status">Bezig met laden…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <RecentListensTable
        {listens}
        on:selectListen={showListenDetail}
        on:selectArtist={showArtistDetail}
        on:selectAlbum={showAlbumDetail}
      />
      <footer class="pagination">
        {#if total === 0}
          <span>Geen listens gevonden voor deze periode.</span>
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
  open={panelType !== null}
  loading={panelLoading}
  error={panelError}
  on:close={closePanel}
>
  {#if panelType === 'listen' && listenDetail}
    <section class="detail-section">
      <h4>Luisterinformatie</h4>
      <dl>
        <dt>Moment</dt>
        <dd>{formatDateTime(listenDetail.listened_at)}</dd>
        <dt>Bron</dt>
        <dd>{listenDetail.source}</dd>
        <dt>Positie</dt>
        <dd>{formatDuration(listenDetail.position_secs)}</dd>
        <dt>Luisterduur</dt>
        <dd>{formatDuration(listenDetail.duration_secs)}</dd>
      </dl>
    </section>
    <section class="detail-section">
      <h4>Track</h4>
      <dl>
        <dt>Naam</dt>
        <dd>{listenDetail.track_title}</dd>
        <dt>Duur</dt>
        <dd>{formatDuration(listenDetail.track_duration_secs)}</dd>
        <dt>Tracknummer</dt>
        <dd>
          {#if listenDetail.track_no != null}
            {listenDetail.track_no}{listenDetail.disc_no != null ? ` (Disc ${listenDetail.disc_no})` : ''}
          {:else}
            —
          {/if}
        </dd>
        <dt>MBID</dt>
        <dd>{listenDetail.track_mbid ?? '—'}</dd>
        <dt>ISRC</dt>
        <dd>{listenDetail.isrc ?? '—'}</dd>
      </dl>
    </section>
    <section class="detail-section">
      <h4>Album &amp; artiesten</h4>
      <dl>
        <dt>Album</dt>
        <dd>
          {#if listenDetail.album_title}
            {listenDetail.album_title}
            {#if listenDetail.album_release_year}
              ({listenDetail.album_release_year})
            {/if}
          {:else}
            —
          {/if}
        </dd>
        <dt>Album MBID</dt>
        <dd>{listenDetail.album_mbid ?? '—'}</dd>
        <dt>Artiesten</dt>
        <dd>
          {#if listenDetail.artists.length === 0}
            —
          {:else}
            {listenDetail.artists.map((artist) => artist.name).join(', ')}
          {/if}
        </dd>
        <dt>Genres</dt>
        <dd>
          {#if listenDetail.genres.length === 0}
            —
          {:else}
            {listenDetail.genres.map((genre) => genre.name).join(', ')}
          {/if}
        </dd>
      </dl>
    </section>
  {:else if panelType === 'artist' && artistInsight}
    <section class="detail-section">
      <h4>Statistieken</h4>
      <dl>
        <dt>Totaal aantal listens</dt>
        <dd>{artistInsight.listen_count.toLocaleString()}</dd>
        <dt>Eerste luisterbeurt</dt>
        <dd>{formatDateTime(artistInsight.first_listen)}</dd>
        <dt>Laatste luisterbeurt</dt>
        <dd>{formatDateTime(artistInsight.last_listen)}</dd>
        <dt>MBID</dt>
        <dd>{artistInsight.mbid ?? '—'}</dd>
      </dl>
    </section>
    <section class="detail-section">
      <h4>Topgenres</h4>
      <ul>
        {#each artistInsight.top_genres as item}
          <li>{item.genre} — {item.count.toLocaleString()} listens</li>
        {/each}
      </ul>
    </section>
    <section class="detail-section">
      <h4>Toptracks</h4>
      <ul>
        {#each artistInsight.top_tracks as item}
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
        {#each artistInsight.top_albums as item}
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
  {:else if panelType === 'album' && albumInsight}
    <section class="detail-section">
      <h4>Albuminfo</h4>
      <dl>
        <dt>Naam</dt>
        <dd>{albumInsight.title}</dd>
        <dt>Jaar</dt>
        <dd>{albumInsight.release_year ?? '—'}</dd>
        <dt>MBID</dt>
        <dd>{albumInsight.mbid ?? '—'}</dd>
        <dt>Totaal aantal listens</dt>
        <dd>{albumInsight.listen_count.toLocaleString()}</dd>
        <dt>Eerste luisterbeurt</dt>
        <dd>{formatDateTime(albumInsight.first_listen)}</dd>
        <dt>Laatste luisterbeurt</dt>
        <dd>{formatDateTime(albumInsight.last_listen)}</dd>
      </dl>
    </section>
    <section class="detail-section">
      <h4>Artiesten</h4>
      <ul>
        {#each albumInsight.artists as artist}
          <li>{artist.artist}</li>
        {/each}
      </ul>
    </section>
    <section class="detail-section">
      <h4>Genres</h4>
      <ul>
        {#each albumInsight.genres as item}
          <li>{item.genre} — {item.count.toLocaleString()} listens</li>
        {/each}
      </ul>
    </section>
    <section class="detail-section">
      <h4>Tracks</h4>
      <ol>
        {#each albumInsight.tracks as track}
          <li>
            {#if track.disc_no != null}
              <span class="muted">CD {track.disc_no} · </span>
            {/if}
            {track.track}
            <span class="muted">
              {#if track.track_no != null}
                #{track.track_no}
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
  .home {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
  }

  .summary {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    align-items: center;
  }

  .controls {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    justify-content: center;
    background: rgba(0, 0, 0, 0.15);
    padding: 1rem 1.5rem;
    border-radius: 999px;
    align-items: center;
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

  .all-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.75rem;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    font-weight: 600;
    color: var(--text-color);
  }

  .range {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .range button {
    background: rgba(255, 255, 255, 0.08);
    border: none;
    color: var(--text-color);
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    cursor: pointer;
  }

  .range button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .table-wrapper {
    width: min(960px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
    overflow-x: auto;
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
    font-size: 0.95rem;
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
