<script lang="ts">
  import { onMount } from 'svelte';
  import Albums from './Albums.svelte';
  import Artists from './Artists.svelte';
  import Genres from './Genres.svelte';
  import Home from './Home.svelte';
  import Tracks from './Tracks.svelte';

  type Tab = 'listens' | 'artists' | 'albums' | 'genres' | 'tracks';

  const tabOrder: { id: Tab; label: string }[] = [
    { id: 'listens', label: 'Listens' },
    { id: 'artists', label: 'Artists' },
    { id: 'albums', label: 'Albums' },
    { id: 'genres', label: 'Genres' },
    { id: 'tracks', label: 'Tracks' }
  ];

  let tab: Tab = 'listens';
  let loadingConfig = false;
  let config: Record<string, string> = {};
  let importInProgress = false;
  let importState: 'idle' | 'success' | 'error' = 'idle';
  let importMessage = '';

  async function loadConfig() {
    loadingConfig = true;
    try {
      const response = await fetch('/api/v1/config');
      if (!response.ok) {
        throw new Error('Failed to load configuration');
      }
      const data = await response.json();
      config = data.values ?? {};
    } catch (error) {
      console.error(error);
    } finally {
      loadingConfig = false;
    }
  }

  function buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (config.api_key) {
      headers['X-Api-Key'] = config.api_key;
    }
    return headers;
  }

  function buildPayload(): Record<string, string> {
    const payload: Record<string, string> = {};
    if (config.listenbrainz_user) {
      payload.user = config.listenbrainz_user;
    }
    if (config.listenbrainz_token) {
      payload.token = config.listenbrainz_token;
    }
    return payload;
  }

  async function startImport() {
    if (importInProgress) {
      return;
    }
    importInProgress = true;
    importState = 'idle';
    importMessage = '';
    try {
      const response = await fetch('/api/v1/import/listenbrainz', {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify(buildPayload())
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || response.statusText);
      }
      const data = await response.json();
      const processed = data.processed ?? 0;
      const imported = data.imported ?? 0;
      const skipped = data.skipped ?? 0;
      importState = 'success';
      importMessage = `Import complete: ${imported} imported, ${skipped} skipped out of ${processed} listens.`;
    } catch (error) {
      importState = 'error';
      importMessage = error instanceof Error ? `Import failed: ${error.message}` : 'Import failed';
    } finally {
      importInProgress = false;
    }
  }

  onMount(() => {
    loadConfig();
  });
</script>

<section class="scrobbler">
  <header class="page-header">
    <div class="heading">
      <h1>Scrobbler</h1>
      <p>Explore your listening history and queue new ListenBrainz imports.</p>
    </div>
    <div class="actions">
      <button on:click={startImport} disabled={importInProgress || loadingConfig}>
        {importInProgress ? 'Importing…' : 'Start ListenBrainz import'}
      </button>
      {#if importInProgress}
        <div class="progress" role="status" aria-live="polite">
          <span class="visually-hidden">Import in progress…</span>
        </div>
      {/if}
    </div>
    {#if importMessage}
      <p class:success={importState === 'success'} class:error={importState === 'error'} class="status">{importMessage}</p>
    {/if}
  </header>

  <nav class="tabs" aria-label="Scrobbler sections">
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
    {#if tab === 'listens'}
      <Home />
    {:else if tab === 'artists'}
      <Artists title="Top artists by listens" description="See which artists dominate your listening history." />
    {:else if tab === 'albums'}
      <Albums title="Top albums by listens" description="Your most played records across different periods." />
    {:else if tab === 'genres'}
      <Genres title="Top genres by listens" description="Discover which genres you gravitate towards over time." />
    {:else}
      <Tracks title="Top tracks by listens" description="Find the songs you keep coming back to." />
    {/if}
  </div>
</section>

<style>
  .scrobbler {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    align-items: flex-start;
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

  .actions {
    display: flex;
    align-items: center;
    gap: 1rem;
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
    opacity: 0.6;
    cursor: not-allowed;
  }

  .progress {
    position: relative;
    width: 160px;
    height: 6px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.15);
    overflow: hidden;
  }

  .progress::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0));
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
    margin: 0;
    font-size: 0.95rem;
  }

  .status.success {
    color: #4caf50;
  }

  .status.error {
    color: #ff5252;
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
</style>
