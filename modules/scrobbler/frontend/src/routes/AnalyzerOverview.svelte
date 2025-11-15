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
    genres: []
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
        body: JSON.stringify({})
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

<section class="overview">
  <div class="actions">
    <button on:click={startScan} disabled={scanInProgress}>
      {scanInProgress ? 'Queuing…' : 'Start analyzer scan'}
    </button>
    {#if scanInProgress}
      <div class="progress" role="status" aria-live="polite">
        <span class="visually-hidden">Analyzer scan queued…</span>
      </div>
    {/if}
    {#if scanMessage}
      <span class="status success">{scanMessage}</span>
    {/if}
    {#if error}
      <span class="status error">{error}</span>
    {/if}
  </div>

  {#if loading}
    <p class="status">Loading analyzer data…</p>
  {:else}
    <div class="kpi-grid">
      <KpiCard label="Media files" value={summary.files.toLocaleString()} />
      <KpiCard label="Songs (&lt; 10 min)" value={summary.songs.toLocaleString()} />
      <KpiCard label="Livesets (≥ 10 min)" value={summary.livesets.toLocaleString()} />
    </div>

    <Card element="section" className="overview__panel">
      <h2>Artists with songs</h2>
      {#if summary.artists.length}
        <table class="table">
          <thead>
            <tr>
              <th>Artist</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.artists as artist}
              <tr>
                <td>{artist.artist}</td>
                <td>{artist.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No songs recorded yet.</p>
      {/if}
    </Card>

    <Card element="section" className="overview__panel">
      <h2>Genres with songs</h2>
      {#if summary.genres.length}
        <table class="table">
          <thead>
            <tr>
              <th>Genre</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.genres as genre}
              <tr>
                <td>{genre.genre}</td>
                <td>{genre.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No genres recorded yet.</p>
      {/if}
    </Card>
  {/if}
</section>

<style>
  .overview {
    display: flex;
    flex-direction: column;
    gap: var(--space-2xl);
    align-items: stretch;
    margin: 0 auto;
    width: min(1080px, 100%);
  }

  .actions {
    display: flex;
    gap: var(--space-md);
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
  }

  .actions button {
    background: var(--color-accent);
    color: var(--color-text-primary);
    border: none;
    padding: var(--space-sm) var(--space-xl);
    border-radius: 999px;
    font-weight: 600;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: transform 150ms ease, box-shadow 150ms ease, opacity 150ms ease;
    box-shadow: var(--shadow-md);
  }

  .actions button:hover:not(:disabled),
  .actions button:focus-visible:not(:disabled) {
    transform: translateY(-2px);
  }

  .actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .progress {
    position: relative;
    width: 160px;
    height: 6px;
    border-radius: 999px;
    background: var(--color-accent-soft);
    overflow: hidden;
  }

  .progress::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, var(--color-text-primary), transparent);
    animation: progress-slide 1.4s infinite;
  }

  @keyframes progress-slide {
    0% {
      transform: translateX(-100%);
    }
    50% {
      transform: translateX(0%);
    }
    100% {
      transform: translateX(100%);
    }
  }

  .status {
    font-size: var(--font-size-sm);
  }

  .status.success {
    color: var(--color-success);
  }

  .status.error {
    color: var(--color-danger);
  }

  .kpi-grid {
    display: grid;
    gap: var(--space-lg);
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  :global(.overview__panel) {
    width: 100%;
    overflow-x: auto;
  }

  :global(.overview__panel h2) {
    margin: 0 0 var(--space-md);
    text-align: center;
    font-size: var(--font-size-xl);
  }

  .empty {
    text-align: center;
    margin: var(--space-sm) 0 0;
    color: var(--color-text-soft);
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  .table thead {
    background: rgba(255, 255, 255, 0.04);
  }

  .table tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.02);
  }
</style>
