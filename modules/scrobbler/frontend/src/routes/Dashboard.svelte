<script lang="ts">
  import { onMount } from 'svelte';
  import { Card, KpiCard } from '$ui';

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

<section class="dashboard flex flex-col items-center gap-12 px-4 pb-16 text-center sm:px-8 lg:px-12">
  <header class="max-w-2xl">
    <h1 class="m-0 text-4xl font-semibold leading-[var(--line-height-tight)] sm:text-5xl">Overview</h1>
    <p class="mt-3 text-lg leading-[var(--line-height-snug)] text-[var(--color-text-muted)]">
      Welcome back! Here is a quick snapshot of your library and listening activity.
    </p>
  </header>

  {#if loading}
    <p class="text-sm text-[var(--color-text-soft)]">Loading statistics…</p>
  {:else if error}
    <p class="text-sm text-[var(--color-danger)]">{error}</p>
  {:else if summary}
    <div class="grid w-full max-w-4xl grid-cols-1 gap-6 md:grid-cols-2">
      <KpiCard label="Total listens" value={totalListens.toLocaleString()} />
      <KpiCard label="Total media files" value={summary.files.toLocaleString()} />
    </div>

    <div class="grid w-full max-w-4xl grid-cols-1 gap-6 lg:grid-cols-2">
      <Card element="section" className="flex flex-col gap-5 text-left">
        <h2 class="text-center text-2xl font-semibold text-[var(--color-text-primary)]">Library artists</h2>
        {#if summary.artists.length}
          <ul class="m-0 flex list-none flex-col gap-3 p-0">
            {#each summary.artists.slice(0, 5) as artist}
              <li class="flex items-center justify-between gap-4">
                <span class="font-semibold text-[var(--color-text-primary)]">{artist.artist}</span>
                <span class="text-[var(--color-text-muted)]">{artist.songs.toLocaleString()} songs</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="text-center text-[var(--color-text-soft)]">
            Run the analyzer scan to populate artists.
          </p>
        {/if}
      </Card>
      <Card element="section" className="flex flex-col gap-5 text-left">
        <h2 class="text-center text-2xl font-semibold text-[var(--color-text-primary)]">Library genres</h2>
        {#if summary.genres.length}
          <ul class="m-0 flex list-none flex-col gap-3 p-0">
            {#each summary.genres.slice(0, 5) as genre}
              <li class="flex items-center justify-between gap-4">
                <span class="font-semibold text-[var(--color-text-primary)]">{genre.genre}</span>
                <span class="text-[var(--color-text-muted)]">{genre.songs.toLocaleString()} songs</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="text-center text-[var(--color-text-soft)]">
            Genre data becomes available after scanning your media library.
          </p>
        {/if}
      </Card>
    </div>
  {:else}
    <p class="text-sm text-[var(--color-text-soft)]">
      No data available yet. Start by scanning your library or importing listens.
    </p>
  {/if}
</section>
