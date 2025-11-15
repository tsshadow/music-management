<script lang="ts">
  /** Analyzer overview card summarising scan status and top-level metrics. */
  import { onMount } from 'svelte';
  import { Card, KpiCard } from '$ui';

  type ArtistSummary = { artist: string; songs: number };
  type GenreSummary = { genre: string; songs: number };
  type AnalyzerSummary = {
    files: number;
    songs: number;
    livesets: number;
    artists: ArtistSummary[];
    genres: GenreSummary[];
  };

  let summary: AnalyzerSummary = {
    files: 0,
    songs: 0,
    livesets: 0,
    artists: [],
    genres: [],
  };
  let loading = true;
  let scanInProgress = false;
  let scanMessage: string | null = null;
  let error: string | null = null;

  async function loadSummary() {
    loading = true;
    error = null;
    try {
      const response = await fetch('/api/v1/analyzer/summary');
      if (!response.ok) {
        throw new Error('Failed to load analyzer summary');
      }
      summary = (await response.json()) as AnalyzerSummary;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error while loading data';
    } finally {
      loading = false;
    }
  }

  async function startScan() {
    scanInProgress = true;
    scanMessage = null;
    error = null;
    try {
      const response = await fetch('/api/v1/analyzer/library/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail ?? 'Failed to queue analyzer scan');
      }
      const payload = await response.json();
      scanMessage = `Library scan queued (job ${payload.job_id})`;
      await loadSummary();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error while starting scan';
    } finally {
      scanInProgress = false;
    }
  }

  onMount(() => {
    loadSummary();
  });
</script>

<section class="overview mx-auto flex w-full max-w-5xl flex-col gap-12">
  <div class="flex flex-wrap items-center justify-center gap-4">
    <button
      class="rounded-full bg-[var(--color-accent)] px-6 py-2 font-semibold tracking-wide text-[var(--color-text-primary)] shadow-[var(--shadow-md)] transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-60"
      on:click={startScan}
      disabled={scanInProgress}
    >
      {scanInProgress ? 'Queuing…' : 'Start analyzer scan'}
    </button>
    {#if scanInProgress}
      <div class="relative h-1.5 w-40 overflow-hidden rounded-full bg-[var(--color-accent-soft)]">
        <span class="sr-only">Analyzer scan queued…</span>
        <div class="absolute inset-0 w-full -translate-x-full animate-progress-slide bg-[linear-gradient(90deg,transparent,var(--color-text-primary),transparent)]"></div>
      </div>
    {/if}
    {#if scanMessage}
      <span class="text-sm text-[var(--color-success)]">{scanMessage}</span>
    {/if}
    {#if error}
      <span class="text-sm text-[var(--color-danger)]">{error}</span>
    {/if}
  </div>

  {#if loading}
    <p class="text-sm text-[var(--color-text-soft)]">Loading analyzer data…</p>
  {:else}
    <div class="grid grid-cols-1 gap-6 md:grid-cols-3">
      <KpiCard label="Media files" value={summary.files.toLocaleString()} />
      <KpiCard label="Songs (&lt; 10 min)" value={summary.songs.toLocaleString()} />
      <KpiCard label="Livesets (≥ 10 min)" value={summary.livesets.toLocaleString()} />
    </div>

    <Card element="section" className="w-full overflow-x-auto">
      <h2 class="mb-4 text-center text-2xl font-semibold text-[var(--color-text-primary)]">Artists with songs</h2>
      {#if summary.artists.length}
        <table class="table">
          <thead class="bg-white/5">
            <tr>
              <th>Artist</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.artists as artist}
              <tr class="even:bg-white/5">
                <td>{artist.artist}</td>
                <td>{artist.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="text-center text-[var(--color-text-soft)]">No songs recorded yet.</p>
      {/if}
    </Card>

    <Card element="section" className="w-full overflow-x-auto">
      <h2 class="mb-4 text-center text-2xl font-semibold text-[var(--color-text-primary)]">Genres with songs</h2>
      {#if summary.genres.length}
        <table class="table">
          <thead class="bg-white/5">
            <tr>
              <th>Genre</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.genres as genre}
              <tr class="even:bg-white/5">
                <td>{genre.genre}</td>
                <td>{genre.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="text-center text-[var(--color-text-soft)]">No genres recorded yet.</p>
      {/if}
    </Card>
  {/if}
</section>
