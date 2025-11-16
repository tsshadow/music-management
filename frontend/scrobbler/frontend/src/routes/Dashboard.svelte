<script lang="ts">
  import { onMount } from 'svelte';
  import KpiCard from '../lib/components/KpiCard.svelte';

  /** Display high-level metrics across listens and the analyzer library. */
  interface AnalyzerSummary {
    files: number;
    songs: number;
    livesets: number;
    artists: { artist: string; songs: number }[];
    genres: { genre: string; songs: number }[];
  }

  let loading = true;
  let error: string | null = null;
  let summary: AnalyzerSummary | null = null;
  let totalListens = 0;

  async function loadData() {
    loading = true;
    error = null;
    try {
      const [summaryResponse, listensResponse] = await Promise.all([
        fetch('/api/v1/analyzer/summary'),
        fetch('/api/v1/listens/count'),
      ]);
      if (!summaryResponse.ok) {
        throw new Error('Failed to load analyzer summary');
      }
      if (!listensResponse.ok) {
        throw new Error('Failed to load listen statistics');
      }
      summary = (await summaryResponse.json()) as AnalyzerSummary;
      const listensData: { count: number } = await listensResponse.json();
      totalListens = listensData.count ?? 0;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error while loading data';
      summary = null;
      totalListens = 0;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadData();
  });
</script>

<section class="dashboard">
  <header>
    <h1>Overview</h1>
    <p>Welcome back! Here is a quick snapshot of your library and listening activity.</p>
  </header>

  {#if loading}
    <p class="status">Loading statistics…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else if summary}
    <div class="kpi-grid">
      <KpiCard label="Total listens" value={totalListens.toLocaleString()} />
      <KpiCard label="Total media files" value={summary.files.toLocaleString()} />
    </div>

    <div class="lists">
      <section class="list-panel">
        <h2>Library artists</h2>
        {#if summary.artists.length}
          <ul>
            {#each summary.artists.slice(0, 5) as artist}
              <li>
                <span class="label">{artist.artist}</span>
                <span class="value">{artist.songs.toLocaleString()} songs</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">Run the analyzer scan to populate artists.</p>
        {/if}
      </section>
      <section class="list-panel">
        <h2>Library genres</h2>
        {#if summary.genres.length}
          <ul>
            {#each summary.genres.slice(0, 5) as genre}
              <li>
                <span class="label">{genre.genre}</span>
                <span class="value">{genre.songs.toLocaleString()} songs</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">Genre data becomes available after scanning your media library.</p>
        {/if}
      </section>
    </div>
  {:else}
    <p class="status">No data available yet. Start by scanning your library or importing listens.</p>
  {/if}
</section>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
    text-align: center;
  }

  header {
    max-width: 640px;
  }

  header h1 {
    margin: 0;
    font-size: clamp(2rem, 5vw, 3rem);
  }

  header p {
    margin: 0.5rem 0 0;
    color: rgba(255, 255, 255, 0.75);
  }

  .status {
    margin: 0;
  }

  .status.error {
    color: #ff6b6b;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1.5rem;
    width: min(960px, 100%);
  }

  .lists {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1.5rem;
    width: min(960px, 100%);
  }

  .list-panel {
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1.5rem;
    text-align: left;
  }

  .list-panel h2 {
    margin: 0 0 1rem;
    text-align: center;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  li {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
  }

  .label {
    font-weight: 600;
  }

  .value {
    color: rgba(255, 255, 255, 0.75);
  }

  .empty {
    margin: 0;
    text-align: center;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
