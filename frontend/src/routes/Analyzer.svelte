<script lang="ts">
  import { onMount } from 'svelte';
  import KpiCard from '../lib/components/KpiCard.svelte';

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

<section class="analyzer">
  <div class="actions">
    <button on:click={startScan} disabled={scanInProgress}>
      {scanInProgress ? 'Queuing…' : 'Start analyzer scan'}
    </button>
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

    <div class="table-wrapper">
      <h2>Artists with songs</h2>
      {#if summary.artists.length}
        <table>
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
    </div>

    <div class="table-wrapper">
      <h2>Genres with songs</h2>
      {#if summary.genres.length}
        <table>
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
    </div>
  {/if}
</section>

<style>
  .analyzer {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
  }

  .actions {
    display: flex;
    gap: 1rem;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
  }

  .actions button {
    background: var(--accent-color);
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 999px;
    cursor: pointer;
    transition: opacity 0.2s ease;
  }

  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .status {
    font-size: 0.9rem;
  }

  .status.success {
    color: #4caf50;
  }

  .status.error {
    color: #f44336;
  }

  .kpi-grid {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .table-wrapper {
    width: min(960px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.75rem 1rem;
    text-align: left;
  }

  thead {
    background: rgba(255, 255, 255, 0.05);
  }

  tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }

  .empty {
    text-align: center;
    margin: 0.5rem 0 0;
    opacity: 0.7;
  }
</style>
