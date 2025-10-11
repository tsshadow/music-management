<script lang="ts">
  import Header from './lib/components/Header.svelte';
  import Albums from './routes/Albums.svelte';
  import Analyzer from './routes/Analyzer.svelte';
  import Artists from './routes/Artists.svelte';
  import Genres from './routes/Genres.svelte';
  import Home from './routes/Home.svelte';
  import Tracks from './routes/Tracks.svelte';
  import Settings from './routes/Settings.svelte';

  type Page = 'home' | 'analyzer' | 'genres' | 'artists' | 'albums' | 'tracks' | 'settings';

  let page: Page = 'home';

  function show(newPage: Page) {
    page = newPage;
  }
</script>

<main>
  <Header title="Scrobbler" />
  <nav>
    <button class:active={page === 'home'} on:click={() => show('home')}>Home</button>
    <button class:active={page === 'analyzer'} on:click={() => show('analyzer')}>
      Analyzer
    </button>
    <button class:active={page === 'genres'} on:click={() => show('genres')}>Genres</button>
    <button class:active={page === 'artists'} on:click={() => show('artists')}>
      Artiesten
    </button>
    <button class:active={page === 'albums'} on:click={() => show('albums')}>Albums</button>
    <button class:active={page === 'tracks'} on:click={() => show('tracks')}>
      Tracks
    </button>
    <button class:active={page === 'settings'} on:click={() => show('settings')}>Settings</button>
  </nav>

  {#if page === 'home'}
    <Home />
  {:else if page === 'analyzer'}
    <Analyzer />
  {:else if page === 'genres'}
    <Genres />
  {:else if page === 'artists'}
    <Artists />
  {:else if page === 'albums'}
    <Albums />
  {:else if page === 'tracks'}
    <Tracks />
  {:else}
    <Settings />
  {/if}
</main>

<style>
  main {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  nav {
    display: flex;
    justify-content: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }

  nav button {
    background: rgba(255, 255, 255, 0.05);
    border: none;
    color: var(--text-color);
    padding: 0.75rem 1.5rem;
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  nav button.active {
    background: var(--accent-color);
    color: white;
  }
</style>
