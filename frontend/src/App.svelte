<script lang="ts">
  import Header from './lib/components/Header.svelte';
  import Analyzer from './routes/Analyzer.svelte';
  import Scrobbler from './routes/Scrobbler.svelte';
  import Settings from './routes/Settings.svelte';

  type Page = 'scrobbler' | 'analyzer' | 'settings';

  let page: Page = 'scrobbler';

  function show(newPage: Page) {
    page = newPage;
  }
</script>

<main>
  <Header title="Scrobbler" />
  <nav class="primary-nav">
    <button class:active={page === 'scrobbler'} on:click={() => show('scrobbler')}>
      Scrobbler
    </button>
    <button class:active={page === 'analyzer'} on:click={() => show('analyzer')}>
      Analyzer
    </button>
    <button class:active={page === 'settings'} on:click={() => show('settings')}>
      Settings
    </button>
  </nav>

  {#if page === 'scrobbler'}
    <Scrobbler />
  {:else if page === 'analyzer'}
    <Analyzer />
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

  .primary-nav {
    display: flex;
    justify-content: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }

  .primary-nav button {
    background: rgba(255, 255, 255, 0.05);
    border: none;
    color: var(--text-color);
    padding: 0.75rem 1.5rem;
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .primary-nav button.active {
    background: var(--accent-color);
    color: white;
  }
</style>
