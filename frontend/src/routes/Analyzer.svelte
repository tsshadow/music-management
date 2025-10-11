<script lang="ts">
  import Albums from './Albums.svelte';
  import AnalyzerOverview from './AnalyzerOverview.svelte';
  import Artists from './Artists.svelte';
  import Genres from './Genres.svelte';
  import Tracks from './Tracks.svelte';

  type Tab = 'overview' | 'artists' | 'albums' | 'genres' | 'tracks';

  const tabOrder: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'artists', label: 'Artists' },
    { id: 'albums', label: 'Albums' },
    { id: 'genres', label: 'Genres' },
    { id: 'tracks', label: 'Tracks' }
  ];

  let tab: Tab = 'overview';
</script>

<section class="analyzer">
  <header class="page-header">
    <div class="heading">
      <h1>Analyzer</h1>
      <p>Inspect your local library after scanning it with the analyzer service.</p>
    </div>
  </header>

  <nav class="tabs" aria-label="Analyzer sections">
    {#each tabOrder as item}
      <button
        type="button"
        class:active={tab === item.id}
        on:click={() => (tab = item.id)}
      >
        {item.label}
      </button>
    {/each}
  </nav>

  <div class="content">
    {#if tab === 'overview'}
      <AnalyzerOverview />
    {:else if tab === 'artists'}
      <Artists
        title="Library artists"
        description="Artists detected in your normalized music library."
      />
    {:else if tab === 'albums'}
      <Albums
        title="Library albums"
        description="Albums available in your media library."
      />
    {:else if tab === 'genres'}
      <Genres title="Library genres" description="Genre distribution across your library." />
    {:else}
      <Tracks title="Library tracks" description="Tracks registered during the last analyzer scan." />
    {/if}
  </div>
</section>

<style>
  .analyzer {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .heading h1 {
    font-size: clamp(2rem, 4vw, 2.75rem);
    margin: 0;
  }

  .heading p {
    margin: 0;
    max-width: 48ch;
    color: rgba(255, 255, 255, 0.75);
  }

  .tabs {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .tabs button {
    background: rgba(255, 255, 255, 0.05);
    border: none;
    color: var(--text-color);
    padding: 0.5rem 1.25rem;
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .tabs button.active {
    background: var(--accent-color);
    color: white;
  }

  .content {
    min-height: 320px;
  }
</style>
