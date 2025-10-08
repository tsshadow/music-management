<script lang="ts">
  import Header from './lib/components/Header.svelte';
  import Home from './routes/Home.svelte';
  import Settings from './routes/Settings.svelte';

  let page: 'home' | 'settings' = 'home';

  function show(newPage: 'home' | 'settings') {
    page = newPage;
  }
</script>

<main>
  <Header title="Scrobbler" />
  <nav>
    <button class:active={page === 'home'} on:click={() => show('home')}>Home</button>
    <button class:active={page === 'settings'} on:click={() => show('settings')}>Settings</button>
  </nav>

  {#if page === 'home'}
    <Home />
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
